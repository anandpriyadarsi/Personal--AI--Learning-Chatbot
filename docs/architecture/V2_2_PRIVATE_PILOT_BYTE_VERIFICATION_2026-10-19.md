# Private IKS pilot ZIP authenticity review — 19 October 2026

## Scope
This evidence records local, read-only checks of the **two original personal Library attachments** previously supplied by the owner. It contains no private files, source text, images, lesson content, filesystem paths, screenshots, or credential material.

## Byte identities checked independently
| Role | Total bytes | SHA-256 | Original presentation SHA-256 | Outcome |
| --- | ---: | --- | --- | --- |
| recovered | 2,880,076 | `e26d03de4a300dda0186ee005745d98afa41f0a23d12d6612965079e995f6923` | `75cd41956da56018967fea70ae5829803a9b54effa827e25883ac184bffcf411` | Matches the pinned recovered role |
| bad_v3 | 2,891,010 | `a49c7fcd16f129ccf62a3260fd0a914be3b278b32ee460cf8833bbdf531e9cdd` | `f812fb27240fc5cd5265a1608f80ac480f241b56f9b27d4826bb6453b319735b` | Matches the pinned historic invalid role |

These identities are already pinned in `scripts/architecture_private_fixtures.py`; this file contains no new private hash identifiers.

## Structural checks
Both archives: CRC passed, no unsafe member paths observed, 32 archive members, expected module schema, 20 numbered pages, 20 distinct lesson images, 31 questions, all 20 lesson image hashes matched, and all 20 lesson source-text hashes matched. The recovered role's PDF matched its declared source hash; the historic invalid role's PDF did not, as required.

## Strict boundaries / not claimed
- The independent structural check is **not** equivalent to executing the repository's four original pilot acceptance tests.
- Existing Architecture V2.2 PR #27 documents 2,580 locally passing strict tests using these pinned originals. This new review does not replace those checks.
- Public GitHub-hosted Ubuntu and Windows jobs cannot access these private originals; their four fixture checks remain blocked without restricted user-authorized runner provisioning.
- No original ZIP was uploaded to GitHub or imported into ANVAYA Learning Studio.
- Installed production Windows/B3/WAL authority remains separately blocked.
