# ANVAYA GitHub Actions — storage and CI policy (2026-11-08)

## Why this exists

On 2026-11-08, the owner received a GitHub Actions **storage** alert:
0.45 GB used of 0.5 GB included, resetting for the billing cycle on
2026-12-01. This is not a runner-minute warning.

An observed canonical architecture run on 2026-11-07 stored roughly
93.7 MB of Ubuntu evidence plus 68.6 MB of Windows evidence. The two
runs' screenshot/log bundles are the highest-priority storage source.

## Safe operating policy

- **Keep tests running.** The global synthetic architecture (Ubuntu and
  Windows) and web integration checks remain unchanged and authoritative.
  Never treat lightweight selector checks as full acceptance.
- **Upload compact architecture summaries on success.** Keep JSON/XML,
  manifests and release-related attestations. Upload bulky screenshots
  and `*.log` only when the architecture development job fails.
- **Short artifact retention by default.** Routine UI/feature evidence:
  3 days. Cross-platform architecture and installed Android evidence:
  7 days. Independent release files belong in GitHub Releases; keep a
  provenance report in Actions for 7 days.
- **Avoid duplicate APKs.** The Android release is already stored in a
  versioned GitHub Release. The Actions provenance artifact contains
  only checksums, test report, signing and metadata.
- **Scope legacy feature-specific PR workflows.** A native Android
  matrix should not run for a web-only pull request; the Smart
  Verification coordinator still detects changed native sources.
  Mobile-PWA-only acceptance remains available via manual dispatch.
- **Benchmark on demand.** The verification benchmark no longer
  automatically follows each successful architecture run. Dispatch it
  manually with an optional architecture run ID to compare timings.
- **Do not weaken merge acceptance.** Full tests and browser checks
  continue to execute where they already ran. Investigate failures
  rather than suppressing or marking checks as passed.

## Storage cleanup still required

Changing artifact retention on future runs does **not** delete existing
stored artifacts or instantly erase billed usage.

1. Review artifacts in GitHub > repository > Actions, keeping release
   assets, diagnostics for active failures, and any personally needed
   reports. Download valuable evidence before deletion.
2. Delete old, superseded workflow artifacts as appropriate.
3. Check Settings > Actions > General for repository artifact/log
   retention; a short default (e.g. 7 days) is recommended.
4. Check account Settings > Billing > Budgets. An Actions budget with
   stop-usage controls can prevent unwanted spending but may stop
   billable runs or uploads.
5. Review storage usage again after expiry/cleanup. No account billing
   controls or existing artifact deletions are performed by this PR.

## Validation and known limits

A repository CI-only PR still runs the repository's global PR
acceptance suites. All modified workflow YAML must be accepted by
GitHub Actions before merge. This change does not modify Android code,
academic data, Tutor, Library, or Learning Studio behavior.

Important: the default branch was **unprotected** on inspection.
Enable branch protection or a ruleset with required architecture and
web checks once their exact check names are confirmed. Until then,
do not merge a PR without reading its actual checks.
