# V1.2 Tutor compatibility boundary

Automatic Tutor consumption: **BLOCKED**. The read-only producer and compatibility diagnostic are implemented; they do not create a Tutor session or call a provider.

## Inspected interface

`AcademicAgentWebService.create_session` in `personal_learning_assistant/services/academic_agent_web_service.py` accepts `course_id`, `mode`, `source_policy`, and `title`. It creates a Tutor session through the academic database repository, with origin metadata. It does not accept or enforce module ID/revision, immutable source SHA, exact question revision, or a Learning Studio evidence producer. Linking `/agent?course_id=...` therefore cannot meet this contract.

`TutorSessionSpec` in `personal_learning_assistant/domain/tutor_models.py` includes `resource_id` and free-form metadata, but those fields alone are no consumer contract: the existing grounding path uses resource/document retrieval and does not enforce a Learning Studio immutable PDF snapshot. No teaching reasoning, provider grading, Tutor session service, Tutor repository or memory policy is changed in V1.2.

## Implemented producer boundary

`learning_studio/tutor_bridge.py:prepare_review` requires an explicit action flag, accepts exactly `module_id` and `module_revision`, and fetches the server-owned exact historical published context. It rejects forged owner/correctness/hash/timestamp/mapping/prompt/redirect fields. Its allowlist omits private keys, explanations and option text; citations, wrong-to-correct history and evidence labels survive. Output is bounded to 20 misses and 24,000 UTF-8 bytes, with a disclosed omitted count. Repeated actions produce identical projections without persistence. The guarded HTTP boundary is owned by the Learning Studio blueprint. The response remains BLOCKED; no successful Tutor turn is implied.

Manual `/review-brief` copying/downloading remains available. Published source snapshots are verified against their recorded SHA. Later registry changes do not rewrite historical snapshots; unknown revisions and unavailable/invalid immutable snapshots fail safely.

## Small Tutor-owned follow-up

1. Add an explicit authorized Tutor review entry point accepting only module ID/revision and an idempotent action token. Fetch the server producer rather than client context.
2. Define an owner-bound immutable Learning source adapter including source SHA, page locators and module/question revisions. Separate source teaching content from private assessment keys.
3. Validate live mapping separately from historical mapping, using source-first behavior when unmapped/stale. Preserve limited evidence and uncertainty.
4. Create sessions only through Tutor's existing authorized mechanism and only after those checks. Fail safely on provider/source unavailability. Do not write Learning events or mastery.
5. Re-run the ten handoff contract tests against the actual consumer, plus provider/session call spies, bounded context and duplicate-action tests. Producer tests are not consumer acceptance.

The current tests exercise all ten named contracts on the unavailable-consumer boundary, plus forged input variants, invalid locators, bounds, duplicate actions and pure integrated Analysis. The full automatic-consumer acceptance row remains BLOCKED.
