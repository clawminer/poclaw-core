#!/usr/bin/env python3
"""
deploy_token_tee.py — Deploy POCLAWToken with TEE wallet as verifier.

Usage:
    python3 deploy_token_tee.py \\
        --verifier 0x<tee_wallet from GET /health> \\
        --rpc      https://mainnet.infura.io/v3/<key> \\
        --key      <deployer private key (hex, with or without 0x)>

Or let the script fetch the TEE wallet address automatically:
    python3 deploy_token_tee.py \\
        --tee-server http://localhost:8001 \\
        --rpc      https://mainnet.infura.io/v3/<key> \\
        --key      <deployer private key>

After deployment, update KMS:
    POW_CONTRACT_ADDRESS = <printed contract address>
"""

import argparse
import json
import os
import sys

from web3 import Web3
from eth_account import Account


# ── Compiled contract ABI + bytecode ─────────────────────────────────────────
# Run `forge build` or `solc --combined-json abi,bin contracts/POCLAWToken.sol`
# and paste the outputs below.  This stub expects them in
# contracts/POCLAWToken_abi.json and contracts/POCLAWToken_bin.txt

ABI_PATH = os.path.join(os.path.dirname(__file__), "contracts", "POCLAWToken_abi.json")
BIN_PATH = os.path.join(os.path.dirname(__file__), "contracts", "POCLAWToken_bin.txt")


def load_contract_artifacts() -> tuple[list, str]:
    if not os.path.exists(ABI_PATH) or not os.path.exists(BIN_PATH):
        sys.exit(
            "❌  Compiled artifacts not found.\n"
            f"   Expected:\n     {ABI_PATH}\n     {BIN_PATH}\n"
            "   Run `forge build` (Foundry) or `solc --combined-json abi,bin` first."
        )
    with open(ABI_PATH) as f:
        abi = json.load(f)
    with open(BIN_PATH) as f:
        bytecode = f.read().strip()
    return abi, bytecode


def fetch_tee_wallet(tee_server: str) -> str:
    import urllib.request
    url = tee_server.rstrip("/") + "/health"
    with urllib.request.urlopen(url, timeout=10) as r:
        data = json.loads(r.read())
    wallet = data.get("tee_wallet")
    if not wallet:
        sys.exit(f"❌  /health did not return tee_wallet (got: {data})")
    print(f"✅ Fetched TEE wallet from {url}: {wallet}")
    return wallet


def deploy(verifier: str, rpc_url: str, deployer_key: str) -> str:
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        sys.exit(f"❌  Cannot connect to RPC: {rpc_url}")

    pk = deployer_key if deployer_key.startswith("0x") else "0x" + deployer_key
    deployer = Account.from_key(pk)
    print(f"📦  Deployer address : {deployer.address}")
    print(f"🔒  TEE verifier     : {verifier}")

    abi, bytecode = load_contract_artifacts()

    contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    nonce    = w3.eth.get_transaction_count(deployer.address)
    gas_price = w3.eth.gas_price

    tx = contract.constructor(
        Web3.to_checksum_address(verifier)
    ).build_transaction({
        "from":     deployer.address,
        "nonce":    nonce,
        "gasPrice": gas_price,
    })

    # Estimate gas with 20% buffer
    estimated = w3.eth.estimate_gas(tx)
    tx["gas"] = int(estimated * 1.2)

    signed = deployer.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"📡  Tx sent          : {tx_hash.hex()}")
    print("⏳  Waiting for receipt...")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    if receipt.status != 1:
        sys.exit(f"❌  Deployment failed (status={receipt.status})")

    contract_address = receipt.contractAddress
    print(f"\n✅  POCLAWToken deployed!")
    print(f"   Contract address : {contract_address}")
    print(f"   Verifier (TEE)   : {verifier}")
    print(f"   Block            : {receipt.blockNumber}")
    print(f"\nNext step — update KMS:")
    print(f"   POW_CONTRACT_ADDRESS = {contract_address}")
    print(f"Then restart the TEE container.")
    return contract_address


def main():
    parser = argparse.ArgumentParser(description="Deploy POCLAWToken with TEE wallet as verifier")
    parser.add_argument("--verifier",   help="TEE wallet address (0x...)")
    parser.add_argument("--tee-server", help="TEE server URL to fetch verifier from /health")
    parser.add_argument("--rpc",        required=True, help="Ethereum RPC URL")
    parser.add_argument("--key",        required=True, help="Deployer private key (hex)")
    args = parser.parse_args()

    if args.verifier:
        verifier = args.verifier
    elif args.tee_server:
        verifier = fetch_tee_wallet(args.tee_server)
    else:
        parser.error("Provide either --verifier <address> or --tee-server <url>")

    deploy(verifier, args.rpc, args.key)


if __name__ == "__main__":
    main()
