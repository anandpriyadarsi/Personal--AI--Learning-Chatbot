-- Assessment Studio Phase D: deterministic/objective evaluation,
-- rubric-versioned subjective review, signed scoring, canonical attempts,
-- and audited mistake classification.
--
-- Session/response snapshots from Phase C remain immutable. Phase D evaluates
-- those snapshots only after the session is terminal.

ALTER TABLE question_attempts
    ADD COLUMN signed_score_milli INTEGER;

ALTER TABLE question_attempts
    ADD COLUMN evaluation_ref TEXT;

CREATE TABLE assessment_session_evaluations (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL UNIQUE
        REFERENCES assessment_test_sessions(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending_review'
        CHECK (status IN ('pending_review', 'provisional', 'confirmed')),
    engine_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    confirmed_at TEXT
);

CREATE TABLE assessment_response_evaluations (
    id TEXT PRIMARY KEY,
    session_evaluation_id TEXT NOT NULL
        REFERENCES assessment_session_evaluations(id) ON DELETE CASCADE,
    session_question_id TEXT NOT NULL UNIQUE
        REFERENCES assessment_test_session_questions(id) ON DELETE CASCADE,
    question_id TEXT NOT NULL
        REFERENCES questions(id) ON DELETE RESTRICT,
    response_id TEXT NOT NULL UNIQUE
        REFERENCES assessment_test_responses(id) ON DELETE RESTRICT,
    evaluator_type TEXT NOT NULL
        CHECK (
            evaluator_type IN (
                'deterministic',
                'user',
                'teacher',
                'alex_ai'
            )
        ),
    evaluator_model TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL
        CHECK (
            status IN (
                'auto_confirmed',
                'awaiting_review',
                'provisional',
                'confirmed'
            )
        ),
    outcome TEXT NOT NULL
        CHECK (
            outcome IN (
                'correct',
                'partially_correct',
                'incorrect',
                'unanswered',
                'pending_review'
            )
        ),
    awarded_marks_milli INTEGER,
    max_marks_milli INTEGER NOT NULL CHECK (max_marks_milli >= 0),
    penalty_marks_milli INTEGER NOT NULL DEFAULT 0
        CHECK (penalty_marks_milli >= 0),
    scoring_policy TEXT NOT NULL,
    rubric_version TEXT NOT NULL DEFAULT '',
    confidence REAL
        CHECK (confidence IS NULL OR confidence BETWEEN 0.0 AND 1.0),
    feedback_text TEXT NOT NULL DEFAULT '',
    details_json TEXT NOT NULL DEFAULT '{}',
    question_attempt_id TEXT UNIQUE
        REFERENCES question_attempts(id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    confirmed_at TEXT,
    CHECK (
        awarded_marks_milli IS NULL
        OR awarded_marks_milli <= max_marks_milli
    )
);

CREATE TABLE assessment_evaluation_mistakes (
    id TEXT PRIMARY KEY,
    response_evaluation_id TEXT NOT NULL
        REFERENCES assessment_response_evaluations(id) ON DELETE CASCADE,
    category TEXT NOT NULL
        CHECK (
            category IN (
                'concept_gap',
                'formula_recall',
                'calculation_error',
                'misread',
                'wrong_method',
                'incomplete_reasoning',
                'time_pressure',
                'careless',
                'guessing',
                'other'
            )
        ),
    note TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL DEFAULT 'user'
        CHECK (source_type IN ('user', 'teacher', 'alex_ai')),
    status TEXT NOT NULL DEFAULT 'confirmed'
        CHECK (status IN ('provisional', 'confirmed')),
    mistake_event_id TEXT UNIQUE
        REFERENCES mistake_events(id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    confirmed_at TEXT,
    UNIQUE (response_evaluation_id, category)
);

CREATE TABLE assessment_evaluation_events (
    id TEXT PRIMARY KEY,
    session_evaluation_id TEXT NOT NULL
        REFERENCES assessment_session_evaluations(id) ON DELETE CASCADE,
    response_evaluation_id TEXT
        REFERENCES assessment_response_evaluations(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    occurred_at TEXT NOT NULL
);

CREATE INDEX assessment_session_evaluations_status_ix
    ON assessment_session_evaluations(status, updated_at);

CREATE INDEX assessment_response_evaluations_session_ix
    ON assessment_response_evaluations(session_evaluation_id, status);

CREATE INDEX assessment_response_evaluations_question_ix
    ON assessment_response_evaluations(question_id, updated_at);

CREATE INDEX assessment_evaluation_mistakes_response_ix
    ON assessment_evaluation_mistakes(response_evaluation_id, status);

CREATE INDEX assessment_evaluation_events_session_ix
    ON assessment_evaluation_events(session_evaluation_id, occurred_at);
