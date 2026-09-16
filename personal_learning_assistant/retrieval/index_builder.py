"""Build disposable lexical/semantic indexes from authoritative SQLite chunks."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

from personal_learning_assistant.domain.retrieval_models import BuiltIndex


INDEX_FORMAT_VERSION = 1
BUILDER_VERSION = "phase5.8-v1"


class RetrievalIndexBuildError(RuntimeError):
    pass


def _utc_now():
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _sha256_file(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _generation_id(source_fingerprint, semantic_enabled, model_name, model_version):
    raw = "|".join(
        (
            INDEX_FORMAT_VERSION.__str__(),
            BUILDER_VERSION,
            source_fingerprint,
            "semantic" if semantic_enabled else "lexical",
            model_name,
            model_version,
        )
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


class RetrievalIndexBuilder:
    def __init__(
        self,
        source_repository,
        index_root,
        *,
        now=_utc_now,
    ):
        self.source_repository = source_repository
        self.index_root = Path(index_root)
        self._now = now

    def preview(self, *, embedding_provider=None):
        records = self.source_repository.active_records()
        fingerprint = self.source_repository.source_fingerprint()
        model_name = "" if embedding_provider is None else embedding_provider.model_name
        model_version = "" if embedding_provider is None else embedding_provider.model_version
        generation = _generation_id(
            fingerprint,
            embedding_provider is not None,
            model_name,
            model_version,
        )
        manifest = self.read_current_manifest()
        return {
            "active_document_count": len({r["document_id"] for r in records}),
            "active_chunk_count": len(records),
            "source_fingerprint": fingerprint,
            "planned_generation_id": generation,
            "current_generation_id": "" if manifest is None else manifest.get("generation_id", ""),
            "index_is_current": bool(
                manifest
                and manifest.get("generation_id") == generation
                and self.verify_manifest_files(manifest)
            ),
            "semantic_requested": embedding_provider is not None,
            "model_name": model_name,
            "model_version": model_version,
        }

    def read_current_manifest(self):
        pointer = self.index_root / "current.json"
        if not pointer.is_file():
            return None
        try:
            pointer_data = json.loads(pointer.read_text(encoding="utf-8"))
            generation = str(pointer_data["generation_id"])
            manifest_path = self.index_root / "indexes" / generation / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, KeyError, json.JSONDecodeError):
            return None
        return manifest

    def verify_manifest_files(self, manifest):
        try:
            generation = str(manifest["generation_id"])
            directory = self.index_root / "indexes" / generation
            lexical = directory / "lexical.sqlite3"
            if _sha256_file(lexical) != manifest["files"]["lexical.sqlite3"]["sha256"]:
                return False
            if manifest.get("semantic_enabled"):
                vectors = directory / "embeddings.npz"
                if _sha256_file(vectors) != manifest["files"]["embeddings.npz"]["sha256"]:
                    return False
            return True
        except (OSError, KeyError):
            return False

    def build(self, *, embedding_provider=None, acknowledge=True):
        records = self.source_repository.active_records()
        if not records:
            raise RetrievalIndexBuildError("no active knowledge chunks are available")
        fingerprint = self.source_repository.source_fingerprint()
        semantic_enabled = embedding_provider is not None
        model_name = "" if embedding_provider is None else str(embedding_provider.model_name)
        model_version = "" if embedding_provider is None else str(embedding_provider.model_version)
        generation = _generation_id(
            fingerprint, semantic_enabled, model_name, model_version
        )
        final_dir = self.index_root / "indexes" / generation
        self.index_root.mkdir(parents=True, exist_ok=True)
        (self.index_root / "indexes").mkdir(parents=True, exist_ok=True)

        if final_dir.is_dir():
            manifest_path = final_dir / "manifest.json"
            try:
                existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                shutil.rmtree(final_dir, ignore_errors=True)
            else:
                if (
                    existing.get("source_fingerprint") == fingerprint
                    and self.verify_manifest_files(existing)
                ):
                    self._install_pointer(generation)
                    if acknowledge:
                        self.source_repository.acknowledge_build(
                            generation_id=generation,
                            semantic_enabled=semantic_enabled,
                            model_name=model_name,
                            model_version=model_version,
                            now=self._now(),
                        )
                    return BuiltIndex(
                        generation_id=generation,
                        directory=str(final_dir),
                        chunk_count=len(records),
                        lexical_backend=str(existing["lexical_backend"]),
                        semantic_enabled=semantic_enabled,
                        embedding_model=model_name,
                        embedding_version=model_version,
                        source_fingerprint=fingerprint,
                    )

        temp_dir = Path(
            tempfile.mkdtemp(prefix=".build-", dir=str(self.index_root / "indexes"))
        )
        try:
            lexical_backend = self._build_lexical(temp_dir / "lexical.sqlite3", records)
            files = {
                "lexical.sqlite3": {
                    "sha256": _sha256_file(temp_dir / "lexical.sqlite3"),
                }
            }
            semantic_dimension = 0
            if semantic_enabled:
                semantic_dimension = self._build_semantic(
                    temp_dir / "embeddings.npz",
                    records,
                    embedding_provider,
                )
                files["embeddings.npz"] = {
                    "sha256": _sha256_file(temp_dir / "embeddings.npz"),
                }

            manifest = {
                "format_version": INDEX_FORMAT_VERSION,
                "builder_version": BUILDER_VERSION,
                "generation_id": generation,
                "source_fingerprint": fingerprint,
                "chunk_count": len(records),
                "document_count": len({r["document_id"] for r in records}),
                "lexical_backend": lexical_backend,
                "semantic_enabled": semantic_enabled,
                "embedding_model": model_name,
                "embedding_version": model_version,
                "embedding_dimension": semantic_dimension,
                "created_at": self._now(),
                "files": files,
            }
            (temp_dir / "manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            if final_dir.exists():
                shutil.rmtree(final_dir)
            os.replace(str(temp_dir), str(final_dir))
            temp_dir = None
            self._install_pointer(generation)
            if acknowledge:
                self.source_repository.acknowledge_build(
                    generation_id=generation,
                    semantic_enabled=semantic_enabled,
                    model_name=model_name,
                    model_version=model_version,
                    now=self._now(),
                )
            return BuiltIndex(
                generation_id=generation,
                directory=str(final_dir),
                chunk_count=len(records),
                lexical_backend=lexical_backend,
                semantic_enabled=semantic_enabled,
                embedding_model=model_name,
                embedding_version=model_version,
                source_fingerprint=fingerprint,
            )
        finally:
            if temp_dir is not None and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    def _install_pointer(self, generation):
        pointer_tmp = self.index_root / ".current.json.tmp"
        pointer_tmp.write_text(
            json.dumps({"generation_id": generation}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(str(pointer_tmp), str(self.index_root / "current.json"))

    def _build_lexical(self, path: Path, records):
        connection = sqlite3.connect(str(path))
        connection.row_factory = sqlite3.Row
        try:
            connection.execute(
                "CREATE TABLE chunks("
                "chunk_id TEXT PRIMARY KEY,document_id TEXT NOT NULL,"
                "ordinal INTEGER NOT NULL,page_number INTEGER,text TEXT NOT NULL,"
                "locator_json TEXT NOT NULL,resource_ids_json TEXT NOT NULL,"
                "course_ids_json TEXT NOT NULL,topic_ids_json TEXT NOT NULL,"
                "providers_json TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE INDEX chunks_document_ix ON chunks(document_id,ordinal)"
            )
            fts5 = True
            try:
                connection.execute(
                    "CREATE VIRTUAL TABLE chunk_fts USING fts5("
                    "chunk_id UNINDEXED,text,tokenize='unicode61')"
                )
            except sqlite3.OperationalError:
                fts5 = False

            for record in records:
                connection.execute(
                    "INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        record["chunk_id"],
                        record["document_id"],
                        record["ordinal"],
                        record["page_number"],
                        record["text"],
                        _json(record["locator"]),
                        _json(record["resource_ids"]),
                        _json(record["course_ids"]),
                        _json(record["topic_ids"]),
                        _json(record["providers"]),
                    ),
                )
                if fts5:
                    connection.execute(
                        "INSERT INTO chunk_fts(chunk_id,text) VALUES (?,?)",
                        (record["chunk_id"], record["text"]),
                    )
            connection.commit()
            return "fts5" if fts5 else "token_overlap"
        finally:
            connection.close()

    def _build_semantic(self, path: Path, records, provider):
        try:
            import numpy as np
        except ImportError as error:
            raise RetrievalIndexBuildError(
                "semantic index build requires NumPy"
            ) from error
        vectors = provider.embed([record["text"] for record in records])
        if len(vectors) != len(records):
            raise RetrievalIndexBuildError("embedding provider returned wrong vector count")
        matrix = np.asarray(vectors, dtype=np.float32)
        if matrix.ndim != 2 or matrix.shape[0] != len(records):
            raise RetrievalIndexBuildError("embedding provider returned invalid matrix")
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        matrix = matrix / norms
        chunk_ids = np.asarray([record["chunk_id"] for record in records])
        np.savez_compressed(path, chunk_ids=chunk_ids, embeddings=matrix)
        return int(matrix.shape[1])
