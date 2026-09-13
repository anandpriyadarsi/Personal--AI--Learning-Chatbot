import builtins
import importlib
import sys
import types

import pytest


OPTIONAL_ROOTS = {
    "requests",
    "fitz",
    "PIL",
    "dotenv",
}


def _fresh_vision_import(monkeypatch, blocked_packages=()):
    """
    Import vision_math_reader while selected optional packages
    are unavailable. Core import must remain safe.
    """
    sys.modules.pop("vision_math_reader", None)

    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        root_name = name.split(".", 1)[0]

        if root_name in blocked_packages:
            raise ModuleNotFoundError(
                f"blocked optional package: {root_name}"
            )

        return real_import(
            name,
            *args,
            **kwargs
        )

    monkeypatch.setattr(
        builtins,
        "__import__",
        guarded_import,
    )

    return importlib.import_module(
        "vision_math_reader"
    )


def test_vision_module_import_does_not_require_optional_packages(
    monkeypatch,
):
    module = _fresh_vision_import(
        monkeypatch,
        blocked_packages=OPTIONAL_ROOTS,
    )

    assert module._requests_module is None
    assert module._fitz_module is None
    assert module._image_class is None
    assert module._env_loaded is False


def test_vision_config_works_without_python_dotenv(
    monkeypatch,
):
    module = _fresh_vision_import(
        monkeypatch
    )

    monkeypatch.setenv(
        "VISION_API_URL",
        "https://example.invalid/vision",
    )
    monkeypatch.setenv(
        "VISION_API_KEY",
        "test-key",
    )
    monkeypatch.setenv(
        "VISION_MODEL",
        "test-vision-model",
    )

    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name.split(".", 1)[0] == "dotenv":
            raise ModuleNotFoundError(
                "blocked optional package: dotenv"
            )

        return real_import(
            name,
            *args,
            **kwargs
        )

    monkeypatch.setattr(
        builtins,
        "__import__",
        guarded_import,
    )

    config = module.vision_config()

    assert config == (
        "https://example.invalid/vision",
        "test-key",
        "test-vision-model",
    )
    assert module._env_loaded is True


def test_missing_requests_fails_only_when_vision_request_is_used(
    monkeypatch,
):
    module = _fresh_vision_import(
        monkeypatch
    )

    monkeypatch.setattr(
        module,
        "vision_config",
        lambda: (
            "https://example.invalid/vision",
            "test-key",
            "test-vision-model",
        ),
    )
    monkeypatch.setattr(
        module,
        "_resize_png_if_needed",
        lambda data: data,
    )

    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name.split(".", 1)[0] == "requests":
            raise ModuleNotFoundError(
                "blocked optional package: requests"
            )

        return real_import(
            name,
            *args,
            **kwargs
        )

    monkeypatch.setattr(
        builtins,
        "__import__",
        guarded_import,
    )
    module._requests_module = None

    with pytest.raises(
        module.VisionDependencyError,
        match="requires the 'requests' package",
    ):
        module.transcribe_image_bytes(
            b"fake-png"
        )


def test_missing_pymupdf_fails_only_when_pdf_rendering_is_used(
    monkeypatch,
):
    module = _fresh_vision_import(
        monkeypatch
    )

    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name.split(".", 1)[0] == "fitz":
            raise ModuleNotFoundError(
                "blocked optional package: fitz"
            )

        return real_import(
            name,
            *args,
            **kwargs
        )

    monkeypatch.setattr(
        builtins,
        "__import__",
        guarded_import,
    )
    module._fitz_module = None

    with pytest.raises(
        module.VisionDependencyError,
        match="PyMuPDF is required",
    ):
        module.render_pdf_page(
            "missing.pdf",
            1,
        )


def test_missing_pillow_keeps_original_png_bytes(
    monkeypatch,
):
    module = _fresh_vision_import(
        monkeypatch
    )

    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name.split(".", 1)[0] == "PIL":
            raise ModuleNotFoundError(
                "blocked optional package: PIL"
            )

        return real_import(
            name,
            *args,
            **kwargs
        )

    monkeypatch.setattr(
        builtins,
        "__import__",
        guarded_import,
    )
    module._image_class = None

    original = b"not-a-real-png"

    assert (
        module._resize_png_if_needed(original)
        == original
    )


def test_vision_http_provider_is_loaded_lazily_and_response_is_preserved(
    monkeypatch,
):
    module = _fresh_vision_import(
        monkeypatch
    )

    monkeypatch.setattr(
        module,
        "vision_config",
        lambda: (
            "https://example.invalid/vision",
            "test-key",
            "test-vision-model",
        ),
    )
    monkeypatch.setattr(
        module,
        "_resize_png_if_needed",
        lambda data: data,
    )

    calls = []

    class FakeTimeout(Exception):
        pass

    class FakeRequestException(Exception):
        pass

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": "x + y = 4"
                        }
                    }
                ]
            }

    fake_requests = types.ModuleType(
        "requests"
    )
    fake_requests.Timeout = FakeTimeout
    fake_requests.RequestException = (
        FakeRequestException
    )

    def fake_post(
        url,
        headers,
        json,
        timeout,
    ):
        calls.append({
            "url": url,
            "headers": headers,
            "json": json,
            "timeout": timeout,
        })
        return FakeResponse()

    fake_requests.post = fake_post

    monkeypatch.setitem(
        sys.modules,
        "requests",
        fake_requests,
    )
    module._requests_module = None

    result = module.transcribe_image_bytes(
        b"fake-png",
        page_label=1,
        timeout=30,
    )

    assert result == "x + y = 4"
    assert len(calls) == 1
    assert calls[0]["timeout"] == 30

    first = module._get_requests()
    second = module._get_requests()

    assert first is second
    assert first is fake_requests
