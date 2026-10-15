"""Plain-text human handoff, never an automatic Tutor provider request."""


def format_review_brief(context):
    lines = ['ANVAYA Learning Studio review brief',
        'Manual handoff only. Tutor has NOT automatically consumed this evidence.',
        f"{context['evidence_label']}; low-stakes practice, not official grades or mastery.",
        f"Module: {context['module_id']} / revision {context['module_revision']} — {context['title']}",
        f"Source: {context['source']['source_id']} / SHA-256 {context['source']['sha256']}",
        f"Mapping: {context['mapping_status']}; semantic review pending on {context['semantic_review_pages']} pages.",
        f"Recorded attempts in this revision: {context['attempts']}"]
    if context['mapping_snapshot']:
        lines.append('Historical mapping snapshot: '+context['mapping_snapshot']['course_id']+' / '+context['mapping_snapshot']['topic_name'])
    for q in context['missed_questions']:
        lines.extend(['',f"Question: {q['question_id']} / revision {q['question_revision']} — {q['prompt']}",
            f"Recorded misses: {q['incorrect_count']}; latest response: {q['latest_response']}; status: {q['status']}",
            f"Last incorrect: {q['last_incorrect']}",f"Lesson: {q['lesson_url']}",
            'Source pages: '+', '.join(q['source_urls']),f"Recheck: {q['question_url']}"])
    if not context['missed_questions']: lines.append('No recorded missed questions in this revision.')
    lines.append('\nUse these observations to plan a source-grounded recheck. They do not establish a diagnosis or mastery.')
    return '\n'.join(lines)
