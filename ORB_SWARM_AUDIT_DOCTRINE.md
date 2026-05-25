# ORB Swarm Audit Doctrine

Status: Canonical doctrine for advanced Dock Station and swarm governance.
Scope: Prime-ORB-directed micro-orb task execution, return validation, and forensic reconstruction.

## STRICT_COHERENCE LOCK

This doctrine is under strict coherence for Prime ORB swarm cardinality:

- Approved canonical swarm-count set: `2, 3, 5, 7, 11`
- All requested counts (manual, query-derived, automated) must normalize into this set
- No active runtime path may use non-canonical swarm counts for deployment or return reconstruction
- Any deviation is an audit fault and must be logged as policy violation

## 1. Purpose

Define deterministic swarm auditing rules so participation, missing returns, replay attempts, and tamper signals can be verified consistently across ORB runtime components.

## 2. Prime-ID Assignment

- Each micro-orb in a mission is assigned a unique prime ID from the approved prime set.
- Prime ID assignment is controlled by mission registry logic, not by clients.
- The assignment registry must prevent duplicate prime allocation within a mission.

Canonical statement:

Prime-number spawn sets give the ORB swarm a deterministic, collision-free participation map where micro-orb lineage, return status, and missing nodes can be reconstructed through unique factorization; when combined with signed trace hashes, mission nonces, and timestamps, the system becomes tamper-evident and forensically auditable.

Tightened identity claim:

Because each micro-orb is assigned a unique prime ID, and prime products decompose uniquely, participation signatures cannot collide when generated from the approved prime set.

## 3. Spawn Batch Manifest

Each mission writes a batch manifest containing at minimum:

- mission_id
- mission_nonce
- mode (research or diagnostics)
- assigned_prime_ids
- expected_product_signature
- spawn_timestamp_utc
- ttl_ms

The manifest is authoritative for expected participation.

## 4. Return Product Signature

- Returning micro-orbs contribute their prime IDs to the participation product.
- Product signature is computed as:

$$
P_{return} = \prod_{i \in returned} p_i
$$

- Expected signature is:

$$
P_{expected} = \prod_{j \in assigned} p_j
$$

Prime products compress participation state only.

## 5. Missing Node Detection

If $P_{expected}$ is divisible by $P_{return}$, missing factors identify missing micro-orbs:

$$
P_{missing} = \frac{P_{expected}}{P_{return}}
$$

Prime factorization of $P_{missing}$ maps directly to missing prime IDs.

If divisibility fails, emit integrity fault state (invalid return product).

## 6. Trace Hash Binding

- Every micro-orb return must include a trace digest.
- Prime participation products are bound to mission trace hash aggregates.
- Hash binding proves payload consistency; prime products alone do not.

Required rule:

Do not treat product signatures as cryptographic proof in isolation.

## 7. Mission Nonce Binding

- mission_nonce is unique per mission execution.
- All return artifacts and signatures are bound to mission_nonce.
- Duplicate nonce with non-identical trace set is replay/tamper candidate.

## 8. Timestamp and TTL Rules

- All mission and return records include UTC timestamp.
- Returns after ttl_ms are marked late and excluded from canonical completion state unless explicit override policy is active.
- Audit reconstruction must preserve on-time, late, and missing distinctions.

## 9. Signature Verification

Verification order:

1. Validate mission manifest schema and approved prime set membership.
2. Verify nonce uniqueness and timestamp window.
3. Recompute and compare return product signature.
4. Validate divisibility and derive missing factors.
5. Verify trace hashes and signature envelope.
6. Persist mission verdict and failure state.

## 10. Failure, Tamper, and Replay States

The audit state machine must support at least:

- COMPLETE: all expected prime IDs returned within TTL and hash/signature checks pass.
- PARTIAL: valid subset returned; missing factors identified.
- LATE: valid returns exceeded TTL policy.
- INVALID_PRODUCT: non-divisible or non-prime-compliant return product.
- HASH_MISMATCH: participation present but trace integrity failed.
- NONCE_REPLAY: repeated nonce outside accepted idempotent policy.
- TAMPER_SUSPECTED: signature envelope or binding checks failed.

## Operational Boundaries

- Prime IDs provide deterministic participation proof.
- Hashes, signatures, and nonces provide tamper evidence.
- Timestamps and trace records provide forensic detail.

This doctrine applies to advanced swarm governance and should not be treated as a requirement for the minimal baseline ORB runtime.
