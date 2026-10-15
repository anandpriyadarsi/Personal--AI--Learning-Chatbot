# Learning Studio V1.4 integration diff audit

## Verified ancestry and reconciliation

- Verified V1.3: `6e520035b6b9ccf8e14c176b35b43e384c95d103`; exact-SHA Ubuntu/Windows run `38578508031` succeeded.
- Verified main: `e15c347e5a7bf58c7ec29708eee49b1fed13f712`.
- Common ancestor: `f859a3c7cdf44baadc17d9bd1a6c656530c1b5bf`; histories diverged by 13 V1.3-side and 10 main-side commits.
- New branch starts from V1.3 and imports main through an explicit two-parent merge. No automatic conflict policy, rebase, old-branch rewrite, main merge or cherry-pick from active branches.
- Git's merge had **zero textual conflicts**. The 50 main-side paths are inherited verbatim, including B1/B2/Gate A read-safety code and tests. They are integration dependencies, not newly implemented B3 or Assessment functionality.

## Shared files and ownership

| Shared surface | Resolution and validation |
|---|---|
| `ui/web/__init__.py` | Retain V1.3 Learning blueprint/CSRF registration; main did not change this path since the common ancestor. No other blueprint is replaced. |
| `ui/web/routes.py` | Retain V1.3 additive read-only Analysis component. No Assessment/Tutor handler changes. |
| `ui/web/templates/base.html` | Retain V1.3 sidebar extension block and Learning navigation link. No global CSS/JS rewrite. |
| `ui/web/templates/analysis.html` | Retain V1.3 component include with evidence category boundaries. No official assessment or B3 evidence ingestion. |
| `course_manager.py`, `learning_memory.py` | Import main's read-without-initialization changes verbatim. V1.4 does not edit them. |
| JSON course repository, structured authority router, Topic Intelligence repository/domain | Import exact current-main B1/B2 read safety; no adapter to a production DB, B3 changes or schema migration. |
| `requirements-dev.txt`, architecture scripts/tests/workflow | Import current main verbatim; Learning validation includes pinned main test dependencies and explicit characterization/read-safety gates. Architecture workflow remains unmodified and is not triggered by this feature branch push. |
| Learning-only route/template/domain/CSS | V1.4-owned scope: indexed cards, truthful revision scope/priorities, printable lesson supplements, contextual source navigation, selected original/exercise, mechanical preflight diagnostics, physical availability axes and stale mapping notice. |
| `.github/workflows/learning-studio.yml` | Add only this exact feature branch to the existing push matrix; comparison base is verified V1.3. No PR creation or redundant dispatch. |

Exact inherited authority paths are `personal_learning_assistant/domain/topic_intelligence.py`, `personal_learning_assistant/repositories/json/course_repository.py`, `personal_learning_assistant/repositories/sqlite/topic_intelligence_repository.py` and `personal_learning_assistant/repositories/structured_authority_router.py`. V1.4 introduces no delta to these relative to main.

The validation default and its retained health-test assertion both advance from the V1.2 SHA to verified V1.3. This is an intentional baseline pin update, not suppression of an error or removal of a test.

## Why prior evidence remains useful

V1.3's immutable source storage, grading, CSRF, schema, evidence taxonomy, manual Tutor producer, sidebar and focus implementation remain intact. Those exact tests run again rather than treating old CI as current acceptance. Only the retained full-companion selector is scoped to its direct article because Full Revision now includes supplemental lesson articles; all seven journey IDs and their original content assertions remain.

## New validation required and executed by the gate

V1.4 feature/unit/route and real Chromium tests, seven widths, print and no-JS/offline content; exact card identities and durable revisions; source/question/context preservation; all retained Learning tests; focused Assessment/startup/Notes/Analysis regressions; current-main characterization/Topic read-safety; sequential whole-suite exact-node/exit-code comparison against V1.3. Final source SHA, actual platform results and raw baseline failures are in the private exact-SHA acceptance evidence.

## Protected boundaries

No V1.4 edits to Assessment Studio/Coding Helper source, Tutor consumer/providers/sessions, production academic files, source files, coverage ledgers, Notes/Knowledge/Obsidian, registry or active B3/Gate C0 branches. The public example original and question list are unchanged. All app writes during acceptance use disposable feature stores. Private pilot bytes are only read locally; no original lecture material enters the public diff or CI.

No main readiness claim follows merely from a clean merge or a green delta. Raw legacy failures remain named, and production authority/private semantic verification remain separate acceptance gates.
