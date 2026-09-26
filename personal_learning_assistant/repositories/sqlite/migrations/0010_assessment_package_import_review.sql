-- Assessment Studio Phase B: versioned ANVAYA Assessment Package staging,
-- review, provenance and canonical question/runtime metadata.
--
-- Imported packages are never written directly into canonical assessments.
-- They are staged, reviewed and explicitly approved first.

CREATE TABLE assessment_import_batches (
    id TEXT PRIMARY KEY,
    package_id TEXT NOT NULL,
    package_revision INTEGER NOT NULL CHECK (package_revision > 0),
    package_schema TEXT NOT NULL,
    package_version INTEGER NOT NULL CHECK (package_version > 0),
    source_filename TEXT NOT NULL DEFAULT '',
    source_sha256 TEXT NOT NULL CHECK (length(source_sha256) = 64),
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE RESTRICT,
    title TEXT NOT NULL,
    assessment_type TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('exam', 'practice')),
    duration_minutes INTEGER NOT NULL CHECK (duration_minutes > 0),
    total_marks_milli INTEGER NOT NULL CHECK (total_marks_milli >= 0),
    instructions_text TEXT NOT NULL DEFAULT '',
    authoring_engine TEXT NOT NULL,
    authoring_model TEXT NOT NULL DEFAULT '',
    authoring_purpose TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'review'
        CHECK (status IN ('review', 'approved', 'rejected')),
    package_json TEXT NOT NULL,
    validation_notes_json TEXT NOT NULL DEFAULT '[]',
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    assessment_id TEXT UNIQUE REFERENCES assessments(id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    approved_at TEXT,
    rejected_at TEXT,
    UNIQUE (package_id, package_revision)
);

CREATE TABLE assessment_import_questions (
    id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL
        REFERENCES assessment_import_batches(id) ON DELETE CASCADE,
    package_question_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    question_number TEXT NOT NULL DEFAULT '',
    section_label TEXT NOT NULL DEFAULT '',
    question_type TEXT NOT NULL,
    question_text TEXT NOT NULL,
    max_marks_milli INTEGER
        CHECK (max_marks_milli IS NULL OR max_marks_milli >= 0),
    negative_marks_milli INTEGER NOT NULL DEFAULT 0
        CHECK (negative_marks_milli >= 0),
    scoring_policy TEXT NOT NULL DEFAULT 'standard',
    difficulty TEXT NOT NULL DEFAULT '',
    expected_method TEXT NOT NULL DEFAULT '',
    estimated_seconds INTEGER
        CHECK (estimated_seconds IS NULL OR estimated_seconds > 0),
    chapter_label TEXT NOT NULL DEFAULT '',
    raw_topic_label TEXT NOT NULL DEFAULT '',
    subtopic_label TEXT NOT NULL DEFAULT '',
    concepts_json TEXT NOT NULL DEFAULT '[]',
    authoring_confidence REAL
        CHECK (
            authoring_confidence IS NULL
            OR authoring_confidence BETWEEN 0.0 AND 1.0
        ),
    mapping_confidence REAL
        CHECK (
            mapping_confidence IS NULL
            OR mapping_confidence BETWEEN 0.0 AND 1.0
        ),
    selected_topic_id TEXT
        REFERENCES topics(id) ON DELETE RESTRICT,
    review_required INTEGER NOT NULL DEFAULT 0
        CHECK (review_required IN (0, 1)),
    solution_text TEXT NOT NULL DEFAULT '',
    rubric_text TEXT NOT NULL DEFAULT '',
    answer_json TEXT NOT NULL DEFAULT '{}',
    source_kind TEXT NOT NULL DEFAULT '',
    source_label TEXT NOT NULL DEFAULT '',
    source_page INTEGER CHECK (source_page IS NULL OR source_page >= 1),
    source_locator TEXT NOT NULL DEFAULT '',
    canonical_question_id TEXT UNIQUE
        REFERENCES questions(id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (batch_id, package_question_id),
    UNIQUE (batch_id, ordinal)
);

CREATE TABLE assessment_import_question_options (
    question_id TEXT NOT NULL
        REFERENCES assessment_import_questions(id) ON DELETE CASCADE,
    option_id TEXT NOT NULL,
    position INTEGER NOT NULL CHECK (position > 0),
    option_text TEXT NOT NULL,
    is_correct INTEGER NOT NULL DEFAULT 0 CHECK (is_correct IN (0, 1)),
    PRIMARY KEY (question_id, option_id),
    UNIQUE (question_id, position)
);

CREATE TABLE assessment_runtime_specs (
    assessment_id TEXT PRIMARY KEY
        REFERENCES assessments(id) ON DELETE CASCADE,
    mode TEXT NOT NULL CHECK (mode IN ('exam', 'practice')),
    duration_minutes INTEGER NOT NULL CHECK (duration_minutes > 0),
    instructions_text TEXT NOT NULL DEFAULT '',
    origin TEXT NOT NULL DEFAULT 'external_package',
    package_id TEXT NOT NULL DEFAULT '',
    package_revision INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE assessment_question_specs (
    question_id TEXT PRIMARY KEY
        REFERENCES questions(id) ON DELETE CASCADE,
    package_question_id TEXT NOT NULL DEFAULT '',
    question_number TEXT NOT NULL DEFAULT '',
    section_label TEXT NOT NULL DEFAULT '',
    question_type TEXT NOT NULL,
    negative_marks_milli INTEGER NOT NULL DEFAULT 0
        CHECK (negative_marks_milli >= 0),
    scoring_policy TEXT NOT NULL DEFAULT 'standard',
    difficulty TEXT NOT NULL DEFAULT '',
    expected_method TEXT NOT NULL DEFAULT '',
    estimated_seconds INTEGER
        CHECK (estimated_seconds IS NULL OR estimated_seconds > 0),
    chapter_label TEXT NOT NULL DEFAULT '',
    subtopic_label TEXT NOT NULL DEFAULT '',
    concepts_json TEXT NOT NULL DEFAULT '[]',
    authoring_confidence REAL
        CHECK (
            authoring_confidence IS NULL
            OR authoring_confidence BETWEEN 0.0 AND 1.0
        ),
    solution_text TEXT NOT NULL DEFAULT '',
    rubric_text TEXT NOT NULL DEFAULT '',
    answer_json TEXT NOT NULL DEFAULT '{}',
    source_kind TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE question_options (
    question_id TEXT NOT NULL
        REFERENCES questions(id) ON DELETE CASCADE,
    option_id TEXT NOT NULL,
    position INTEGER NOT NULL CHECK (position > 0),
    option_text TEXT NOT NULL,
    is_correct INTEGER NOT NULL DEFAULT 0 CHECK (is_correct IN (0, 1)),
    PRIMARY KEY (question_id, option_id),
    UNIQUE (question_id, position)
);

CREATE INDEX assessment_import_batches_status_ix
    ON assessment_import_batches(status, created_at);

CREATE INDEX assessment_import_batches_course_ix
    ON assessment_import_batches(course_id, status, created_at);

CREATE INDEX assessment_import_questions_batch_ix
    ON assessment_import_questions(batch_id, ordinal);

CREATE INDEX assessment_import_questions_topic_ix
    ON assessment_import_questions(selected_topic_id, batch_id);

CREATE INDEX assessment_question_specs_type_ix
    ON assessment_question_specs(question_type);
