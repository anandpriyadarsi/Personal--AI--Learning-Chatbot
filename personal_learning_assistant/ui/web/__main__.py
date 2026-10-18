"""Run the Phase 7.5 local web interface with ``python phase7_web.py``.

Only this explicit launcher activates Assessment migrations or the installed
academic WAL snapshot publisher. Imports and generic create_app() remain inert.
"""
from __future__ import annotations

import os

from . import create_app


def prepare_local_app(*, assessment_enabled=None, database_path=None):
    """Build local ANVAYA with its trusted WAL publication owner (if eligible).

    The Assessment activation step remains backup-first and runs before the
    publisher. All WAL snapshots are RAM-only and owned by a local worker;
    no Analysis/Planning GET opens the live SQLite WAL or shared-memory files.
    """
    import config as installed_config
    from personal_learning_assistant.services.academic_wal_installation import (
        InstalledAcademicWalPublisher, InstalledWalPublisherError,
    )

    enabled = (os.environ.get("ANVAYA_ASSESSMENT_EXTENDED", "true").strip().lower() == "true"
               if assessment_enabled is None else bool(assessment_enabled))
    database = database_path if database_path is not None else installed_config.DATABASE_PATH
    if enabled:
        from personal_learning_assistant.services.assessment_activation import (
            activate_assessment_extension,
        )
        status = activate_assessment_extension(database_path=database)
        print("Assessment Studio practice: enabled (migration 0015 verified).", flush=True)
        if status["backup"]:
            print("Pre-migration database backup:", status["backup"], flush=True)

    publication = None
    config = {"ASSESSMENT_EXTENDED_ENABLED": enabled}
    # The publisher has explicitly authorized read-only access in a worker
    # thread. Ordinary app factories and HTTP handlers never start it.
    candidate = InstalledAcademicWalPublisher(database)
    try:
        state = candidate.start()
    except InstalledWalPublisherError:
        print("Academic WAL overview: no trusted WAL publisher needed/available.", flush=True)
    else:
        publication = candidate
        config["ACADEMIC_WAL_SNAPSHOT_PROVIDER"] = publication.feed.latest
        config["ACADEMIC_WAL_SNAPSHOT_MAX_AGE"] = 120
        print(
            "Academic WAL overview: " +
            ("connected to committed local snapshots." if state.has_snapshot
             else "waiting for a valid committed local snapshot."),
            flush=True,
        )
    try:
        app = create_app(config)
        if publication is not None:
            app.extensions["academic_wal_publisher"] = publication
        return app, publication
    except Exception:
        if publication is not None:
            publication.stop()
        raise


def main() -> None:
    """Start the normal local ANVAYA server on loopback only."""
    port = int(os.environ.get("PLA_WEB_PORT", "5000"))
    app, publication = prepare_local_app()
    try:
        app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
    finally:
        if publication is not None:
            publication.stop()


if __name__ == "__main__":
    main()
