# ANVAYA Tutor 2.3.7 — Live Teaching-Orchestration Validation

**Status:** READY FOR LOCAL EXECUTION — not yet live-validated.

Tutor 2.3.7 is the final acceptance stage for Tutor 2.3. It adds no new
teaching behavior. It validates the complete chain through the real local web
UI and configured Tutor provider:

student request -> session goal -> teaching plan -> diagnostic / Socratic
decision -> prerequisite reasoning -> adaptive practice -> correctness /
hidden evaluation -> understanding exit check -> session-local goal outcome.

## 1. Safety boundary

Do not run live validation against the production database.

From repository root:

~~~powershell
git branch --show-current
git status --short
git log --oneline -5
~~~

Required branch:

~~~text
anvaya/tutor-2.3-teaching-orchestration
~~~

The working tree must be clean and Tutor 2.3.6 must already have a green gate.

Capture the production database hash:

~~~powershell
$prodDb = (Resolve-Path .\data\learning_assistant.db).Path
$prodHashBefore = (Get-FileHash $prodDb -Algorithm SHA256).Hash
$prodHashBefore
~~~

Stop any ANVAYA server using the production database before copying it.

Create the disposable database:

~~~powershell
New-Item -ItemType Directory -Force .live_validation | Out-Null
Remove-Item .\.live_validation\tutor23_live.db* -Force -ErrorAction SilentlyContinue
Copy-Item .\data\learning_assistant.db .\.live_validation\tutor23_live.db -Force
.\.venv\Scripts\python.exe -c "from pathlib import Path; from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations; print(apply_migrations(Path(r'.live_validation\tutor23_live.db')))"
~~~

Set the disposable path:

~~~powershell
$env:ANVAYA_TUTOR23_LIVE_DB = (Resolve-Path .\.live_validation\tutor23_live.db).Path
~~~

Record protected table counts before testing:

~~~powershell
.\.venv\Scripts\python.exe -c "import json,os,sqlite3; c=sqlite3.connect(os.environ['ANVAYA_TUTOR23_LIVE_DB']); print(json.dumps({'learning_memory_entries':c.execute('SELECT COUNT(*) FROM learning_memory_entries').fetchone()[0],'progress_snapshots':c.execute('SELECT COUNT(*) FROM progress_snapshots').fetchone()[0]},sort_keys=True)); c.close()"
~~~

Save that output.

Start a disposable local web runtime on port 5002:

~~~powershell
.\.venv\Scripts\python.exe -c "import os; from personal_learning_assistant.ui.web import create_app; from personal_learning_assistant.services.academic_agent_web_service import AcademicAgentWebService; db=os.environ['ANVAYA_TUTOR23_LIVE_DB']; app=create_app({'ACADEMIC_AGENT_WEB_SERVICE_FACTORY': lambda: AcademicAgentWebService(database_path=db)}); app.run(host='127.0.0.1', port=5002, debug=False)"
~~~

Open:

~~~text
http://127.0.0.1:5002/agent
~~~

The Tutor provider should show as configured before provider-backed scenarios
are judged.

## 2. Read-only inspector

After any scenario, copy the Tutor session id from its URL and run:

~~~powershell
.\.venv\Scripts\python.exe .\tutor23_live_inspect.py --database .\.live_validation\tutor23_live.db --session-id "PASTE_SESSION_ID"
~~~

The inspector is read-only. It reports canonical course/topic scope, session
goal, goal evidence, teaching plan, pending-question/Socratic state, adaptive
practice state, Tutor 2.2 context and policy, recent turns/evidence, protected
table counts, and state-invariant checks.

For every inspected session, this is required:

~~~text
all_state_checks_pass = true
~~~

# 3. Live scenarios

Use separate sessions where instructed. Do not force all scenarios through one
conversation.

## Scenario A — vague gap -> diagnostic question

Create:

~~~text
Course: MA103N · Linear Algebra
Topic: LU Factorization
Mode: Doubt
Source policy: Source First
Title: Tutor 2.3.7 A Diagnostic
~~~

Ask:

> I don't understand LU factorization. Help me figure out what part I am missing before you explain everything.

Expected:

- one diagnostic question;
- ANVAYA waits for the answer;
- no full explanation is dumped first.

Inspector:

~~~text
pending_question_kind = diagnostic
awaiting_student_answer = true
teaching_plan.next_move = ask_diagnostic
~~~

PASS only if the visible question and internal pending state agree.

## Scenario B — hint preserves pending diagnostic, then Socratic continuation

Before answering Scenario A's diagnostic, ask:

> Give me one hint only. Keep the question for me to answer.

Expected:

- ANVAYA gives a hint;
- the diagnostic question is not consumed or replaced;
- the same pending question remains.

Inspector:

~~~text
pending_question_kind = diagnostic
awaiting_student_answer = true
~~~

Then answer the original diagnostic honestly.

Expected:

- hidden evaluation is not visible;
- a Socratic outcome is recorded;
- at most one next pedagogical question is asked.

Inspector:

~~~text
last_socratic_outcome = advance | clarify | repair | unclear
~~~

No raw ANVAYA_EVAL marker may appear in the browser.

## Scenario C — known prerequisite gap bypasses generic diagnosis

Create a fresh session:

~~~text
Course: MA103N · Linear Algebra
Topic: LU Factorization
Mode: Doubt
Source policy: Source First
Title: Tutor 2.3.7 C Prerequisite
~~~

Ask:

> I understand Gaussian elimination, but I do not understand elimination multipliers in LU factorization. Explain only what I need so I can return to LU.

Expected:

- a specific prerequisite gap is selected;
- generic diagnosis is not asked first;
- ANVAYA teaches only the bounded prerequisite;
- it reconnects the prerequisite to LU.

Inspector:

~~~text
teaching_plan.next_move = review_prerequisite
teaching_plan.prerequisite_concept = Elimination Multipliers
teaching_plan.target_concept = LU Factorization
teaching_plan.return_to_goal = true
~~~

When a canonical prerequisite topic exists, retrieval must remain inside MA103N
and use that prerequisite topic scope. FAIL if ANVAYA recursively opens
multiple prerequisite branches.

## Scenario D — adaptive computational practice

Create a fresh MA103N / LU Factorization session:

~~~text
Mode: Concept
Source policy: Source First
Title: Tutor 2.3.7 D Practice
~~~

Ask:

> Give me one computational practice problem on elimination multipliers in LU factorization. Wait for my answer.

Expected:

- exactly one task;
- no full worked solution in the same turn;
- the task is tracked as practice.

Inspector: record initial practice level as L0.

Required:

~~~text
pending_question_kind = practice
practice_active = true
1 <= practice_level <= 5
practice_format = computational
~~~

Answer the actual problem correctly.

Expected new level:

~~~text
min(L0 + 1, 5)
~~~

There must be at most one next task.

Then answer the next computational task deliberately incorrectly.

Expected new level:

~~~text
max(previous_level - 1, 1)
~~~

One answer must never jump more than one level. If a misconception is
identified, the next practice format may become misconception_targeted.

No visible wording may call a practice level mastery, intelligence, ability, or
academic progress.

## Scenario E — explicit practice request beats automatic preference

Continue Scenario D or create a fresh practice session.

Ask:

> Give me a harder computational practice problem. One problem only.

Expected:

- computational format remains authoritative;
- difficulty moves by one bounded level only;
- Tutor 2.2 historical policy does not override the explicit request.

Then ask:

> Give me an easier computational practice problem. One problem only.

Expected:

- one bounded step downward;
- still computational;
- one task only.

## Scenario F — topic shift cancels old pedagogical state

Create a course-level MA103N session with no explicit topic.

Start with:

> Give me one practice problem about LU factorization and wait for my answer.

While the practice task is pending, ask:

> Skip the practice question. Now explain determinant expansion by cofactors. Do not continue LU.

Expected:

- old pending work is cancelled;
- current request is authoritative;
- goal shifts to determinant/cofactor work;
- ANVAYA does not continue LU because of history.

Inspector:

~~~text
practice_active = false
pending_question = ""
pending_question_kind = ""
~~~

The session goal and teaching plan must reflect the new request.

## Scenario G — regression: mixed understanding + new question

Create a suitable MA103N session and ask exactly:

> I understand span but why does a basis need linear independence?

Expected:

- normal teaching request;
- ANVAYA answers the linear-independence question;
- Tutor 2.3.6 does not interpret "I understand span" as session closure.

Inspector must not show:

~~~text
pending_question_kind = exit_check
reason = student_reports_understanding
~~~

## Scenario H — self-report -> one exit check -> likely met

Create a fresh topic-scoped Tutor session and have a short genuine discussion
until the goal is clear.

Then say:

> I understand it now.

Expected immediately:

- ANVAYA does not declare mastery;
- ANVAYA asks exactly one goal-specific exit check;
- it waits for the answer.

Inspector:

~~~text
pending_question_kind = exit_check
awaiting_student_answer = true
goal.status = active | unresolved
exit_check_count >= 1
~~~

Answer the exit check correctly in your own words.

Expected:

~~~text
goal.status = likely_met
pending_question_kind = ""
~~~

The UI must explicitly label this as current-session evidence only and not
mastery. No second exit check should open in the same turn.

## Scenario I — likely-met goal can reopen

Continue Scenario H after likely_met.

Say:

> I am still confused about why the elimination multiplier appears with a positive sign in L.

Expected:

~~~text
goal.status = unresolved
~~~

ANVAYA should address the new confusion rather than treating the earlier state
as permanent mastery. Goal evidence should contain a bounded
student_reported_unresolved entry.

## Scenario J — Source Only deterministic exit check

Create a fresh Tutor session:

~~~text
Course scope: optional
Mode: Concept
Source policy: Source Only
Title: Tutor 2.3.7 J Source Only
~~~

Establish a session goal, then ask:

> Check if I understand this.

PASS if ANVAYA can ask the deterministic exit-check question even when no
retrieved project evidence is available.

The exit-check prompt itself must not invent unsupported academic claims. If
support is insufficient, the UI may label the response insufficient; it must
not silently pretend it is grounded.

## Scenario K — correctness and mathematical rendering

In MA103N ask:

> Take the matrix A = [[2,1,1],[4,3,3],[8,7,9]]. Compute its LU factorization step by step and verify that LU = A before giving the final result.

Check visually:

- matrix notation renders normally;
- no raw LaTeX delimiters, hidden evaluation marker, or raw Markdown formatting
  is exposed;
- numerical factorization is internally consistent;
- repaired/blocked calculations are not presented as verified correct;
- no HTTP 500 page or SQLite cross-thread error appears.

# 4. Final state checks

Inspect the important sessions from A/B, C, D/E, F, G, H/I, and J.

Every inspected session must report:

~~~text
all_state_checks_pass = true
~~~

Run protected table counts again:

~~~powershell
.\.venv\Scripts\python.exe -c "import json,os,sqlite3; c=sqlite3.connect(os.environ['ANVAYA_TUTOR23_LIVE_DB']); print(json.dumps({'learning_memory_entries':c.execute('SELECT COUNT(*) FROM learning_memory_entries').fetchone()[0],'progress_snapshots':c.execute('SELECT COUNT(*) FROM progress_snapshots').fetchone()[0]},sort_keys=True)); c.close()"
~~~

Counts must match the baseline unless you explicitly performed a Tutor 2.2
human-approved memory action during this disposable run. Tutor 2.3 scenarios
themselves must not create learning-memory or progress rows automatically.

Stop the port-5002 server and confirm production database protection:

~~~powershell
$prodHashAfter = (Get-FileHash $prodDb -Algorithm SHA256).Hash
$prodHashAfter
$prodHashBefore -eq $prodHashAfter
~~~

Required:

~~~text
True
~~~

# 5. Final automated gate

After live scenarios are complete, stop the disposable server and ensure the
Git working tree is clean.

Run:

~~~powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tutor23_fix7_gate.ps1
~~~

The automated gate is necessary but is not sufficient by itself.

Tutor 2.3.7 is complete only when the manual live scenarios pass, production
hash is unchanged, protected learning-memory/progress counts are unchanged by
Tutor 2.3, no runtime/rendering regression is observed, and the automated gate
is green.

# 6. Final acceptance criteria

Tutor 2.3 may be declared live validated only if:

1. vague confusion produces one diagnostic question;
2. hints preserve pending diagnostic/practice work;
3. diagnostic answers continue through bounded Socratic state;
4. known prerequisite gaps bypass unnecessary generic diagnosis;
5. prerequisite repair stays course-scoped and returns to the goal;
6. practice is one-task-at-a-time and levels stay within 1..5;
7. answer evidence changes practice difficulty only by the bounded rule;
8. explicit practice preferences remain authoritative;
9. topic shifts cancel stale pedagogical state;
10. mixed "I understand X, but why Y?" remains a teaching request;
11. self-reported understanding alone never becomes likely_met;
12. a correct evaluated exit check can produce only session-local likely_met;
13. partial / incorrect / unclear exit checks produce unresolved;
14. new explicit confusion can reopen likely_met;
15. Source Only does not invent grounding;
16. hidden evaluation metadata is never visible;
17. mathematical output respects correctness verification/repair/blocking;
18. no HTTP 500 or SQLite thread regression appears;
19. Tutor 2.3 does not automatically write learning memory or progress;
20. production database, retrieval index, and vault remain protected;
21. final automated gate passes.

## Live result

**NOT YET EXECUTED.**

Do not mark Tutor 2.3 complete until observed local results are recorded here.
