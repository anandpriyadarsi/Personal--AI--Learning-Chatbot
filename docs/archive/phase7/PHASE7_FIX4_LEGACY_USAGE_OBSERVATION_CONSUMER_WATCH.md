# Phase 7.4 — Legacy Usage Observation / Consumer Watch

## Starting point

Phase 7.4 starts from the completed Phase 7.3 commit:

`12848c9de34b9f55487eb5c056c237c62fbb00d9`

Branch:

`phase7/deprecation-observation`

Phase 7.1 produced the static legacy/compatibility candidate inventory.
Phase 7.2 produced two verified recovery bundles.
Phase 7.3 proved independent full restore, rebuild and reverse-restore.

Phase 7.4 now begins **runtime evidence collection**.

It does not retire anything.

## Why observation is needed

Static analysis can prove that a candidate has a visible caller, but static
absence cannot prove a component is unused.

For example, the V13 `main.py` still routes many historical features through
lazy `FEATURE_ACTIONS` imports. A component may also be run manually as a
script.

Phase 7.4 answers a narrower question:

> While I deliberately use the application through the observation runner,
> which Phase 7.1 candidates actually execute?

A positive event proves use.

No event does **not** prove non-use.

## No invasive instrumentation

Phase 7.4 does not edit:

- `main.py`;
- root legacy modules;
- Phase 4 compatibility repositories;
- SQLite services;
- Tutor Workspace;
- Academic Agent;
- production data.

Instead the operator launches a normal project Python script through:

```text
phase7_consumer_watch.py run
```

A Python profile hook observes candidate source files at runtime.

This keeps legacy code unchanged and makes the observation layer removable.

## What is captured

Only first-seen execution identities are written:

- session ID;
- UTC timestamp;
- candidate repository-relative path;
- candidate module/kind;
- `module_load` or `python_call`;
- function/code symbol name;
- source code first-line number;
- caller repository-relative path, or `<external>`;
- whether the caller itself is a watched candidate.

Repeated identical calls within one session are deduplicated.

The observer is intended to prove **presence of use**, not build behavioral
analytics.

## What is never captured

The watch deliberately does **not** record:

- function arguments;
- function return values;
- local/global variable values;
- note content;
- resource content;
- retrieval queries;
- quiz/PYQ answers;
- assessment content;
- environment variables;
- passwords/tokens/credentials;
- absolute project/vault/source paths;
- provider/network payloads.

Session metadata records only the count of script arguments, never their values.

## Observation root

Runtime evidence must remain outside the repository.

Example:

```powershell
$watch = "C:\Users\91994\Downloads\phase7-consumer-observation"
```

The root is append-only at the session level:

```text
phase7-consumer-observation/
└── sessions/
    ├── <session>.started.json
    ├── <session>.events.jsonl
    └── <session>.completed.json
```

A new session always receives a new UUID-based identity.

Existing evidence is never overwritten.

If a run is interrupted before completion, the started/event evidence remains
and is reported as an incomplete session.

## Using the normal V13 CLI under observation

Instead of:

```powershell
python .\main.py
```

use:

```powershell
python .\phase7_consumer_watch.py run `
  --project-root . `
  --observation-root $watch `
  --script .\main.py
```

The normal menu remains interactive.

Use the application normally.

If you select Notes, Resources, old planners, old dashboard, old RAG, the
historical agent or another watched feature, the execution is recorded without
capturing the data you type into that feature.

## Other project scripts

A project script can also be observed directly:

```powershell
python .\phase7_consumer_watch.py run `
  --project-root . `
  --observation-root $watch `
  --script .\some_project_script.py
```

The runner refuses scripts outside the project and refuses observation output
inside the project.

## Report

At any time:

```powershell
python .\phase7_consumer_watch.py report `
  --project-root . `
  --observation-root $watch `
  --format markdown
```

Or save a report outside the repository:

```powershell
python .\phase7_consumer_watch.py report `
  --project-root . `
  --observation-root $watch `
  --format json `
  --output "$watch\consumer_report.json"
```

The report combines Phase 7.1 static inventory with observed sessions.

Runtime states are intentionally only:

```text
observed_runtime_use
not_observed_yet
```

Phase 7.4 never emits `retirement_candidate`.

## Evidence integrity

For every completed session:

- the event stream SHA-256 is stored in the completion record;
- report generation recalculates it;
- unique event counts must match;
- completed records without matching starts are rejected;
- events naming a component absent from the current inventory are rejected.

This is observation evidence, not an audit/security logging system, but silent
editing of a completed event stream will be detected.

## Incomplete sessions

A crash or hard termination can leave:

```text
.started.json
.events.jsonl
```

without:

```text
.completed.json
```

The report calls that an incomplete session.

Positive events from such a session can still prove that a component executed,
but the time interval is not counted as completed observation time.

## Gate behavior

The Phase 7.4 gate:

1. runs focused tests;
2. performs a real read-only preview of the current repository inventory;
3. launches the real `main.py` through the watch in a temporary external
   observation directory and supplies menu option `40` (Exit);
4. verifies that `main.py` runtime use was recorded;
5. runs Phase 7.1-7.3, Phase 6, Phase 5/4/3 and complete regressions;
6. verifies production SQLite, authority, legacy JSON and retrieval bytes are
   unchanged.

The gate's observation evidence exists only in a temporary directory.

It does **not** start the retained long-term observation period.

## What Phase 7.4 proves

Phase 7.4 proves we have a privacy-minimal, opt-in mechanism for collecting
runtime evidence about legacy/compatibility surfaces without rewriting those
surfaces.

It does not prove that any unobserved component is unused.

## Next boundary

Phase 7.5 — Cross-Interface Parity & Compatibility Closure.

Runtime observation should continue while Phase 7.5-7.7 are developed.

The longer academic-cycle observation requirement remains Phase 7.8.
