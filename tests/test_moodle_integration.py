from __future__ import annotations

import sqlite3

from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations


class FakeMoodleClient:
    def site_info(self):
        return {"userid": 42, "sitename": "NITK Moodle"}

    def enrolled_courses(self, user_id):
        assert user_id == 42
        return (
            {
                "id": 10,
                "shortname": "MA103N",
                "fullname": "Linear Algebra",
            },
        )

    def course_contents(self, course_id):
        assert int(course_id) == 10
        return (
            {
                "id": 1,
                "name": "Week 1",
                "modules": (
                    {
                        "id": 100,
                        "name": "LU notes",
                        "contents": (
                            {
                                "type": "file",
                                "filename": "LU Factorization.md",
                                "fileurl": "https://moodle.example/pluginfile.php/1/lu.md",
                                "mimetype": "text/markdown",
                                "contenthash": "abc123",
                                "timemodified": 1790000000,
                            },
                        ),
                    },
                ),
            },
        )

    def download_file(self, file_url):
        assert file_url.startswith("https://moodle.example/")
        return b"# LU Factorization\n\nPA = LU and elimination multipliers.\n"


def _db(tmp_path):
    path = tmp_path / "moodle.db"
    apply_migrations(path)
    c = sqlite3.connect(path)
    c.execute(
        "INSERT INTO courses "
        "(id,code,name,status,description,created_at,updated_at,deleted_at) "
        "VALUES ('c-ma','MA103N','Linear Algebra','active','','x','x',NULL)"
    )
    c.commit()
    c.close()
    return path


def test_moodle_sync_downloads_registers_and_ingests_learning_file(tmp_path):
    from personal_learning_assistant.repositories.sqlite.moodle_sync_repository import (
        SQLiteMoodleSyncRepository,
    )
    from personal_learning_assistant.services.moodle_sync_service import (
        MoodleSyncService,
    )

    database = _db(tmp_path)
    root = tmp_path / "knowledge" / "moodle"
    service = MoodleSyncService(
        client=FakeMoodleClient(),
        repository=SQLiteMoodleSyncRepository(database),
        database_path=database,
        root_path=root,
    )

    preview = service.preview()
    assert preview["summary"]["new"] == 1
    assert preview["files"][0]["anvaya_course_id"] == "c-ma"

    result = service.sync()
    assert result["downloaded"] == 1
    assert result["ingestion"]["registered"] == 1
    assert result["ingestion"]["ingested"] == 1
    assert result["index_rebuild_required"] is True

    stored = root / "MA103N" / "LU notes" / "LU Factorization.md"
    assert stored.is_file()

    c = sqlite3.connect(database)
    assert c.execute(
        "SELECT status FROM moodle_sync_files"
    ).fetchone()[0] == "downloaded"
    assert c.execute(
        "SELECT COUNT(*) FROM knowledge_documents WHERE path_key LIKE 'moodle/%'"
    ).fetchone()[0] == 1
    assert c.execute(
        "SELECT COUNT(*) FROM knowledge_chunks"
    ).fetchone()[0] >= 1
    c.close()


def test_moodle_page_does_not_call_remote_on_get():
    from personal_learning_assistant.ui.web import create_app

    class FakeService:
        def status(self):
            return {
                "configured": False,
                "migration_ready": True,
                "root_path": "knowledge/moodle",
                "recent": (),
            }

        def preview(self):
            raise AssertionError("GET must not contact Moodle")

        def sync(self):
            raise AssertionError("GET must not contact Moodle")

    app = create_app(
        {
            "TESTING": True,
            "MOODLE_SYNC_SERVICE_FACTORY": lambda: FakeService(),
        }
    )
    response = app.test_client().get("/integrations/moodle")
    assert response.status_code == 200
    assert "Moodle" in response.get_data(as_text=True)
