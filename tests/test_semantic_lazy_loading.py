import builtins
import importlib
import sys
import types

import pytest


def _fresh_semantic_import(monkeypatch, blocked_packages=()):
    """
    Import semantic_retrieval while making selected optional packages
    unavailable. This verifies that importing the module itself does
    not require or initialize the semantic provider.
    """
    sys.modules.pop("semantic_retrieval", None)

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
        "semantic_retrieval"
    )


def test_semantic_module_import_does_not_require_fastembed_or_numpy(
    monkeypatch,
):
    module = _fresh_semantic_import(
        monkeypatch,
        blocked_packages={
            "fastembed",
            "numpy",
        },
    )

    assert module.embedding_model is None
    assert module._numpy_module is None


def test_embedding_model_is_created_lazily_and_reused(monkeypatch):
    module = _fresh_semantic_import(
        monkeypatch
    )

    created_models = []

    class FakeTextEmbedding:
        def __init__(self, model_name):
            self.model_name = model_name
            created_models.append(self)

    fake_fastembed = types.ModuleType(
        "fastembed"
    )
    fake_fastembed.TextEmbedding = (
        FakeTextEmbedding
    )

    monkeypatch.setitem(
        sys.modules,
        "fastembed",
        fake_fastembed,
    )

    module.embedding_model = None

    first = module.get_embedding_model()
    second = module.get_embedding_model()

    assert first is second
    assert len(created_models) == 1
    assert (
        created_models[0].model_name
        == module.MODEL_NAME
    )


def test_missing_fastembed_fails_only_when_semantic_feature_is_used(
    monkeypatch,
):
    module = _fresh_semantic_import(
        monkeypatch
    )
    module.embedding_model = None

    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name.split(".", 1)[0] == "fastembed":
            raise ModuleNotFoundError(
                "blocked optional package: fastembed"
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
        RuntimeError,
        match="requires FastEmbed",
    ):
        module.get_embedding_model()
