import hashlib
import io
from pypdf import PdfWriter


def source_pdf(pages=2):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def catalogue():
    return {'available': True, 'courses': [
        {'id': f'c{i}', 'code': f'C{i}', 'name': f'Course {i}', 'academic_year': '2026–27',
         'semester': 'Semester 1', 'topics': [{'id': f't{i}', 'name': 'Topic'}]} for i in range(6)]}


def package(raw=None, module_id='synthetic', revision=1, mapped=False):
    raw = raw or source_pdf()
    return {
        'schema': 'anvaya.learning-module.v1', 'module_id': module_id, 'module_revision': revision,
        'title': 'A source-grounded lesson with a long descriptive title', 'unit': 'Unit 1',
        'source': {'source_id': 'fixture-source', 'sha256': hashlib.sha256(raw).hexdigest(),
                   'filename': 'source.pdf', 'media_type': 'application/pdf', 'page_count': 2},
        'mapping': {'course_id': 'c0', 'topic_id': 't0', 'topic_name': 'Topic',
                    'reviewed': True, 'confidence': .95} if mapped else None,
        'pages': [{'page': i, 'status': 'needs_review', 'text': 'Original source text',
                   'review_flags': ['Semantic fidelity requires review']} for i in range(1, 3)],
        'sections': [{'id': 'lesson-1', 'title': 'Learn this concept', 'pages': [1], 'blocks': [
            {'kind': 'source', 'text': 'Original source text', 'pages': [1]},
            {'kind': 'teaching', 'text': '**Extra explanation**', 'pages': [1]},
            {'kind': 'flowchart', 'nodes': ['Observe', 'Compare', 'Recall'],
             'alt': 'Observe, then compare, then recall.', 'pages': [1]}]}],
        'revision': [{'kind': 'teaching', 'text': '## Memory trap\nRecall the contrast.', 'pages': [1, 2]}],
        'questions': [{'id': 'q1', 'revision': 1, 'kind': 'mcq', 'prompt': 'Which option?',
                       'options': ['Incorrect', 'Correct'], 'correct_index': 1,
                       'explanation': 'Compare the original source.', 'pages': [1],
                       'difficulty': 'normal', 'low_stakes': True}],
    }
