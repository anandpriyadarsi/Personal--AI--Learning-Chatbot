# ANVAYA Tutor 2.2.5 — Live Cross-Session Validation

This stage validates the complete Tutor 2.2 chain in the real local web UI before any Tutor 2.3 work begins.

Validation chain:

conversation -> session state -> signals -> stable patterns -> candidate memory -> accepted memory -> personalized teaching policy -> response

## Safety

Use a disposable copy of the SQLite database. Stop the local server before copying it.

PowerShell from repository root:

    New-Item -ItemType Directory -Force .live_validation | Out-Null
    Copy-Item .\data\learning_assistant.db .\.live_validation\tutor22_live.db -Force
    .\.venv\Scripts\python.exe -c "from pathlib import Path; from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations; print(apply_migrations(Path(r'.live_validation\tutor22_live.db')))"

The migration output must end at schema version 9.

Set the disposable path:

    $env:ANVAYA_TUTOR22_LIVE_DB = (Resolve-Path .\.live_validation\tutor22_live.db).Path

Start a Tutor-only disposable web runtime on port 5001:

    .\.venv\Scripts\python.exe -c "import os; from personal_learning_assistant.ui.web import create_app; from personal_learning_assistant.services.academic_agent_web_service import AcademicAgentWebService; db=os.environ['ANVAYA_TUTOR22_LIVE_DB']; app=create_app({'ACADEMIC_AGENT_WEB_SERVICE_FACTORY': lambda: AcademicAgentWebService(database_path=db)}); app.run(host='127.0.0.1', port=5001, debug=False)"

Open http://127.0.0.1:5001/agent

## Read-only inspector

Copy a Tutor session id from its URL and run:

    .\.venv\Scripts\python.exe .\tutor22_live_inspect.py --database .\.live_validation\tutor22_live.db --session-id "PASTE_SESSION_ID"

The inspector opens SQLite read-only and prints current learning state, persistent student model, personalized teaching policy, and memory candidates.

## Scenario A — first support signal

Create MA103N / LU Factorization / Doubt / Source First.

Ask:

> I understand Gaussian elimination, but I still get confused about why the elimination multipliers are stored in L. Give me a hint only, not the full solution.

Expected: hint behavior, hint_requested signal, but no stable cross-session hint pattern yet.

Before proceeding to Scenario B, run the inspector and verify:

- `topic_id` is non-null;
- the selected topic is the canonical LU Factorization topic;
- old course-level Basis/Redundancy history is not being pulled merely because
  the Tutor session title says "LU Factorization".

If `topic_id` is null, stop validation and fix Tutor session creation scope.

## Scenario B — repeated signal in a second session

Create a completely new MA103N / LU Factorization Tutor session.

Ask:

> Give me a hint for understanding how the elimination multiplier becomes an entry of L. Please do not solve the whole example for me.

Then create a third fresh MA103N / LU session and inspect it.

PASS if the persistent model contains a stable hint_requested pattern with at least 2 sessions and 2 observations.

## Scenario C — personalized teaching

In the third session ask:

> Teach me how to construct L from elimination multipliers for a 3x3 matrix. Start from intuition and let me do some of the reasoning.

Expected policy for the repeated-support case:

- scaffolding = guided
- prerequisite_depth = brief_reinforcement
- explanation_style = intuition_then_steps
- practice_difficulty = supported
- quiz_progression = hold

Visible response should use smaller steps, avoid a full dump, and never claim the student is weak or has mastered the topic.

## Scenario D — current question beats old history

Create a course-level MA103N session with no explicit topic and ask:

> Now explain determinant expansion by cofactors. Do not continue the LU discussion.

PASS only if ANVAYA answers the determinant question and does not continue teaching LU. Historical LU context may influence style but not topic selection.

## Scenario E — proposal and rejection

In a session where the stable pattern is visible under Across sessions, click Propose memory.

Verify a Proposed candidate appears and no authoritative learning memory is created merely by proposal.

Enter review note: Live validation rejection test.

Click Reject.

PASS if the candidate becomes Rejected and accepted_memory_entry_id remains empty.

## Scenario F — stronger evidence and acceptance

Create one more fresh MA103N/LU session and genuinely request a hint again so the stable evidence window grows.

Propose the updated stable pattern. On the disposable database only, accept it with review note:

    Tutor 2.2.5 disposable live acceptance validation.

PASS if status becomes Accepted, accepted_memory_entry_id exists, and exactly one provenance-linked learning-memory row is created.

## Scenario G — accepted memory affects a later session

Create another fresh MA103N/LU session and ask:

> Explain how L is constructed during LU factorization, but adapt the explanation to what would help me most.

PASS if the accepted memory appears in the persistent student model and influences teaching style without becoming an unquestionable claim about ability.

## Final pass criteria

1. One session alone does not create a stable pattern.
2. Two distinct sessions can create a stable pattern.
3. Stable patterns influence policy in the expected direction.
4. Current question always beats historical context.
5. Proposal alone does not write learning memory.
6. Rejection writes no learning memory.
7. Explicit acceptance creates exactly one provenance-linked memory.
8. Accepted memory is visible in a later session.
9. Current confusion overrides historical strength.
10. No production database, vault, or retrieval index is changed.
11. No 500 page, raw Markdown/LaTeX regression, or SQLite thread error appears.

After live validation rerun:

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tutor22_gate.ps1

Only after both live validation and the gate are green should Tutor 2.2 be marked complete.