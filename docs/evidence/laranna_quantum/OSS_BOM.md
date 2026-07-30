# LarannA Quantum repository verifier — OSS BOM

Scope: Quantum repository signature verification only. ImageLab is excluded.
The gate workflow uses Ubuntu 24.04 x86_64 and CPython 3.13.14. Installation is
binary-only and hash-locked by
`requirements/laranna-quantum-verifier.txt`.

| Component | Version | Purpose | License | Exact admitted artifact SHA-256 |
|---|---:|---|---|---|
| Python | 3.13.14 | Gate runtime | Python Software Foundation License 2.0 | Runtime selected by `actions/setup-python`; no Python binary is committed |
| cryptography | 49.0.0 | Ed25519 public-signature verification | Apache-2.0 OR BSD-3-Clause | `cbc77da8c523d5abd028635ba850a6966fcee2c82e2bf65a41d1d8afe0f98be9` |
| cffi | 2.1.0 | cryptography runtime dependency | MIT-0 | `799416bae98336e400981ff6e532d67d5c709cfb30afb79865a1315f94b0e224` |
| pycparser | 3.0 | cffi runtime dependency | BSD-3-Clause | `b727414169a36b7d524c1c3e31839a521725078d7b2ff038656844266160a992` |

Official project records:

- https://www.python.org/downloads/release/python-31314/
- https://pypi.org/project/cryptography/49.0.0/
- https://pypi.org/project/cffi/2.1.0/
- https://pypi.org/project/pycparser/3.0/

No paid API, SaaS verifier, telemetry package, private key, GitHub write token,
or ImageLab dependency is introduced. The Windows private Ed25519 key remains
outside GitHub; this repository stores only the signed public binding, permit,
result, and receipt evidence.
