# MA103N Canonical Topic Catalogue Expansion

## Purpose

Expand ANVAYA's canonical MA103N Linear Algebra topic catalogue to the user's
confirmed current syllabus through Week 6, without changing any existing topic
progress, deleting topics, or forcing assessment-review loops.

This catalogue is used by Assessment Studio when it injects canonical course
topics into the Alex/ChatGPT authoring prompt and when imported questions are
mapped to ANVAYA topics.

## Confirmed syllabus coverage

The reconciler preserves the existing MA103N topics and ensures coverage for:

- linear systems, elementary row operations, echelon/RREF, rank, Rouché–Capelli,
  consistency and solution classification;
- Gaussian/Gauss–Jordan elimination, matrix inverse by elimination,
  LU factorisation, determinants;
- vector spaces, axioms, standard/examples and structural properties;
- subspaces, linear independence, bases and dimension;
- span, basis theorems, coordinate representations and dimension theorems;
- inner products in R^n, orthogonal/orthonormal sets, orthogonal matrices,
  Gram–Schmidt and orthonormal bases;
- orthogonal complements, QR factorisation, least squares and best approximation.

The code deliberately does not add transition matrices, eigenvalues, SVD, or
other topics outside the supplied current scope.

## Safety properties

- Existing topic order, status, confidence, progress evidence and IDs are
  preserved.
- Missing canonical topics are appended as `not_started`.
- The operation is idempotent.
- SQLite aliases are added only when SQLite is the active structured authority.
- An alias already owned by another MA103N topic is treated as a conflict rather
  than silently reassigned.
- The command is explicit and does not run on application startup, so it cannot
  mutate the catalogue during an in-progress timed assessment.

## Command

After finishing any in-progress test and pulling the branch:

```powershell
python -m personal_learning_assistant.services.ma103n_topic_catalogue_service
```

The command prints a JSON summary with the number of topics and aliases added.

## Assessment labels specifically covered

Aliases/canonical names cover the labels that previously caused the
`ma103n.quiz.super-hard.003` review loop, including:

- Determinants
- Coordinate Representations
- Span
- Dimension Theorems
- Vector Space Axioms
- Bases and Coordinate Representations
- Subspaces
- Bases and Dimension
