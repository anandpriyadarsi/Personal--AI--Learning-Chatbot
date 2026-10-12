# ANVAYA after Gate B2

Starting source: B1 `6d2c3a01d6deca5b64bfc19ce2041769a8b00929`. Dedicated branch: `anvaya/topic-intelligence-b2-read-safety`. Recover from GitHub at the exact final tested SHA in the evidence handoff; never apply old patches over that branch or mix equivalent patch/bundle inputs.

Reviewed implementation `ce2a770d9358fad1e00b0032436a8f3f46da7ac6` passed [run38286115666](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/actions/runs/38286115666) on Ubuntu and Windows plus aggregate: full1863, focused54, fixture orders41 each, characterization17, Chromium43, Node20; all15 categories and zero failures/errors/skips. Both source records are clean. The evidence-only report successor changes these three Markdown reports; its exact final SHA/run is independently verified before delivery and recorded in the archive. Missing attachments remain recoverable from this branch and its matching Actions acceptance. Main stays `f859a3c7cdf44baadc17d9bd1a6c656530c1b5bf`, unmerged.

| Gate | Boundary |
|---|---|
| GATE_A_DEV_AUTOMATED | PASS at reviewed B2 implementation SHA on Ubuntu/Windows and aggregate |
| B1_SOURCE_ONLY_IMPLEMENTATION | PASS, unchanged closed-snapshot evidence adapter and45 regressions |
| B2_SOURCE_ONLY_READ_SAFETY | PASS: local/hosted1863/43/all15; independent whole-delta169 and correction68 PASS |
| GATE_A_LOCAL_PRODUCTION_AUTHORITY | BLOCKED: installed launcher/interpreter/backend/schema/projection lineage absent |
| ASSESSMENT_PAUSE_RESUME_DESIGN | PASS, full existing design retained; AP1/AP2 implementation not done |
| ASSESSMENT_PAPER_SUBJECTIVE_DESIGN | PASS, full existing design retained; PS1/PS2 implementation not done |
| Full Gate B | BLOCKED on attribution/writer/projection authority; no migration number guessed |
| NEXT_SAFE_WORK | DEV READY for read-only authority collection/specification; genuine installed evidence is still required before dependent implementation |
| NEXT_SAFE_IMPLEMENTATION_GATE | BLOCKED: remaining B contracts require verified installed lineage; Gate C additionally requires completed B contracts and separate authorization |

Next independent prerequisite: identify actual installed Windows launcher/checkout/interpreter and review closed stable schema/ledger, canonical IDs, normalized/projection parity and freshness. This cannot be established from synthetic fixture migrations or a count of projection keys. The user must not run hours of manual regression; hosted Ubuntu/Windows is development authority.

The tracked `ANVAYA_RESUME_WINDOWS_HANDOFF.md` and `scripts/architecture_local_collector.py` retain the one-command redacted collector procedure. Default collection does not open/copy a DB. Use the actual launcher interpreter and installed checkout:

```powershell
& $LivePython $Collector --repo $InstalledRepo --output (Join-Path $env:TEMP ('ANVAYA-local-authority-' + [guid]::NewGuid().ToString('N') + '.json'))
```

Only use --closed-no-writers after all app/backup/sync writers are actually closed. Its private stable copy is checked read-only and deleted locally. Share only redacted JSON, never DB/vault/secrets/private source/paths. Collector output alone does not prove normalized/projection freshness or parity.

Later order remains B attribution/writer/projection contracts → C pure deterministic recovery policy → D truthful read-only Analysis2.0 → E canonical Planning2.0 allocator and explicit preview/acceptance → F bounded end-to-end/local acceptance → Tutor compatibility. B2 does not unlock a migration or production rollout. No C/D/E implementation was done here.

AP1/AP2 pause/resume remain separate feature branches after execution lineage is verified: server active-time clock, transactional save-drain/idempotency, restart and race tests. PS1/PS2 paper self-grading depend on typed self-report provenance plus lineage: versioned rubric/marks/reveal history and no independent recovery qualification or official grade overwrite. Preserve the full `ANVAYA_ASSESSMENT_PAUSE_OFFLINE_SUBJECTIVE_SPEC.md`; no redesign or implementation is required in B2. Coding Helper and Assessment behavior remain compatible.

Continue only from this branch's actual final acceptance report. Do not merge main, deploy, alter production records or merge old Tutor/Library/Learning Studio branches. Missing attachments cannot block recovery: essential reports and source are committed on GitHub.

CI resource follow-up: the first report-only tip5509380's Windows full suite timed out at900s; Ubuntu and all other Windows categories passed, aggregate FAIL. Generous finite deadlines now permit full1800s, two probe subprocesses300s and job45min, with other categories900s and unchanged correctness gates. Two additional real-process harness regressions make the full suite1865. New exact-source acceptance must be verified before final delivery; this follow-up does not change production/B/C/Assessment gate dependencies.
