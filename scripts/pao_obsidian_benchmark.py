#!/usr/bin/env python3
"""Disposable local read-cost benchmark; never opens a configured personal vault."""
import json
import os
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from personal_learning_assistant.services.obsidian_workspace_service import ObsidianWorkspaceService
from personal_learning_assistant.repositories.filesystem.obsidian_workspace_reader import ObsidianWorkspaceReader


class FixtureConfig:
    def __init__(self, root):
        self.path = root.parent / "fixture-config.json"
        self.save_config({"vault_path": str(root), "enabled": True})
    def load_config(self):
        return json.loads(self.path.read_text(encoding="utf-8"))
    def save_config(self, value):
        self.path.write_text(json.dumps(value), encoding="utf-8")
    def validate_vault_path(self, path):
        return True, "fixture"


def benchmark(sizes=(100, 1000, 10000), repetitions=20):
    results = []
    for count in sizes:
        with tempfile.TemporaryDirectory(prefix="pao-synthetic-vault-") as directory:
            root = Path(directory) / "vault"
            (root / ".obsidian").mkdir(parents=True)
            for index in range(count):
                (root / f"N{index}.md").write_text(f"# Note {index}\n\n[[N0]]\n\nSynthetic source text.", encoding="utf-8")
            service = ObsidianWorkspaceService(FixtureConfig(root), ObsidianWorkspaceReader)
            began = time.perf_counter()
            service.refresh_manifest()
            elapsed = time.perf_counter() - began
            samples, reads = [], []
            original = ObsidianWorkspaceReader.read_note
            def counted(reader, path, **kwargs):
                reads.append(path)
                return original(reader, path, **kwargs)
            ObsidianWorkspaceReader.read_note = counted
            try:
                for _ in range(repetitions):
                    began = time.perf_counter()
                    service.validate_note_version(f"N{count - 1}.md")
                    samples.append((time.perf_counter() - began) * 1000)
            finally:
                ObsidianWorkspaceReader.read_note = original
            results.append({"notes": count, "refresh_seconds": round(elapsed, 3),
                            "validation_p50_ms": round(statistics.median(samples), 3),
                            "validation_p95_ms": round(sorted(samples)[max(0, int(len(samples)*.95)-1)], 3),
                            "source_opens_per_validation": len(reads) / repetitions})
    return {"system": platform.platform(), "machine": platform.machine(), "logical_cpus": os.cpu_count(),
            "repetitions": repetitions, "config": "JSON reloaded per validation; synthetic tiny Markdown; warm local scratch filesystem", "results": results}


if __name__ == "__main__":
    print(json.dumps(benchmark(), indent=2))
