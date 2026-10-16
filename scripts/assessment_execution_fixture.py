"""Launch an isolated synthetic Assessment Studio candidate; never opens user data.

python scripts/assessment_execution_fixture.py --port 8766
A new private temporary store is created. For restart, pass its printed --resume
folder; only a fixture-owned marker and manifest permit that route.
"""

from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from personal_learning_assistant.repositories.sqlite.migration_runner import (
    apply_migrations,
)
from personal_learning_assistant.services.assessment_runner_service import (
    AssessmentRunnerService,
)
from personal_learning_assistant.services.assessment_execution_service import (
    AssessmentExecutionService,
)
from personal_learning_assistant.ui.web.assessment_execution_candidate import (
    create_candidate_app,
)


def create_fixture(directory, *, now_fn=None):
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    (directory / "fixture-owner.json").write_text(
        json.dumps({"scope": "disposable-synthetic-only", "version": 1}),
        encoding="utf-8",
    )
    path = directory / "synthetic.db"
    apply_migrations(path)
    now = (now_fn() if now_fn else datetime.now(timezone.utc)).isoformat()
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO courses(id,code,name,status,description,created_at,updated_at) VALUES ('fixture-course','MA103N','Synthetic Linear Algebra','active','',?,?)",
            (now, now),
        )
        for kind in ("online", "paper"):
            aid = "fixture-" + kind
            db.execute(
                "INSERT INTO assessments(id,course_id,assessment_type,title,status,max_points_milli,created_at,updated_at) VALUES (?,'fixture-course','practice',?,'pending',6000,?,?)",
                (
                    aid,
                    (
                        "Practice with pauses"
                        if kind == "online"
                        else "Linear Algebra · Paper Practice"
                    ),
                    now,
                    now,
                ),
            )
            db.execute(
                "INSERT INTO assessment_runtime_specs(assessment_id,mode,duration_minutes,instructions_text,origin,package_id,package_revision,created_at,updated_at) VALUES (?,'practice',30,?,'external_package',?,1,?,?)",
                (
                    aid,
                    "Work independently. Pause explicitly when you need a break.",
                    "synthetic." + kind,
                    now,
                    now,
                ),
            )
            for ordinal in (1, 2):
                qid = aid + "-q" + str(ordinal)
                text = (
                    (
                        "Explain how LU factorization solves Ax = b. Show each triangular solve."
                        if ordinal == 1
                        else "Explain why rank(A) = n guarantees a unique solution for an n × n system."
                    )
                    if kind == "paper"
                    else (
                        "In A = LU, which factor is lower triangular?"
                        if ordinal == 1
                        else "Which condition guarantees a unique solution for an n × n matrix?"
                    )
                )
                solution = (
                    "Factor A = LU. Solve Ly = b by forward substitution. Solve Ux = y by backward substitution."
                    if ordinal == 1
                    else "Full column rank gives a trivial null space. A square full-rank matrix is invertible, so x = A⁻¹b is unique."
                )
                rubric = "Award up to 3 marks for a complete correct argument. Accept any correct equivalent proof. Do not award credit for an unsupported conclusion."
                if kind == "paper" and ordinal == 1:
                    steps = []
                    for key, label, work, deps in [
                        ("factor", "Factorization", "State A = LU.", []),
                        (
                            "forward",
                            "Forward substitution",
                            "Solve Ly = b.",
                            ["factor"],
                        ),
                        ("back", "Backward substitution", "Solve Ux = y.", ["forward"]),
                    ]:
                        steps.append(
                            dict(
                                id=key,
                                label=label,
                                expected_work=work,
                                max_marks_milli=1000,
                                prerequisites=deps,
                                award_when=["Correct mathematical method"],
                                do_not_award_when=[
                                    "Unsupported equation or wrong direction"
                                ],
                                allowed_awards_milli=[0, 500, 1000],
                                alternative_group=None,
                            )
                        )
                    rubric = json.dumps(
                        dict(
                            schema="anvaya.subjective-rubric",
                            version=1,
                            question_id=qid,
                            total_marks_milli=3000,
                            grading_increment_milli=500,
                            steps=steps,
                            common_mistakes=[
                                "Interchanging forward and backward substitution"
                            ],
                            review_required=False,
                        )
                    )
                db.execute(
                    "INSERT INTO questions(id,assessment_id,ordinal,question_text,max_marks_milli,status,user_notes,created_at,updated_at) VALUES (?,?,?,?,3000,'not_started','',?,?)",
                    (qid, aid, ordinal, text, now, now),
                )
                db.execute(
                    "INSERT INTO assessment_question_specs(question_id,package_question_id,question_number,section_label,question_type,negative_marks_milli,scoring_policy,difficulty,expected_method,chapter_label,subtopic_label,concepts_json,authoring_confidence,solution_text,rubric_text,answer_json,source_kind,created_at,updated_at) VALUES (?,?,?,'A',?,0,'standard','medium','','Systems','Reasoning','[]',0.99,?,?,?,'original',?,?)",
                    (
                        qid,
                        qid,
                        str(ordinal),
                        "long_subjective" if kind == "paper" else "mcq",
                        solution,
                        rubric if kind == "paper" else "",
                        json.dumps(
                            {"correct_option_ids": ["B"], "accepted_answers": []}
                        ),
                        now,
                        now,
                    ),
                )
                if kind == "online":
                    for pos, (oid, label) in enumerate(
                        [
                            (
                                "A",
                                (
                                    "The upper triangular factor"
                                    if ordinal == 1
                                    else "rank(A) < n"
                                ),
                            ),
                            (
                                "B",
                                (
                                    "The lower triangular factor"
                                    if ordinal == 1
                                    else "rank(A) = n"
                                ),
                            ),
                        ],
                        1,
                    ):
                        db.execute(
                            "INSERT INTO question_options VALUES (?,?,?,?,?)",
                            (qid, oid, pos, label, int(oid == "B")),
                        )
        db.executescript(
            (ROOT / "scripts/fixtures/assessment_execution_candidate.sql").read_text(
                encoding="utf-8"
            )
        )
    old = AssessmentRunnerService(path, now_fn=now_fn)
    service = AssessmentExecutionService(path, now_fn=now_fn)
    ids = {}
    for kind in ("online", "paper"):
        sid = old.start("fixture-" + kind, confirmed=True)["session_id"]
        service.adopt(
            sid,
            kind="online_timed" if kind == "online" else "paper_subjective",
            reviewed_fixture=kind == "paper",
        )
        ids[kind] = sid
    (directory / "sessions.json").write_text(json.dumps(ids), encoding="utf-8")
    key = secrets.token_bytes(48)
    (directory / "fixture-signing-key").write_bytes(key)
    return service, ids, key


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument(
        "--resume", type=Path, help="Previously generated synthetic fixture folder only"
    )
    args = parser.parse_args()
    if args.resume:
        directory = args.resume.absolute()
        if directory.is_symlink() or any(p.is_symlink() for p in directory.parents):
            raise ValueError("Fixture symlinks are not allowed.")
        marker = json.loads((directory / "fixture-owner.json").read_text())
        if marker != {"scope": "disposable-synthetic-only", "version": 1}:
            raise ValueError("Unknown fixture ownership.")
        ids = json.loads((directory / "sessions.json").read_text())
        key = (directory / "fixture-signing-key").read_bytes()
        service = AssessmentExecutionService(directory / "synthetic.db")
        for sid in ids.values():
            service.state(sid)
    else:
        directory = (
            Path(tempfile.mkdtemp(prefix="anvaya-assessment-preview-")) / "fixture"
        )
        service, ids, key = create_fixture(directory)
    print("Synthetic preview only. Production activation is BLOCKED.", flush=True)
    print(f"Open the demo homepage: http://127.0.0.1:{args.port}/", flush=True)
    for kind, sid in ids.items():
        print(
            f"{kind}: http://127.0.0.1:{args.port}/assessments/candidate/sessions/{sid}",
            flush=True,
        )
    print(
        "Restart with: python scripts/assessment_execution_fixture.py --port "
        + str(args.port)
        + ' --resume "'
        + str(directory)
        + '"',
        flush=True,
    )
    create_candidate_app(service, secret_key=key, landing_sessions=ids).run(
        host="127.0.0.1", port=args.port, debug=False, use_reloader=False
    )


if __name__ == "__main__":
    main()
