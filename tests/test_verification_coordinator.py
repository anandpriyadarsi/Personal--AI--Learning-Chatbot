"""Synthetic coverage, omission and fail-closed tests for four-stream coordination."""
import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verification_coordinator.py"
sys.path.insert(0, str(SCRIPT.parent))
spec = importlib.util.spec_from_file_location("verification_coordinator", SCRIPT)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def root(tmp_path):
    for name in set(sum((list(v) for v in module.BASE_SMOKES.values()), [])):
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("def test_ok(): pass\n", encoding="utf-8")
    p = tmp_path / "tests/js/assessment_runner.test.cjs"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("// synthetic\n", encoding="utf-8")
    return tmp_path


def test_each_stream_is_detected(tmp_path):
    cases = {
        "performance_reader": "personal_learning_assistant/ui/web/asset_cache.py",
        "handwritten_media": "personal_learning_assistant/services/notes_media_service.py",
        "native_documents": "personal_learning_assistant/services/native_document_extraction.py",
        "assessment_review": "personal_learning_assistant/services/assessment_execution_service.py",
    }
    for stream, path in cases.items():
        actual = module.plan([path], root(tmp_path))
        assert stream in actual["streams"]


def test_android_shared_bridge_selects_every_stream_and_android_acceptance(tmp_path):
    p = module.plan(["android/app/src/main/java/in/anvaya/privateapp/MainActivity.java"], root(tmp_path))
    assert set(p["streams"]) == set(module.STREAMS)
    assert p["requires_android_installed_acceptance"]
    assert p["requires_full_regression"]
    assert p["reasons"]


def test_feature_combination_unions_streams(tmp_path):
    p = module.plan(["personal_learning_assistant/services/notes_media_service.py",
                     "personal_learning_assistant/ui/web/native_library.py",
                     "personal_learning_assistant/services/assessment_package_service.py"], root(tmp_path))
    assert set(p["streams"]) == {"handwritten_media", "native_documents", "assessment_review"}


def test_shared_web_init_and_dependencies_require_full(tmp_path):
    for filename in ("personal_learning_assistant/ui/web/__init__.py", "requirements-learning-studio.txt"):
        p = module.plan([filename], root(tmp_path))
        assert set(p["streams"]) == set(module.STREAMS)
        assert p["reasons"]


def test_new_feature_tests_are_selected_when_present(tmp_path):
    r = root(tmp_path)
    f = r / "tests/test_native_document_library.py"
    f.write_text("def test_original(): pass\n")
    p = module.plan(["personal_learning_assistant/services/native_document_library.py"], r)
    assert "tests/test_native_document_library.py" in p["python_tests"]
    assert not p["javascript_tests"]


def test_changed_tests_never_silently_ignored(tmp_path):
    r = root(tmp_path)
    p = r / "tests/test_new_assessment_review.py"
    p.write_text("def test_new(): pass\n")
    result = module.plan(["tests/test_new_assessment_review.py"], r)
    assert "tests/test_new_assessment_review.py" in result["python_tests"]
    assert "tests/js/assessment_runner.test.cjs" in result["javascript_tests"]


def test_deleted_test_fails_closed(tmp_path):
    p = module.plan(["tests/test_native_document_library.py"], root(tmp_path))
    assert any("Deleted Python test" in reason for reason in p["reasons"])


def test_unclassified_source_is_cross_feature_not_silent_green(tmp_path):
    p = module.plan(["personal_learning_assistant/services/new_crosscutting_service.py"], root(tmp_path))
    assert set(p["streams"]) == set(module.STREAMS)
    assert p["reasons"]


def test_unmapped_config_fails_closed(tmp_path):
    p = module.plan(["custom_test_config.yaml"], root(tmp_path))
    assert p["requires_full_regression"]
    assert p["selector_requires_full"]


def test_docs_only_cannot_certify_release(tmp_path):
    p = module.plan(["docs/verification/readme.md"], root(tmp_path))
    assert p["streams"] == []
    assert p["python_tests"] == []
    assert p["requires_full_regression"]


def test_empty_input_has_explicit_reason(tmp_path):
    p = module.plan([], root(tmp_path))
    assert p["reasons"]
    assert p["requires_full_regression"]


def test_test_loss_requires_visible_missing_smoke(tmp_path):
    p = module.plan(["personal_learning_assistant/services/assessment_execution_service.py"], tmp_path)
    assert any("Missing required smoke" in reason for reason in p["reasons"])


def test_path_normalization(tmp_path):
    p = module.plan([r"personal_learning_assistant\\services\\notes_media_service.py"], root(tmp_path))
    assert "handwritten_media" in p["streams"]

def test_assessment_authoring_prompt_is_not_docs_only(tmp_path):
    p = module.plan(["ANVAYA_ASSESSMENT_PACKAGE_AUTHORING_PROMPT.md"], root(tmp_path))
    assert "assessment_review" in p["streams"]
    assert p["python_tests"]
    assert any("question-authoring policy" in reason for reason in p["reasons"])

