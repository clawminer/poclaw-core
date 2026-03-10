// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/**
 * @title POCLAWToken
 * @notice POCLAW ERC-20 with PoW streak-weighted mining and LP vesting.
 *
 * Reward schedule (per epoch, per wallet):
 *   streak = 1  →  1   × baseReward  (answered 1 challenge correctly)
 *   streak = 2  →  20  × baseReward  (answered 2 challenges correctly in a row)
 *   streak = 3  →  600 × baseReward  (answered 3 challenges correctly in a row)
 *
 * A wrong answer resets the streak to 0 — no reward can be claimed.
 * Each wallet may claim at most once per 2-hour epoch.
 *
 * LP vesting:
 *   - 2%  of the reward is minted immediately to the claimant.
 *   - 98% is locked and vests linearly over 90 days.
 *   - Call release() at any time to withdraw unlocked vested tokens.
 *
 * Base reward decays 0.2% (2‰) per epoch once the decay threshold is crossed.
 */
contract POCLAWToken is ERC20, EIP712, Ownable, ReentrancyGuard {
    using ECDSA for bytes32;

    // ── Config ────────────────────────────────────────────────────────────────

    address public verifier;

    uint256 public constant MAX_SUPPLY      = 21_000_000 * 1e18;
    uint256 public constant EPOCH_SECONDS   = 7200;           // 2 hours
    uint256 public constant DECAY_RATE_NUM  = 998;            // 0.2% decay (998/1000)
    uint256 public constant DECAY_RATE_DEN  = 1000;
    uint256 public constant VESTING_DURATION = 90 days;
    uint256 public constant INSTANT_BPS     = 200;            // 2%  (basis points)
    uint256 public constant BPS_DENOM       = 10_000;

    // EIP-712 struct typehash
    bytes32 public constant CLAIM_TYPEHASH = keccak256(
        "Claim(address wallet,uint256 amount,uint256 nonce,uint256 epoch,uint256 expiry)"
    );

    // ── Streak multiplier table (mirrors pow_server.py STREAK_SCORES) ─────────
    //   streak 1 → 1×, streak 2 → 20×, streak 3+ → 600×
    //   Final token amount = multiplier × baseReward / 1e18  (baseReward already in wei)

    // ── Vesting ───────────────────────────────────────────────────────────────

    struct VestingSchedule {
        uint256 total;      // total tokens locked for this wallet (cumulative)
        uint256 released;   // tokens already released
        uint256 start;      // vesting start timestamp (first claim sets this)
        uint256 duration;   // vesting duration in seconds (VESTING_DURATION)
    }

    mapping(address => VestingSchedule) public vestingOf;

    // ── Dynamic decay state ───────────────────────────────────────────────────

    uint256 public baseReward         = 1 * 1e18;   // 1 POCLAW unit; multiplied by streak factor
    uint256 public minedTotal;
    uint256 public nextDecayThreshold;
    uint256 public lastDecayEpoch;

    // ── Epoch agent accounting ────────────────────────────────────────────────

    uint256 public trackedEpoch;
    uint256 public agentsInCurrentEpoch;
    uint256 public agentsInLastEpoch;

    // ── Anti-replay / anti-double-claim ──────────────────────────────────────

    /// @notice Prevents the same wallet from claiming twice in one epoch.
    mapping(address => mapping(uint256 => bool)) public epochClaimed;

    /// @notice Global registry of spent nonces (issued by pow_server.py).
    mapping(uint256 => bool) public usedNonces;

    // ── Events ────────────────────────────────────────────────────────────────

    event Claimed(address indexed wallet, uint256 instant, uint256 vested, uint256 streak, uint256 epoch);
    event Released(address indexed wallet, uint256 amount);
    event EpochRotated(uint256 indexed epoch, uint256 agentsPrev);
    event DecayTriggered(uint256 newBaseReward, uint256 newThreshold);

    // ── Constructor ───────────────────────────────────────────────────────────

    constructor(address _verifier)
        ERC20("POCLAW", "POCLAW")
        EIP712("POCLAWToken", "1")
        Ownable(msg.sender)
    {
        verifier     = _verifier;
        trackedEpoch = _epochNow();

        // Genesis liquidity mint (1 epoch worth at streak-3 level = 600 SYN)
        uint256 genesis = streakAmount(3);
        _mint(msg.sender, genesis);
        minedTotal += genesis;

        // Apply first decay step
        baseReward         = (baseReward * DECAY_RATE_NUM) / DECAY_RATE_DEN;
        nextDecayThreshold = genesis + streakAmount(3);
        lastDecayEpoch     = trackedEpoch;
    }

    // ── Admin ─────────────────────────────────────────────────────────────────

    function setVerifier(address _newVerifier) external onlyOwner {
        verifier = _newVerifier;
    }

    // ── View helpers ──────────────────────────────────────────────────────────

    function _epochNow() internal view returns (uint256) {
        return block.timestamp / EPOCH_SECONDS;
    }

    /**
     * @notice Returns the SYN amount (in wei) for a given streak count.
     *         Amount = streakMultiplier × baseReward.
     *   streak = 1 →   1 × baseReward
     *   streak = 2 →  20 × baseReward
     *   streak ≥ 3 → 600 × baseReward
     */
    function streakAmount(uint256 streak) public view returns (uint256) {
        if (streak == 0) return 0;
        if (streak == 1) return 1   * baseReward;
        if (streak == 2) return 20  * baseReward;
        return                  600 * baseReward;  // streak >= 3
    }

    /**
     * @notice Returns how many vested tokens a wallet can release right now.
     */
    function releasable(address wallet) public view returns (uint256) {
        VestingSchedule storage v = vestingOf[wallet];
        if (v.total == 0 || block.timestamp < v.start) return 0;
        uint256 elapsed = block.timestamp - v.start;
        uint256 vested = elapsed >= v.duration
            ? v.total
            : (v.total * elapsed) / v.duration;
        return vested > v.released ? vested - v.released : 0;
    }

    // ── Core: claim ───────────────────────────────────────────────────────────

    /**
     * @notice Redeem a streak reward signed by the PoW server.
     *         2% is minted immediately; 98% enters a 90-day linear vesting schedule.
     *
     * @param amount    SYN amount in wei (must match streakAmount(streak)).
     * @param nonce     Server-issued nonce (prevents signature reuse).
     * @param epoch     2-hour epoch number the challenges were solved in.
     * @param expiry    Unix timestamp after which the signature is invalid.
     * @param streak    Number of consecutive correct answers (1, 2, or 3).
     * @param signature EIP-712 signature from the PoW verifier.
     */
    function claim(
        uint256 amount,
        uint256 nonce,
        uint256 epoch,
        uint256 expiry,
        uint256 streak,
        bytes calldata signature
    ) external nonReentrant {
        // 1. Expiry guard
        require(block.timestamp <= expiry, "Claim expired");

        // 2. Must be the same epoch the challenges were solved in
        require(epoch == _epochNow(), "Wrong epoch");

        // 3. One claim per wallet per epoch
        require(!epochClaimed[msg.sender][epoch], "Already claimed this epoch");

        // 4. Nonce must be fresh
        require(!usedNonces[nonce], "Nonce already used");

        // 5. Amount must match the current streak tier
        require(
            amount == streakAmount(streak),
            "Amount does not match streak reward"
        );

        // 6. Supply cap
        require(totalSupply() + amount <= MAX_SUPPLY, "Max supply reached");

        // 7. Verify EIP-712 signature
        bytes32 structHash = keccak256(abi.encode(
            CLAIM_TYPEHASH,
            msg.sender,
            amount,
            nonce,
            epoch,
            expiry
        ));
        bytes32 digest = _hashTypedDataV4(structHash);
        require(ECDSA.recover(digest, signature) == verifier, "Invalid signature");

        // 8. Record state
        epochClaimed[msg.sender][epoch] = true;
        usedNonces[nonce]               = true;

        // 9. Epoch rotation
        _maybeRotateEpoch();
        agentsInCurrentEpoch++;

        // 10. Decay check
        _maybeDecay();

        // 11. Split: 2% instant, 98% vested
        uint256 instantAmount = (amount * INSTANT_BPS) / BPS_DENOM;
        uint256 vestedAmount  = amount - instantAmount;

        minedTotal += amount;

        // Mint instant portion directly
        _mint(msg.sender, instantAmount);

        // Accumulate vesting schedule (resets start time on first claim only)
        VestingSchedule storage v = vestingOf[msg.sender];
        if (v.total == 0) {
            v.start    = block.timestamp;
            v.duration = VESTING_DURATION;
        }
        v.total += vestedAmount;
        // Mint vested portion to contract (held on behalf of wallet)
        _mint(address(this), vestedAmount);

        emit Claimed(msg.sender, instantAmount, vestedAmount, streak, epoch);
    }

    // ── Core: release ─────────────────────────────────────────────────────────

    /**
     * @notice Release any unlocked vested tokens to the caller.
     */
    function release() external nonReentrant {
        uint256 amount = releasable(msg.sender);
        require(amount > 0, "Nothing to release");

        vestingOf[msg.sender].released += amount;
        _transfer(address(this), msg.sender, amount);

        emit Released(msg.sender, amount);
    }

    // ── Internal helpers ──────────────────────────────────────────────────────

    function _maybeRotateEpoch() internal {
        uint256 epoch = _epochNow();
        if (epoch > trackedEpoch) {
            agentsInLastEpoch    = agentsInCurrentEpoch > 0 ? agentsInCurrentEpoch : 1;
            agentsInCurrentEpoch = 0;
            trackedEpoch         = epoch;
            emit EpochRotated(epoch, agentsInLastEpoch);
        }
    }

    function _maybeDecay() internal {
        uint256 epoch = _epochNow();
        if (epoch > lastDecayEpoch && minedTotal >= nextDecayThreshold) {
            baseReward         = (baseReward * DECAY_RATE_NUM) / DECAY_RATE_DEN;
            nextDecayThreshold += streakAmount(3);
            lastDecayEpoch     = epoch;
            emit DecayTriggered(baseReward, nextDecayThreshold);
        }
    }
}
