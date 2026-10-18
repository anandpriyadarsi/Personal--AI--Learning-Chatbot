# Phase 7.5.10 — ANVAYA Product Shell + Branding

## Status

Implementation scope: presentation shell only.

Visible product identity:

> **ANVAYA — Personal Learning Intelligence**

Phase 7.5.10 replaces the generic Phase 7.5 browser chrome with the approved ANVAYA dark-first shell while preserving the existing Flask routes, academic services, persistence/authority boundaries, tutor behaviour, and read/write semantics.

## What changed

- Added the ANVAYA desktop wordmark and symbol-only app mark as local static assets.
- Added repository brand-reference artwork under `docs/brand/`.
- Replaced the generic header/sidebar with a persistent ANVAYA product shell.
- Added grouped primary navigation matching the approved product information architecture.
- Renamed the visible `Academic Agent` navigation destination to **Tutor** without changing the `/agent` route or backend behaviour.
- Added a dark-first token system using the approved brand colours.
- Added an accessible mobile drawer with dependency-free local JavaScript.
- Preserved the existing page CSS vocabulary so all Phase 7.5.1-7.5.9 templates inherit the new shell without page-specific rewrites.

## Real routes preserved

These destinations remain real links and retain their existing route behaviour:

- Home — `/`
- Tutor — `/agent`
- Notes — `/notes`
- Resources — `/resources`
- Knowledge — `/knowledge`
- Courses — `/courses`
- Assessments — `/assessments`
- Calendar — `/calendar`
- Planning — `/planning`

## Visible but deferred

The approved navigation also shows these future workspaces as disabled, non-link items with a visible `Soon` marker:

- Obsidian
- Progress
- Grades
- Settings

Phase 7.5.10 does not invent placeholder routes or fake readiness/status for these capabilities.

## Safety boundary

Phase 7.5.10 adds **no new academic write capability**.

It does not modify:

- `personal_learning_assistant/ui/web/routes.py`;
- services or repositories;
- SQLite schema or migrations;
- authority routing;
- tutor/retrieval logic;
- production academic data;
- retrieval indexes;
- existing page templates other than `base.html`.

The existing CLI remains available and unchanged.

## Brand asset mapping

The supplied ANVAYA PNGs are copied byte-for-byte without resizing, recolouring, rotating, glow effects, or re-encoding.

| Supplied asset role | Repository target | Product use |
| --- | --- | --- |
| Symbol-only transparent ANVAYA mark | `personal_learning_assistant/ui/web/static/brand/anvaya-mark.png` | favicon, mobile mark |
| Transparent white ANVAYA wordmark/tagline | `personal_learning_assistant/ui/web/static/brand/anvaya-wordmark-white.png` | desktop sidebar identity |
| Light-background primary logo | `docs/brand/ANVAYA_PRIMARY_LIGHT.png` | documentation/reference |
| Dark README banner | `docs/brand/ANVAYA_README_BANNER.png` | README/portfolio use |
| Splash artwork | `docs/brand/ANVAYA_SPLASH.png` | optional onboarding/about use |
| Mini brand guide | `docs/brand/ANVAYA_MINI_BRAND_GUIDE.png` | brand reference |

The README banner, splash artwork, and mini brand guide are intentionally **not** rendered in ordinary dashboard workspaces.

## Brand colours

- Primary Dark: `#0B0F14`
- Primary Light: `#E8EDF2`
- Accent Teal: `#55C2B8`
- Supporting Blue-Gray: `#64748B`

The interface is dark-first. Accent teal is reserved for active/focus/primary emphasis rather than used as constant decoration.

## Accessibility and responsive behaviour

- Skip link remains available.
- Active navigation receives `aria-current="page"`.
- Disabled future destinations use `aria-disabled="true"` and are not links.
- Keyboard focus is visibly styled.
- The mobile navigation toggle exposes `aria-controls` and `aria-expanded`.
- `Escape` closes the mobile drawer and returns focus to its toggle.
- Reduced-motion preferences suppress non-essential transitions/animations.
- Normal mobile workflows avoid horizontal page scrolling.

## Run locally

From the repository root:

```powershell
python -m personal_learning_assistant.ui.web
```

If `python` is not the active interpreter, use the project virtual environment or `py` as appropriate.

Open:

```text
http://127.0.0.1:5000
```

Stop the development server with `Ctrl+C`.

## Completion gate

Run before any implementation commit:

```powershell
powershell -ExecutionPolicy Bypass -File .\phase7_5_fix10_gate.ps1
```

A valid completion ends with:

```text
PHASE 7.5.10 ANVAYA PRODUCT SHELL: PASS
```

The gate verifies the new shell and assets, all existing Phase 7.5 web regressions, Phase 7.1-7.4 regressions, the complete pytest suite, Python/package health, SQLite integrity/foreign keys, protected backend hashes, scoped Git changes, and production-data/retrieval-index immutability.

## Deferred functional work

This phase deliberately does not solve the current read-only limitations of Notes, Resources, Calendar, Planning, or Assessments. It establishes the stable ANVAYA product shell around the existing functionality.

**Next planned phase:** Phase 7.5.11 — Operational Notes + Resources.
