# docs/adr/001-adopt-volatile-in-memory-key-pattern.md

# ADR-001: Adopt Volatile In-Memory Key Pattern for At-Rest Data Security

**Status:** Completed

## Context

The initial design for data persistence involved storing an encrypted master key on disk, which was itself encrypted by a user-derived key. The updated threat model includes physical seizure of hardware, extra-legal threats, and the future risk of cryptographic breaks ("Q Day"). This threat model renders any key stored at rest, in any form, a significant liability. The system must be secure against forensic analysis in a powered-off state.

## Decision

We will adopt a **Volatile In-Memory Key Pattern**. The master decryption key for the persistent database will **never be stored on disk**.

1.  The key will be derived on-demand at the beginning of each authenticated session using a strong Key Derivation Function (Argon2id).
2.  The inputs to the KDF will be a high-entropy user passphrase and a non-secret salt stored on disk.
3.  The derived Master Key will exist exclusively in the application's RAM for the duration of the session.

## Consequences

*   **Positive:**
    *   Dramatically improves at-rest security. The only attack vector against a powered-off system is a computationally infeasible brute-force attack on the user's passphrase.
    *   Mitigates the risk of future cryptographic breakthroughs rendering a statically stored key vulnerable.
    *   Simplifies the on-disk secret management to just the encrypted data and a public salt.

*   **Negative:**
    *   A forgotten user passphrase results in **permanent, irrecoverable data loss**. There is no recovery mechanism by design.
    *   Increases application startup complexity, requiring the user to enter their passphrase at the beginning of every session.
    *   Places the entire at-rest security burden on the strength of the user's passphrase.
