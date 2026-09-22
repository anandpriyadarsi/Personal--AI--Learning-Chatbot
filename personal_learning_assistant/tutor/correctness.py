"""Deterministic verification for bounded Tutor 2.1 mathematical claims.

This layer intentionally verifies only machine-readable numeric claims that can
be checked exactly and safely without evaluating arbitrary Python/LaTeX.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from fractions import Fraction


_MATH_PATTERN = re.compile(
    r"\s*<!--ANVAYA_MATH\s+(.+?)\s*-->\s*",
    re.DOTALL,
)
_MAX_CLAIMS = 12
_MAX_DIMENSION = 8


@dataclass(frozen=True)
class MathVerification:
    applicable: bool
    passed: bool
    checked_claims: int
    issues: tuple[str, ...]
    marker_present: bool


def requires_deterministic_math(question):
    """Require a math marker for explicit supported numerical computation requests."""
    clean = " ".join(str(question or "").casefold().split())
    if not clean:
        return False

    operation = any(
        re.search(pattern, clean)
        for pattern in (
            r"\bcompute\b",
            r"\bcalculate\b",
            r"\bverify\b",
            r"\bwork(?:ed)?\s+(?:example|calculation)\b",
            r"\bstep by step\b",
            r"\bnumerical example\b",
        )
    )
    supported_subject = any(
        re.search(pattern, clean)
        for pattern in (
            r"\bmatrix\b",
            r"\bmatrices\b",
            r"\bdeterminant\b",
            r"\bvector\b",
            r"\blu\b",
            r"\blinear combination\b",
            r"\bdecomposition\b",
        )
    )
    return bool(operation and supported_subject)


def correctness_protocol():
    return (
        "DETERMINISTIC MATH VERIFICATION: whenever your visible answer contains a "
        "numerical vector linear-combination equality, matrix product, or determinant "
        "claim, include exactly one hidden machine-readable marker before the visible "
        "answer. Use: "
        '<!--ANVAYA_MATH {"claims":[...]}-->. '
        "Supported claim schemas are: "
        '{"type":"vector_linear_combination","target":[...],"vectors":[[...],...],'
        '"coefficients":[...]}; '
        '{"type":"matrix_product","left":[[...]],"right":[[...]],"result":[[...]]}; '
        '{"type":"determinant","matrix":[[...]],"result":number}. '
        "Include every supported numerical claim that the explanation relies on. "
        "Do not put prose inside the marker. Do not emit a marker when no supported "
        "numerical claim appears. ANVAYA will independently check these claims and may "
        "reject the worked example if they are false. The hidden marker and the verification "
        "mechanism are internal implementation details: never mention ANVAYA_MATH, hidden "
        "markers, machine-readable metadata, deterministic verifiers, or internal verification "
        "machinery in the visible student-facing answer."
    )


def _number(value):
    if isinstance(value, bool):
        raise ValueError("booleans are not numeric claims")
    if isinstance(value, int):
        return Fraction(value, 1)
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise ValueError("non-finite number")
        return Fraction(str(value))
    if isinstance(value, str):
        clean = value.strip()
        if not clean:
            raise ValueError("empty number")
        return Fraction(clean)
    raise ValueError("unsupported numeric value")


def _vector(value):
    if not isinstance(value, list) or not value or len(value) > _MAX_DIMENSION:
        raise ValueError("invalid vector")
    return tuple(_number(item) for item in value)


def _matrix(value):
    if not isinstance(value, list) or not value or len(value) > _MAX_DIMENSION:
        raise ValueError("invalid matrix")
    rows = tuple(_vector(row) for row in value)
    width = len(rows[0])
    if width == 0 or width > _MAX_DIMENSION:
        raise ValueError("invalid matrix width")
    if any(len(row) != width for row in rows):
        raise ValueError("ragged matrix")
    return rows


def _fmt_number(value):
    value = Fraction(value)
    if value.denominator == 1:
        return str(value.numerator)
    return "{}/{}".format(value.numerator, value.denominator)


def _fmt_vector(vector):
    return "(" + ", ".join(_fmt_number(item) for item in vector) + ")"


def _fmt_matrix(matrix):
    return "[" + ", ".join(_fmt_vector(row) for row in matrix) + "]"


def _verify_vector_linear_combination(claim):
    target = _vector(claim.get("target"))
    raw_vectors = claim.get("vectors")
    raw_coefficients = claim.get("coefficients")
    if not isinstance(raw_vectors, list) or not isinstance(raw_coefficients, list):
        raise ValueError("vectors and coefficients are required")
    if not raw_vectors or len(raw_vectors) != len(raw_coefficients):
        raise ValueError("vector/coefficient count mismatch")
    if len(raw_vectors) > _MAX_DIMENSION:
        raise ValueError("too many vectors")
    vectors = tuple(_vector(item) for item in raw_vectors)
    if any(len(vector) != len(target) for vector in vectors):
        raise ValueError("vector dimension mismatch")
    coefficients = tuple(_number(item) for item in raw_coefficients)
    actual = tuple(
        sum(
            (coefficients[j] * vectors[j][i] for j in range(len(vectors))),
            Fraction(0, 1),
        )
        for i in range(len(target))
    )
    if actual != target:
        return (
            False,
            "vector linear combination evaluates to {} instead of target {}".format(
                _fmt_vector(actual),
                _fmt_vector(target),
            ),
        )
    return True, ""


def _verify_matrix_product(claim):
    left = _matrix(claim.get("left"))
    right = _matrix(claim.get("right"))
    expected = _matrix(claim.get("result"))
    if len(left[0]) != len(right):
        raise ValueError("matrix dimensions are incompatible")
    actual = tuple(
        tuple(
            sum(
                (left[i][k] * right[k][j] for k in range(len(right))),
                Fraction(0, 1),
            )
            for j in range(len(right[0]))
        )
        for i in range(len(left))
    )
    if len(expected) != len(actual) or len(expected[0]) != len(actual[0]):
        raise ValueError("matrix result dimension mismatch")
    if actual != expected:
        return (
            False,
            "matrix product evaluates to {} instead of claimed {}".format(
                _fmt_matrix(actual),
                _fmt_matrix(expected),
            ),
        )
    return True, ""


def _determinant(matrix):
    size = len(matrix)
    if any(len(row) != size for row in matrix):
        raise ValueError("determinant requires a square matrix")
    work = [list(row) for row in matrix]
    det = Fraction(1, 1)
    sign = 1
    for col in range(size):
        pivot = next(
            (row for row in range(col, size) if work[row][col] != 0),
            None,
        )
        if pivot is None:
            return Fraction(0, 1)
        if pivot != col:
            work[col], work[pivot] = work[pivot], work[col]
            sign *= -1
        pivot_value = work[col][col]
        det *= pivot_value
        for row in range(col + 1, size):
            if work[row][col] == 0:
                continue
            factor = work[row][col] / pivot_value
            for j in range(col, size):
                work[row][j] -= factor * work[col][j]
    return det * sign


def _verify_determinant(claim):
    matrix = _matrix(claim.get("matrix"))
    expected = _number(claim.get("result"))
    actual = _determinant(matrix)
    if actual != expected:
        return (
            False,
            "determinant evaluates to {} instead of claimed {}".format(
                _fmt_number(actual),
                _fmt_number(expected),
            ),
        )
    return True, ""


def _verify_claim(claim, index):
    if not isinstance(claim, dict):
        return False, "claim {} is not an object".format(index)
    claim_type = str(claim.get("type") or "").strip()
    verifiers = {
        "vector_linear_combination": _verify_vector_linear_combination,
        "matrix_product": _verify_matrix_product,
        "determinant": _verify_determinant,
    }
    verifier = verifiers.get(claim_type)
    if verifier is None:
        return False, "claim {} has unsupported type {!r}".format(index, claim_type)
    try:
        passed, issue = verifier(claim)
    except (ValueError, ZeroDivisionError) as error:
        return False, "claim {} is malformed: {}".format(index, error)
    if passed:
        return True, ""
    return False, "claim {} failed: {}".format(index, issue)


def sanitize_correctness_prose(content):
    """Remove internal correctness-protocol wording from student-facing prose."""
    text = str(content or "")

    # The model may narrate the hidden protocol even when the actual metadata
    # marker was correctly stripped. Keep ordinary mathematical "Verification"
    # wording, but remove implementation-detail qualifiers.
    text = re.sub(
        r"(?i)\bverification\s*\(\s*hidden\s+marker\s*\)\s*:",
        "Verification:",
        text,
    )
    text = re.sub(
        r"(?i)\b(?:hidden|machine-readable)\s+(?:math\s+)?marker\b",
        "",
        text,
    )
    text = re.sub(
        r"(?i)\bANVAYA_MATH\b",
        "",
        text,
    )
    text = re.sub(
        r"(?i)\bdeterministic\s+(?:math\s+)?verifier\b",
        "calculation check",
        text,
    )
    text = re.sub(
        r"(?i)\binternal\s+verification\s+machinery\b",
        "calculation check",
        text,
    )
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def extract_and_verify_math(content):
    """Strip hidden math metadata and verify all declared supported claims."""
    raw = str(content or "")
    matches = list(_MATH_PATTERN.finditer(raw))
    if not matches:
        return raw.strip(), MathVerification(
            applicable=False,
            passed=True,
            checked_claims=0,
            issues=(),
            marker_present=False,
        )

    # Multiple markers complicate repair semantics and are unnecessary.
    if len(matches) != 1:
        stripped = _MATH_PATTERN.sub("", raw).strip()
        return stripped, MathVerification(
            applicable=True,
            passed=False,
            checked_claims=0,
            issues=("multiple ANVAYA_MATH markers were emitted",),
            marker_present=True,
        )

    match = matches[0]
    stripped = (raw[: match.start()] + raw[match.end() :]).strip()
    try:
        payload = json.loads(match.group(1))
    except (TypeError, ValueError, json.JSONDecodeError):
        return stripped, MathVerification(
            applicable=True,
            passed=False,
            checked_claims=0,
            issues=("ANVAYA_MATH metadata is not valid JSON",),
            marker_present=True,
        )
    claims = payload.get("claims") if isinstance(payload, dict) else None
    if not isinstance(claims, list) or not claims:
        return stripped, MathVerification(
            applicable=True,
            passed=False,
            checked_claims=0,
            issues=("ANVAYA_MATH must contain a non-empty claims list",),
            marker_present=True,
        )
    if len(claims) > _MAX_CLAIMS:
        return stripped, MathVerification(
            applicable=True,
            passed=False,
            checked_claims=0,
            issues=("ANVAYA_MATH contains too many claims",),
            marker_present=True,
        )

    issues = []
    checked = 0
    for index, claim in enumerate(claims, start=1):
        checked += 1
        passed, issue = _verify_claim(claim, index)
        if not passed:
            issues.append(issue)

    return stripped, MathVerification(
        applicable=True,
        passed=not issues,
        checked_claims=checked,
        issues=tuple(issues),
        marker_present=True,
    )
