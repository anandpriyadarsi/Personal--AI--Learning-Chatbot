"""Run a disposable Assessment Studio fixture, never the production database.

From the repository root:
    python scripts/assessment_live_acceptance.py
Use --live-helper to exercise the existing configured provider deliberately.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))


def build_fixture(directory, *, exam=False, live_helper=False):
    from test_assessment_studio_phase_c import _app, _database, _service
    from personal_learning_assistant.domain.tutor_models import TutorProviderResponse
    from flask import abort, request

    path = _database(directory)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE assessment_runtime_specs SET mode=?, duration_minutes=180", ("exam" if exam else "practice",))
        db.execute("UPDATE courses SET code='UC100N', name='Data Science and AI'")
        db.execute("UPDATE assessments SET title='Disposable DSAI acceptance fixture'")
        db.execute("UPDATE questions SET question_text='Practice task: select one synthetic response and test navigation.' WHERE id='q-mcq'")
    clock = lambda: datetime.now(timezone.utc)
    sid = _service(path, clock).start("assessment-1", confirmed=True)["session_id"]
    app = _app(path, clock)

    class DemoProvider:
        def complete(self, request):
            return TutorProviderResponse(
                "DEMO RESPONSE — no AI request was sent.\n"
                "Try pd.Series([1, 4, 7]) > 3. Predict the Boolean result, then filter the values.\n"
                "Explain why the mask and the data must align. Rebuild the operation without copying.\n"
                "Use --live-helper when you want to test your configured provider.",
                "acceptance-demo", "offline",
            )
    if not live_helper:
        app.config["CODING_HELPER_PROVIDER_FACTORY"] = DemoProvider

    allowed = {
        "web.assessment_session", "web.assessment_session_autosave",
        "web.assessment_session_heartbeat", "web.assessment_session_question_action",
        "web.assessment_session_submit", "web.assessment_session_summary",
        "assessment_tools.coding_helper", "static",
    }

    @app.before_request
    def fixture_only():
        if request.endpoint not in allowed:
            abort(404)
        if request.view_args and request.view_args.get("session_id", sid) != sid:
            abort(404)

    return app, sid, path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=5057)
    parser.add_argument("--exam", action="store_true")
    parser.add_argument("--live-helper", action="store_true")
    args = parser.parse_args()
    with TemporaryDirectory(prefix="anvaya-assessment-acceptance-") as temporary:
        app, sid, _ = build_fixture(Path(temporary), exam=args.exam, live_helper=args.live_helper)
        print("Disposable test data only. Stop with Ctrl+C.")
        print(f"OPEN: http://127.0.0.1:{args.port}/assessments/sessions/{sid}", flush=True)
        app.run(host="127.0.0.1", port=args.port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
