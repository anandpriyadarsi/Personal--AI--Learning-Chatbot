"""V12.1 Semester Grade & CGPA Intelligence.

Provides configurable, transparent academic-grade planning:
- semester course + credit setup
- assessment-weightage tracking
- current weighted course-score calculation
- final-score projection
- required remaining-assessment average
- configurable letter-grade / grade-point scale
- SGPA projection and target-SGPA what-if analysis

Important:
This module does NOT assume that a default grade boundary is official NITK policy.
The user can edit the grade scale. Calculations are planning estimates until the
official course grading scheme and grades are known.
"""

import json
import os
from copy import deepcopy

from knowledge_paths import BASE_DIR
from course_manager import choose_course, find_course
from assignment_exam_assistant import (
    list_assessments,
    assessment_weightage_percent,
    assessment_course_credits,
    weighted_course_score_contribution,
)


DATA_DIR = os.path.join(BASE_DIR, "data")
GRADE_CONFIG_FILE = os.path.join(
    DATA_DIR,
    "semester_grade_config.json"
)

CONFIG_VERSION = 1

# Planning default only. User should replace with the official/current scheme.
DEFAULT_GRADE_SCALE = [
    {"letter": "A+", "min_score": 90.0, "grade_point": 10.0},
    {"letter": "A",  "min_score": 80.0, "grade_point": 9.0},
    {"letter": "B+", "min_score": 70.0, "grade_point": 8.0},
    {"letter": "B",  "min_score": 60.0, "grade_point": 7.0},
    {"letter": "C",  "min_score": 50.0, "grade_point": 6.0},
    {"letter": "D",  "min_score": 40.0, "grade_point": 5.0},
    {"letter": "F",  "min_score": 0.0,  "grade_point": 0.0},
]


def _float_or_none(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def default_config():
    return {
        "version": CONFIG_VERSION,
        "semester_name": "Semester 1",
        "target_sgpa": None,
        "courses": [],
        "grade_scale": deepcopy(
            DEFAULT_GRADE_SCALE
        ),
    }


def load_config():
    os.makedirs(
        DATA_DIR,
        exist_ok=True
    )

    if not os.path.exists(
        GRADE_CONFIG_FILE
    ):
        return default_config()

    try:
        with open(
            GRADE_CONFIG_FILE,
            "r",
            encoding="utf-8"
        ) as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return default_config()

    if not isinstance(data, dict):
        return default_config()

    config = default_config()
    config.update(data)

    if not isinstance(
        config.get("courses"),
        list
    ):
        config["courses"] = []

    if not isinstance(
        config.get("grade_scale"),
        list
    ) or not config["grade_scale"]:
        config["grade_scale"] = deepcopy(
            DEFAULT_GRADE_SCALE
        )

    return config


def save_config(config):
    os.makedirs(
        DATA_DIR,
        exist_ok=True
    )

    temporary = (
        GRADE_CONFIG_FILE
        + ".tmp"
    )

    with open(
        temporary,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            config,
            file,
            indent=2,
            ensure_ascii=False
        )

    os.replace(
        temporary,
        GRADE_CONFIG_FILE
    )


def course_assessments(course_id):
    return [
        item
        for item in list_assessments(
            include_completed=True
        )
        if str(
            item.get("course_id")
        ) == str(course_id)
    ]


def course_grade_record(course_id):
    config = load_config()

    for item in config["courses"]:
        if str(
            item.get("course_id")
        ) == str(course_id):
            return item

    return None


def resolve_course_credits(
    course_id
):
    record = course_grade_record(
        course_id
    )

    if record:
        value = _float_or_none(
            record.get("credits")
        )
        if value is not None:
            return value

    course = find_course(
        course_id
    )

    if course:
        for key in (
            "credits",
            "credit",
            "course_credits",
        ):
            value = _float_or_none(
                course.get(key)
            )

            if value is not None:
                return value

    assessments = course_assessments(
        course_id
    )

    for item in assessments:
        value = assessment_course_credits(
            item,
            course=course
        )

        if value is not None:
            return value

    return None


def sort_grade_scale(scale):
    return sorted(
        scale,
        key=lambda item: float(
            item.get(
                "min_score",
                0
            )
        ),
        reverse=True
    )


def grade_for_score(
    score,
    scale=None
):
    if score is None:
        return None

    if scale is None:
        scale = load_config()[
            "grade_scale"
        ]

    for item in sort_grade_scale(
        scale
    ):
        minimum = _float_or_none(
            item.get("min_score")
        )

        if (
            minimum is not None
            and score >= minimum
        ):
            return {
                "letter": item.get(
                    "letter",
                    "?"
                ),
                "grade_point": (
                    _float_or_none(
                        item.get(
                            "grade_point"
                        )
                    )
                    or 0.0
                ),
                "min_score": minimum,
            }

    return None


def assessment_score_fraction(
    item
):
    total_marks = _float_or_none(
        item.get("total_marks")
    )

    if total_marks is None:
        total_marks = _float_or_none(
            item.get("maximum_marks")
        )

    obtained = _float_or_none(
        item.get("obtained_marks")
    )

    if (
        total_marks is None
        or obtained is None
        or total_marks <= 0
    ):
        return None

    return max(
        0.0,
        min(
            obtained / total_marks,
            1.0
        )
    )


def course_weight_summary(
    course_id
):
    assessments = course_assessments(
        course_id
    )

    rows = []

    total_declared_weight = 0.0
    completed_weight = 0.0
    current_points = 0.0

    for item in assessments:
        weightage = (
            assessment_weightage_percent(
                item
            )
        )

        if weightage is None:
            continue

        total_declared_weight += weightage

        fraction = assessment_score_fraction(
            item
        )

        contribution = None

        if fraction is not None:
            contribution = (
                fraction * weightage
            )
            completed_weight += weightage
            current_points += contribution

        rows.append({
            "title": item.get(
                "title",
                "Assessment"
            ),
            "type": item.get(
                "type"
            ),
            "weightage": weightage,
            "score_fraction": fraction,
            "weighted_points": contribution,
        })

    remaining_known_weight = max(
        0.0,
        total_declared_weight
        - completed_weight
    )

    undeclared_weight = max(
        0.0,
        100.0
        - total_declared_weight
    )

    return {
        "rows": rows,
        "total_declared_weight": round(
            total_declared_weight,
            3
        ),
        "completed_weight": round(
            completed_weight,
            3
        ),
        "current_weighted_points": round(
            current_points,
            3
        ),
        "remaining_known_weight": round(
            remaining_known_weight,
            3
        ),
        "undeclared_weight": round(
            undeclared_weight,
            3
        ),
    }


def projected_final_score(
    course_id,
    remaining_average
):
    summary = course_weight_summary(
        course_id
    )

    current = summary[
        "current_weighted_points"
    ]

    completed = summary[
        "completed_weight"
    ]

    remaining = max(
        0.0,
        100.0 - completed
    )

    projected = (
        current
        + (
            remaining_average
            / 100.0
        )
        * remaining
    )

    return max(
        0.0,
        min(
            projected,
            100.0
        )
    )


def required_remaining_average(
    course_id,
    target_final_score
):
    summary = course_weight_summary(
        course_id
    )

    current = summary[
        "current_weighted_points"
    ]

    completed = summary[
        "completed_weight"
    ]

    remaining = max(
        0.0,
        100.0 - completed
    )

    if remaining <= 0:
        return None

    required = (
        (
            target_final_score
            - current
        )
        / remaining
        * 100.0
    )

    return required


def _ask_float(
    prompt,
    minimum=None,
    maximum=None,
    default=None
):
    while True:
        suffix = ""

        if default is not None:
            suffix = (
                f" [default {default:g}]"
            )

        raw = input(
            f"{prompt}{suffix}: "
        ).strip()

        if not raw:
            return default

        value = _float_or_none(
            raw
        )

        if value is None:
            print(
                "Enter a valid number."
            )
            continue

        if (
            minimum is not None
            and value < minimum
        ):
            print(
                f"Value must be >= {minimum}."
            )
            continue

        if (
            maximum is not None
            and value > maximum
        ):
            print(
                f"Value must be <= {maximum}."
            )
            continue

        return value


def setup_semester():
    config = load_config()

    name = input(
        f"\nSemester name "
        f"[{config['semester_name']}]: "
    ).strip()

    if name:
        config[
            "semester_name"
        ] = name

    target = _ask_float(
        "Target SGPA "
        "(press Enter to leave unchanged)",
        minimum=0.0,
        maximum=10.0,
        default=config.get(
            "target_sgpa"
        )
    )

    config[
        "target_sgpa"
    ] = target

    save_config(
        config
    )

    print(
        "\nSemester settings saved."
    )


def add_course_to_semester():
    course = choose_course(
        "Select Course for Semester Grade Tracking"
    )

    if not course:
        return

    config = load_config()

    existing = None

    for item in config[
        "courses"
    ]:
        if str(
            item.get("course_id")
        ) == str(course["id"]):
            existing = item
            break

    current_credits = (
        _float_or_none(
            existing.get(
                "credits"
            )
        )
        if existing
        else resolve_course_credits(
            course["id"]
        )
    )

    credits = _ask_float(
        "Course credits",
        minimum=0.0,
        default=current_credits
    )

    if credits is None:
        print(
            "\nCredits are required "
            "for SGPA calculation."
        )
        return

    if existing:
        existing[
            "credits"
        ] = credits
    else:
        config[
            "courses"
        ].append({
            "course_id": course["id"],
            "credits": credits,
            "manual_grade_point": None,
            "manual_letter_grade": None,
        })

    save_config(
        config
    )

    print(
        f"\nSaved: "
        f"{course['code']} "
        f"({credits:g} credits)"
    )


def remove_course_from_semester():
    config = load_config()

    if not config[
        "courses"
    ]:
        print(
            "\nNo semester courses configured."
        )
        return

    print(
        "\n========== SEMESTER COURSES =========="
    )

    for index, item in enumerate(
        config["courses"],
        start=1
    ):
        course = find_course(
            item.get(
                "course_id"
            )
        )

        label = (
            f"{course['code']} - "
            f"{course['name']}"
            if course
            else item.get(
                "course_id"
            )
        )

        print(
            f"{index}. "
            f"{label} "
            f"| {item.get('credits')} credits"
        )

    try:
        choice = int(
            input(
                "\nCourse number to remove: "
            ).strip()
        )
    except ValueError:
        print(
            "\nInvalid number."
        )
        return

    if (
        choice < 1
        or choice > len(
            config["courses"]
        )
    ):
        print(
            "\nInvalid selection."
        )
        return

    removed = config[
        "courses"
    ].pop(
        choice - 1
    )

    save_config(
        config
    )

    print(
        f"\nRemoved course "
        f"{removed.get('course_id')}."
    )


def print_grade_scale():
    scale = sort_grade_scale(
        load_config()[
            "grade_scale"
        ]
    )

    print(
        "\n========== GRADE SCALE =========="
    )
    print(
        "Planning configuration — verify against "
        "the official/current grading rules."
    )

    for item in scale:
        print(
            f"{item['letter']:>3} : "
            f"{item['min_score']:>5g}%+ "
            f"-> GP {item['grade_point']:g}"
        )


def configure_grade_scale():
    print(
        "\n========== CONFIGURE GRADE SCALE =========="
    )
    print(
        "Enter the scale you want the planner to use."
    )
    print(
        "Do not treat the default scale as official "
        "unless you have verified it."
    )

    try:
        count = int(
            input(
                "Number of grade bands: "
            ).strip()
        )
    except ValueError:
        print(
            "\nInvalid number."
        )
        return

    if count < 2 or count > 15:
        print(
            "\nUse between 2 and 15 bands."
        )
        return

    scale = []

    for index in range(
        count
    ):
        print(
            f"\nGrade band {index + 1}"
        )

        letter = input(
            "Letter grade: "
        ).strip()

        if not letter:
            print(
                "\nLetter grade cannot be empty."
            )
            return

        minimum = _ask_float(
            "Minimum course score (%)",
            minimum=0.0,
            maximum=100.0
        )

        gp = _ask_float(
            "Grade point",
            minimum=0.0,
            maximum=10.0
        )

        scale.append({
            "letter": letter,
            "min_score": minimum,
            "grade_point": gp,
        })

    config = load_config()
    config[
        "grade_scale"
    ] = sort_grade_scale(
        scale
    )
    save_config(
        config
    )

    print(
        "\nGrade scale saved."
    )


def print_course_grade_intelligence():
    course = choose_course(
        "Select Course for Grade Intelligence"
    )

    if not course:
        return

    summary = course_weight_summary(
        course["id"]
    )

    credits = resolve_course_credits(
        course["id"]
    )

    print(
        "\n========== COURSE GRADE INTELLIGENCE =========="
    )
    print(
        f"{course['code']} - "
        f"{course['name']}"
    )

    if credits is not None:
        print(
            f"Credits: {credits:g}"
        )

    print(
        f"\nDeclared assessment weight: "
        f"{summary['total_declared_weight']:g}%"
    )
    print(
        f"Completed/known-result weight: "
        f"{summary['completed_weight']:g}%"
    )
    print(
        f"Current weighted points earned: "
        f"{summary['current_weighted_points']:g}/100"
    )

    if summary[
        "undeclared_weight"
    ] > 0:
        print(
            f"Weight not yet represented in tracker: "
            f"{summary['undeclared_weight']:g}%"
        )

    if summary["rows"]:
        print(
            "\nAssessment breakdown:"
        )

        for row in summary[
            "rows"
        ]:
            line = (
                f"- {row['title']}: "
                f"{row['weightage']:g}%"
            )

            if row[
                "score_fraction"
            ] is not None:
                line += (
                    f" | score "
                    f"{row['score_fraction'] * 100:.1f}%"
                    f" | contribution "
                    f"{row['weighted_points']:.2f}"
                )
            else:
                line += (
                    " | result not recorded"
                )

            print(line)


def projection_tool():
    course = choose_course(
        "Select Course for Projection"
    )

    if not course:
        return

    expected_remaining = _ask_float(
        "Expected average (%) on all remaining course weight",
        minimum=0.0,
        maximum=100.0,
        default=75.0
    )

    final_score = projected_final_score(
        course["id"],
        expected_remaining
    )

    grade = grade_for_score(
        final_score
    )

    print(
        "\n========== COURSE PROJECTION =========="
    )
    print(
        f"Projected final score: "
        f"{final_score:.2f}%"
    )

    if grade:
        print(
            f"Projected grade: "
            f"{grade['letter']} "
            f"(GP {grade['grade_point']:g})"
        )

    print(
        "\nThis projection assumes the same average "
        "across all remaining uncompleted course weight."
    )


def target_score_tool():
    course = choose_course(
        "Select Course for Target Calculation"
    )

    if not course:
        return

    target = _ask_float(
        "Target final course score (%)",
        minimum=0.0,
        maximum=100.0
    )

    required = required_remaining_average(
        course["id"],
        target
    )

    print(
        "\n========== REQUIRED REMAINING PERFORMANCE =========="
    )

    if required is None:
        print(
            "No remaining course weight is available "
            "for this calculation."
        )
        return

    print(
        f"Required average on remaining weight: "
        f"{required:.2f}%"
    )

    if required > 100:
        print(
            "Target is not achievable from the currently "
            "recorded completed score and remaining weight."
        )

    elif required <= 0:
        print(
            "Target is already secured mathematically "
            "under the recorded weight model."
        )

    elif required >= 90:
        print(
            "This target requires very high performance "
            "on the remaining assessment weight."
        )


def manual_grade_entry():
    config = load_config()

    if not config[
        "courses"
    ]:
        print(
            "\nConfigure semester courses first."
        )
        return

    print(
        "\n========== ENTER / OVERRIDE COURSE GRADE =========="
    )

    for index, item in enumerate(
        config["courses"],
        start=1
    ):
        course = find_course(
            item.get(
                "course_id"
            )
        )

        label = (
            course["code"]
            if course
            else item.get(
                "course_id"
            )
        )

        print(
            f"{index}. {label}"
        )

    try:
        choice = int(
            input(
                "\nCourse number: "
            ).strip()
        )
    except ValueError:
        print(
            "\nInvalid number."
        )
        return

    if (
        choice < 1
        or choice > len(
            config["courses"]
        )
    ):
        print(
            "\nInvalid selection."
        )
        return

    item = config[
        "courses"
    ][
        choice - 1
    ]

    gp = _ask_float(
        "Grade point",
        minimum=0.0,
        maximum=10.0
    )

    letter = input(
        "Letter grade (optional): "
    ).strip()

    item[
        "manual_grade_point"
    ] = gp

    item[
        "manual_letter_grade"
    ] = (
        letter
        or None
    )

    save_config(
        config
    )

    print(
        "\nCourse grade override saved."
    )


def projected_course_grade_point(
    course_record,
    default_remaining_average=75.0
):
    manual = _float_or_none(
        course_record.get(
            "manual_grade_point"
        )
    )

    if manual is not None:
        return {
            "grade_point": manual,
            "letter": (
                course_record.get(
                    "manual_letter_grade"
                )
                or "manual"
            ),
            "source": "manual",
            "projected_score": None,
        }

    course_id = course_record[
        "course_id"
    ]

    score = projected_final_score(
        course_id,
        default_remaining_average
    )

    grade = grade_for_score(
        score
    )

    if not grade:
        return None

    return {
        "grade_point": grade[
            "grade_point"
        ],
        "letter": grade[
            "letter"
        ],
        "source": (
            "projected at "
            f"{default_remaining_average:g}% "
            "remaining-average assumption"
        ),
        "projected_score": score,
    }


def sgpa_projection():
    config = load_config()

    if not config[
        "courses"
    ]:
        print(
            "\nConfigure semester courses first."
        )
        return

    remaining_average = _ask_float(
        "Default expected average (%) on remaining course weight",
        minimum=0.0,
        maximum=100.0,
        default=75.0
    )

    numerator = 0.0
    denominator = 0.0

    rows = []

    for record in config[
        "courses"
    ]:
        course = find_course(
            record.get(
                "course_id"
            )
        )

        credits = _float_or_none(
            record.get("credits")
        )

        if (
            credits is None
            or credits <= 0
        ):
            continue

        result = projected_course_grade_point(
            record,
            default_remaining_average=remaining_average
        )

        if not result:
            continue

        numerator += (
            result[
                "grade_point"
            ]
            * credits
        )

        denominator += credits

        rows.append({
            "course": course,
            "course_id": record[
                "course_id"
            ],
            "credits": credits,
            **result,
        })

    print(
        "\n========== SGPA PROJECTION =========="
    )

    if denominator <= 0:
        print(
            "No usable course-credit/grade information."
        )
        return

    sgpa = numerator / denominator

    for row in rows:
        label = (
            row["course"]["code"]
            if row["course"]
            else row[
                "course_id"
            ]
        )

        line = (
            f"- {label}: "
            f"{row['credits']:g} cr "
            f"| {row['letter']} "
            f"| GP {row['grade_point']:g}"
        )

        if (
            row[
                "projected_score"
            ]
            is not None
        ):
            line += (
                f" | projected "
                f"{row['projected_score']:.1f}%"
            )

        print(line)

    print(
        f"\nProjected SGPA: "
        f"{sgpa:.3f}"
    )

    target = _float_or_none(
        config.get(
            "target_sgpa"
        )
    )

    if target is not None:
        difference = (
            sgpa - target
        )

        print(
            f"Target SGPA   : "
            f"{target:.3f}"
        )

        if difference >= 0:
            print(
                f"Above target  : "
                f"{difference:.3f}"
            )
        else:
            print(
                f"Below target  : "
                f"{abs(difference):.3f}"
            )

    print(
        "\nProjection note: this is a planning estimate, "
        "not an official grade result."
    )


def target_sgpa_scenario():
    config = load_config()

    if not config[
        "courses"
    ]:
        print(
            "\nConfigure semester courses first."
        )
        return

    target = _ask_float(
        "Target SGPA",
        minimum=0.0,
        maximum=10.0,
        default=(
            config.get(
                "target_sgpa"
            )
            or 8.0
        )
    )

    total_credits = sum(
        _float_or_none(
            item.get(
                "credits"
            )
        )
        or 0.0
        for item in config[
            "courses"
        ]
    )

    if total_credits <= 0:
        print(
            "\nNo course credits configured."
        )
        return

    locked_points = 0.0
    locked_credits = 0.0

    unknown_credits = 0.0

    for item in config[
        "courses"
    ]:
        credits = _float_or_none(
            item.get(
                "credits"
            )
        ) or 0.0

        manual_gp = _float_or_none(
            item.get(
                "manual_grade_point"
            )
        )

        if (
            credits > 0
            and manual_gp is not None
        ):
            locked_points += (
                credits * manual_gp
            )
            locked_credits += credits
        else:
            unknown_credits += credits

    required_total_points = (
        target * total_credits
    )

    remaining_points = (
        required_total_points
        - locked_points
    )

    print(
        "\n========== TARGET SGPA SCENARIO =========="
    )
    print(
        f"Target SGPA: {target:.3f}"
    )
    print(
        f"Total credits: {total_credits:g}"
    )

    if unknown_credits <= 0:
        actual = (
            locked_points
            / total_credits
        )

        print(
            f"All configured grades are fixed. "
            f"SGPA = {actual:.3f}"
        )
        return

    required_average_gp = (
        remaining_points
        / unknown_credits
    )

    print(
        f"Credits with fixed/manual grades: "
        f"{locked_credits:g}"
    )
    print(
        f"Credits still open: "
        f"{unknown_credits:g}"
    )
    print(
        f"Required average grade point "
        f"across open credits: "
        f"{required_average_gp:.3f}"
    )

    if required_average_gp > 10:
        print(
            "The target is impossible under the "
            "currently fixed grade points."
        )

    elif required_average_gp <= 0:
        print(
            "The target is already mathematically secured "
            "by the fixed grade points."
        )


def semester_grade_intelligence_menu():
    while True:
        config = load_config()

        print(
            "\n========== V12.1 SEMESTER GRADE & CGPA INTELLIGENCE =========="
        )
        print(
            f"Semester: "
            f"{config['semester_name']}"
        )

        if config.get(
            "target_sgpa"
        ) is not None:
            print(
                f"Target SGPA: "
                f"{config['target_sgpa']}"
            )

        print(
            "\n1. Semester Setup / Target SGPA"
        )
        print(
            "2. Add / Update Semester Course Credits"
        )
        print(
            "3. Remove Semester Course"
        )
        print(
            "4. View / Configure Grade Scale"
        )
        print(
            "5. Course Grade Intelligence"
        )
        print(
            "6. Project Final Course Score"
        )
        print(
            "7. Required Score on Remaining Weight"
        )
        print(
            "8. Enter Known Course Grade / Grade Point"
        )
        print(
            "9. Project Semester SGPA"
        )
        print(
            "10. Target SGPA What-If"
        )
        print(
            "11. Back"
        )

        choice = input(
            "\nEnter your choice (1-11): "
        ).strip()

        if choice == "1":
            setup_semester()

        elif choice == "2":
            add_course_to_semester()

        elif choice == "3":
            remove_course_from_semester()

        elif choice == "4":
            print_grade_scale()

            answer = input(
                "\nConfigure/replace this scale? "
                "Type yes to continue: "
            ).strip().lower()

            if answer == "yes":
                configure_grade_scale()

        elif choice == "5":
            print_course_grade_intelligence()

        elif choice == "6":
            projection_tool()

        elif choice == "7":
            target_score_tool()

        elif choice == "8":
            manual_grade_entry()

        elif choice == "9":
            sgpa_projection()

        elif choice == "10":
            target_sgpa_scenario()

        elif choice == "11":
            break

        else:
            print(
                "\nInvalid choice. "
                "Please enter 1 to 11."
            )


if __name__ == "__main__":
    semester_grade_intelligence_menu()
