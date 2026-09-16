"""Web error handlers that keep the interface inside the shared shell."""

from __future__ import annotations

from flask import Flask, render_template


def register_error_handlers(app: Flask) -> None:
    """Register presentation-only error pages."""

    @app.errorhandler(404)
    def page_not_found(error):
        del error
        return render_template("errors/404.html", active_page=None), 404

    @app.errorhandler(500)
    def internal_server_error(error):
        del error
        return render_template("errors/500.html", active_page=None), 500
