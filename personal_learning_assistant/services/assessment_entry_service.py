"""Storage boundary for paper admission before the web runner starts an attempt."""
from contextlib import closing
import sqlite3

from personal_learning_assistant.services.assessment_paper_admission import inspect_paper_import
from personal_learning_assistant.services.assessment_runner_service import AssessmentRunnerValidationError

AssessmentStorageError = sqlite3.Error


def inspect_existing_paper(database, assessment_id):
    if not database.is_file() or database.is_symlink():
        raise AssessmentRunnerValidationError('Practice database unavailable.')
    with closing(sqlite3.connect(database.resolve().as_uri()+'?mode=ro', uri=True)) as readonly:
        readonly.execute('PRAGMA query_only=ON')
        readonly.execute('BEGIN')
        admission = inspect_paper_import(readonly, assessment_id)
        readonly.rollback()
    return admission
