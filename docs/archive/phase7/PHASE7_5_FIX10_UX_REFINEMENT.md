# Phase 7.5.10 — ANVAYA UX Refinement Patch

## Purpose

This bounded patch refines the already-completed Phase 7.5.10 ANVAYA product shell after real laptop review. It does not add academic write capability or change backend behaviour.

## User-facing changes

- Shrinks the desktop sidebar from 16.5rem to 15rem and reduces the ANVAYA wordmark footprint.
- Removes the desktop sidebar's independent scrollbar; the normal desktop experience uses the page scroll.
- Keeps the most-used workspaces visible and moves secondary/deferred destinations into a native `More` disclosure.
- Replaces the oversized Home hero with an action-first ANVAYA command centre.
- Removes developer-facing `Phase 7.5.2` and `read-only view` copy from the normal Home experience.
- Moves ANVAYA's best-next-action recommendation above the metric summary.
- Makes the four academic metrics compact so they no longer dominate the first screen.
- Adds honest quick links to existing workspaces only. `+ Task` remains visibly disabled as `Soon`; no fake task or Obsidian route is introduced.
- Replaces the duplicated desktop top-bar descriptor with compact `Academic workspace` / `Local-first` language.

## Safety boundary

This patch modifies presentation only:

- `personal_learning_assistant/ui/web/templates/base.html`
- `personal_learning_assistant/ui/web/templates/home.html`
- `personal_learning_assistant/ui/web/static/css/app.css`

It also adds/updates tests and this gate/documentation.

It does **not** modify:

- Flask routes;
- services or repositories;
- SQLite schema/migrations;
- authority routing;
- tutor/retrieval logic;
- production academic data;
- retrieval indexes;
- JavaScript behaviour;
- brand PNG assets.

No new academic write capability is introduced.

## Base commit

The patch is designed for:

`e55eedd9b4b1abdef4a793bb89cd8305253567c1` — `feat: add Phase 7.5.10 ANVAYA product shell`

## Run locally

```powershell
python -m personal_learning_assistant.ui.web
```

Open `http://127.0.0.1:5000`.

## Completion gate

Run before committing:

```powershell
powershell -ExecutionPolicy Bypass -File .\phase7_5_fix10_ux_gate.ps1
```

A valid completion ends with:

```text
PHASE 7.5.10 ANVAYA UX REFINEMENT: PASS
```

After this patch is closed, the next functional milestone remains **Phase 7.5.11 — Operational Notes + Resources**.
