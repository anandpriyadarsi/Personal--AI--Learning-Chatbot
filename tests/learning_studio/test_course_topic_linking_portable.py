"""Course/topic mapping for original self-contained Learning Studio modules."""
import copy
import hashlib
import io

from pypdf import PdfWriter

from personal_learning_assistant.domain import course_normalization
from personal_learning_assistant.domain.course_models import CreateCourseCommand
from personal_learning_assistant.learning_studio.service import LearningStudioService
from personal_learning_assistant.services.course_dashboard_service import build_course_catalogue_from_result
from personal_learning_assistant.services.course_service import CourseService
from personal_learning_assistant.ui.web import create_app


class MemoryCourses:
    def __init__(self):
        self.state = course_normalization.default_course_data()

    def load_state(self):
        return copy.deepcopy(self.state)

    def save_state(self, state):
        self.state = course_normalization._normalise_data(state)
        return self.load_state()


def _pdf():
    buffer = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(buffer)
    return buffer.getvalue()


def _package(pdf):
    digest = hashlib.sha256(pdf).hexdigest()
    return {
        'schema': 'anvaya.learning-module.v2',
        'module_id': 'uc100n.preprocessing.mapping.test',
        'module_revision': 1,
        'title': 'Data Preprocessing',
        'unit': 'UC100N',
        'source': {'source_id': 'portable.' + digest, 'sha256': digest,
                   'filename': 'Data_Preprocessing.pdf', 'media_type': 'application/pdf',
                   'page_count': 1},
        'mapping': None,
        'pages': [{'page': 1, 'status': 'verified', 'text': 'Data preprocessing',
                   'review_flags': []}],
        'sections': [{'id': 'encoding', 'title': 'Encoding', 'pages': [1],
                      'blocks': [{'kind': 'teaching', 'pages': [1], 'text': 'Encoding categories'}]}],
        'revision': [{'kind': 'recall', 'pages': [1], 'text': 'What is encoding?',
                      'answer': 'Making categorical data usable as numeric data.'}],
        'questions': [],
    }


def _setup(tmp_path):
    courses = CourseService(MemoryCourses())
    catalogue = lambda: build_course_catalogue_from_result(courses.list_courses())
    studio = LearningStudioService(
        tmp_path / 'learning_studio.sqlite3',
        source_loader=lambda source_id: (_ for _ in ()).throw(
            AssertionError('Portable source must not be looked up in a separate registry')),
        catalogue_loader=catalogue,
    )
    pdf = _pdf()
    module = _package(pdf)
    studio.stage(module, source_bytes=pdf)
    studio.publish(module['module_id'], 1)
    return courses, catalogue, studio, pdf, module


def test_course_catalogue_creates_stable_topic_ids_without_mutating_legacy_json(tmp_path):
    courses, catalogue, studio, _, _ = _setup(tmp_path)
    courses.create_course(CreateCourseCommand(
        code='UC100N', name='Data Science & AI', semester='Semester 1',
        topics=({'name': 'Data Preprocessing'},)))
    a, b = catalogue(), catalogue()
    assert a['courses'][0]['topics'][0]['id'] == b['courses'][0]['topics'][0]['id']
    assert a['courses'][0]['topics'][0]['id'].startswith('topic-')
    assert 'id' not in courses.repository.load_state()['courses'][0]['topics'][0]


def test_portable_link_creates_new_reviewed_revision_and_preserves_original(tmp_path):
    courses, catalogue, studio, original, module = _setup(tmp_path)
    courses.create_course(CreateCourseCommand(
        code='UC100N', name='Data Science & AI', semester='Semester 1',
        topics=({'name': 'Data Preprocessing'},)))
    candidates = studio.mapping_candidates(module['module_id'], 1)['candidates']
    assert len(candidates) == 1
    topic = candidates[0]
    linked = studio.confirm_mapping(module['module_id'], 1, {
        'module_revision': 2,
        'course_id': topic['course_id'],
        'topic_id': topic['topic_id'],
        'topic_name': topic['topic_name'],
        'confidence': 1.0,
        'confirmed': True,
    })
    assert linked['revision'] == 2
    assert studio.module(module['module_id'], 2, staged=True)['mapping']['course_id'] == topic['course_id']
    assert studio.source(module['module_id'], 1) == original
    assert studio.source(module['module_id'], 2, staged=True) == original
    assert studio.publish(module['module_id'], 2)['state'] == 'published'
    assert studio.source(module['module_id'], 2) == original


def test_mapping_setup_post_creates_uc100n_topic_with_csrf_and_no_duplicate(tmp_path):
    courses, catalogue, studio, pdf, module = _setup(tmp_path)
    app = create_app({
        'TESTING': True,
        'LEARNING_STUDIO_SERVICE_FACTORY': lambda: studio,
        'LEARNING_STUDIO_COURSE_SERVICE_FACTORY': lambda: courses,
    })
    route = f"/learning/modules/{module['module_id']}/1/mapping/catalogue"
    csrf = app.extensions['learning_studio_csrf']
    client = app.test_client()
    denied = client.post(route, data={'action': 'create', 'code': 'UC100N',
                                     'name': 'Data Science & AI', 'topic': 'Data Preprocessing'})
    assert denied.status_code == 403
    created = client.post(route, data={'csrf_token': csrf, 'action': 'create',
                                       'code': 'UC100N', 'name': 'Data Science & AI',
                                       'semester': 'Semester 1', 'topic': 'Data Preprocessing'})
    assert created.status_code == 303
    assert len(catalogue()['courses']) == 1
    assert len(catalogue()['courses'][0]['topics']) == 1
    again = client.post(route, data={'csrf_token': csrf, 'action': 'add_topic',
                                     'course_id': catalogue()['courses'][0]['id'],
                                     'topic': 'Data Preprocessing'})
    assert again.status_code == 303
    assert len(catalogue()['courses'][0]['topics']) == 1
