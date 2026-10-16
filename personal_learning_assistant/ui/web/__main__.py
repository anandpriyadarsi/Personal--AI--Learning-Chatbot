"""Run the Phase 7.5 local web interface with ``python -m``."""

from __future__ import annotations

import os

from . import create_app


def main() -> None:
    """Start the development server on loopback only."""
    port = int(os.environ.get("PLA_WEB_PORT", "5000"))
    # The normal `python phase7_web.py` launcher enables new private practice
    # by default. Tests/imports and explicit create_app() remain side-effect
    # free. Set ANVAYA_ASSESSMENT_EXTENDED=false to run the legacy UI instead.
    enabled = os.environ.get("ANVAYA_ASSESSMENT_EXTENDED", "true").strip().lower() == "true"
    if enabled:
        from personal_learning_assistant.services.assessment_activation import activate_assessment_extension
        status = activate_assessment_extension()
        print("Assessment Studio practice: enabled (migration 0015 verified).", flush=True)
        if status["backup"]:
            print("Pre-migration database backup:", status["backup"], flush=True)
    app = create_app({"ASSESSMENT_EXTENDED_ENABLED": enabled})
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    main()
