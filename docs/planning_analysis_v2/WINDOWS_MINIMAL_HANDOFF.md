# Windows minimal handoff

No mandatory duplicate manual regression suite. GitHub Actions runs the real Windows interpreter, full pytest, Chromium suites, Node, compile, focused integrations, architecture fixtures and migration integrity on the exact pushed source. CI status and exceptions are recorded in CROSS_PLATFORM_ACCEPTANCE.md.

Optional installed-only checks require separate local authority: confirm the intended database path, schema lineage and current data-owner approvals without copying secrets or private DBs into CI; open /analysis and /planning on that installation. Expect strict evidence-unavailable for WAL storage in this branch. Do not change journal mode to bypass the gate. Do not run migrations, reset records, seed data or overwrite an authority file.

To reproduce synthetic automation in an isolated checkout:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-learning-studio.txt
.venv\Scripts\python scripts/architecture_checkout_eol.py --repo .
.venv\Scripts\python -m playwright install chromium
.venv\Scripts\python scripts/architecture_validation.py --require-clean --output C:\Temp\anvaya-planning-validation
```

Use a new or validator-owned output directory outside the checkout. The validator exports tracked source to a disposable tree and strips provider credentials; never point it at an installed production working directory. Four external Learning pilot assets are absent; exact IDs remain visible, not suppressed. Production eligibility stays blocked independently of a green synthetic regression result.
