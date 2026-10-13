# Disposable V1.2 trial

Create a separate checkout of `feature/learning-studio-v1-2`. Use Python 3.12, create a virtual environment, install `requirements-learning-studio.txt`, and run `python -m playwright install --with-deps chromium` once. Existing pinned dependency caches are safe; do not reuse production databases or fixtures.

These commands are equivalent in Ubuntu Bash and Windows PowerShell:

```text
python scripts/learning_studio_validate.py --scope feature --output learning-studio-evidence
python -m personal_learning_assistant.learning_studio.demo --directory fresh-v12-demo
```

Open the URL printed by the demo and `/learning`. Choose a fresh directory: the demo refuses user directories and marks its owned disposable root. Private improved pilot use adds `--pilot-zip recovered-private-pilot.zip --quality-pilot` (V2/new revision with twelve recall cards); never publish that input. The synthetic default has six clearly labelled courses with twelve lectures each, plus an unmapped module.

The validation command checks imports and actually launches Chromium before executing browser/feature tests. Browser absence is an error, not a skip. `--scope health` runs just this diagnosis; `--scope focused` runs authority/startup/Assessment regressions; `--scope all` also runs the verified V1.1 base and feature full suites sequentially and compares node IDs. Whole-suite baseline failures remain visible even when the regression delta passes.

Every invocation creates a uniquely named evidence directory containing health/exit status JSON, log paths, feature/focused JUnit and browser artifacts. Temporary test roots are owned and removed by that invocation. No routine manual Windows screenshot or quiz checklist is required. Public CI uses synthetic content; private-pilot Windows execution is a separately reported boundary.
