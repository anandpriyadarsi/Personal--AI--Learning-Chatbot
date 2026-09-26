-- Assessment Studio Phase C: timed CBT sessions, immutable question snapshots,
-- response persistence, meaningful runner events, and bounded focus-time evidence.
--
-- Grading is intentionally deferred to Phase D. Answer keys/solutions/rubrics are
-- snapshotted server-side and are never part of the public runner read model.

CREATE TABLE assessment_test_sessions (
    id TEXT PRIMARY KEY,
    assessment_id TEXT NOT NULL
        REFERENCES assessments(id) ON DELETE RESTRICT,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'submitted', 'expired')),
    mode TEXT NOT NULL
        CHECK (mode IN ('exam', 'practice')),
    title_snapshot TEXT NOT NULL,
    course_code_snapshot TEXT NOT NULL DEFAULT '',
    course_name_snapshot TEXT NOT NULL DEFAULT '',
    instructions_snapshot TEXT NOT NULL DEFAULT '',
    duration_seconds INTEGER NOT NULL CHECK (duration_seconds > 0),
    question_count INTEGER NOT NULL CHECK (question_count > 0),
    max_marks_milli INTEGER NOT NULL CHECK (max_marks_milli >= 0),
    started_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    submitted_at TEXT,
    submission_reason TEXT
        CHECK (
            submission_reason IS NULL
            OR submission_reason IN ('user', 'timeout')
        ),
    current_ordinal INTEGER NOT NULL DEFAULT 1 CHECK (current_ordinal > 0),
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX assessment_test_sessions_one_active_ix
    ON assessment_test_sessions(assessment_id)
    WHERE status = 'active';

CREATE INDEX assessment_test_sessions_assessment_ix
    ON assessment_test_sessions(assessment_id, started_at DESC);

CREATE INDEX assessment_test_sessions_status_expiry_ix
    ON assessment_test_sessions(status, expires_at);

CREATE TABLE assessment_test_session_questions (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL
        REFERENCES assessment_test_sessions(id) ON DELETE CASCADE,
    question_id TEXT NOT NULL
        REFERENCES questions(id) ON DELETE RESTRICT,
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    question_number TEXT NOT NULL DEFAULT '',
    section_label TEXT NOT NULL DEFAULT '',
    question_type TEXT NOT NULL,
    question_text TEXT NOT NULL,
    max_marks_milli INTEGER NOT NULL CHECK (max_marks_milli >= 0),
    negative_marks_milli INTEGER NOT NULL DEFAULT 0
        CHECK (negative_marks_milli >= 0),
    scoring_policy TEXT NOT NULL DEFAULT 'standard',
    topic_id TEXT
        REFERENCES topics(id) ON DELETE RESTRICT,
    chapter_label TEXT NOT NULL DEFAULT '',
    subtopic_label TEXT NOT NULL DEFAULT '',
    concepts_json TEXT NOT NULL DEFAULT '[]',
    difficulty TEXT NOT NULL DEFAULT '',
    expected_method TEXT NOT NULL DEFAULT '',
    options_json TEXT NOT NULL DEFAULT '[]',
    answer_key_json TEXT NOT NULL DEFAULT '{}',
    solution_text TEXT NOT NULL DEFAULT '',
    rubric_text TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE (session_id, ordinal),
    UNIQUE (session_id, question_id)
);

CREATE INDEX assessment_test_session_questions_session_ix
    ON assessment_test_session_questions(session_id, ordinal);

CREATE INDEX assessment_test_session_questions_topic_ix
    ON assessment_test_session_questions(topic_id, session_id);

CREATE TABLE assessment_test_responses (
    id TEXT PRIMARY KEY,
    session_question_id TEXT NOT NULL UNIQUE
        REFERENCES assessment_test_session_questions(id) ON DELETE CASCADE,
    state TEXT NOT NULL DEFAULT 'not_visited'
        CHECK (
            state IN (
                'not_visited',
                'not_answered',
                'answered',
                'marked_for_review',
                'answered_marked_for_review'
            )
        ),
    response_json TEXT NOT NULL DEFAULT '{}',
    focus_seconds INTEGER NOT NULL DEFAULT 0 CHECK (focus_seconds >= 0),
    visited_at TEXT,
    answered_at TEXT,
    saved_at TEXT,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    updated_at TEXT NOT NULL
);

CREATE INDEX assessment_test_responses_state_ix
    ON assessment_test_responses(state, updated_at);

CREATE TABLE assessment_test_events (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL
        REFERENCES assessment_test_sessions(id) ON DELETE CASCADE,
    session_question_id TEXT
        REFERENCES assessment_test_session_questions(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    occurred_at TEXT NOT NULL
);

CREATE INDEX assessment_test_events_session_ix
    ON assessment_test_events(session_id, occurred_at);

CREATE INDEX assessment_test_events_question_ix
    ON assessment_test_events(session_question_id, occurred_at);
