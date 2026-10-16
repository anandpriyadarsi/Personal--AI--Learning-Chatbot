"""Standalone disposable preview. Deliberately NOT registered by create_app."""

from __future__ import annotations
from pathlib import Path
import secrets
import sqlite3
from urllib.parse import urlsplit
from flask import Blueprint, Flask, abort, jsonify, redirect, render_template, request, url_for
from itsdangerous import URLSafeSerializer, BadSignature


def create_candidate_app(service, *, secret_key, landing_sessions=None):
    """Standalone disposable demo with a discoverable, read-only landing page.

    Session identifiers come from the trusted synthetic fixture, never an
    installed ANVAYA database. The production blueprint has no root route.
    """
    root = Path(__file__).resolve().parent
    app = Flask(
        __name__,
        template_folder=str(root / "templates"),
        static_folder=str(root / "static"),
    )
    app.config.update(MAX_CONTENT_LENGTH=150000)
    _create_routes(app, service, secret_key=secret_key, production=False)
    visible = {
        label: str(session)
        for label, session in (landing_sessions or {}).items()
        if label in {"online", "paper"}
        and isinstance(session, str)
        and 0 < len(session) <= 100
    }

    @app.get("/")
    def preview_home():
        return render_template(
            "assessment_execution_preview_index.html",
            sessions=visible,
        )

    return app


class _ServiceProxy:
    def __init__(self, factory):
        self.factory = factory

    def __getattr__(self, name):
        # Factory is evaluated per request; no global connection or user state.
        return getattr(self.factory(), name)


def create_production_blueprint(service_factory, *, secret_key):
    """Opt-in private self-study routes mounted by the normal create_app."""
    root = Path(__file__).resolve().parent
    bp = Blueprint("assessment_extended", __name__, template_folder=str(root / "templates"))

    @bp.record_once
    def register_mutation_signer(state):
        # Overview uses the *same* scoped, process-local signer as this
        # blueprint for a native one-click POST resume. No GET mutation.
        state.app.extensions["assessment_extended_mutation_signer"] = URLSafeSerializer(
            secret_key, salt="assessment-candidate-mutation-v1"
        )

    return _create_routes(bp, _ServiceProxy(service_factory),
                          secret_key=secret_key, production=True)


def _create_routes(app, service, *, secret_key, production):
    if not isinstance(secret_key, bytes) or len(secret_key) < 32:
        raise ValueError("A private mutation signing key is required.")
    signer = URLSafeSerializer(secret_key, salt="assessment-candidate-mutation-v1")
    base = ("/assessments/extended/sessions/<sid>" if production
            else "/assessments/candidate/sessions/<sid>")
    endpoint_prefix = "assessment_extended." if production else ""

    @app.after_request
    def headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    def page(sid, *, error="", code=200, unsaved=None):
        state = service.state(sid)
        retained = None
        if unsaved:
            retained = {
                key: unsaved.getlist(key) for key in unsaved if key != "mutation_token"
            }
            question = next(
                (
                    q
                    for q in state["questions"]
                    if q["session_question_id"] == unsaved.get("question_id")
                ),
                None,
            )
            if question is not None and state["kind"] == "online_timed":
                if question["question_type"] in {"mcq", "msq"}:
                    question["response"] = {
                        "selected_option_ids": unsaved.getlist("option_ids")
                    }
                else:
                    answer = unsaved.get("answer", "")
                    question["response"] = {"value": answer, "text": answer}
                question["marked"] = unsaved.get("marked") == "on"
        return (
            render_template(
                "assessment_execution_candidate.html",
                state=state,
                guides=service.authorized_guides(sid),
                history=service.review_history(sid),
                retained=retained,
                mutation_token=signer.dumps({"session_id": sid}),
                new_id=lambda: secrets.token_urlsafe(18),
                endpoint_prefix=endpoint_prefix,
                error=error,
            ),
            code,
        )

    @app.get(base)
    def workspace(sid):
        return page(sid)

    @app.get(base + "/state")
    def state(sid):
        return jsonify(service.state(sid))

    @app.get(base + "/review-summary")
    def summary(sid):
        return jsonify(service.review_summary(sid))

    def same_origin(value):
        try:
            u = urlsplit(value)
            return (
                u.scheme in {"http", "https"}
                and u.netloc == request.host
                and u.scheme == request.scheme
                and not u.username
                and not u.password
            )
        except ValueError:
            return False

    def authorize(sid, data):
        if production and request.content_length is not None and request.content_length > 150000:
            abort(413)
        origin = request.headers.get("Origin")
        site = request.headers.get("Sec-Fetch-Site")
        if site and site != "same-origin":
            abort(403)
        if origin:
            if not same_origin(origin):
                abort(403)
        elif not (
            site == "same-origin" and same_origin(request.headers.get("Referer", ""))
        ):
            abort(403)
        try:
            if signer.loads(data.get("mutation_token", "")) != {"session_id": sid}:
                abort(403)
        except (BadSignature, TypeError):
            abort(403)

    @app.post(base + "/<action>")
    def mutate(sid, action):
        data = (
            request.get_json(silent=True) if request.is_json else request.form.to_dict()
        )
        if not isinstance(data, dict):
            abort(400)
        authorize(sid, data)
        payload = {
            k: v for k, v in data.items() if k not in {"mutation_token", "command"}
        }
        if not request.is_json:
            for key in ("expected_revision", "expected_response_revision", "ordinal"):
                if key in payload:
                    try:
                        payload[key] = int(payload[key])
                    except ValueError:
                        raise ValueError("Invalid numeric field.") from None
            action = data.get("command", action)
            if action in {"save", "pause", "navigate"} and "question_id" in payload:
                q = next(
                    (
                        q
                        for q in service.state(sid)["questions"]
                        if q["session_question_id"] == payload["question_id"]
                    ),
                    None,
                )
                if q is None:
                    raise LookupError("Question not found.")
                if q["question_type"] in {"mcq", "msq"}:
                    response = {
                        "selected_option_ids": request.form.getlist("option_ids")
                    }
                elif q["question_type"] in {"numerical", "fill_blank", "true_false"}:
                    response = {"value": payload.get("answer", "")}
                else:
                    response = {"text": payload.get("answer", "")}
                payload["response"] = response
                payload["marked"] = data.get("marked") == "on"
            if "attempted" in payload:
                payload["attempted"] = payload["attempted"] == "true"
            if action == "self_save":
                reasons = {
                    key[len("criterion_reason_") :]: value
                    for key, value in payload.items()
                    if key.startswith("criterion_reason_")
                }
                for key in list(payload):
                    if key.startswith("criterion_reason_"):
                        del payload[key]
                if data.get("unattempted") == "on":
                    payload["unattempted"] = True
                    payload.pop("marks", None)
                steps = {
                    key[5:]: value
                    for key, value in payload.items()
                    if key.startswith("step_")
                }
                for key in list(payload):
                    if key.startswith("step_"):
                        del payload[key]
                if steps and not payload.get("unattempted"):
                    payload["steps"] = steps
                if reasons:
                    payload["step_reasons"] = reasons
            if "confirmed" in payload:
                payload["confirmed"] = payload["confirmed"] == "on"
            for key in ("option_ids", "answer"):
                payload.pop(key, None)
            if action != "navigate":
                payload.pop("ordinal", None)
            if action in {"submit", "resume", "finish_solving"}:
                # Native finish is deliberate: save acknowledgement is a separate action.
                payload = {
                    key: value
                    for key, value in payload.items()
                    if key in {"request_id", "expected_revision"}
                }
        result = service.command(sid, action, payload)
        if request.is_json or request.headers.get("Accept") == "application/json":
            return jsonify(ok=True, **result)
        return redirect(url_for(endpoint_prefix + "workspace", sid=sid), code=303)

    @app.errorhandler(ValueError)
    def invalid(error):
        message = str(error)
        code = 409 if message.startswith("Conflict:") else 422
        if request.is_json or request.headers.get("Accept") == "application/json":
            return jsonify(ok=False, error=message), code
        sid = (request.view_args or {}).get("sid")
        if sid:
            try:
                return page(sid, error=message, code=code, unsaved=request.form)
            except (ValueError, LookupError, sqlite3.Error):
                pass
        return "Assessment request is unavailable.", code

    @app.errorhandler(LookupError)
    def missing(error):
        return jsonify(ok=False, error="Attempt or question not found."), 404

    @app.errorhandler(sqlite3.Error)
    def storage(error):
        return (
            jsonify(
                ok=False,
                error="Assessment storage unavailable. No acknowledgement received; preserve your work and retry.",
            ),
            503,
        )

    return app
