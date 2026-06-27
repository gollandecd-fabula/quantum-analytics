# A6 Data Proof Plan

## Proofs

- exact source SHA-256;
- immutable raw storage;
- structural fingerprint;
- semantic fingerprint;
- known schema detection;
- unknown schema quarantine;
- same-header semantic drift quarantine;
- canonical event normalization;
- revision and supersession;
- reversal;
- exact replay without duplicates;
- metric-to-source Evidence Chain.

## Expected synthetic result

- first import inserts four canonical events;
- exact replay inserts zero events and identifies four duplicates;
- revision 2 supersedes revision 1 for `sale-002`;
- return reverses `sale-001`;
- active synthetic gross-sale amount is 1400.00 RUB;
- unknown and semantically invalid files remain quarantined.
