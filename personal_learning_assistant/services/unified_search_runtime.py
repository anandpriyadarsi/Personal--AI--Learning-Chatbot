"""Application-scoped retrieval runtime with stale-index protection."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
import sqlite3
from urllib.parse import quote


class UnifiedSearchRuntimeError(RuntimeError):
    pass


class UnifiedSearchStaleIndexError(UnifiedSearchRuntimeError):
    pass


class UnifiedSearchRuntime:
    def __init__(
        self,
        *,
        database_path="data/learning_assistant.db",
        index_root=".phase5_retrieval",
        embedding_provider_factory=None,
    ):
        self.database_path = Path(database_path)
        self.index_root = Path(index_root)
        self._embedding_provider_factory = embedding_provider_factory
        self._store = None
        self._service = None
        self._generation = None
        self._provider = None

    def _current_pointer_generation(self):
        pointer = self.index_root / "current.json"
        if not pointer.is_file():
            return ""
        import json
        try:
            return str(json.loads(pointer.read_text(encoding="utf-8"))["generation_id"])
        except Exception as error:
            raise UnifiedSearchRuntimeError("retrieval pointer is invalid") from error

    def _open_ro_database(self):
        if not self.database_path.is_file() or self.database_path.is_symlink():
            raise UnifiedSearchRuntimeError("academic database is unavailable")
        uri = "file:{}?mode=ro".format(
            quote(str(self.database_path.resolve()).replace("\\", "/"), safe="/:")
        )
        con = sqlite3.connect(uri, uri=True, timeout=5.0)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        return con

    def _source_fingerprint(self):
        module = import_module(
            "personal_learning_assistant.repositories.sqlite.retrieval_source_repository"
        )
        con = self._open_ro_database()
        try:
            return module.SQLiteRetrievalSourceRepository(con).source_fingerprint()
        finally:
            con.close()

    def _ensure_current(self):
        generation = self._current_pointer_generation()
        if not generation:
            raise UnifiedSearchRuntimeError("no current retrieval generation")
        if self._store is not None and generation == self._generation:
            return
        self.close()
        store_module = import_module("personal_learning_assistant.retrieval.index_store")
        service_module = import_module(
            "personal_learning_assistant.services.retrieval_service"
        )
        store = store_module.RetrievalIndexStore(self.index_root)
        if store.manifest.get("semantic_enabled"):
            if self._provider is None:
                factory = self._embedding_provider_factory
                if factory is None:
                    embedding_module = import_module(
                        "personal_learning_assistant.retrieval.embedding"
                    )
                    factory = embedding_module.FastEmbedProvider
                kwargs = {}
                if store.manifest.get("embedding_model"):
                    kwargs["model_name"] = str(store.manifest["embedding_model"])
                if store.manifest.get("embedding_version"):
                    kwargs["model_version"] = str(store.manifest["embedding_version"])
                self._provider = factory(**kwargs)
            store.embedding_provider = self._provider
        self._store = store
        self._service = service_module.RetrievalService(store)
        self._generation = generation

    def assert_fresh(self):
        self._ensure_current()
        expected = str(self._store.manifest.get("source_fingerprint") or "")
        current = self._source_fingerprint()
        if not expected or expected != current:
            raise UnifiedSearchStaleIndexError(
                "learning material changed since the current knowledge index"
            )

    def search(self, query, **kwargs):
        self.assert_fresh()
        return self._service.search(query, **kwargs)

    @property
    def manifest(self):
        self._ensure_current()
        return dict(self._store.manifest)

    def close(self):
        if self._store is not None:
            self._store.close()
        self._store = None
        self._service = None
        self._generation = None


_APP_RUNTIMES = {}


def get_unified_search_runtime(
    *,
    database_path="data/learning_assistant.db",
    index_root=".phase5_retrieval",
):
    key = (
        str(Path(database_path).resolve(strict=False)),
        str(Path(index_root).resolve(strict=False)),
    )
    runtime = _APP_RUNTIMES.get(key)
    if runtime is None:
        runtime = UnifiedSearchRuntime(
            database_path=database_path,
            index_root=index_root,
        )
        _APP_RUNTIMES[key] = runtime
    return runtime
