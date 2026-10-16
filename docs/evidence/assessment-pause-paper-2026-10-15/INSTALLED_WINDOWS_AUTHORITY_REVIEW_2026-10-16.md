# Assessment Studio installed Windows authority review — 16 October 2026

Source of facts: two user-supplied **redacted** manifests made with `scripts/architecture_local_collector.py`; no raw academic database or WAL was received or opened. This report records the contents as operator-supplied evidence, not an independently authenticated system attestation. The uploaded raw JSON documents are **not committed**.

## Installed snapshot and reproducible evidence
- Initial no-database manifest SHA-256: `4f75cdac558ec904c97e2c2254217c536e8f682fb0e61524822000d9c52f0bbe`.
- Closed stable-copy manifest SHA-256: `d7204f09de9e68ba1e274864a408e0f9437182b9753fb5df44abc0e05985ed27`.
- Installed checkout: clean `main`, `e15c347e5a7bf58c7ec29708eee49b1fed13f712`; current GitHub `main` at review was `aebd8a8828cd4fa452128343882a44b9025aea0d`, not the installed source.
- Windows Python 3.12.10, SQLite 3.49.1, config root matched supplied checkout, backend reported `sqlite`.
- The user explicitly invoked `--closed-no-writers` and process scan reported no other Python processes. The collector expressly warns this alone cannot rule out hidden backup/sync writers.
- The stable copy had contiguous matching applied migrations **0001–0014**, all required tables present, integrity `ok`, 0 FK violations, stable source bytes, and the temporary copy was locally destroyed.
- Nine existing compatibility projection keys are present, **not** proof of normalized-field/identity parity or freshness. Collector explicitly reports `projection_freshness_and_identity: BLOCKED`, `GATE_A_LOCAL_PRODUCTION_AUTHORITY: BLOCKED`, and launcher interpreter provenance still requires operator confirmation.

## Engineering decision
**PASS (bounded):** real-user reported closed schema lineage/integrity for migrations 0001–0014, matching the documented source inventory.

**BLOCKED:** confirmed actual launcher interpreter, any normalized-to-projection record/field parity, verified freshness and transactional ownership, B3 review-authority writer, approved paper rubric/import-review identity and provenance, conflict/collision check at migration allocation, and integration across normal Assessment Studio readers/writers. B3's source-only synthetic approval is not an installed writer authority and old mappings cannot be trusted retrospectively.

No migration number may be allocated from the installed `e15c347` history alone, and no existing applied 0001–0014 SQL checksum is to change. No optional score from paper self-review is an official grade/mastery/recovery/Tutor/Planner signal.

## Exact remaining safe actions
1. Run the pinned, published B3 **redacted** local authority inspector in closed-no-writers mode for deeper normalized/projection evidence; upload **only** its manifest. Never upload SQLite/database sidecars, academic rows, secrets or private notes.
2. Confirm `$Python` is the interpreter actually used to start `phase7_web.py`. Do not install a new interpreter or copy a user DB for validation.
3. Implement additive source-only migration and normal runner/integration only after explicit provenance contract and collision/authority review; keep existing routes and historical records stable and provide a disabled-by-default release/rollback plan.
4. Require an exact-head isolated assessment Ubuntu/Windows acceptance matrix and full project regression evidence. Four external Learning Studio real-pilot skips remain independently blocked, not waived.
5. Only after genuine integration and release review mark PR #11 ready to merge into `main`. No production migration or deployment is requested/authorized here.

New dedicated synthetic assessment workflow `.github/workflows/assessment-studio.yml` executes matching Ubuntu/Windows assessment-related tests (including Chromium, paper, Coding Helper and no-JS flows), requires zero skipped assessment tests, and retains the strict existing full-project gate as a separate signal.

This file is a non-sensitive decision record only. It is not a production release permit.
