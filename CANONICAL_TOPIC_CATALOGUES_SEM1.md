# ANVAYA Canonical Topic Catalogues — Semester 1

## Purpose

Assessment Studio verifies every imported `academic_map.topic` against the
selected course's ANVAYA topic catalogue. If a course has no topics, a valid
assessment package is forced into the Alex-review queue as `topic_unmapped`.

This change adds a source-backed, explicit reconciliation command for the five
confirmed Semester-1 academic courses:

| Course | Coverage | Canonical topics |
|---|---|---:|
| MA103N — Linear Algebra | Full official course plan | 51 |
| UC100N — Data Science and Artificial Intelligence | Full official course plan | 67 |
| CY100N — Engineering Chemistry | Full official course plan + lab | 83 |
| UC103N — Indian Knowledge System | Supplied class-note set / current 90Q package | 81 |
| DE100N — Design Thinking and Prototyping | Minimal: confirmed course title only | 2 |

Total: **284 canonical topics**.

DE100N is deliberately conservative. A detailed official DE100N course plan was
not supplied, so ANVAYA seeds only `Design Thinking` and `Prototyping` rather
than inventing a standard design-thinking syllabus.

PL110N, PL120N, PL130N and PL140N are also not given invented assessment
taxonomies without source material.

## Current UC103N blocker

The current handoff
`UC103N.iks.90q.practice-test.001_rev1_alex-review.anvaya-review.json`
contains 90 questions but an empty `canonical_topic_catalogue`. Its 90
questions use 81 unique topic labels.

The UC103N catalogue in this change uses those **81 exact source-backed topic
labels as canonical names**, so the current package can map deterministically
after reconciliation rather than relying on fuzzy guesses.

## Safety contract

The reconciliation service:

- never creates missing courses;
- never runs automatically at application startup;
- preserves existing topic status/confidence/history;
- treats an existing alias spelling as the same semantic topic instead of
  creating a duplicate;
- appends only genuinely missing topics;
- when SQLite is authoritative, writes aliases transactionally to
  `topic_aliases`;
- is idempotent.

## Run

After updating the checkout to a commit containing this change:

```powershell
python -m personal_learning_assistant.services.canonical_topic_catalogue_service
```

To repair only the current IKS blocker:

```powershell
python -m personal_learning_assistant.services.canonical_topic_catalogue_service UC103N
```

The command prints a JSON report with added-topic counts, aliases added,
authority backend and any course that was not present.

After the UC103N reconciliation, regenerate the Assessment Studio Alex-review
handoff (or re-stage the clean revision-2 package) so the handoff contains the
new canonical catalogue.

## Source policy

The catalogue definitions are in
`personal_learning_assistant/domain/canonical_topic_catalogues.py`.

The reconciliation/application boundary is
`personal_learning_assistant/services/canonical_topic_catalogue_service.py`.

Tests are in
`tests/test_canonical_topic_catalogue_service.py`, including an exact check
that all 81 unique raw UC103N labels in the current 90-question handoff are
covered.
