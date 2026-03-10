"""
POCLAW PoW Server — TEE Edition
=============================
Architecture:
  - secret_logic.enc   : encrypted challenge generator (Fernet, AES-128-CBC)
  - CORE_DECRYPTION_KEY: injected by EigenCloud KMS at TEE boot, never on disk
  - ast_core_v3.py     : public operation registry (included in image)

TEE Wallet (signing key):
  - POW_TEE_SEED (32-byte hex) is injected by KMS at boot
  - TEE derives eth_account.Account.from_key(seed) in memory — never stored on disk
  - TEE wallet address is published via GET /health (tee_wallet field)
  - Contract verifier = TEE wallet address (set at deploy time)
  - EIP-712 claim signatures are signed exclusively by the TEE wallet

Startup:
  1. Read CORE_DECRYPTION_KEY + POW_TEE_SEED from KMS environment
  2. Decrypt secret_logic.enc in-memory → CoreModule.generate_challenge() live
  3. Derive TEE_ACCOUNT from POW_TEE_SEED in memory
  4. If any key missing → affected endpoints return 503 (safe failure)

Endpoints:
  GET  /pow/challenge?tier=haiku|sonnet|opus&wallet=0x...
  POST /pow/submit
  POST /pow/claim
  GET  /health         ← exposes tee_wallet (public address only)

Stateless design:
  challenge_token = HMAC-signed payload (answer hash + wallet + epoch)
  state_nonce     = HMAC-signed streak/score state
  claim_signature = EIP-712 signed by TEE wallet
"""

import os
import sys
import json
import hmac
import hashlib
import time
import base64
import types
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from cryptography.fernet import Fernet, InvalidToken

# ==========================================
# Config
# ==========================================

SECRET           = os.environ.get("POW_SECRET", "change-me-in-production-use-env-var")
TEE_SEED         = os.environ.get("POW_TEE_SEED", "")          # 32-byte hex from KMS → TEE wallet
CONTRACT_ADDRESS = os.environ.get("POW_CONTRACT_ADDRESS", "0x0000000000000000000000000000000000000000")
CHAIN_ID         = int(os.environ.get("POW_CHAIN_ID", "1"))
CORE_KEY         = os.environ.get("CORE_DECRYPTION_KEY", "")   # From EigenCloud KMS
ENC_FILE         = os.environ.get("POW_ENC_FILE", "secret_logic.enc")

CHALLENGE_TTL    = 600    # 10 min to answer
STATE_NONCE_TTL  = 7200   # 2 hours for streak accumulation
EPOCH_SECONDS    = 7200   # one claim per (wallet, epoch)
MIN_STREAK       = 1      # minimum streak to claim

# ==========================================
# TEE Core Loader
# ==========================================

CoreModule  = None  # populated at startup
TEE_ACCOUNT = None  # eth_account.Account, derived from POW_TEE_SEED at startup


def _load_tee_wallet():
    """
    Derive the TEE signing wallet from POW_TEE_SEED (KMS-injected, 32-byte hex).
    The resulting Account lives only in memory; the seed is never written to disk.
    """
    global TEE_ACCOUNT
    if not TEE_SEED:
        print("⚠️  POW_TEE_SEED not set — /pow/claim will return 503")
        return None
    try:
        from eth_account import Account
        seed_bytes = bytes.fromhex(TEE_SEED.strip())
        if len(seed_bytes) != 32:
            raise ValueError(f"POW_TEE_SEED must be exactly 32 bytes (got {len(seed_bytes)})")
        TEE_ACCOUNT = Account.from_key(seed_bytes)
        print(f"✅ TEE wallet derived: {TEE_ACCOUNT.address}")
        return TEE_ACCOUNT
    except Exception as e:
        print(f"❌ Failed to derive TEE wallet: {e}")
        return None


def _load_core():
    """
    Decrypt secret_logic.enc using CORE_DECRYPTION_KEY (from KMS env var)
    and exec() it into an in-memory module. Returns the module or None.
    """
    global CoreModule

    if not CORE_KEY:
        print("⚠️  CORE_DECRYPTION_KEY not set — challenge generation disabled")
        return None

    enc_path = os.path.join(os.path.dirname(__file__), ENC_FILE)
    if not os.path.exists(enc_path):
        print(f"⚠️  Encrypted logic file not found: {enc_path}")
        return None

    try:
        with open(enc_path, "rb") as f:
            encrypted_data = f.read()

        cipher = Fernet(CORE_KEY.encode() if isinstance(CORE_KEY, str) else CORE_KEY)
        decrypted_code = cipher.decrypt(encrypted_data)

        mod = types.ModuleType("core_logic")
        # Make the module's __file__ point to the TEE working directory
        mod.__file__ = enc_path
        exec(compile(decrypted_code, "<secret_logic>", "exec"), mod.__dict__)

        CoreModule = mod
        print("✅ Core logic loaded securely into TEE memory")
        return mod

    except InvalidToken:
        print("❌ Decryption failed: invalid key or corrupted payload")
        return None
    except Exception as e:
        print(f"❌ Failed to load core logic: {e}")
        return None


# ==========================================
# HMAC Token Helpers
# ==========================================

def _make_token(data: dict) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"))
    sig = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    envelope = {"d": data, "s": sig}
    return base64.urlsafe_b64encode(
        json.dumps(envelope, separators=(",", ":")).encode()
    ).decode().rstrip("=")


def _verify_token(token: str) -> dict:
    try:
        padded = token + "=" * (-len(token) % 4)
        envelope = json.loads(base64.urlsafe_b64decode(padded.encode()))
        data = envelope["d"]
        sig  = envelope["s"]
        payload = json.dumps(data, sort_keys=True, separators=(",", ":"))
        expected = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            raise ValueError("Invalid signature")
        if data.get("exp", 0) < time.time():
            raise ValueError("Token expired")
        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid token: {e}")


def _hash_answer(answer: str) -> str:
    return hashlib.sha256(answer.strip().lower().encode()).hexdigest()


def current_epoch() -> int:
    return int(time.time()) // EPOCH_SECONDS


# ==========================================
# EIP-712 Claim Signature
# ==========================================

def _eip712_claim_signature(wallet: str, amount_wei: int, nonce: int, epoch: int, expiry: int) -> str:
    """Sign an EIP-712 Claim struct using the TEE wallet (derived from POW_TEE_SEED)."""
    if TEE_ACCOUNT is None:
        raise HTTPException(status_code=503, detail="TEE wallet not initialised (set POW_TEE_SEED in KMS)")

    from eth_account.messages import encode_typed_data

    domain = {
        "name": "SYNToken", "version": "1",
        "chainId": CHAIN_ID, "verifyingContract": CONTRACT_ADDRESS,
    }
    message = {
        "wallet": wallet, "amount": amount_wei,
        "nonce": nonce, "epoch": epoch, "expiry": expiry,
    }
    structured = encode_typed_data(
        domain_data=domain,
        message_types={"Claim": [
            {"name": "wallet", "type": "address"},
            {"name": "amount", "type": "uint256"},
            {"name": "nonce",  "type": "uint256"},
            {"name": "epoch",  "type": "uint256"},
            {"name": "expiry", "type": "uint256"},
        ]},
        message_data=message,
    )
    signed = TEE_ACCOUNT.sign_message(structured)
    return signed.signature.hex()


# ==========================================
# FastAPI App
# ==========================================

app = FastAPI(title="POCLAW PoW — TEE Edition", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    _load_tee_wallet()
    _load_core()


# ==========================================
# GET /pow/challenge
# ==========================================

@app.get("/pow/challenge")
def get_challenge(
    tier:   str = Query("haiku", description="haiku | sonnet | opus"),
    wallet: str = Query(...,     description="Solver's ETH wallet address (0x...)"),
):
    """Issue a signed PoW challenge bound to the caller's wallet and current epoch."""
    if tier not in ("haiku", "sonnet", "opus"):
        raise HTTPException(status_code=400, detail="tier must be haiku, sonnet, or opus")
    if not wallet.startswith("0x") or len(wallet) != 42:
        raise HTTPException(status_code=400, detail="wallet must be a valid 0x ETH address (42 chars)")
    if CoreModule is None:
        raise HTTPException(status_code=503, detail="Core logic not loaded (CORE_DECRYPTION_KEY missing or invalid)")

    challenge = CoreModule.generate_challenge(tier)
    if challenge is None:
        raise HTTPException(status_code=500, detail="Failed to generate challenge")

    now = int(time.time())
    epoch = current_epoch()
    token_data = {
        "cid":      challenge["id"],
        "tier":     tier,
        "reward":   challenge["reward_syn"],
        "depth":    challenge["depth"],
        "ans_hash": _hash_answer(challenge["answer"]),
        "wallet":   wallet.lower(),
        "epoch":    epoch,
        "ts":       now,
        "iat":      now,
        "exp":      now + CHALLENGE_TTL,
    }

    return {
        "challenge_id":     challenge["id"],
        "tier":             tier,
        "tier_label":       challenge["tier_label"],
        "depth":            challenge["depth"],
        "est_tokens":       challenge["est_tokens"],
        "reward_syn":       challenge["reward_syn"],
        "question":         challenge["question"],
        "challenge_token":  _make_token(token_data),
        "expires_in":       CHALLENGE_TTL,
        "wallet":           wallet.lower(),
        "epoch":            epoch,
        "epoch_expires_in": EPOCH_SECONDS - (now % EPOCH_SECONDS),
    }


# ==========================================
# POST /pow/submit
# ==========================================

class SubmitRequest(BaseModel):
    wallet:          str
    challenge_token: str
    answer:          str
    state_nonce:     Optional[str] = None


@app.post("/pow/submit")
def submit_answer(req: SubmitRequest):
    """
    Verify answer. Correct → new state_nonce (streak+1). Wrong → streak reset.
    """
    ct = _verify_token(req.challenge_token)

    # Wallet binding
    if ct.get("wallet") and ct["wallet"] != req.wallet.lower():
        raise HTTPException(status_code=400, detail="Wallet mismatch: challenge issued to a different address")

    # Epoch check
    epoch_now = current_epoch()
    if ct.get("epoch") is not None and ct["epoch"] != epoch_now:
        raise HTTPException(status_code=400, detail="Challenge expired: epoch has rotated, request a new challenge")

    correct = hmac.compare_digest(_hash_answer(req.answer), ct["ans_hash"])

    # Load prior streak
    prev_streak, prev_score, prev_solved, prev_epoch = 0, 0, [], epoch_now
    if req.state_nonce:
        try:
            sn = _verify_token(req.state_nonce)
            if sn.get("wallet", "").lower() != req.wallet.lower():
                raise HTTPException(status_code=400, detail="Wallet mismatch: state_nonce belongs to a different wallet")
            prev_epoch  = sn.get("epoch", epoch_now)
            if prev_epoch != epoch_now:
                raise HTTPException(status_code=400, detail="Epoch mismatch: state_nonce is from a previous epoch, streak reset")
            prev_streak = sn.get("streak", 0)
            prev_score  = sn.get("score",  0)
            prev_solved = sn.get("solved", [])
        except HTTPException:
            raise
        except Exception:
            pass  # expired/invalid nonce → fresh start

    # Replay guard
    if ct["cid"] in prev_solved:
        raise HTTPException(status_code=400, detail="Challenge already used in this streak")

    now = int(time.time())

    if correct:
        new_streak = prev_streak + 1
        new_score  = prev_score + ct["reward"]
        new_solved = prev_solved + [ct["cid"]]
        new_nonce  = _make_token({
            "wallet": req.wallet.lower(),
            "streak": new_streak,
            "score":  new_score,
            "solved": new_solved,
            "epoch":  epoch_now,
            "ts":     now,
            "iat":    now,
            "exp":    now + STATE_NONCE_TTL,
        })
    else:
        new_streak, new_score, new_solved, new_nonce = 0, 0, [], None

    return {
        "correct":     correct,
        "streak":      new_streak,
        "score":       new_score,
        "state_nonce": new_nonce,
        "can_claim":   new_streak >= MIN_STREAK,
        "message": (
            f"Correct! Streak: {new_streak}, Score: {new_score} POCLAW"
            if correct else "Wrong answer. Streak reset to 0."
        ),
    }


# ==========================================
# POST /pow/claim
# ==========================================

class ClaimRequest(BaseModel):
    wallet:      str
    state_nonce: str


@app.post("/pow/claim")
def claim_reward(req: ClaimRequest):
    """
    Verify state_nonce and issue an EIP-712 signature redeemable on-chain.
    One claim per (wallet, epoch).
    """
    sn = _verify_token(req.state_nonce)

    if sn.get("wallet", "").lower() != req.wallet.lower():
        raise HTTPException(status_code=400, detail="Wallet mismatch")

    streak = sn.get("streak", 0)
    score  = sn.get("score",  0)

    if streak < MIN_STREAK:
        raise HTTPException(status_code=400, detail=f"Minimum streak {MIN_STREAK} required (current: {streak})")
    if score <= 0:
        raise HTTPException(status_code=400, detail="No score to claim")

    claim_epoch  = sn.get("epoch", current_epoch())
    nonce_source = f"{req.wallet.lower()}:{claim_epoch}"
    claim_nonce  = int(hashlib.sha256(nonce_source.encode()).hexdigest(), 16) % (2**64)

    now    = int(time.time())
    expiry = (claim_epoch + 1) * EPOCH_SECONDS + 3600  # end-of-epoch + 1h grace

    amount_wei = score * (10 ** 18)
    signature  = _eip712_claim_signature(req.wallet, amount_wei, claim_nonce, claim_epoch, expiry)

    return {
        "wallet":      req.wallet,
        "amount_syn":  score,
        "amount_wei":  str(amount_wei),
        "claim_nonce": str(claim_nonce),
        "epoch":       claim_epoch,
        "expiry":      expiry,
        "signature":   signature,
        "contract":    CONTRACT_ADDRESS,
        "chain_id":    CHAIN_ID,
        "streak":      streak,
        "ts":          now,
        "call": {
            "function": "claim(address,uint256,uint256,uint256,uint256,bytes)",
            "args": [req.wallet, str(amount_wei), str(claim_nonce), claim_epoch, expiry, signature],
        },
    }


# ==========================================
# Health
# ==========================================

@app.get("/health")
def health():
    return {
        "status":      "ok",
        "service":     "pow-server-tee",
        "tee_active":  CoreModule is not None,
        "core_loaded": CoreModule is not None,
        # TEE wallet public address — set this as `verifier` when deploying SyniumToken
        "tee_wallet":  TEE_ACCOUNT.address if TEE_ACCOUNT else None,
    }


# ==========================================
# Main
# ==========================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("POW_PORT", "8001"))
    print(f"🔒 Starting POCLAW PoW Server (TEE Edition) on port {port}")
    if SECRET == "change-me-in-production-use-env-var":
        print("⚠️  WARNING: Using default POW_SECRET — set POW_SECRET in KMS!")
    if not TEE_SEED:
        print("⚠️  WARNING: POW_TEE_SEED not set — /pow/claim will return 503")
    if not CORE_KEY:
        print("⚠️  WARNING: CORE_DECRYPTION_KEY not set — /pow/challenge will return 503")
    uvicorn.run(app, host="0.0.0.0", port=port)
