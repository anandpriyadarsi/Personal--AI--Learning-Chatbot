# Preservation and integration boundaries

Product changes are templates plus opt-in CSS/JavaScript. No routes, services, repositories, schema/migrations, assessment policies/scoring/answer projections, Tutor prompts/orchestration, Topic Intelligence, or production academic data are modified. app.css/app.js and all Planning/Analysis/Learning/Assessment/Tutor product templates remain unchanged from the integration base.

`base.html` adds extension points only. Native search, sidebar regrouping, focus controls and design tokens are enabled by workspace_base.html. The protected shell keeps its original form-free search markup. A separate real-browser gate covers Planning, Analysis, Assessment library + active runner, Learning library + published reader, and Tutor at 390/1366: controls remain usable, dark canvas, one main, no workspace assets or page overflow.

Existing Learning reader progress POST and Assessment sidecar behavior are not claimed to be write-free. The protected gate does not submit mutation actions; it explicitly permits the existing Learning progress endpoint. Source/read-only fingerprint assertions are made only for the listed disposable workspace flows, with JavaScript disabled where tracking would otherwise operate.

One inherited full-suite fixture defect was repaired in tests/test_planning_v21_wal_installed_launcher.py: config import-isolation tests can replace sys.modules['config'] while Assessment activation retains the earlier module reference. The backup test now patches that actual dependency too. The order-dependent failure was reproduced before repair and passed afterward; original backup count, integrity, foreign-key and course-preservation assertions remain. No protected product behavior changed.

Rollback: revert this feature PR's scoped template/style/control/test commits. There are no production migrations or data rollback steps. Reconcile any future base.html block edits explicitly; PR #20 owns its Learning files and has no overlapping product files with this branch. Evidence manifests contain synthetic fixture paths only.
