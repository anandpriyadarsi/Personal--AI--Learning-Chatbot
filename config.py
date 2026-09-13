"""Central project paths for the Personal AI Learning Assistant.

Phase 1.5 keeps path discovery side-effect free:
importing this module never creates directories or files.
"""

from pathlib import Path
from typing import Iterable, Union


PathLike = Union[str, Path]

BASE_PATH = Path(__file__).resolve().parent
DATA_PATH = BASE_PATH / "data"
BACKUP_PATH = BASE_PATH / "backup"
EXPORT_PATH = BASE_PATH / "exports"

NOTES_PATH = DATA_PATH / "notes.json"
RESOURCES_PATH = DATA_PATH / "resources.json"

# Compatibility strings for the existing V1-V13 modules.
BASE_DIR = str(BASE_PATH)
DATA_DIR = str(DATA_PATH)
BACKUP_DIR = str(BACKUP_PATH)
EXPORT_DIR = str(EXPORT_PATH)
NOTES_FILE = str(NOTES_PATH)
RESOURCES_FILE = str(RESOURCES_PATH)


def ensure_directories(
    directories: Iterable[PathLike],
) -> None:
    """Create directories only when a write operation explicitly needs them."""
    for directory in directories:
        Path(directory).mkdir(
            parents=True,
            exist_ok=True,
        )


def ensure_data_dir() -> str:
    ensure_directories([DATA_PATH])
    return DATA_DIR


def ensure_backup_dir() -> str:
    ensure_directories([BACKUP_PATH])
    return BACKUP_DIR


def ensure_export_dir() -> str:
    ensure_directories([EXPORT_PATH])
    return EXPORT_DIR


def ensure_runtime_directories() -> None:
    """Explicit compatibility helper for commands that need all legacy folders."""
    ensure_directories(
        [
            DATA_PATH,
            BACKUP_PATH,
            EXPORT_PATH,
        ]
    )
