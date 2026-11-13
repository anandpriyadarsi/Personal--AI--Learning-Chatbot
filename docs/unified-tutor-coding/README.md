# Unified Tutor + Coding Studio (local web)

**Permanent integration:** Coding Studio is available by default in the local Tutor. You no longer need to set `ANVAYA_TUTOR_CODING_ENABLED=true` before each launch. One-time backup-first activation of optional schema 0017 is still required on each existing database. Its tables persist across ANVAYA restarts, and restarting never repeats the migration. `ANVAYA_TUTOR_CODING_ENABLED=false` remains an explicit emergency opt-out. The web app does not migrate or create a database during startup or a GET request.

Academic and Coding share one Tutor history, rename flow, source policy and compact composer. Coding is versioned session metadata, never a new SQL teaching mode. Assessment Studio keeps its own UC100N/practice/exam policy and signed ephemeral context; it only shares the pure teaching catalogue/prompt builder.

## Windows update and explicit activation

Use PowerShell in your existing ANVAYA repository. Stop the server first with Ctrl+C. These commands update code without resetting academic records. Resolve any reported Git conflicts before proceeding; do not discard your local work.

```powershell
cd C:\path\to\Personal--AI--Learning-Chatbot
git switch main
git pull --ff-only origin main
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt -r requirements-assessment-browser.txt
.\.venv\Scripts\python.exe -m personal_learning_assistant.services.coding_activation --database data/learning_assistant.db
# No coding feature environment variable is required after activation.
.\.venv\Scripts\python.exe phase7_web.py
```

Open **http://127.0.0.1:5000/agent** (or the exact loopback URL printed by your launcher if you supplied a different port). If your installation uses another canonical database, pass that exact path to `--database`; do not activate an empty replacement. Keep existing provider configuration in your private environment/`.env`: `LLM_API_URL`, `LLM_API_KEY`, `LLM_MODEL`. Do not put credentials in Git or notebook cells. The provider remains optional for task storage, offline operation cards and notebook export.

Activation requires an existing canonical Tutor owner. It first creates an integrity-checked SQLite backup beside that database, named `*.before-coding-<UTC>.bak`, then applies optional migration 0017 transactionally. It records optional version 17 separately from the core migration ledger (optional 15/16 are not implicitly enabled). It changes no existing table or teaching-mode CHECK. Ordinary startup, imports and GETs never apply this migration. Repeat activation is harmless. The server should remain stopped throughout activation.

For a complete study backup, also retain your original Library/native-library storage and Learning Studio files using their existing backup procedures. The activation backup covers the entire canonical database, including Tutor tables; a Library-only export is insufficient to restore Tutor history. Development never reads or migrates your installed production data.

## Student flow

1. In Tutor, create a Coding Studio conversation with the intended course/topic/source policy, or switch an existing conversation to Coding Studio. Changing workspace preserves scope and unsent drafts; changing source policy/course requires a new conversation.
2. Open **Code & tools**, choose a reviewed template or describe a Python task, and **Save task locally**. This makes no AI call. Saved task code persists after restart. Save edits explicitly; each save advances a revision.
3. Review the source selection/provider disclosure under **Sources and provider consent**, then approve the displayed scope. The review uses server-owned source identities and current versions. Source/provider changes require a new review; replaced source-bound material requires a new scoped conversation. With Source Only and no evidence, create an explicit Source First conversation for general practice.
4. Choose Explain, Debug, Predict, Hint or another teaching action, review the code/output/attempt, close tools, and press Send. Output pasted from Colab is student-provided and unverified. Full solutions require a fresh explicit checkbox for Debug/Explain code/Pseudocode; hint actions never allow that checkbox.
5. **Download practice notebook** → **Open Colab** → **File → Upload notebook**. Run cells manually in Colab. ANVAYA cannot see the other tab. Paste revised code/output/error back for debugging or one-question viva. Downloads contain empty outputs and `not_executed` provenance. Uploading a notebook transfers it to Google.

Five authored templates cover Python collections, NumPy shape/axis, Pandas loc/iloc/groupby, missing-value cleaning and Matplotlib histograms. Their checks are visible synthetic practice, not official grading. A student-defined task exports without invented assertions. Export includes saved student code only when explicitly selected, never professor extraction text or hidden solutions. Template changes use a new task.

All 82 operation cards work locally without an AI provider. Task save, history and notebook export are local too. No local Python runner, notebook import, OAuth, Drive sync, Colab API/MCP, automatic Learning Studio conversational review, code grading, mastery update or automatic long-term-memory write is part of this release. Existing Learning Studio offline help and manual review brief remain available.

## Failure and retention behavior

One coding request per local session can be in flight. Identical completed requests replay their durable receipt without another AI call; changed semantics under the same identity are rejected. Provider failures retain the draft and retry identity, with no partial turns. Task/source changes during a reply reject the stale exchange. Stop waiting only stops the browser wait: the server/provider may finish. Reopen the transcript before retrying to reconcile a completed receipt. There is no automatic paid retry.

Task archiving hides a task and retains its sent context/history. It does not erase provider retention or exported notebooks. Drafts live only in page memory, survive workspace toggles, and warn before dirty navigation; they are not silently saved in browser storage. Tracebacks/code are editable for manual redaction. ANVAYA does not claim to detect every secret.

## Rollback

To temporarily disable Coding Studio, stop the server and set `$env:ANVAYA_TUTOR_CODING_ENABLED='false'`, then restart. Remove that override to enable Coding Studio again after its existing one-time activation. Existing Academic Tutor remains available. New optional tables and sent context stay intact. Code rollback may retain these additive tables. Do not run a destructive down migration or restore a backup over newer study records; compare dates and restore only through the canonical owner recovery process if needed.

## Verification commands

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
$env:ANVAYA_BROWSER_TESTS='1'
.\.venv\Scripts\python.exe -m pytest -q tests/test_coding_teaching.py tests/test_tutor_coding.py tests/test_coding_notebooks.py tests/test_tutor_coding_browser.py tests/test_assessment_coding_helper.py tests/test_assessment_coding_helper_2.py tests/test_tutor_ui_v3.py tests/test_tutor_ui_v3_browser.py tests/test_phase6_tutor_foundation.py tests/test_phase6_grounded_tutor_engine.py tests/test_tutor_topic_scope_web.py tests/test_library2_tutor_bridge.py tests/test_tutor_grounding_v24.py tests/test_learning_tutor_session_v24.py tests/learning_studio/test_v12_tutor_bridge.py
node --test tests/js/assessment_coding_helper.test.cjs tests/js/tutor_coding.test.cjs
```

The existing web CI runs focused regressions, the real Chromium coding journey, notebook checks and Node contracts on **Ubuntu and Windows** at the actual PR head. Its JUnit gate rejects skipped focused cases. Canonical repository CI is retained. Results/screenshots are synthetic. Live-provider educational quality and authenticated Colab execution are separate and are not certified by fake-provider tests.
