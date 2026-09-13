import builtins
import importlib
import os
import sys
import types

import pytest


def _fresh_rag_import(monkeypatch, block_requests=False):
    """
    Import rag_answer while optionally making requests unavailable.
    Importing the RAG module itself must not require the HTTP client.
    """
    sys.modules.pop("rag_answer", None)

    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if (
            block_requests
            and name.split(".", 1)[0] == "requests"
        ):
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

    return importlib.import_module(
        "rag_answer"
    )


def test_rag_module_import_does_not_require_requests(monkeypatch):
    module = _fresh_rag_import(
        monkeypatch,
        block_requests=True,
    )

    assert module._requests_module is None
    assert hasattr(module, "call_llm")


def test_unconfigured_llm_does_not_load_requests(monkeypatch):
    module = _fresh_rag_import(
        monkeypatch
    )

    # Do not depend on the developer/user's real .env file.
    # rag_answer.load_local_env() may legitimately repopulate
    # LLM_* values from BASE_DIR/.env, so force the configuration
    # boundary itself to represent "not configured".
    monkeypatch.setattr(
        module,
        "get_llm_config",
        lambda: ("", "", ""),
    )

    module._requests_module = None

    with pytest.raises(
        RuntimeError,
        match="LLM is not configured",
    ):
        module.call_llm(
            [{"role": "user", "content": "Hello"}]
        )

    assert module._requests_module is None


def test_missing_requests_fails_only_when_answer_generation_is_used(
    monkeypatch,
):
    module = _fresh_rag_import(
        monkeypatch
    )

    monkeypatch.setenv(
        "LLM_API_URL",
        "https://example.invalid/chat",
    )
    monkeypatch.setenv(
        "LLM_API_KEY",
        "test-key",
    )
    monkeypatch.setenv(
        "LLM_MODEL",
        "test-model",
    )

    module._requests_module = None

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

    with pytest.raises(
        module.LLMDependencyError,
        match="requires the 'requests' package",
    ):
        module.call_llm(
            [{"role": "user", "content": "Hello"}]
        )


def test_requests_is_loaded_lazily_and_successful_response_is_preserved(
    monkeypatch,
):
    module = _fresh_rag_import(
        monkeypatch
    )

    monkeypatch.setenv(
        "LLM_API_URL",
        "https://example.invalid/chat",
    )
    monkeypatch.setenv(
        "LLM_API_KEY",
        "test-key",
    )
    monkeypatch.setenv(
        "LLM_MODEL",
        "test-model",
    )

    calls = []

    class FakeTimeout(Exception):
        pass

    class FakeRequestException(Exception):
        pass

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": "Grounded test answer"
                        }
                    }
                ]
            }

    fake_requests = types.ModuleType("requests")
    fake_requests.Timeout = FakeTimeout
    fake_requests.RequestException = FakeRequestException

    def fake_post(url, headers, json, timeout):
        calls.append(
            {
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            }
        )
        return FakeResponse()

    fake_requests.post = fake_post

    monkeypatch.setitem(
        sys.modules,
        "requests",
        fake_requests,
    )
    module._requests_module = None

    answer = module.call_llm(
        [{"role": "user", "content": "Hello"}]
    )

    assert answer == "Grounded test answer"
    assert len(calls) == 1
    assert calls[0]["timeout"] == 90

    first_module = module._get_requests()
    second_module = module._get_requests()

    assert first_module is second_module
    assert first_module is fake_requests


def test_timeout_is_wrapped_in_rag_specific_error(monkeypatch):
    module = _fresh_rag_import(
        monkeypatch
    )

    monkeypatch.setenv(
        "LLM_API_URL",
        "https://example.invalid/chat",
    )
    monkeypatch.setenv(
        "LLM_API_KEY",
        "test-key",
    )
    monkeypatch.setenv(
        "LLM_MODEL",
        "test-model",
    )

    class FakeTimeout(Exception):
        pass

    class FakeRequestException(Exception):
        pass

    fake_requests = types.SimpleNamespace(
        Timeout=FakeTimeout,
        RequestException=FakeRequestException,
    )

    def fake_post(*args, **kwargs):
        raise FakeTimeout("slow provider")

    fake_requests.post = fake_post
    module._requests_module = fake_requests

    with pytest.raises(
        module.LLMTimeoutError,
        match="timed out",
    ):
        module.call_llm(
            [{"role": "user", "content": "Hello"}]
        )
