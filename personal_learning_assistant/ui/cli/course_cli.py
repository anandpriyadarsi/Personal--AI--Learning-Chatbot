"""Course Manager command-line adapter.

All terminal input/output for Course Manager lives here.  The root
``course_manager.py`` module remains a compatibility facade and domain/storage
bridge during Phase 2, while CourseService handles typed course commands and
queries underneath it.
"""

from typing import Callable, Optional

import course_manager


class CourseCLI:
    """Interactive terminal adapter for the existing Course Manager menu."""

    def __init__(
        self,
        course_api=course_manager,
        input_fn: Callable[[str], str] = input,
        output_fn: Callable[[str], None] = print,
    ):
        self.api = course_api
        self.input = input_fn
        self.output = output_fn

    def print_course_progress(
        self,
        course_identifier,
    ):
        progress = self.api.get_course_progress(
            course_identifier
        )

        if progress is None:
            self.output(
                "\nCourse not found."
            )
            return

        course = progress["course"]

        self.output(
            "\n" + "=" * 60
        )
        self.output(
            f"{course['code']} - {course['name']}"
        )

        if course["semester"]:
            self.output(
                f"Semester : {course['semester']}"
            )

        self.output(
            "Status   : "
            + course["status"]
            .replace("_", " ")
            .title()
        )
        self.output(
            "Progress : "
            f"{progress['mastered_topics']}/"
            f"{progress['total_topics']} "
            "topics mastered "
            f"({progress['progress_percent']}%)"
        )
        self.output(
            "=" * 60
        )

        if not course["topics"]:
            self.output(
                "\nNo topics added yet."
            )
            return

        for number, topic in enumerate(
            course["topics"],
            start=1,
        ):
            status = (
                topic["status"]
                .replace("_", " ")
                .title()
            )
            confidence = topic["confidence"]
            confidence_text = (
                f" | confidence {confidence}/5"
                if confidence
                else ""
            )

            self.output(
                f"{number}. {topic['name']} - "
                f"{status}{confidence_text}"
            )

    def choose_course(
        self,
        prompt="Select a course",
        allow_back=True,
    ):
        courses = self.api.list_courses()

        if not courses:
            self.output(
                "\nNo courses exist yet. "
                "Open Course Manager and add one first."
            )
            return None

        active = self.api.get_active_course()

        self.output(
            f"\n========== {prompt.upper()} =========="
        )

        for number, course in enumerate(
            courses,
            start=1,
        ):
            marker = (
                " [ACTIVE]"
                if (
                    active
                    and active["id"]
                    == course["id"]
                )
                else ""
            )

            self.output(
                f"{number}. "
                f"{course['code']} - "
                f"{course['name']}"
                f"{marker}"
            )

        if allow_back:
            self.output(
                f"{len(courses) + 1}. Back"
            )

        try:
            choice = int(
                self.input(
                    "\nEnter course number: "
                ).strip()
            )
        except ValueError:
            self.output(
                "\nPlease enter a valid number."
            )
            return None

        if (
            allow_back
            and choice
            == len(courses) + 1
        ):
            return None

        if (
            choice < 1
            or choice > len(courses)
        ):
            self.output(
                "\nInvalid course number."
            )
            return None

        return self.api.set_active_course(
            courses[
                choice - 1
            ]["id"]
        )

    def show_courses(self):
        courses = self.api.list_courses()
        active = self.api.get_active_course()

        self.output(
            "\n========== MY COURSES =========="
        )

        if not courses:
            self.output(
                "\nNo courses added yet."
            )
            return

        for number, course in enumerate(
            courses,
            start=1,
        ):
            marker = (
                " [ACTIVE]"
                if (
                    active
                    and active["id"]
                    == course["id"]
                )
                else ""
            )

            progress = (
                self.api.get_course_progress(
                    course["id"]
                )
            )

            self.output(
                f"{number}. "
                f"{course['code']} - "
                f"{course['name']}"
                f" | "
                f"{course['semester'] or 'Semester not set'}"
                f" | "
                f"{progress['progress_percent']}% mastered"
                f"{marker}"
            )

    def add_course_interactive(self):
        self.output(
            "\n========== ADD COURSE =========="
        )

        code = self.input(
            "Course code (example MA103N): "
        ).strip()
        name = self.input(
            "Course name: "
        ).strip()
        semester = self.input(
            "Semester (example Semester 1): "
        ).strip()

        try:
            course = self.api.create_course(
                code,
                name,
                semester,
            )
            self.output(
                f"\nCourse added: "
                f"{course['code']} - "
                f"{course['name']}"
            )
        except ValueError as error:
            self.output(
                f"\n{error}"
            )

    def add_topic_interactive(self):
        course = self.choose_course(
            "Add Topic To Course"
        )

        if course is None:
            return

        topic = self.input(
            "\nTopic name: "
        ).strip()

        try:
            saved, created = self.api.add_topic(
                course["id"],
                topic,
            )

            if created:
                self.output(
                    f"\nTopic added: "
                    f"{saved['name']}"
                )
            else:
                self.output(
                    "\nThat topic already exists."
                )

        except ValueError as error:
            self.output(
                f"\n{error}"
            )

    def update_topic_interactive(self):
        course = self.choose_course(
            "Update Topic Progress"
        )

        if course is None:
            return

        self.print_course_progress(
            course["id"]
        )

        topic = self.input(
            "\nTopic name: "
        ).strip()

        self.output(
            "Statuses: not_started, learning, weak, "
            "review, practiced, mastered"
        )

        status = self.input(
            "New status: "
        ).strip()

        confidence_text = self.input(
            "Confidence 0-5 "
            "(press Enter to skip): "
        ).strip()

        confidence = (
            confidence_text
            if confidence_text
            else None
        )

        try:
            saved = self.api.update_topic_status(
                course["id"],
                topic,
                status,
                confidence,
            )

            self.output(
                f"\nUpdated "
                f"{saved['name']} "
                f"to {saved['status']}."
            )

        except ValueError as error:
            self.output(
                f"\n{error}"
            )

    def link_document_interactive(self):
        course = self.choose_course(
            "Link Knowledge Source"
        )

        if course is None:
            return

        try:
            from knowledge import (
                describe_source,
                find_documents,
            )
            documents = find_documents()
        except ImportError:
            self.output(
                "\nKnowledge module is not available."
            )
            return

        if not documents:
            self.output(
                "\nNo supported documents found."
            )
            return

        self.output(
            "\n========== KNOWLEDGE SOURCES =========="
        )

        for number, path in enumerate(
            documents,
            start=1,
        ):
            metadata = (
                self.api.get_document_metadata(
                    path
                )
            )
            current = (
                f" [{metadata['course_code']}]"
                if metadata["course_code"]
                else " [UNTAGGED]"
            )

            self.output(
                f"{number}. "
                f"{describe_source(path)}"
                f"{current}"
            )

        try:
            choice = int(
                self.input(
                    "\nEnter source number: "
                ).strip()
            )
        except ValueError:
            self.output(
                "\nPlease enter a valid number."
            )
            return

        if (
            choice < 1
            or choice > len(documents)
        ):
            self.output(
                "\nInvalid source number."
            )
            return

        selected = documents[
            choice - 1
        ]

        topic = self.input(
            "Related topic (optional): "
        ).strip()

        self.api.link_document(
            selected,
            course["id"],
            topic,
        )

        self.output(
            f"\nSource linked to "
            f"{course['code']}."
        )

    def show_linked_sources(self):
        course = self.choose_course(
            "View Linked Sources"
        )

        if course is None:
            return

        links = (
            self.api.linked_documents_for_course(
                course["id"]
            )
        )

        self.output(
            f"\n========== "
            f"{course['code']} SOURCES "
            f"=========="
        )

        if not links:
            self.output(
                "\nNo explicitly linked sources yet."
            )
            self.output(
                "Files can also be auto-tagged from "
                "course codes in paths or Markdown tags."
            )
            return

        for number, link in enumerate(
            links,
            start=1,
        ):
            topic = (
                f" | topic: {link['topic']}"
                if link["topic"]
                else ""
            )

            self.output(
                f"{number}. "
                f"{link['display_path']}"
                f" | "
                f"{link['source_type'].replace('_', ' ')}"
                f"{topic}"
            )

    def run(self):
        while True:
            active = self.api.get_active_course()
            active_text = (
                f"{active['code']} - "
                f"{active['name']}"
                if active
                else "None"
            )

            self.output(
                "\n========== COURSE MANAGER V8 =========="
            )
            self.output(
                f"Active course: {active_text}"
            )
            self.output(
                "1. View All Courses"
            )
            self.output(
                "2. Add Course"
            )
            self.output(
                "3. Select Active Course"
            )
            self.output(
                "4. View Active Course Progress"
            )
            self.output(
                "5. Add Topic"
            )
            self.output(
                "6. Update Topic Status"
            )
            self.output(
                "7. Link Knowledge Source to Course"
            )
            self.output(
                "8. View Linked Sources"
            )
            self.output(
                "9. Back"
            )

            choice = self.input(
                "\nEnter your choice (1-9): "
            ).strip()

            if choice == "1":
                self.show_courses()

            elif choice == "2":
                self.add_course_interactive()

            elif choice == "3":
                course = self.choose_course(
                    "Select Active Course"
                )
                if course:
                    self.output(
                        f"\nActive course: "
                        f"{course['code']} - "
                        f"{course['name']}"
                    )

            elif choice == "4":
                if active:
                    self.print_course_progress(
                        active["id"]
                    )
                else:
                    self.output(
                        "\nNo active course. "
                        "Add or select a course first."
                    )

            elif choice == "5":
                self.add_topic_interactive()

            elif choice == "6":
                self.update_topic_interactive()

            elif choice == "7":
                self.link_document_interactive()

            elif choice == "8":
                self.show_linked_sources()

            elif choice == "9":
                break

            else:
                self.output(
                    "\nInvalid choice. "
                    "Please enter 1 to 9."
                )


def course_manager_menu():
    """Run Course Manager using the default terminal input/output."""
    CourseCLI().run()
