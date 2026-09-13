import ast
import json

import course_manager

from personal_learning_assistant.ui.cli.course_cli import (
    CourseCLI,
)


class FakeCourseAPI:
    def __init__(self):
        self.courses = [
            {
                "id": "ma103n",
                "code": "MA103N",
                "name": "Linear Algebra",
                "semester": "Semester 1",
                "status": "active",
                "topics": [
                    {
                        "name": "LU Factorization",
                        "status": "practiced",
                        "confidence": 4,
                        "last_updated": None,
                    }
                ],
                "created_at": None,
                "updated_at": None,
            },
            {
                "id": "cy100n",
                "code": "CY100N",
                "name": "Chemistry",
                "semester": "Semester 1",
                "status": "active",
                "topics": [],
                "created_at": None,
                "updated_at": None,
            },
        ]
        self.active_id = "ma103n"
        self.created = []

    def list_courses(self):
        return list(self.courses)

    def get_active_course(self):
        for course in self.courses:
            if course["id"] == self.active_id:
                return course
        return None

    def set_active_course(self, identifier):
        self.active_id = identifier
        return self.get_active_course()

    def get_course_progress(self, identifier):
        for course in self.courses:
            if course["id"] == identifier:
                mastered = sum(
                    1
                    for topic in course["topics"]
                    if topic["status"] == "mastered"
                )
                return {
                    "course": course,
                    "total_topics": len(course["topics"]),
                    "mastered_topics": mastered,
                    "progress_percent": (
                        round(
                            mastered
                            / len(course["topics"])
                            * 100
                        )
                        if course["topics"]
                        else 0
                    ),
                    "counts": {},
                }
        return None

    def create_course(
        self,
        code,
        name,
        semester="",
    ):
        course = {
            "id": code.lower(),
            "code": code.upper(),
            "name": name,
            "semester": semester,
            "status": "active",
            "topics": [],
            "created_at": None,
            "updated_at": None,
        }
        self.courses.append(course)
        self.created.append(course)
        return course

    def add_topic(
        self,
        course_identifier,
        topic_name,
    ):
        for course in self.courses:
            if course["id"] == course_identifier:
                topic = {
                    "name": topic_name,
                    "status": "not_started",
                    "confidence": 0,
                    "last_updated": None,
                }
                course["topics"].append(topic)
                return topic, True
        raise ValueError("Course not found.")

    def update_topic_status(
        self,
        course_identifier,
        topic_name,
        status,
        confidence=None,
    ):
        for course in self.courses:
            if course["id"] != course_identifier:
                continue
            for topic in course["topics"]:
                if topic["name"] == topic_name:
                    topic["status"] = status
                    if confidence is not None:
                        topic["confidence"] = int(confidence)
                    return topic
        raise ValueError("Course not found.")

    def linked_documents_for_course(
        self,
        course_identifier,
    ):
        return []

    def get_document_metadata(self, path):
        return {
            "course_code": None
        }

    def link_document(
        self,
        path,
        course_identifier,
        topic="",
    ):
        return {
            "course_id": course_identifier,
            "topic": topic,
        }


def _scripted_input(values):
    values = iter(values)

    def input_fn(prompt):
        return next(values)

    return input_fn


def test_course_manager_root_module_contains_no_direct_terminal_calls():
    source = open(
        course_manager.__file__,
        "r",
        encoding="utf-8",
    ).read()
    tree = ast.parse(source)

    direct_calls = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        if isinstance(node.func, ast.Name):
            if node.func.id in {
                "input",
                "print",
            }:
                direct_calls.append(
                    node.func.id
                )

    assert direct_calls == []


def test_course_cli_menu_can_exit_without_mutating_courses():
    api = FakeCourseAPI()
    output = []

    cli = CourseCLI(
        course_api=api,
        input_fn=_scripted_input(
            ["9"]
        ),
        output_fn=output.append,
    )

    before = json.dumps(
        api.courses,
        sort_keys=True,
    )

    cli.run()

    after = json.dumps(
        api.courses,
        sort_keys=True,
    )

    assert before == after
    assert any(
        "COURSE MANAGER V8"
        in line
        for line in output
    )


def test_course_cli_choose_course_uses_api_and_returns_selected_course():
    api = FakeCourseAPI()
    output = []

    cli = CourseCLI(
        course_api=api,
        input_fn=_scripted_input(
            ["2"]
        ),
        output_fn=output.append,
    )

    selected = cli.choose_course(
        "Select Active Course"
    )

    assert selected["code"] == "CY100N"
    assert api.active_id == "cy100n"


def test_course_cli_add_course_is_terminal_only_adapter():
    api = FakeCourseAPI()
    output = []

    cli = CourseCLI(
        course_api=api,
        input_fn=_scripted_input(
            [
                "CS101",
                "Programming",
                "Semester 1",
            ]
        ),
        output_fn=output.append,
    )

    cli.add_course_interactive()

    assert len(api.created) == 1
    assert api.created[0]["code"] == "CS101"
    assert any(
        "Course added: CS101 - Programming"
        in line
        for line in output
    )


def test_course_cli_progress_renderer_keeps_practiced_status_visible():
    api = FakeCourseAPI()
    output = []

    cli = CourseCLI(
        course_api=api,
        input_fn=_scripted_input([]),
        output_fn=output.append,
    )

    cli.print_course_progress(
        "ma103n"
    )

    assert any(
        "LU Factorization - Practiced"
        in line
        for line in output
    )


def test_course_manager_menu_delegates_to_extracted_cli(
    monkeypatch,
):
    calls = []

    class FakeCLI:
        def run(self):
            calls.append("run")

    monkeypatch.setattr(
        course_manager,
        "_build_course_cli",
        lambda: FakeCLI(),
    )

    course_manager.course_manager_menu()

    assert calls == ["run"]


def test_legacy_choose_course_wrapper_delegates_to_cli(
    monkeypatch,
):
    calls = []

    class FakeCLI:
        def choose_course(
            self,
            prompt,
            allow_back,
        ):
            calls.append(
                (
                    prompt,
                    allow_back,
                )
            )
            return {
                "id": "ma103n"
            }

    monkeypatch.setattr(
        course_manager,
        "_build_course_cli",
        lambda: FakeCLI(),
    )

    result = course_manager.choose_course(
        "Pick Course",
        allow_back=False,
    )

    assert result == {
        "id": "ma103n"
    }
    assert calls == [
        (
            "Pick Course",
            False,
        )
    ]
