# Tutor read-only handoff for V1.2

V1.1 implements a **manual** brief: Weak Questions → Copy review brief or Download review brief. A user may explicitly paste it into Tutor. No code sends it to `/agent`, creates a conversation, calls a provider, changes Tutor memory, or records mastery. The automatic Tutor button remains visibly disabled. Existing Tutor contracts do not consume this versioned context; this document is a future specification, not an implemented adapter.

## Current producer

`GET /learning/modules/<module_id>/<revision>/review-context` returns `anvaya.learning-review-context.v1`; `/review-brief` returns the plain-text projection. Both are read-only and scoped to the local owner and exact published module revision. They verify the immutable source snapshot. The context contains module/source identity, historical mapping snapshot and current mapping status, number of unverified pages, attempt count, evidence label, and only ever-missed questions. Each miss includes question revision, source pages, latest selected response, server correctness, retry counts, last wrong timestamp, and exact historical lesson/source/question links. Private answer keys and explanations are omitted. Empty history yields No evidence; fewer than five distinct question versions yields Limited evidence. Wrong→correct remains recovered-needs-recheck.

## Proposed bounded consumer

A separately reviewed Tutor-owned entry point should accept only module ID and revision after an explicit user action. It must fetch the server producer, verify schema/owner/source identity and mapping against the current catalogue, then pass bounded evidence to an already authorized source-grounded session. Never accept client correctness, caller-supplied owner, free-form course attribution or an unverified source. Unmapped/stale mapping requires source-first review and no canonical attribution. Preserve uncertainty and page citations. Any provider/session write stays within Tutor's own authorized boundary; Learning Studio remains a read-only producer. Adding this consumer requires the Tutor owner's review and tests outside this V1.1 branch.

## Exact automated acceptance contract

| Future test | Required assertion |
|---|---|
| `test_adapter_requires_explicit_action` | Merely GETting a reader/context creates no session, provider call or memory change. |
| `test_adapter_reads_exact_owner_module_revision` | A miss from another module/owner/revision is never included. |
| `test_adapter_rejects_forged_source_and_correctness` | Client owner, source hash, correctness and timestamps cannot replace server evidence; mismatches fail closed. |
| `test_adapter_keeps_empty_and_limited_labels` | Empty and <5 distinct question versions retain honest evidence labels; no mastery/grade claim. |
| `test_adapter_keeps_wrong_then_correct_history` | Recovered status retains the original miss and cites the attempted question version. |
| `test_adapter_requires_live_reviewed_mapping` | Deleted/renamed topic and null mapping cannot become a reviewed canonical course; source-first behavior remains available. |
| `test_adapter_verifies_source_and_references` | Stale bytes, unknown revisions and invalid page locators are rejected before provider use. |
| `test_adapter_omits_private_answer_keys` | Context/prompt excludes hidden keys/explanations; teaching additions remain distinguished from source. |
| `test_adapter_does_not_mutate_other_authorities` | Hashes/snapshots of academic grades, Notes, Knowledge, Obsidian and Learning Studio events are unchanged. |
| `test_adapter_respects_provider_unavailable` | Unavailable provider leaves evidence accessible and creates no successful Tutor turn. |

Already executed producer coverage: `tests/learning_studio/test_review_context.py` checks exact historical revision, empty/limited evidence, cross-module isolation, key exclusion, deleted mapping and byte-identical GET persistence. These tests do **not** prove an automatic Tutor consumer.
