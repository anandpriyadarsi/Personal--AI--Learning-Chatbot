"""Run the Phase 7.5 local web interface with ``python -m``."""

from __future__ import annotations

import os

from . import create_app


def main() -> None:
    """Start the development server on loopback only."""
    port = int(os.environ.get("PLA_WEB_PORT", "5000"))
    create_app().run(
        host="127.0.0.1",
        port=port,
        debug=False,
    )


if __name__ == "__main__":
    main()
