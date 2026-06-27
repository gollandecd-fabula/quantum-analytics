# Deployment Platform Evaluation

Status: `PLANNED`
Requirement: `Q-DEPLOY-001`

## Candidates

1. Railway
2. Cloudflare
3. Vercel

## Preliminary architecture fit

| Platform | Current architecture fit | Free-tier risk | Expected adaptation |
|---|---|---|---|
| Railway | High | Medium to high for API + Worker + PostgreSQL | Low |
| Cloudflare | Medium after redesign | Low to medium within documented quotas | High: Workers, D1/R2, Queues/Workflows |
| Vercel | Medium for frontend and HTTP functions | Medium for durable ingestion and workers | Medium to high |

This table is a hypothesis, not an approved platform decision.

## Required proof matrix

For every candidate, record:

- recurring cost at idle and expected load;
- number and type of services;
- API runtime limits;
- background-worker and queue semantics;
- PostgreSQL compatibility or migration impact;
- source-file storage and immutability;
- authentication and approved-user-only access;
- backup and restore;
- rollback;
- observability;
- staging deployment procedure;
- synthetic A6 proof result;
- vendor lock-in and exit plan.

## Decision rule

Choose the lowest-cost platform that satisfies all mandatory data integrity, background processing, security, recovery, and access-control requirements without hidden paid dependencies.

Architecture compatibility takes priority over superficial ease of deployment. A free platform that cannot reliably process files, persist events, recover jobs, or restrict users is not acceptable.
