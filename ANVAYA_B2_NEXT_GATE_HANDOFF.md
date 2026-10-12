# ANVAYA after Gate B2

Starting source: B1 `6d2c3a01d6deca5b64bfc19ce2041769a8b00929`. Dedicated branch: `anvaya/topic-intelligence-b2-read-safety`. Recover from GitHub at the exact final tested SHA in the evidence handoff; never apply old patches over that branch or mix equivalent patch/bundle inputs.

| Gate | Boundary |
|---|---|
| GATE_A_DEV_AUTOMATED | B1 verified PASS; B2 exact-source CI must be observed before delivery |
| B1_SOURCE_ONLY_IMPLEMENTATION | PASS, unchanged closed-snapshot evidence adapter and45 regressions |
| B2_SOURCE_ONLY_READ_SAFETY | Local1861/43/all15 PASS; independent169 PASS; hosted acceptance pending publication |
| GATE_A_LOCAL_PRODUCTION_AUTHORITY | BLOCKED: installed launcher/interpreter/backend/schema/projection lineage absent |
| ASSESSMENT_PAUSE_RESUME_DESIGN | PASS, full existing design retained; AP1/AP2 implementation not done |
| ASSESSMENT_PAPER_SUBJECTIVE_DESIGN | PASS, full existing design retained; PS1/PS2 implementation not done |
| Full Gate B | BLOCKED on attribution/writer/projection authority; no migration number guessed |
| NEXT_SAFE_IMPLEMENTATION_GATE | DEV READY for prerequisite collection/specification; Gate C implementation remains BLOCKED until full B evidence contracts and separate authorization |

Next independent prerequisite: identify actual installed Windows launcher/checkout/interpreter and review closed stable schema/ledger, canonical IDs, normalized/projection parity and freshness. This cannot be established from synthetic fixture migrations or a count of projection keys. The user must not run hours of manual regression; hosted Ubuntu/Windows is development authority.

The tracked `ANVAYA_RESUME_WINDOWS_HANDOFF.md` and `scripts/architecture_local_collector.py` retain the one-command redacted collector procedure. Default collection does not open/copy a DB. Use the actual launcher interpreter and installed checkout:

```powershell
& $LivePython $Collector --repo $InstalledRepo --output (Join-Path $env:TEMP ('ANVAYA-local-authority-' + [guid]::NewGuid().ToString('N') + '.json'))
```

Only use --closed-no-writers after all app/backup/sync writers are actually closed. Its private stable copy is checked read-only and deleted locally. Share only redacted JSON, never DB/vault/secrets/private source/paths. Collector output alone does not prove normalized/projection freshness or parity.

Later order remains B attribution/writer/projection contracts → C pure deterministic recovery policy → D truthful read-only Analysis2.0 → E canonical Planning2.0 allocator and explicit preview/acceptance → F bounded end-to-end/local acceptance → Tutor compatibility. B2 does not unlock a migration or production rollout. No C/D/E implementation was done here.

AP1/AP2 pause/resume remain separate feature branches after execution lineage is verified: server active-time clock, transactional save-drain/idempotency, restart and race tests. PS1/PS2 paper self-grading depend on typed self-report provenance plus lineage: versioned rubric/marks/reveal history and no independent recovery qualification or official grade overwrite. Preserve the full `ANVAYA_ASSESSMENT_PAUSE_OFFLINE_SUBJECTIVE_SPEC.md`; no redesign or implementation is required in B2. Coding Helper and Assessment behavior remain compatible.

Continue only from this branch's actual final acceptance report. Do not merge main, deploy, alter production records or merge old Tutor/Library/Learning Studio branches. Missing attachments cannot block recovery: essential reports and source are committed on GitHub.
