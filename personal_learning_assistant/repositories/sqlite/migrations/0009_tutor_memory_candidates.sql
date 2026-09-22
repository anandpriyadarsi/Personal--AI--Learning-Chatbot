-- Tutor 2.2.3: reviewable candidate long-term learning signals.
-- Candidates are not authoritative learning memory or topic progress.
-- Acceptance/rejection is explicit and provenance-backed.

CREATE TABLE tutor_memory_candidates (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL
        REFERENCES courses(id) ON DELETE RESTRICT,
    topic_id TEXT
        REFERENCES topics(id) ON DELETE RESTRICT,
    signal_kind TEXT NOT NULL,
    candidate_kind TEXT NOT NULL,
    candidate_text TEXT NOT NULL,
    confidence INTEGER NOT NULL
        CHECK (confidence BETWEEN 1 AND 5),
    evidence_count INTEGER NOT NULL
        CHECK (evidence_count >= 2),
    session_count INTEGER NOT NULL
        CHECK (session_count >= 2),
    first_observed_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL,
    provenance_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'proposed'
        CHECK (status IN ('proposed','accepted','rejected','superseded')),
    supersedes_candidate_id TEXT
        REFERENCES tutor_memory_candidates(id) ON DELETE RESTRICT,
    accepted_memory_entry_id TEXT
        REFERENCES learning_memory_entries(id) ON DELETE RESTRICT,
    review_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    reviewed_at TEXT,
    CHECK (
        (status = 'proposed' AND reviewed_at IS NULL)
        OR (status IN ('accepted','rejected','superseded') AND reviewed_at IS NOT NULL)
    ),
    CHECK (
        status <> 'accepted'
        OR accepted_memory_entry_id IS NOT NULL
    )
);

CREATE UNIQUE INDEX tutor_memory_candidates_identity_uq
    ON tutor_memory_candidates (
        course_id,
        COALESCE(topic_id, ''),
        signal_kind,
        candidate_text,
        first_observed_at,
        last_observed_at
    );

CREATE INDEX tutor_memory_candidates_scope_status_ix
    ON tutor_memory_candidates (
        course_id,
        topic_id,
        status,
        last_observed_at DESC
    );

CREATE INDEX tutor_memory_candidates_status_ix
    ON tutor_memory_candidates (
        status,
        updated_at DESC
    );
