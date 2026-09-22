# ANVAYA Tutor 2.0 — Conversational Academic Tutor Foundation

Branch: `anvaya/tutor-2.0`  
Baseline: green `anvaya/operational-ux-integrations` at `6f02b1e`.

## Goal

Move ANVAYA from a grounded search-like chat toward a genuine personal academic
Tutor while preserving the proven Phase 6 evidence, persistence, and safety
boundaries.

Tutor 2.0 is not a new academic database and does not replace ANVAYA's existing
knowledge, course, Obsidian, planner, or retrieval authorities.

## This first Tutor 2.0 unit implements

### 1. Readable model output

Assistant answers are rendered with Mistune using escaped raw HTML.

Supported presentation includes:

- headings;
- emphasis;
- lists;
- tables;
- code blocks;
- task-list syntax;
- mathematical delimiters;
- project citations such as `[S1]`.

Citations become local links to the corresponding evidence card.

Raw model HTML remains escaped. Model output is never inserted as trusted raw
HTML.

MathJax typesets LaTeX in the Tutor page. The current first unit loads MathJax
from jsDelivr; future local-first hardening may vendor the required static asset
or replace it with a local renderer.

### 2. Conversation-first layout

The broken narrow user-message grid is removed.

Tutor messages now use:

- a wide reading column;
- right-aligned student bubbles;
- lightweight ANVAYA answers;
- a single page scroll rather than an inner transcript scroll;
- sticky composer;
- human-readable course labels;
- technical UUID/chunk/provider information collapsed under details.

### 3. Source First as the normal browser Tutor experience

Existing direct service compatibility remains Source Only by default.

The browser's normal new-session flow now selects `source_first`.

- **Source First**: ANVAYA uses project evidence as primary context but may use
  clearly separated general academic knowledge to teach.
- **Strict Source Only**: existing fail-closed evidence behavior remains.

Source-grounded sessions launched directly from a Knowledge Reader remain
`source_only`.

### 4. General teaching fallback

Previously, retrieval returning zero chunks always produced:

> I do not have enough project evidence...

Tutor 2.0 keeps that behavior for Strict Source Only.

For Source First sessions, zero retrieved project evidence may now call the
configured Tutor provider and return a clearly general explanation. Such turns are persisted with the existing `mixed` support level, which means the answer is not fully grounded in project evidence. No new Tutor database enum or schema migration is introduced.

### 5. Tutor Brain prompt

The provider prompt now explicitly treats ANVAYA as a personal academic Tutor,
not a search-results page.

It instructs the model to:

- optimize for student understanding rather than information density;
- infer whether the student wants explanation, hint, verification, practice,
  revision, summary, assessment help, or another teaching move;
- diagnose the missing idea or misconception before expanding;
- prefer intuition -> example -> formal detail where appropriate;
- respect "hint only", "do not solve", and similar requests;
- avoid encyclopedic dumps;
- use Markdown and LaTeX;
- use short checks for understanding when useful;
- preserve the existing prompt-injection/evidence boundary;
- never invent source identities/citations;
- never claim academic state changed when no write occurred.

Mode-specific teaching behavior remains layered on top of this Tutor Brain.

### 6. Local teaching-intent router

A deterministic local classifier identifies high-confidence requests for:

- hint;
- quiz;
- reasoning verification;
- worked example;
- practice;
- summary;
- guidance;
- explain differently;
- default explanation.

This performs no LLM call and no academic write.

The original student question is still sent unchanged to the provider. Intent is
only an additional pedagogical hint.

### 7. Real Tutor feedback

The existing `tutor_feedback` authority is now reachable from the web UI.

Each assistant response offers explicit helpful / not-helpful controls.

Feedback writes only to the Tutor feedback store. It does not update mastery,
learning memory, grades, plans, notes, or resources.

This creates the first clean signal for future evaluation and possible
fine-tuning datasets.

### 8. Follow-up teaching controls

The composer exposes lightweight follow-up prompts:

- Explain differently
- Example
- Hint
- Check me
- Quiz me

These populate the normal Tutor input. They do not create a parallel execution
path.

## Preserved safety and architecture

Tutor 2.0 still:

- persists only Tutor session/turn/evidence/feedback data through Tutor writes;
- does not modify grades, mastery, notes, plans, assessments, or source files;
- validates project evidence citations;
- rejects unavailable citation labels;
- treats retrieved evidence as data rather than instructions;
- keeps source-grounded Knowledge Reader sessions strict;
- keeps provider and retrieval boundaries lazy;
- performs no provider call on GET routes.

## Deferred Tutor 2.0 work

This first unit does **not** yet implement:

- multi-query retrieval;
- cross-encoder reranking;
- persistent misconception/student-model memory;
- automatic learning-memory writes;
- streamed token responses;
- function/tool calling;
- image/diagram generation inside Tutor;
- voice Tutor;
- local-LLM model management;
- LoRA/QLoRA fine-tuning;
- automatic evaluation from grades/assessment outcomes.

Those are later Tutor 2.0 units after this conversation foundation is proven
useful in real MA103N/CY100N/UC100N study sessions.

## Validation target

A successful live check should show:

1. student messages no longer wrapping one character per line;
2. Markdown headings/bold/lists display as normal formatted text;
3. LaTeX matrices/equations typeset on an internet-connected browser;
4. course scope shows e.g. `MA103N · Linear Algebra`, not a UUID;
5. evidence is readable and technical IDs are collapsed;
6. a Source First session can still teach when retrieval returns no useful chunk;
7. "hint only" and "quiz me" requests produce different teaching behavior;
8. helpful/not-helpful feedback submits without changing other academic state.
