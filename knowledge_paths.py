"""Compatibility path exports for V8-V13 modules.

The canonical project-root definition now lives in config.py.
Importing this module performs no filesystem writes.
"""

from config import BASE_DIR, BASE_PATH

__all__ = [
    "BASE_DIR",
    "BASE_PATH",
]
