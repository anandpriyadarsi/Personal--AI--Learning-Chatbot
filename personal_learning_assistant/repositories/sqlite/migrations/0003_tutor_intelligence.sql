-- Phase 6.1: Academic Tutor session/evidence foundation.
-- This migration adds only tutor-specific conversational state.
-- Existing academic progress, learning memory, resources, assessments, plans,
-- source files, and retrieval indexes remain authoritative in their own domains.

CREATE TABLE tutor_sessions (
    id TEXT PRIMARY KEY,
    course_id TEXT
        REFERENCES courses(id) ON DELETE RESTRICT,
    topic_id TEXT
        REFERENCES topics(id) ON DELETE RESTRICT,
    assessment_id TEXT
        REFERENCES assessments(id) ON DELETE RESTRICT,
    resource_id TEXT
        REFERENCES resources(id) ON DELETE RESTRICT,
    mode TEXT NOT NULL,
    source_policy TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    title TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    CHECK (mode IN (
        'concept',
        'doubt',
        'summary',
        'exam',
        'lecture',
        'revision',
        'guidance',
        'free'
    )),
    CHECK (source_policy IN ('source_only', 'source_first')),
    CHECK (status IN ('active', 'completed', 'abandoned')),
    CHECK (
        (status = 'active' AND completed_at IS NULL)
        OR (status IN ('completed', 'abandoned'))
    )
);

CREATE TABLE tutor_turns (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL
        REFERENCES tutor_sessions(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    support_level TEXT NOT NULL,
    provider_name TEXT NOT NULL DEFAULT '',
    provider_model TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    CHECK (role IN ('user', 'assistant')),
    CHECK (support_level IN (
        'not_evaluated',
        'grounded',
        'mixed',
        'insufficient'
    )),
    CHECK (
        (role = 'user' AND support_level = 'not_evaluated')
        OR (role = 'assistant' AND support_level <> 'not_evaluated')
    ),
    UNIQUE (session_id, ordinal)
);

CREATE TABLE tutor_evidence_links (
    turn_id TEXT NOT NULL
        REFERENCES tutor_turns(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    chunk_id TEXT NOT NULL
        REFERENCES knowledge_chunks(id) ON DELETE RESTRICT,
    document_id TEXT NOT NULL
        REFERENCES knowledge_documents(id) ON DELETE RESTRICT,
    relation_type TEXT NOT NULL DEFAULT 'support',
    retrieval_score REAL,
    citation_label TEXT NOT NULL,
    created_at TEXT NOT NULL,
    CHECK (relation_type IN ('support', 'background', 'contrast')),
    PRIMARY KEY (turn_id, ordinal),
    UNIQUE (turn_id, chunk_id, relation_type)
);

CREATE TABLE tutor_feedback (
    id TEXT PRIMARY KEY,
    turn_id TEXT NOT NULL
        REFERENCES tutor_turns(id) ON DELETE CASCADE,
    rating INTEGER CHECK (rating IS NULL OR rating BETWEEN 1 AND 5),
    helpful INTEGER CHECK (helpful IS NULL OR helpful IN (0, 1)),
    feedback_text TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    CHECK (
        rating IS NOT NULL
        OR helpful IS NOT NULL
        OR feedback_text <> ''
    )
);

CREATE INDEX tutor_sessions_scope_ix
    ON tutor_sessions (course_id, topic_id, status, updated_at DESC);

CREATE INDEX tutor_sessions_resource_ix
    ON tutor_sessions (resource_id, status, updated_at DESC)
    WHERE resource_id IS NOT NULL;

CREATE INDEX tutor_turns_session_order_ix
    ON tutor_turns (session_id, ordinal);

CREATE INDEX tutor_evidence_chunk_ix
    ON tutor_evidence_links (chunk_id, turn_id);

CREATE INDEX tutor_evidence_document_ix
    ON tutor_evidence_links (document_id, turn_id);

CREATE INDEX tutor_feedback_turn_ix
    ON tutor_feedback (turn_id, created_at DESC);
