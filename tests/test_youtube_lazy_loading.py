import builtins
import importlib
import os
import sys

import pytest


def _fresh_youtube_import(monkeypatch, block_api=False):
    """
    Import youtube_ingestion in a controlled environment.
    The module must not require youtube-transcript-api or
    create its transcript directory just to import.
    """
    sys.modules.pop("youtube_ingestion", None)

    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if (
            block_api
            and name.split(".", 1)[0]
            == "youtube_transcript_api"
        ):
            raise ModuleNotFoundError(
                "blocked optional package: youtube_transcript_api"
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
        "youtube_ingestion"
    )


def test_youtube_module_import_has_no_optional_dependency_or_directory_write(
    monkeypatch,
):
    def fail_if_makedirs_called(*args, **kwargs):
        raise AssertionError(
            "youtube_ingestion created a directory during import"
        )

    monkeypatch.setattr(
        os,
        "makedirs",
        fail_if_makedirs_called,
    )

    module = _fresh_youtube_import(
        monkeypatch,
        block_api=True,
    )

    assert hasattr(
        module,
        "get_transcript",
    )


def test_missing_youtube_package_fails_only_when_transcript_is_requested(
    monkeypatch,
):
    module = _fresh_youtube_import(
        monkeypatch
    )

    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if (
            name.split(".", 1)[0]
            == "youtube_transcript_api"
        ):
            raise ModuleNotFoundError(
                "blocked optional package: youtube_transcript_api"
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
        match="YouTube transcript support is not installed",
    ):
        module.get_transcript(
            "dQw4w9WgXcQ"
        )


def test_transcript_directory_is_created_only_when_saving(
    monkeypatch,
    tmp_path,
):
    module = _fresh_youtube_import(
        monkeypatch
    )

    transcript_dir = (
        tmp_path
        / "youtube_transcripts"
    )

    monkeypatch.setattr(
        module,
        "YOUTUBE_DIR",
        str(transcript_dir),
    )

    assert not transcript_dir.exists()

    path = module.save_transcript(
        "abcdefghijk",
        [
            {
                "text": "Example transcript line.",
                "start": 0.0,
                "duration": 2.0,
            }
        ],
        title="Example Lecture",
        source_url="https://youtu.be/abcdefghijk",
    )

    assert transcript_dir.is_dir()
    assert os.path.isfile(path)


def test_listing_missing_transcript_directory_does_not_create_it(
    monkeypatch,
    tmp_path,
    capsys,
):
    module = _fresh_youtube_import(
        monkeypatch
    )

    transcript_dir = (
        tmp_path
        / "youtube_transcripts"
    )

    monkeypatch.setattr(
        module,
        "YOUTUBE_DIR",
        str(transcript_dir),
    )

    module.list_imported_transcripts()

    assert not transcript_dir.exists()

    output = capsys.readouterr().out
    assert (
        "No YouTube transcripts imported yet."
        in output
    )
