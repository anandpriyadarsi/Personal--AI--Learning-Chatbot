import assignment_file_importer


def test_fallback_currently_splits_math_prompt_matrix_and_instruction():
    """
    Characterization of the current paragraph-fallback defect.

    When no top-level question numbering is detected, blank lines are
    treated as question boundaries. A prompt, its matrix, and its final
    instruction therefore become separate question records.
    """
    text = """Find the rank of the matrix A.

A = [1 2 3]
    [2 4 6]
    [1 1 1]

Use elementary row operations and justify your answer."""

    rows = (
        assignment_file_importer
        .extract_questions_from_plain_text(text)
    )

    assert len(rows) == 3

    assert rows[0]["text"] == (
        "Find the rank of the matrix A."
    )

    assert rows[1]["text"] == (
        "A = [1 2 3]\n"
        "    [2 4 6]\n"
        "    [1 1 1]"
    )

    assert rows[2]["text"] == (
        "Use elementary row operations and justify your answer."
    )

    assert all(
        row["source_question_number"] is None
        for row in rows
    )


def test_nested_numbered_equations_can_override_real_question_numbering():
    """
    Characterization of the current numbered-question defect.

    The importer selects whichever QUESTION_PATTERNS family produces
    the most matches. If numbered equations/subparts such as (1), (2),
    (3) outnumber real top-level questions 1., 2., the equation pattern
    wins. The top-level prompt can disappear and the next real question
    can be merged into the last equation record.
    """
    text = """1. Solve the following system of equations.
(1) x + y = 4
(2) x - y = 2
(3) 2x + y = 5
2. State whether the system is consistent."""

    rows = (
        assignment_file_importer
        .extract_questions_from_plain_text(text)
    )

    assert len(rows) == 3

    assert [
        row["source_question_number"]
        for row in rows
    ] == ["1", "2", "3"]

    assert rows[0]["text"] == "x + y = 4"
    assert rows[1]["text"] == "x - y = 2"

    assert rows[2]["text"] == (
        "2x + y = 5\n"
        "2. State whether the system is consistent."
    )

    combined = "\n".join(
        row["text"]
        for row in rows
    )

    assert (
        "Solve the following system of equations."
        not in combined
    )
