# Phase 7.5.1 — Local Web Interface Foundation

## Objective

Introduce the smallest safe browser interface for the Personal AI Learning Assistant without changing the authoritative academic data model, bypassing service boundaries, or replacing the existing CLI.

## Scope

Phase 7.5.1 adds:

- a Flask application factory under `personal_learning_assistant.ui.web`;
- a local-only launcher bound to `127.0.0.1`;
- a shared Jinja navigation/application shell;
- a read-only Home route;
- a side-effect-free `/healthz` route;
- a project 404 page;
- local CSS with responsive and dark-mode support;
- focused regression tests and a Phase 7.5.1 gate.

## Deliberately deferred

This phase does **not** add course, assessment, planning, calendar, notes, resources, knowledge/RAG, or Academic Agent workflows. It does not expose direct SQLite CRUD. HTMX behavior is deferred until a screen needs partial-page interaction; the architecture remains Flask/Jinja-first and ready for progressive enhancement.

## Safety boundaries

- Existing `main.py` remains the developer/debug CLI.
- Web startup must not import optional AI/RAG/vision/YouTube engines.
- Web startup must not import the legacy root `notes.py`, `resources.py`, or `course_manager.py` facades.
- GET `/` and GET `/healthz` must not create runtime directories, modify SQLite, or mutate academic data.
- No SQLite migrations, authority switches, deprecation decisions, or Phase 7.1–7.4 changes are part of this work.
- All browser assets used by the foundation are local; no CDN is required.

## Running locally

Install the updated dependencies, then start the loopback-only development server:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
.\.venv\Scripts\python.exe phase7_web.py
```

Open `http://127.0.0.1:5000/` in the browser. The health endpoint is `http://127.0.0.1:5000/healthz`.

## Gate expectation

Run:

```powershell
.\phase7_5_fix1_gate.ps1
```

The gate verifies focused web behavior, startup isolation, Phase 7 regressions, full regressions, compilation, dependencies, SQLite read-only integrity, and working-tree scope before the phase is committed.
