"""Stateless helper endpoint; only the current public task reaches a provider."""
from flask import Blueprint, current_app, jsonify, request

from personal_learning_assistant.services.assessment_coding_helper import CodingHelperError, build_request

assessment_tools_blueprint = Blueprint("assessment_tools", __name__)


@assessment_tools_blueprint.post("/assessments/sessions/<session_id>/questions/<session_question_id>/coding-helper")
def coding_helper(session_id, session_question_id):
    from .routes import _assessment_runner_service, _assessment_runner_error_status

    if request.content_length and request.content_length > 25000:
        return jsonify(error="Help request is too long."), 413
    try:
        context = _assessment_runner_service().coding_context(session_id, session_question_id)
    except Exception as error:
        return jsonify(error="This question is unavailable for coding help."), _assessment_runner_error_status(error)
    try:
        provider_request = build_request(session_id, context, request.get_json(silent=True), current_app.config)
    except CodingHelperError as error:
        return jsonify(error=str(error)), error.status
    try:
        factory = current_app.config.get("CODING_HELPER_PROVIDER_FACTORY")
        if factory is not None:
            provider = factory()
        else:
            from personal_learning_assistant.tutor.http_provider import OpenAICompatibleTutorProvider
            provider = OpenAICompatibleTutorProvider(timeout_seconds=45)
        reply = provider.complete(provider_request).content
        if not isinstance(reply, str) or not reply.strip():
            raise ValueError("Empty provider reply")
        return jsonify(reply=reply.strip()[:16000])
    except Exception:
        return jsonify(error="Coding help is temporarily unavailable. Your assessment is unchanged. Use the Operations Map or try again."), 503
