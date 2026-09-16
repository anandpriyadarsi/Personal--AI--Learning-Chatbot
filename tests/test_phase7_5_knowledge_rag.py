from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace


def _hit(**overrides):
    values = {
        "chunk_id": "chunk-1",
        "document_id": "doc-1",
        "text": "LU factorization writes a matrix as a product of lower and upper triangular matrices.",
        "score": 0.0327,
        "lexical_rank": 1,
        "semantic_rank": 2,
        "page_number": 14,
        "locator": {
            "topic": "LU Factorization",
            "lecture_number": "4",
            "lecture_title": "Factorization into A = LU",
            "source_url": "https://example.edu/lecture4",
            "source": {"provider": "MIT OCW", "kind": "lecture"},
        },
        "resource_ids": ("resource-1",),
        "course_ids": ("ma103n",),
        "topic_ids": ("lu",),
        "providers": ("MIT OCW",),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_build_knowledge_dashboard_exposes_read_only_index_status():
    from personal_learning_assistant.services.knowledge_dashboard_service import build_knowledge_dashboard
    dashboard = build_knowledge_dashboard({
        "generation_id": "gen-20260917",
        "chunk_count": 128,
        "document_count": 12,
        "lexical_backend": "fts5",
        "semantic_enabled": True,
        "embedding_model": "BAAI/bge-small-en-v1.5",
        "embedding_version": "fastembed-0.8.0",
    }, query="")
    assert dashboard["available"] is True
    assert dashboard["query"] == ""
    assert dashboard["searched"] is False
    assert dashboard["index"]["generation_id"] == "gen-20260917"
    assert dashboard["index"]["chunk_count"] == 128
    assert dashboard["index"]["document_count"] == 12
    assert dashboard["index"]["semantic_enabled"] is True
    assert dashboard["results"] == []
    assert dashboard["context"]["source_count"] == 0


def test_build_knowledge_dashboard_normalizes_hits_and_rag_context():
    from personal_learning_assistant.services.knowledge_dashboard_service import build_knowledge_dashboard
    context = SimpleNamespace(source_count=1,total_characters=321,context_text="[S1 | MIT L4 | p.14 | LU Factorization]\nsource evidence")
    dashboard = build_knowledge_dashboard({"generation_id":"gen-1","chunk_count":5,"semantic_enabled":True}, query="  LU factorization  ", hits=(_hit(),), context=context)
    assert dashboard["searched"] is True
    assert dashboard["query"] == "LU factorization"
    assert dashboard["summary"]["result_count"] == 1
    item = dashboard["results"][0]
    assert item["document_id"] == "doc-1"
    assert item["page_number"] == 14
    assert item["topic"] == "LU Factorization"
    assert item["lecture_number"] == "4"
    assert item["lecture_title"] == "Factorization into A = LU"
    assert item["provider"] == "MIT OCW"
    assert item["source_kind"] == "lecture"
    assert item["source_url"] == "https://example.edu/lecture4"
    assert item["course_ids"] == ["ma103n"]
    assert item["lexical_rank"] == 1
    assert item["semantic_rank"] == 2
    assert item["score_label"] == "0.032700"
    assert "lower and upper triangular" in item["text"]
    assert dashboard["context"]["source_count"] == 1
    assert dashboard["context"]["total_characters"] == 321
    assert "source evidence" in dashboard["context"]["text"]


def test_long_result_text_is_bounded_for_browser_rendering():
    from personal_learning_assistant.services.knowledge_dashboard_service import build_knowledge_dashboard
    dashboard = build_knowledge_dashboard({"generation_id":"g"}, query="rank", hits=(_hit(text="x"*3000),))
    assert len(dashboard["results"][0]["text"]) <= 1201
    assert dashboard["results"][0]["text"].endswith("…")


def test_unavailable_knowledge_dashboard_is_safe_and_preserves_query():
    from personal_learning_assistant.services.knowledge_dashboard_service import unavailable_knowledge_dashboard
    dashboard = unavailable_knowledge_dashboard("rank of a matrix")
    assert dashboard["available"] is False
    assert dashboard["query"] == "rank of a matrix"
    assert dashboard["results"] == []
    assert "not changed" in dashboard["message"].lower()
    assert dashboard["context"]["text"] == ""


def test_knowledge_service_source_has_no_index_build_or_llm_calls():
    root = Path(__file__).resolve().parents[1]
    source = (root / "personal_learning_assistant/services/knowledge_dashboard_service.py").read_text(encoding="utf-8")
    for forbidden in ("build_and_save_index(","build_index(","IndexBuilder(","save_semantic_index(","call_llm(","rag_answer(","record_activity(",".write_text("):
        assert forbidden not in source


def test_routes_source_declares_get_only_knowledge_endpoint():
    root = Path(__file__).resolve().parents[1]
    source = (root / "personal_learning_assistant/ui/web/routes.py").read_text(encoding="utf-8")
    assert '@web_blueprint.get("/knowledge")' in source
    assert 'render_template("knowledge.html"' in source
    assert "KNOWLEDGE_DASHBOARD_PROVIDER" in source
    assert 'request.args.get("q"' in source
    assert '@web_blueprint.post("/knowledge")' not in source


def test_base_navigation_exposes_knowledge_as_real_link():
    root = Path(__file__).resolve().parents[1]
    source = (root / "personal_learning_assistant/ui/web/templates/base.html").read_text(encoding="utf-8")
    assert "url_for('web.knowledge')" in source
    assert "active_page == 'knowledge'" in source
    assert '<span class="nav-item is-disabled" aria-disabled="true">Knowledge</span>' not in source


def _dashboard_fixture(query=""):
    from personal_learning_assistant.services.knowledge_dashboard_service import build_knowledge_dashboard
    context = None
    hits = ()
    if query:
        hits = (_hit(),)
        context = SimpleNamespace(source_count=1,total_characters=42,context_text="[S1] grounded context")
    return build_knowledge_dashboard({
        "generation_id":"gen-web","chunk_count":25,"document_count":4,"lexical_backend":"fts5","semantic_enabled":True,
        "embedding_model":"BAAI/bge-small-en-v1.5","embedding_version":"fastembed-0.8.0",
    }, query=query, hits=hits, context=context)


def _web_app(provider):
    from personal_learning_assistant.ui.web import create_app
    return create_app({"TESTING":True,"KNOWLEDGE_DASHBOARD_PROVIDER":provider})


def test_knowledge_page_renders_index_status_without_query():
    response = _web_app(_dashboard_fixture).test_client().get("/knowledge")
    text = response.get_data(as_text=True)
    assert response.status_code == 200
    for expected in ("Knowledge base &amp; RAG","gen-web","25","4","Semantic enabled","Search your indexed academic sources"):
        assert expected in text
    assert 'method="get"' in text.lower()
    assert 'href="/knowledge"' in text


def test_knowledge_query_renders_grounded_sources_and_context_summary():
    response = _web_app(_dashboard_fixture).test_client().get("/knowledge?q=LU+factorization")
    text = response.get_data(as_text=True)
    assert response.status_code == 200
    for expected in ("LU factorization","LU Factorization","MIT OCW","page 14","Lexical #1","Semantic #2","1 source","grounded context"):
        assert expected in text
    assert "AI-generated answer" not in text


def test_knowledge_provider_failure_degrades_without_leaking_exception_content():
    def failing_provider(query=""):
        raise RuntimeError("SECRET-RETRIEVAL-DETAIL")
    response = _web_app(failing_provider).test_client().get("/knowledge?q=rank")
    text = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Knowledge base is temporarily unavailable" in text
    assert "academic data and retrieval index were not changed" in text
    assert "SECRET-RETRIEVAL-DETAIL" not in text


def test_knowledge_remains_get_only_in_phase758():
    assert _web_app(_dashboard_fixture).test_client().post("/knowledge").status_code == 405


def test_web_app_creation_keeps_retrieval_and_embedding_engines_lazy(tmp_path):
    import os, subprocess, sys
    root = Path(__file__).resolve().parents[1]
    script = r'''
import sys
from personal_learning_assistant.ui.web import create_app
create_app({"TESTING": True})
for name in (
    "personal_learning_assistant.retrieval.index_store",
    "personal_learning_assistant.retrieval.hybrid",
    "personal_learning_assistant.retrieval.embedding",
    "personal_learning_assistant.retrieval.rag_context",
    "semantic_retrieval",
    "hybrid_retrieval",
    "rag_answer",
):
    assert name not in sys.modules, name
'''
    result = subprocess.run([sys.executable,"-c",script],cwd=tmp_path,env={**os.environ,"PYTHONPATH":str(root)},text=True,capture_output=True)
    assert result.returncode == 0, result.stderr
    assert list(tmp_path.iterdir()) == []
