"""SQLite persistence for Assessment Studio Phase B package import/review."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Mapping, Sequence

from personal_learning_assistant.repositories.sqlite.connection import transaction


_REQUIRED_TABLES = {
    "courses",
    "topics",
    "topic_aliases",
    "assessments",
    "assessment_topics",
    "questions",
    "question_topic_mappings",
    "question_sources",
    "assessment_import_batches",
    "assessment_import_questions",
    "assessment_import_question_options",
    "assessment_runtime_specs",
    "assessment_question_specs",
    "question_options",
}


class AssessmentImportRepositoryError(RuntimeError):
    pass


class AssessmentImportRepositorySchemaError(AssessmentImportRepositoryError):
    pass


class AssessmentImportRepositoryNotFoundError(AssessmentImportRepositoryError):
    pass


class AssessmentImportRepositoryConflictError(AssessmentImportRepositoryError):
    pass


class AssessmentImportRepositoryDataError(AssessmentImportRepositoryError):
    pass


def _dict(row):
    return dict(row) if row is not None else None


class SQLiteAssessmentImportRepository:
    """Repository for package staging, review commands, and final approval."""

    def __init__(self, connection: sqlite3.Connection):
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("explicit sqlite3.Connection required")
        self.connection = connection
        self.connection.row_factory = sqlite3.Row
        self._validate_schema()

    def _validate_schema(self) -> None:
        tables = {
            str(row[0])
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        missing = sorted(_REQUIRED_TABLES - tables)
        if missing:
            raise AssessmentImportRepositorySchemaError(
                "Assessment Package schema is unavailable; missing: {}".format(
                    ", ".join(missing)
                )
            )

    def resolve_course_by_code(self, course_code: str):
        row = self.connection.execute(
            "SELECT id, code, name FROM courses "
            "WHERE code=? COLLATE NOCASE AND deleted_at IS NULL",
            (str(course_code).strip(),),
        ).fetchone()
        return _dict(row)

    def get_course(self, course_id: str):
        row = self.connection.execute(
            "SELECT id, code, name FROM courses "
            "WHERE id=? AND deleted_at IS NULL",
            (str(course_id),),
        ).fetchone()
        return _dict(row)

    def topic_catalogue(self, course_id: str):
        rows = self.connection.execute(
            "SELECT id, name, normalized_name FROM topics "
            "WHERE course_id=? AND deleted_at IS NULL "
            "ORDER BY position, name COLLATE NOCASE",
            (str(course_id),),
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            aliases = self.connection.execute(
                "SELECT alias, normalized_alias FROM topic_aliases "
                "WHERE topic_id=? ORDER BY alias COLLATE NOCASE",
                (str(item["id"]),),
            ).fetchall()
            item["aliases"] = tuple(dict(alias) for alias in aliases)
            result.append(item)
        return tuple(result)

    def find_batch_identity(self, package_id: str, package_revision: int):
        row = self.connection.execute(
            "SELECT id, source_sha256, status, assessment_id "
            "FROM assessment_import_batches "
            "WHERE package_id=? AND package_revision=?",
            (str(package_id), int(package_revision)),
        ).fetchone()
        return _dict(row)

    def list_batches(self, *, limit: int = 50):
        rows = self.connection.execute(
            "SELECT b.id, b.package_id, b.package_revision, b.title, "
            "b.assessment_type, b.mode, b.status, b.revision, b.source_filename, "
            "b.created_at, b.updated_at, b.assessment_id, "
            "c.code AS course_code, c.name AS course_name, "
            "(SELECT COUNT(*) FROM assessment_import_questions q "
            " WHERE q.batch_id=b.id) AS question_count "
            "FROM assessment_import_batches b "
            "JOIN courses c ON c.id=b.course_id "
            "ORDER BY b.created_at DESC, b.id DESC LIMIT ?",
            (max(1, min(int(limit), 200)),),
        ).fetchall()
        return tuple(dict(row) for row in rows)

    def _question_options(self, question_id: str):
        rows = self.connection.execute(
            "SELECT option_id, position, option_text, is_correct "
            "FROM assessment_import_question_options "
            "WHERE question_id=? ORDER BY position",
            (str(question_id),),
        ).fetchall()
        return tuple(dict(row) for row in rows)

    def get_question(self, question_id: str):
        row = self.connection.execute(
            "SELECT q.*, t.name AS selected_topic_name "
            "FROM assessment_import_questions q "
            "LEFT JOIN topics t ON t.id=q.selected_topic_id "
            "WHERE q.id=?",
            (str(question_id),),
        ).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["options"] = self._question_options(str(item["id"]))
        return item

    def get_batch(self, batch_id: str):
        row = self.connection.execute(
            "SELECT b.*, c.code AS course_code, c.name AS course_name "
            "FROM assessment_import_batches b "
            "JOIN courses c ON c.id=b.course_id "
            "WHERE b.id=?",
            (str(batch_id),),
        ).fetchone()
        if row is None:
            return None
        batch = dict(row)
        questions = self.connection.execute(
            "SELECT q.*, t.name AS selected_topic_name "
            "FROM assessment_import_questions q "
            "LEFT JOIN topics t ON t.id=q.selected_topic_id "
            "WHERE q.batch_id=? ORDER BY q.ordinal",
            (str(batch_id),),
        ).fetchall()
        decorated = []
        for question in questions:
            item = dict(question)
            item["options"] = self._question_options(str(item["id"]))
            decorated.append(item)
        batch["questions"] = tuple(decorated)
        return batch

    def create_batch(
        self,
        batch: Mapping[str, Any],
        questions: Sequence[Mapping[str, Any]],
    ):
        try:
            with transaction(self.connection, immediate=True):
                self.connection.execute(
                    "INSERT INTO assessment_import_batches "
                    "(id, package_id, package_revision, package_schema, package_version, "
                    "source_filename, source_sha256, course_id, title, assessment_type, "
                    "mode, duration_minutes, total_marks_milli, instructions_text, "
                    "authoring_engine, authoring_model, authoring_purpose, status, "
                    "package_json, validation_notes_json, revision, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                    "'review', ?, ?, 1, ?, ?)",
                    (
                        str(batch["id"]),
                        str(batch["package_id"]),
                        int(batch["package_revision"]),
                        str(batch["package_schema"]),
                        int(batch["package_version"]),
                        str(batch.get("source_filename") or ""),
                        str(batch["source_sha256"]),
                        str(batch["course_id"]),
                        str(batch["title"]),
                        str(batch["assessment_type"]),
                        str(batch["mode"]),
                        int(batch["duration_minutes"]),
                        int(batch["total_marks_milli"]),
                        str(batch.get("instructions_text") or ""),
                        str(batch["authoring_engine"]),
                        str(batch.get("authoring_model") or ""),
                        str(batch["authoring_purpose"]),
                        str(batch["package_json"]),
                        str(batch.get("validation_notes_json") or "[]"),
                        str(batch["created_at"]),
                        str(batch["updated_at"]),
                    ),
                )
                for question in questions:
                    self._insert_staged_question(self.connection, question)
        except sqlite3.IntegrityError as error:
            if (
                "assessment_import_batches.package_id" in str(error)
                or "UNIQUE constraint failed: assessment_import_batches.package_id" in str(error)
            ):
                raise AssessmentImportRepositoryConflictError(
                    "This package ID/revision is already staged."
                ) from error
            raise
        return self.get_batch(str(batch["id"]))

    @staticmethod
    def _insert_staged_question(connection, question: Mapping[str, Any]) -> None:
        connection.execute(
            "INSERT INTO assessment_import_questions "
            "(id, batch_id, package_question_id, ordinal, question_number, "
            "section_label, question_type, question_text, max_marks_milli, "
            "negative_marks_milli, scoring_policy, difficulty, expected_method, "
            "estimated_seconds, chapter_label, raw_topic_label, subtopic_label, "
            "concepts_json, authoring_confidence, mapping_confidence, "
            "selected_topic_id, review_required, solution_text, rubric_text, "
            "answer_json, source_kind, source_label, source_page, source_locator, "
            "created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
            "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(question["id"]),
                str(question["batch_id"]),
                str(question["package_question_id"]),
                int(question["ordinal"]),
                str(question.get("question_number") or ""),
                str(question.get("section_label") or ""),
                str(question["question_type"]),
                str(question["question_text"]),
                question.get("max_marks_milli"),
                int(question.get("negative_marks_milli") or 0),
                str(question.get("scoring_policy") or "standard"),
                str(question.get("difficulty") or ""),
                str(question.get("expected_method") or ""),
                question.get("estimated_seconds"),
                str(question.get("chapter_label") or ""),
                str(question.get("raw_topic_label") or ""),
                str(question.get("subtopic_label") or ""),
                str(question.get("concepts_json") or "[]"),
                question.get("authoring_confidence"),
                question.get("mapping_confidence"),
                question.get("selected_topic_id"),
                1 if question.get("review_required") else 0,
                str(question.get("solution_text") or ""),
                str(question.get("rubric_text") or ""),
                str(question.get("answer_json") or "{}"),
                str(question.get("source_kind") or ""),
                str(question.get("source_label") or ""),
                question.get("source_page"),
                str(question.get("source_locator") or ""),
                str(question["created_at"]),
                str(question["updated_at"]),
            ),
        )
        for option in question.get("options") or ():
            connection.execute(
                "INSERT INTO assessment_import_question_options "
                "(question_id, option_id, position, option_text, is_correct) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    str(question["id"]),
                    str(option["option_id"]),
                    int(option["position"]),
                    str(option["option_text"]),
                    1 if option.get("is_correct") else 0,
                ),
            )

    def update_batch_metadata(
        self,
        batch_id: str,
        *,
        title: str,
        assessment_type: str,
        mode: str,
        duration_minutes: int,
        total_marks_milli: int,
        instructions_text: str,
        now: str,
    ):
        with transaction(self.connection, immediate=True):
            cursor = self.connection.execute(
                "UPDATE assessment_import_batches SET title=?, assessment_type=?, "
                "mode=?, duration_minutes=?, total_marks_milli=?, instructions_text=?, "
                "updated_at=?, revision=revision+1 "
                "WHERE id=? AND status='review'",
                (
                    str(title),
                    str(assessment_type),
                    str(mode),
                    int(duration_minutes),
                    int(total_marks_milli),
                    str(instructions_text),
                    str(now),
                    str(batch_id),
                ),
            )
            if cursor.rowcount != 1:
                self._raise_batch_write_problem(batch_id)
        return self.get_batch(batch_id)

    def update_question(
        self,
        question_id: str,
        record: Mapping[str, Any],
        options: Sequence[Mapping[str, Any]],
        *,
        now: str,
    ):
        with transaction(self.connection, immediate=True):
            row = self.connection.execute(
                "SELECT q.batch_id FROM assessment_import_questions q "
                "JOIN assessment_import_batches b ON b.id=q.batch_id "
                "WHERE q.id=? AND b.status='review'",
                (str(question_id),),
            ).fetchone()
            if row is None:
                self._raise_question_write_problem(question_id)
            cursor = self.connection.execute(
                "UPDATE assessment_import_questions SET "
                "question_number=?, section_label=?, question_type=?, question_text=?, "
                "max_marks_milli=?, negative_marks_milli=?, scoring_policy=?, "
                "difficulty=?, expected_method=?, estimated_seconds=?, chapter_label=?, "
                "raw_topic_label=?, subtopic_label=?, concepts_json=?, "
                "authoring_confidence=?, mapping_confidence=?, selected_topic_id=?, "
                "review_required=?, solution_text=?, rubric_text=?, answer_json=?, "
                "source_kind=?, source_label=?, source_page=?, source_locator=?, "
                "updated_at=? WHERE id=?",
                (
                    str(record.get("question_number") or ""),
                    str(record.get("section_label") or ""),
                    str(record["question_type"]),
                    str(record["question_text"]),
                    record.get("max_marks_milli"),
                    int(record.get("negative_marks_milli") or 0),
                    str(record.get("scoring_policy") or "standard"),
                    str(record.get("difficulty") or ""),
                    str(record.get("expected_method") or ""),
                    record.get("estimated_seconds"),
                    str(record.get("chapter_label") or ""),
                    str(record.get("raw_topic_label") or ""),
                    str(record.get("subtopic_label") or ""),
                    str(record.get("concepts_json") or "[]"),
                    record.get("authoring_confidence"),
                    record.get("mapping_confidence"),
                    record.get("selected_topic_id"),
                    1 if record.get("review_required") else 0,
                    str(record.get("solution_text") or ""),
                    str(record.get("rubric_text") or ""),
                    str(record.get("answer_json") or "{}"),
                    str(record.get("source_kind") or ""),
                    str(record.get("source_label") or ""),
                    record.get("source_page"),
                    str(record.get("source_locator") or ""),
                    str(now),
                    str(question_id),
                ),
            )
            if cursor.rowcount != 1:
                raise AssessmentImportRepositoryNotFoundError("Staged question not found.")
            self.connection.execute(
                "DELETE FROM assessment_import_question_options WHERE question_id=?",
                (str(question_id),),
            )
            for option in options:
                self.connection.execute(
                    "INSERT INTO assessment_import_question_options "
                    "(question_id, option_id, position, option_text, is_correct) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        str(question_id),
                        str(option["option_id"]),
                        int(option["position"]),
                        str(option["option_text"]),
                        1 if option.get("is_correct") else 0,
                    ),
                )
            self.connection.execute(
                "UPDATE assessment_import_batches SET updated_at=?, revision=revision+1 "
                "WHERE id=?",
                (str(now), str(row["batch_id"])),
            )
        return self.get_question(question_id)

    def _batch_question_ids(self, connection, batch_id: str):
        return [
            str(row["id"])
            for row in connection.execute(
                "SELECT id FROM assessment_import_questions "
                "WHERE batch_id=? ORDER BY ordinal",
                (str(batch_id),),
            ).fetchall()
        ]

    @staticmethod
    def _rewrite_order(connection, batch_id: str, ordered_ids: Sequence[str]) -> None:
        if not ordered_ids:
            return
        # Move rows one-by-one to disjoint temporary ordinals. A single
        # UPDATE ordinal=ordinal+N can violate SQLite's UNIQUE(batch, ordinal)
        # constraint transiently depending on row update order.
        for position, question_id in enumerate(ordered_ids, start=1):
            connection.execute(
                "UPDATE assessment_import_questions SET ordinal=? "
                "WHERE id=? AND batch_id=?",
                (1000000 + position, str(question_id), str(batch_id)),
            )
        for ordinal, question_id in enumerate(ordered_ids, start=1):
            connection.execute(
                "UPDATE assessment_import_questions SET ordinal=? "
                "WHERE id=? AND batch_id=?",
                (ordinal, str(question_id), str(batch_id)),
            )

    def reorder_question(self, question_id: str, direction: str, *, now: str):
        with transaction(self.connection, immediate=True):
            row = self.connection.execute(
                "SELECT q.batch_id FROM assessment_import_questions q "
                "JOIN assessment_import_batches b ON b.id=q.batch_id "
                "WHERE q.id=? AND b.status='review'",
                (str(question_id),),
            ).fetchone()
            if row is None:
                self._raise_question_write_problem(question_id)
            batch_id = str(row["batch_id"])
            order = self._batch_question_ids(self.connection, batch_id)
            index = order.index(str(question_id))
            target = index - 1 if direction == "up" else index + 1
            if target < 0 or target >= len(order):
                return
            order[index], order[target] = order[target], order[index]
            self._rewrite_order(self.connection, batch_id, order)
            self.connection.execute(
                "UPDATE assessment_import_batches SET updated_at=?, revision=revision+1 "
                "WHERE id=?",
                (str(now), batch_id),
            )

    def remove_question(self, question_id: str, *, now: str):
        with transaction(self.connection, immediate=True):
            row = self.connection.execute(
                "SELECT q.batch_id FROM assessment_import_questions q "
                "JOIN assessment_import_batches b ON b.id=q.batch_id "
                "WHERE q.id=? AND b.status='review'",
                (str(question_id),),
            ).fetchone()
            if row is None:
                self._raise_question_write_problem(question_id)
            batch_id = str(row["batch_id"])
            self.connection.execute(
                "DELETE FROM assessment_import_questions WHERE id=?",
                (str(question_id),),
            )
            order = self._batch_question_ids(self.connection, batch_id)
            self._rewrite_order(self.connection, batch_id, order)
            self.connection.execute(
                "UPDATE assessment_import_batches SET updated_at=?, revision=revision+1 "
                "WHERE id=?",
                (str(now), batch_id),
            )

    def split_question(
        self,
        question_id: str,
        first: Mapping[str, Any],
        second: Mapping[str, Any],
        *,
        now: str,
    ):
        with transaction(self.connection, immediate=True):
            row = self.connection.execute(
                "SELECT q.batch_id, q.ordinal FROM assessment_import_questions q "
                "JOIN assessment_import_batches b ON b.id=q.batch_id "
                "WHERE q.id=? AND b.status='review'",
                (str(question_id),),
            ).fetchone()
            if row is None:
                self._raise_question_write_problem(question_id)
            if self.connection.execute(
                "SELECT COUNT(*) FROM assessment_import_question_options "
                "WHERE question_id=?",
                (str(question_id),),
            ).fetchone()[0]:
                raise AssessmentImportRepositoryDataError(
                    "Objective questions with options cannot be split safely."
                )
            batch_id = str(row["batch_id"])
            original_order = self._batch_question_ids(self.connection, batch_id)
            index = original_order.index(str(question_id))

            self.connection.execute(
                "UPDATE assessment_import_questions SET question_text=?, "
                "question_number=?, max_marks_milli=NULL, negative_marks_milli=0, "
                "solution_text='', rubric_text='', answer_json='{}', "
                "review_required=1, updated_at=? WHERE id=?",
                (
                    str(first["question_text"]),
                    str(first.get("question_number") or ""),
                    str(now),
                    str(question_id),
                ),
            )
            second_record = dict(second)
            second_record["batch_id"] = batch_id
            second_record["ordinal"] = len(original_order) + 10000
            self._insert_staged_question(self.connection, second_record)
            new_order = (
                original_order[: index + 1]
                + [str(second_record["id"])]
                + original_order[index + 1 :]
            )
            self._rewrite_order(self.connection, batch_id, new_order)
            self.connection.execute(
                "UPDATE assessment_import_batches SET updated_at=?, revision=revision+1 "
                "WHERE id=?",
                (str(now), batch_id),
            )
        return self.get_batch(batch_id)

    def merge_with_next(
        self,
        question_id: str,
        merged: Mapping[str, Any],
        *,
        now: str,
    ):
        with transaction(self.connection, immediate=True):
            row = self.connection.execute(
                "SELECT q.batch_id, q.ordinal FROM assessment_import_questions q "
                "JOIN assessment_import_batches b ON b.id=q.batch_id "
                "WHERE q.id=? AND b.status='review'",
                (str(question_id),),
            ).fetchone()
            if row is None:
                self._raise_question_write_problem(question_id)
            batch_id = str(row["batch_id"])
            next_row = self.connection.execute(
                "SELECT id FROM assessment_import_questions "
                "WHERE batch_id=? AND ordinal=?",
                (batch_id, int(row["ordinal"]) + 1),
            ).fetchone()
            if next_row is None:
                raise AssessmentImportRepositoryDataError(
                    "There is no next question to merge."
                )
            next_id = str(next_row["id"])
            option_count = self.connection.execute(
                "SELECT COUNT(*) FROM assessment_import_question_options "
                "WHERE question_id IN (?, ?)",
                (str(question_id), next_id),
            ).fetchone()[0]
            if option_count:
                raise AssessmentImportRepositoryDataError(
                    "Objective questions with options cannot be merged safely."
                )
            self.connection.execute(
                "UPDATE assessment_import_questions SET question_text=?, "
                "question_number=?, section_label=?, question_type=?, "
                "max_marks_milli=?, negative_marks_milli=?, scoring_policy=?, "
                "difficulty=?, expected_method=?, estimated_seconds=?, "
                "chapter_label=?, raw_topic_label=?, subtopic_label=?, concepts_json=?, "
                "authoring_confidence=?, mapping_confidence=?, selected_topic_id=?, "
                "review_required=1, solution_text=?, rubric_text=?, answer_json=?, "
                "source_kind=?, source_label=?, source_page=?, source_locator=?, "
                "updated_at=? WHERE id=?",
                (
                    str(merged["question_text"]),
                    str(merged.get("question_number") or ""),
                    str(merged.get("section_label") or ""),
                    str(merged["question_type"]),
                    merged.get("max_marks_milli"),
                    int(merged.get("negative_marks_milli") or 0),
                    str(merged.get("scoring_policy") or "standard"),
                    str(merged.get("difficulty") or ""),
                    str(merged.get("expected_method") or ""),
                    merged.get("estimated_seconds"),
                    str(merged.get("chapter_label") or ""),
                    str(merged.get("raw_topic_label") or ""),
                    str(merged.get("subtopic_label") or ""),
                    str(merged.get("concepts_json") or "[]"),
                    merged.get("authoring_confidence"),
                    merged.get("mapping_confidence"),
                    merged.get("selected_topic_id"),
                    str(merged.get("solution_text") or ""),
                    str(merged.get("rubric_text") or ""),
                    str(merged.get("answer_json") or "{}"),
                    str(merged.get("source_kind") or ""),
                    str(merged.get("source_label") or ""),
                    merged.get("source_page"),
                    str(merged.get("source_locator") or ""),
                    str(now),
                    str(question_id),
                ),
            )
            self.connection.execute(
                "DELETE FROM assessment_import_questions WHERE id=?",
                (next_id,),
            )
            order = self._batch_question_ids(self.connection, batch_id)
            self._rewrite_order(self.connection, batch_id, order)
            self.connection.execute(
                "UPDATE assessment_import_batches SET updated_at=?, revision=revision+1 "
                "WHERE id=?",
                (str(now), batch_id),
            )
        return self.get_batch(batch_id)

    def reject_batch(self, batch_id: str, *, now: str):
        with transaction(self.connection, immediate=True):
            cursor = self.connection.execute(
                "UPDATE assessment_import_batches SET status='rejected', "
                "rejected_at=?, updated_at=?, revision=revision+1 "
                "WHERE id=? AND status='review'",
                (str(now), str(now), str(batch_id)),
            )
            if cursor.rowcount != 1:
                self._raise_batch_write_problem(batch_id)
        return self.get_batch(batch_id)

    def approve_batch(self, batch_id: str, canonical: Mapping[str, Any], *, now: str):
        with transaction(self.connection, immediate=True):
            batch = self.connection.execute(
                "SELECT status, assessment_id FROM assessment_import_batches WHERE id=?",
                (str(batch_id),),
            ).fetchone()
            if batch is None:
                raise AssessmentImportRepositoryNotFoundError("Import batch not found.")
            if str(batch["status"]) == "approved":
                return str(batch["assessment_id"])
            if str(batch["status"]) != "review":
                raise AssessmentImportRepositoryConflictError(
                    "Only a batch under review can be approved."
                )

            assessment = canonical["assessment"]
            self.connection.execute(
                "INSERT INTO assessments "
                "(id, course_id, assessment_type, title, due_on, due_time, status, "
                "weight_bps, max_points_milli, earned_points_milli, description, "
                "created_at, updated_at, deleted_at) "
                "VALUES (?, ?, ?, ?, NULL, NULL, 'pending', NULL, ?, NULL, ?, ?, ?, NULL)",
                (
                    str(assessment["id"]),
                    str(assessment["course_id"]),
                    str(assessment["assessment_type"]),
                    str(assessment["title"]),
                    int(assessment["max_points_milli"]),
                    str(assessment.get("description") or ""),
                    str(now),
                    str(now),
                ),
            )
            runtime = canonical["runtime"]
            self.connection.execute(
                "INSERT INTO assessment_runtime_specs "
                "(assessment_id, mode, duration_minutes, instructions_text, origin, "
                "package_id, package_revision, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(assessment["id"]),
                    str(runtime["mode"]),
                    int(runtime["duration_minutes"]),
                    str(runtime.get("instructions_text") or ""),
                    str(runtime.get("origin") or "external_package"),
                    str(runtime.get("package_id") or ""),
                    int(runtime["package_revision"]),
                    str(now),
                    str(now),
                ),
            )
            for topic in canonical.get("assessment_topics") or ():
                self.connection.execute(
                    "INSERT INTO assessment_topics "
                    "(id, assessment_id, topic_id, raw_label, source, confidence, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(topic["id"]),
                        str(assessment["id"]),
                        str(topic["topic_id"]),
                        str(topic.get("raw_label") or ""),
                        "assessment_package_review",
                        topic.get("confidence"),
                        str(now),
                    ),
                )

            for question in canonical["questions"]:
                self.connection.execute(
                    "INSERT INTO questions "
                    "(id, assessment_id, ordinal, question_text, max_marks_milli, "
                    "status, user_notes, import_batch_id, created_at, updated_at, deleted_at) "
                    "VALUES (?, ?, ?, ?, ?, 'not_started', '', ?, ?, ?, NULL)",
                    (
                        str(question["id"]),
                        str(assessment["id"]),
                        int(question["ordinal"]),
                        str(question["question_text"]),
                        int(question["max_marks_milli"]),
                        str(batch_id),
                        str(now),
                        str(now),
                    ),
                )
                spec = question["spec"]
                self.connection.execute(
                    "INSERT INTO assessment_question_specs "
                    "(question_id, package_question_id, question_number, section_label, "
                    "question_type, negative_marks_milli, scoring_policy, difficulty, "
                    "expected_method, estimated_seconds, chapter_label, subtopic_label, "
                    "concepts_json, authoring_confidence, solution_text, rubric_text, "
                    "answer_json, source_kind, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(question["id"]),
                        str(spec.get("package_question_id") or ""),
                        str(spec.get("question_number") or ""),
                        str(spec.get("section_label") or ""),
                        str(spec["question_type"]),
                        int(spec.get("negative_marks_milli") or 0),
                        str(spec.get("scoring_policy") or "standard"),
                        str(spec.get("difficulty") or ""),
                        str(spec.get("expected_method") or ""),
                        spec.get("estimated_seconds"),
                        str(spec.get("chapter_label") or ""),
                        str(spec.get("subtopic_label") or ""),
                        str(spec.get("concepts_json") or "[]"),
                        spec.get("authoring_confidence"),
                        str(spec.get("solution_text") or ""),
                        str(spec.get("rubric_text") or ""),
                        str(spec.get("answer_json") or "{}"),
                        str(spec.get("source_kind") or ""),
                        str(now),
                        str(now),
                    ),
                )
                for option in question.get("options") or ():
                    self.connection.execute(
                        "INSERT INTO question_options "
                        "(question_id, option_id, position, option_text, is_correct) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (
                            str(question["id"]),
                            str(option["option_id"]),
                            int(option["position"]),
                            str(option["option_text"]),
                            1 if option.get("is_correct") else 0,
                        ),
                    )
                source = question.get("source")
                if source:
                    self.connection.execute(
                        "INSERT INTO question_sources "
                        "(id, question_id, document_id, resource_id, note_id, "
                        "page_number, locator, raw_source_label, created_at) "
                        "VALUES (?, ?, NULL, NULL, NULL, ?, ?, ?, ?)",
                        (
                            str(source["id"]),
                            str(question["id"]),
                            source.get("page_number"),
                            str(source.get("locator") or ""),
                            str(source.get("raw_source_label") or ""),
                            str(now),
                        ),
                    )
                mapping = question["mapping"]
                self.connection.execute(
                    "INSERT INTO question_topic_mappings "
                    "(id, question_id, topic_id, score, rank, method, state, reason, "
                    "created_at, reviewed_at) "
                    "VALUES (?, ?, ?, ?, 1, 'package_review_confirmed', 'confirmed', ?, ?, ?)",
                    (
                        str(mapping["id"]),
                        str(question["id"]),
                        str(mapping["topic_id"]),
                        mapping.get("score"),
                        str(mapping.get("reason") or ""),
                        str(now),
                        str(now),
                    ),
                )
                self.connection.execute(
                    "UPDATE assessment_import_questions "
                    "SET canonical_question_id=?, updated_at=? WHERE id=?",
                    (
                        str(question["id"]),
                        str(now),
                        str(question["staged_question_id"]),
                    ),
                )

            self.connection.execute(
                "UPDATE assessment_import_batches SET status='approved', assessment_id=?, "
                "approved_at=?, updated_at=?, revision=revision+1 WHERE id=?",
                (str(assessment["id"]), str(now), str(now), str(batch_id)),
            )
        return str(canonical["assessment"]["id"])

    def _raise_batch_write_problem(self, batch_id: str):
        row = self.connection.execute(
            "SELECT status FROM assessment_import_batches WHERE id=?",
            (str(batch_id),),
        ).fetchone()
        if row is None:
            raise AssessmentImportRepositoryNotFoundError("Import batch not found.")
        raise AssessmentImportRepositoryConflictError(
            "This import batch is no longer editable (status: {}).".format(
                row["status"]
            )
        )

    def _raise_question_write_problem(self, question_id: str):
        row = self.connection.execute(
            "SELECT b.status FROM assessment_import_questions q "
            "JOIN assessment_import_batches b ON b.id=q.batch_id "
            "WHERE q.id=?",
            (str(question_id),),
        ).fetchone()
        if row is None:
            raise AssessmentImportRepositoryNotFoundError("Staged question not found.")
        raise AssessmentImportRepositoryConflictError(
            "This staged question is no longer editable (batch status: {}).".format(
                row["status"]
            )
        )
