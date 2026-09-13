import assignment_file_importer


def test_fallback_preserves_single_math_prompt_matrix_and_instruction():
    """
    Regression test for the paragraph-fallback defect.

    A single unnumbered math question may contain blank lines between
    the prompt, matrix, and final instruction. Those blank lines must
    not create three separate question records.
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

    assert len(rows) == 1

    assert rows[0]["text"] == (
        "Find the rank of the matrix A.\n\n"
        "A = [1 2 3]\n"
        "    [2 4 6]\n"
        "    [1 1 1]\n\n"
        "Use elementary row operations and justify your answer."
    )

    assert rows[0]["source_question_number"] is None


def test_top_level_numbering_wins_over_parenthesised_equation_labels():
    """
    Regression test for the numbered-question defect.

    Parenthesised equation labels such as (1), (2), (3) must stay
    inside the real top-level question instead of becoming separate
    question records.
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

    assert len(rows) == 2

    assert [
        row["source_question_number"]
        for row in rows
    ] == ["1", "2"]

    assert rows[0]["text"] == (
        "Solve the following system of equations.\n"
        "(1) x + y = 4\n"
        "(2) x - y = 2\n"
        "(3) 2x + y = 5"
    )

    assert rows[1]["text"] == (
        "State whether the system is consistent."
    )


def test_parenthesised_question_numbering_still_works_when_it_is_primary():
    """
    Regression protection: if a sheet actually uses parenthesised
    numbers as the main question markers, the importer should still
    split them correctly when no stronger top-level numbering exists.
    """
    text = """(1) Define a vector space.

(2) Give one example of a subspace."""

    rows = (
        assignment_file_importer
        .extract_questions_from_plain_text(text)
    )

    assert len(rows) == 2

    assert [
        row["source_question_number"]
        for row in rows
    ] == ["1", "2"]

    assert rows[0]["text"] == "Define a vector space."
    assert rows[1]["text"] == "Give one example of a subspace."
