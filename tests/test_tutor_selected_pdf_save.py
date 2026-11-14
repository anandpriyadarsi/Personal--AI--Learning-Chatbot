"""Real local PDF-to-Tutor save journey without personal owners or cloud calls."""
from io import BytesIO
from contextlib import closing
import sqlite3

import fitz
from personal_learning_assistant.domain.tutor_models import TutorProviderResponse
from personal_learning_assistant.services.academic_agent_web_service import AcademicAgentWebService
from personal_learning_assistant.services.multimodal_evidence_service import MultimodalEvidenceService
from personal_learning_assistant.ui.web import create_app
from test_multimodal_jobs import owners
from test_multimodal_web import headers


def test_embedded_pdf_to_existing_tutor_saves_turn_and_snapshot_without_cloud(owners):
    lib, database = owners
    page_text = "Eigenvalues and Eigenvectors. A = [[2,0],[0,3]]."
    pdf = fitz.open()
    page = pdf.new_page(width=500, height=700)
    page.insert_text((40, 90), page_text)
    raw = pdf.tobytes()
    pdf.close()
    document = lib.upload(BytesIO(raw), "synthetic-eigenvalues.pdf")
    mm = MultimodalEvidenceService(lib)
    preview = mm.preview(document["id"], {"kind": "pdf_page", "page": 1}, method="local")
    mm.enqueue(document["id"], preview["token"])
    lib.run_pending()
    assert mm.status(document["id"])["state"] == "ready"
    seen = []
    class LocalOnlyProvider:
        local_only = True
        configured = True
        def complete(self, request):
            seen.append(request)
            return TutorProviderResponse("The matrix has eigenvalues 2 and 3 [S1].", "offline", "fake")

    web = AcademicAgentWebService(
        database_path=database,
        index_root=database.parent / "tutor_retrieval",
        provider_factory=LocalOnlyProvider,
        course_catalogue_loader=lambda: {"courses": []},
    )
    app = create_app({
        "TESTING": True, "NATIVE_LIBRARY_SERVICE": lib,
        "ACADEMIC_AGENT_WEB_SERVICE_FACTORY": lambda: web,
        "NATIVE_LIBRARY_CATALOGUE_FACTORY": lambda: {"available": True, "courses": []},
    })
    client = app.test_client()
    handoff = client.post(
        "/library/files/" + document["id"] + "/multimodal/ask",
        json={"locator": {"kind": "pdf_page", "page": 1}},
        headers=headers(app),
    )
    assert handoff.status_code == 201, handoff.get_data(as_text=True)[:300]
    url = handoff.json["url"]
    assert client.get(url).status_code == 200
    posted = client.post(
        url + "/ask",
        data={
            "csrf_token": app.extensions["tutor_action_csrf"],
            "question": "Explain the selected evidence.",
            "request_id": "synthetic_pdf_save_request_0001",
        },
    )
    assert posted.status_code == 303, posted.get_data(as_text=True)[:500]
    with closing(sqlite3.connect(database)) as con:
        assert con.execute("SELECT count(*) FROM tutor_turns").fetchone()[0] == 2
        assert con.execute("SELECT count(*) FROM tutor_evidence_snapshots").fetchone()[0] >= 1
    assert len(seen) <= 1
    assert lib.original(document["id"]).read_bytes() == raw
