-- Phase 6.5: source-grounded active recall / fast quiz persistence.
-- This migration deliberately separates generated practice from formal
-- assessment questions and attempts.

CREATE TABLE practice_sessions (
    id TEXT PRIMARY KEY,
    tutor_session_id TEXT
        REFERENCES tutor_sessions(id) ON DELETE SET NULL,
    course_id TEXT NOT NULL
        REFERENCES courses(id) ON DELETE RESTRICT,
    topic_id TEXT
        REFERENCES topics(id) ON DELETE RESTRICT,
    resource_id TEXT
        REFERENCES resources(id) ON DELETE RESTRICT,
    mode TEXT NOT NULL,
    difficulty TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    source_query TEXT NOT NULL,
    source_policy TEXT NOT NULL DEFAULT 'source_only',
    requested_item_count INTEGER NOT NULL
        CHECK (requested_item_count BETWEEN 1 AND 20),
    generation_provider TEXT NOT NULL DEFAULT '',
    generation_model TEXT NOT NULL DEFAULT '',
    provider_request_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    completed_at TEXT,
    CHECK (mode IN ('checkpoint', 'fast_quiz', 'active_recall')),
    CHECK (difficulty IN ('easy', 'medium', 'hard', 'mixed')),
    CHECK (source_policy = 'source_only'),
    CHECK (status IN ('active', 'completed', 'abandoned')),
    CHECK (
        (status = 'active' AND completed_at IS NULL)
        OR status IN ('completed', 'abandoned')
    )
);

CREATE TABLE practice_items (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL
        REFERENCES practice_sessions(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    item_type TEXT NOT NULL,
    prompt TEXT NOT NULL,
    options_json TEXT NOT NULL DEFAULT '[]',
    answer_key_json TEXT NOT NULL DEFAULT '{}',
    explanation TEXT NOT NULL,
    created_at TEXT NOT NULL,
    CHECK (item_type IN ('single_choice', 'exact_recall', 'free_response')),
    UNIQUE (session_id, ordinal)
);

CREATE TABLE practice_item_sources (
    item_id TEXT NOT NULL
        REFERENCES practice_items(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    chunk_id TEXT NOT NULL
        REFERENCES knowledge_chunks(id) ON DELETE RESTRICT,
    document_id TEXT NOT NULL
        REFERENCES knowledge_documents(id) ON DELETE RESTRICT,
    citation_label TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (item_id, ordinal),
    UNIQUE (item_id, chunk_id)
);

CREATE TABLE practice_attempts (
    id TEXT PRIMARY KEY,
    item_id TEXT NOT NULL
        REFERENCES practice_items(id) ON DELETE RESTRICT,
    attempt_number INTEGER NOT NULL CHECK (attempt_number > 0),
    response_text TEXT NOT NULL,
    outcome TEXT NOT NULL,
    score_bps INTEGER
        CHECK (score_bps IS NULL OR score_bps BETWEEN 0 AND 10000),
    grading_mode TEXT NOT NULL,
    self_confidence INTEGER
        CHECK (self_confidence IS NULL OR self_confidence BETWEEN 0 AND 5),
    feedback TEXT NOT NULL DEFAULT '',
    occurred_at TEXT NOT NULL,
    CHECK (outcome IN ('correct', 'incorrect', 'advisory_ungraded')),
    CHECK (grading_mode IN ('deterministic', 'advisory')),
    CHECK (
        (grading_mode = 'deterministic'
            AND outcome IN ('correct', 'incorrect')
            AND score_bps IS NOT NULL)
        OR
        (grading_mode = 'advisory'
            AND outcome = 'advisory_ungraded'
            AND score_bps IS NULL)
    ),
    UNIQUE (item_id, attempt_number)
);

CREATE INDEX practice_sessions_scope_ix
    ON practice_sessions (course_id, topic_id, resource_id, status, created_at DESC);

CREATE INDEX practice_items_session_ix
    ON practice_items (session_id, ordinal);

CREATE INDEX practice_item_sources_chunk_ix
    ON practice_item_sources (chunk_id, item_id);

CREATE INDEX practice_attempts_item_ix
    ON practice_attempts (item_id, attempt_number);
