-- Phase 3.1 Fix 2: complete structured academic schema.
-- JSON/current files remain authoritative until the Phase 4 cutover.
-- Obsidian Markdown bodies, source PDFs, credentials, and semantic vectors
-- remain outside SQLite; this schema stores metadata and relationships only.

-- ================================================================
-- Academic structure
-- ================================================================

CREATE TABLE semesters (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    academic_year TEXT NOT NULL,
    starts_on TEXT,
    ends_on TEXT,
    status TEXT NOT NULL DEFAULT 'planned',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (academic_year, name)
);

CREATE TABLE courses (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL COLLATE NOCASE,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    UNIQUE (code)
);

CREATE TABLE semester_courses (
    semester_id TEXT NOT NULL
        REFERENCES semesters(id) ON DELETE RESTRICT,
    course_id TEXT NOT NULL
        REFERENCES courses(id) ON DELETE RESTRICT,
    credits_milli INTEGER
        CHECK (credits_milli IS NULL OR credits_milli >= 0),
    instructor TEXT NOT NULL DEFAULT '',
    enrollment_status TEXT NOT NULL DEFAULT 'enrolled',
    PRIMARY KEY (semester_id, course_id)
);

CREATE TABLE course_aliases (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL
        REFERENCES courses(id) ON DELETE RESTRICT,
    alias TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE (provider, normalized_alias)
);

CREATE TABLE course_relations (
    id TEXT PRIMARY KEY,
    from_course_id TEXT NOT NULL
        REFERENCES courses(id) ON DELETE RESTRICT,
    to_course_id TEXT NOT NULL
        REFERENCES courses(id) ON DELETE RESTRICT,
    relation_type TEXT NOT NULL,
    confidence REAL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (from_course_id <> to_course_id),
    UNIQUE (from_course_id, to_course_id, relation_type)
);

CREATE TABLE topics (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL
        REFERENCES courses(id) ON DELETE RESTRICT,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0 CHECK (position >= 0),
    status TEXT NOT NULL DEFAULT 'not_started',
    confidence INTEGER
        CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 5),
    raw_import_status TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    UNIQUE (course_id, normalized_name)
);

CREATE TABLE topic_aliases (
    id TEXT PRIMARY KEY,
    topic_id TEXT NOT NULL
        REFERENCES topics(id) ON DELETE RESTRICT,
    course_id TEXT NOT NULL
        REFERENCES courses(id) ON DELETE RESTRICT,
    alias TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE (course_id, normalized_alias)
);

-- ================================================================
-- Notes and vault metadata
-- ================================================================

CREATE TABLE vaults (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    root_path TEXT NOT NULL,
    path_key TEXT NOT NULL UNIQUE,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    last_scanned_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE note_metadata (
    id TEXT PRIMARY KEY,
    vault_id TEXT NOT NULL
        REFERENCES vaults(id) ON DELETE RESTRICT,
    relative_path TEXT NOT NULL,
    path_key TEXT NOT NULL,
    title TEXT NOT NULL,
    note_type TEXT NOT NULL DEFAULT 'note',
    confidence INTEGER
        CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 5),
    revision_status TEXT NOT NULL DEFAULT 'unreviewed',
    pinned_at TEXT,
    archived_at TEXT,
    trashed_at TEXT,
    source_hash TEXT NOT NULL,
    file_mtime_ns INTEGER NOT NULL CHECK (file_mtime_ns >= 0),
    frontmatter_extra_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (vault_id, path_key)
);

CREATE TABLE tags (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE note_tags (
    note_id TEXT NOT NULL
        REFERENCES note_metadata(id) ON DELETE CASCADE,
    tag_id TEXT NOT NULL
        REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (note_id, tag_id)
);

CREATE TABLE note_courses (
    note_id TEXT NOT NULL
        REFERENCES note_metadata(id) ON DELETE CASCADE,
    course_id TEXT NOT NULL
        REFERENCES courses(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'related',
    PRIMARY KEY (note_id, course_id, role)
);

CREATE TABLE note_topics (
    note_id TEXT NOT NULL
        REFERENCES note_metadata(id) ON DELETE CASCADE,
    topic_id TEXT NOT NULL
        REFERENCES topics(id) ON DELETE CASCADE,
    relation_source TEXT NOT NULL DEFAULT '',
    confidence REAL,
    PRIMARY KEY (note_id, topic_id, relation_source)
);

CREATE TABLE note_links (
    id TEXT PRIMARY KEY,
    source_note_id TEXT NOT NULL
        REFERENCES note_metadata(id) ON DELETE CASCADE,
    target_note_id TEXT
        REFERENCES note_metadata(id) ON DELETE CASCADE,
    unresolved_target TEXT NOT NULL DEFAULT '',
    source_position TEXT NOT NULL,
    heading TEXT NOT NULL DEFAULT '',
    block_id TEXT NOT NULL DEFAULT '',
    link_type TEXT NOT NULL DEFAULT 'wiki',
    created_at TEXT NOT NULL,
    CHECK (target_note_id IS NOT NULL OR unresolved_target <> '')
);

-- ================================================================
-- Learning resources and knowledge documents
-- ================================================================

CREATE TABLE resources (
    id TEXT PRIMARY KEY,
    resource_type TEXT NOT NULL,
    title TEXT NOT NULL,
    canonical_uri TEXT,
    provider TEXT NOT NULL DEFAULT '',
    external_id TEXT,
    status TEXT NOT NULL DEFAULT 'not_started',
    rating INTEGER CHECK (rating IS NULL OR rating BETWEEN 1 AND 5),
    quality_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    archived_at TEXT,
    deleted_at TEXT
);

CREATE TABLE resource_courses (
    resource_id TEXT NOT NULL
        REFERENCES resources(id) ON DELETE CASCADE,
    course_id TEXT NOT NULL
        REFERENCES courses(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'supporting',
    PRIMARY KEY (resource_id, course_id, role)
);

CREATE TABLE resource_topics (
    resource_id TEXT NOT NULL
        REFERENCES resources(id) ON DELETE CASCADE,
    topic_id TEXT NOT NULL
        REFERENCES topics(id) ON DELETE CASCADE,
    relation_source TEXT NOT NULL DEFAULT '',
    confidence REAL,
    PRIMARY KEY (resource_id, topic_id, relation_source)
);

CREATE TABLE resource_notes (
    resource_id TEXT NOT NULL
        REFERENCES resources(id) ON DELETE CASCADE,
    note_id TEXT NOT NULL
        REFERENCES note_metadata(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'related',
    PRIMARY KEY (resource_id, note_id, role)
);

CREATE TABLE resource_progress_events (
    id TEXT PRIMARY KEY,
    resource_id TEXT NOT NULL
        REFERENCES resources(id) ON DELETE RESTRICT,
    occurred_at TEXT NOT NULL,
    status TEXT NOT NULL,
    value REAL,
    max_value REAL CHECK (max_value IS NULL OR max_value >= 0),
    unit TEXT NOT NULL DEFAULT '',
    position TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    CHECK (value IS NULL OR max_value IS NULL OR value <= max_value)
);

CREATE TABLE knowledge_documents (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    canonical_uri TEXT,
    path_key TEXT,
    mime_type TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL,
    size_bytes INTEGER CHECK (size_bytes IS NULL OR size_bytes >= 0),
    source_timestamp TEXT,
    extraction_status TEXT NOT NULL DEFAULT 'pending',
    extraction_version TEXT NOT NULL DEFAULT '',
    extraction_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE resource_documents (
    resource_id TEXT NOT NULL
        REFERENCES resources(id) ON DELETE CASCADE,
    document_id TEXT NOT NULL
        REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'source',
    PRIMARY KEY (resource_id, document_id, role)
);

CREATE TABLE knowledge_chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL
        REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    page_number INTEGER CHECK (page_number IS NULL OR page_number >= 1),
    char_start INTEGER CHECK (char_start IS NULL OR char_start >= 0),
    char_end INTEGER CHECK (char_end IS NULL OR char_end >= 0),
    chunk_type TEXT NOT NULL DEFAULT 'text',
    text_hash TEXT NOT NULL,
    extraction_version TEXT NOT NULL,
    chunk_text TEXT,
    CHECK (char_end IS NULL OR char_start IS NULL OR char_end >= char_start),
    UNIQUE (document_id, extraction_version, ordinal)
);

CREATE TABLE index_jobs (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL
        REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    content_hash TEXT NOT NULL,
    index_kind TEXT NOT NULL,
    model_name TEXT NOT NULL DEFAULT '',
    model_version TEXT NOT NULL DEFAULT '',
    index_version TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    failed_at TEXT,
    error TEXT,
    UNIQUE (
        document_id,
        content_hash,
        index_kind,
        model_name,
        model_version,
        index_version
    )
);

-- ================================================================
-- Assessments and performance
-- ================================================================

CREATE TABLE assessments (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL
        REFERENCES courses(id) ON DELETE RESTRICT,
    assessment_type TEXT NOT NULL,
    title TEXT NOT NULL,
    due_on TEXT,
    due_time TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    weight_bps INTEGER
        CHECK (weight_bps IS NULL OR weight_bps BETWEEN 0 AND 10000),
    max_points_milli INTEGER
        CHECK (max_points_milli IS NULL OR max_points_milli >= 0),
    earned_points_milli INTEGER
        CHECK (earned_points_milli IS NULL OR earned_points_milli >= 0),
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    CHECK (
        earned_points_milli IS NULL
        OR max_points_milli IS NULL
        OR earned_points_milli <= max_points_milli
    )
);

-- Cross-domain assessment relationships are declared after assessments
-- so every foreign-key target already exists when these tables are created.

CREATE TABLE note_assessments (
    note_id TEXT NOT NULL
        REFERENCES note_metadata(id) ON DELETE CASCADE,
    assessment_id TEXT NOT NULL
        REFERENCES assessments(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'related',
    PRIMARY KEY (note_id, assessment_id, role)
);

CREATE TABLE resource_assessments (
    resource_id TEXT NOT NULL
        REFERENCES resources(id) ON DELETE CASCADE,
    assessment_id TEXT NOT NULL
        REFERENCES assessments(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'related',
    PRIMARY KEY (resource_id, assessment_id, role)
);

CREATE TABLE assessment_topics (
    id TEXT PRIMARY KEY,
    assessment_id TEXT NOT NULL
        REFERENCES assessments(id) ON DELETE CASCADE,
    topic_id TEXT
        REFERENCES topics(id) ON DELETE RESTRICT,
    raw_label TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    confidence REAL,
    created_at TEXT NOT NULL,
    CHECK (topic_id IS NOT NULL OR raw_label <> '')
);

CREATE TABLE questions (
    id TEXT PRIMARY KEY,
    assessment_id TEXT NOT NULL
        REFERENCES assessments(id) ON DELETE RESTRICT,
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    question_text TEXT NOT NULL,
    max_marks_milli INTEGER
        CHECK (max_marks_milli IS NULL OR max_marks_milli >= 0),
    status TEXT NOT NULL DEFAULT 'not_started',
    user_notes TEXT NOT NULL DEFAULT '',
    import_batch_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    UNIQUE (assessment_id, ordinal)
);

CREATE TABLE question_topic_mappings (
    id TEXT PRIMARY KEY,
    question_id TEXT NOT NULL
        REFERENCES questions(id) ON DELETE RESTRICT,
    topic_id TEXT NOT NULL
        REFERENCES topics(id) ON DELETE RESTRICT,
    score REAL,
    rank INTEGER CHECK (rank IS NULL OR rank > 0),
    method TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'proposed',
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    reviewed_at TEXT
);

CREATE TABLE question_sources (
    id TEXT PRIMARY KEY,
    question_id TEXT NOT NULL
        REFERENCES questions(id) ON DELETE RESTRICT,
    document_id TEXT
        REFERENCES knowledge_documents(id) ON DELETE RESTRICT,
    resource_id TEXT
        REFERENCES resources(id) ON DELETE RESTRICT,
    note_id TEXT
        REFERENCES note_metadata(id) ON DELETE RESTRICT,
    page_number INTEGER CHECK (page_number IS NULL OR page_number >= 1),
    locator TEXT NOT NULL DEFAULT '',
    raw_source_label TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    CHECK (
        document_id IS NOT NULL
        OR resource_id IS NOT NULL
        OR note_id IS NOT NULL
        OR raw_source_label <> ''
    )
);

CREATE TABLE question_attempts (
    id TEXT PRIMARY KEY,
    question_id TEXT NOT NULL
        REFERENCES questions(id) ON DELETE RESTRICT,
    attempt_number INTEGER NOT NULL CHECK (attempt_number > 0),
    outcome TEXT NOT NULL,
    earned_marks_milli INTEGER
        CHECK (earned_marks_milli IS NULL OR earned_marks_milli >= 0),
    max_marks_milli INTEGER
        CHECK (max_marks_milli IS NULL OR max_marks_milli >= 0),
    response_ref TEXT,
    feedback_ref TEXT,
    occurred_at TEXT NOT NULL,
    CHECK (
        earned_marks_milli IS NULL
        OR max_marks_milli IS NULL
        OR earned_marks_milli <= max_marks_milli
    ),
    UNIQUE (question_id, attempt_number)
);

CREATE TABLE mistake_events (
    id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL
        REFERENCES question_attempts(id) ON DELETE RESTRICT,
    category TEXT NOT NULL,
    mistake_text TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

-- ================================================================
-- Progress, learning memory, and planning
-- ================================================================

CREATE TABLE topic_progress_events (
    id TEXT PRIMARY KEY,
    topic_id TEXT NOT NULL
        REFERENCES topics(id) ON DELETE RESTRICT,
    event_type TEXT NOT NULL,
    previous_status TEXT,
    new_status TEXT,
    confidence INTEGER
        CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 5),
    evidence_type TEXT,
    evidence_id TEXT,
    occurred_at TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT ''
);

CREATE TABLE progress_snapshots (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL
        REFERENCES courses(id) ON DELETE RESTRICT,
    snapshot_date TEXT NOT NULL,
    counts_json TEXT NOT NULL DEFAULT '{}',
    score_json TEXT NOT NULL DEFAULT '{}',
    engine_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (course_id, snapshot_date, engine_version)
);

CREATE TABLE learning_memory_entries (
    id TEXT PRIMARY KEY,
    scope_type TEXT NOT NULL,
    scope_id TEXT,
    kind TEXT NOT NULL,
    topic_id TEXT
        REFERENCES topics(id) ON DELETE RESTRICT,
    raw_topic TEXT NOT NULL DEFAULT '',
    memory_text TEXT NOT NULL DEFAULT '',
    source_entity_type TEXT,
    source_entity_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT
);

CREATE TABLE study_plans (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    horizon TEXT NOT NULL,
    starts_on TEXT NOT NULL,
    ends_on TEXT NOT NULL,
    requested_minutes INTEGER NOT NULL CHECK (requested_minutes >= 0),
    allocated_minutes INTEGER NOT NULL CHECK (allocated_minutes >= 0),
    status TEXT NOT NULL DEFAULT 'proposed',
    engine_name TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    rationale TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (ends_on >= starts_on)
);

CREATE TABLE study_plan_items (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL
        REFERENCES study_plans(id) ON DELETE RESTRICT,
    plan_date TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    course_id TEXT
        REFERENCES courses(id) ON DELETE RESTRICT,
    topic_id TEXT
        REFERENCES topics(id) ON DELETE RESTRICT,
    assessment_id TEXT
        REFERENCES assessments(id) ON DELETE RESTRICT,
    resource_id TEXT
        REFERENCES resources(id) ON DELETE RESTRICT,
    note_id TEXT
        REFERENCES note_metadata(id) ON DELETE RESTRICT,
    minutes INTEGER NOT NULL CHECK (minutes >= 0),
    action TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    score REAL,
    status TEXT NOT NULL DEFAULT 'planned',
    UNIQUE (plan_id, plan_date, ordinal)
);

CREATE TABLE study_sessions (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    duration_minutes INTEGER NOT NULL CHECK (duration_minutes >= 0),
    course_id TEXT
        REFERENCES courses(id) ON DELETE RESTRICT,
    topic_id TEXT
        REFERENCES topics(id) ON DELETE RESTRICT,
    resource_id TEXT
        REFERENCES resources(id) ON DELETE RESTRICT,
    assessment_id TEXT
        REFERENCES assessments(id) ON DELETE RESTRICT,
    note_id TEXT
        REFERENCES note_metadata(id) ON DELETE RESTRICT,
    plan_item_id TEXT
        REFERENCES study_plan_items(id) ON DELETE RESTRICT,
    outcome TEXT NOT NULL DEFAULT '',
    confidence INTEGER
        CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 5),
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    CHECK (ended_at IS NULL OR ended_at >= started_at)
);

-- ================================================================
-- Grades and academic calendar
-- ================================================================

CREATE TABLE grade_scales (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT '',
    verified INTEGER NOT NULL DEFAULT 0 CHECK (verified IN (0, 1)),
    active_from TEXT,
    active_to TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (name, active_from)
);

CREATE TABLE grade_bands (
    id TEXT PRIMARY KEY,
    scale_id TEXT NOT NULL
        REFERENCES grade_scales(id) ON DELETE RESTRICT,
    minimum_bps INTEGER NOT NULL
        CHECK (minimum_bps BETWEEN 0 AND 10000),
    letter_grade TEXT NOT NULL,
    grade_point_milli INTEGER NOT NULL CHECK (grade_point_milli >= 0),
    UNIQUE (scale_id, minimum_bps)
);

CREATE TABLE semester_grade_settings (
    semester_id TEXT PRIMARY KEY
        REFERENCES semesters(id) ON DELETE RESTRICT,
    scale_id TEXT NOT NULL
        REFERENCES grade_scales(id) ON DELETE RESTRICT,
    target_sgpa_milli INTEGER
        CHECK (target_sgpa_milli IS NULL OR target_sgpa_milli >= 0),
    updated_at TEXT NOT NULL
);

CREATE TABLE manual_grade_entries (
    id TEXT PRIMARY KEY,
    semester_id TEXT NOT NULL,
    course_id TEXT NOT NULL,
    score_bps INTEGER CHECK (score_bps IS NULL OR score_bps BETWEEN 0 AND 10000),
    letter_grade TEXT,
    grade_point_milli INTEGER
        CHECK (grade_point_milli IS NULL OR grade_point_milli >= 0),
    entry_kind TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    recorded_at TEXT NOT NULL,
    FOREIGN KEY (semester_id, course_id)
        REFERENCES semester_courses(semester_id, course_id)
        ON DELETE RESTRICT,
    CHECK (
        score_bps IS NOT NULL
        OR letter_grade IS NOT NULL
        OR grade_point_milli IS NOT NULL
    )
);

CREATE TABLE semester_results (
    id TEXT PRIMARY KEY,
    semester_id TEXT NOT NULL UNIQUE
        REFERENCES semesters(id) ON DELETE RESTRICT,
    earned_credits_milli INTEGER NOT NULL CHECK (earned_credits_milli >= 0),
    earned_grade_points_milli INTEGER NOT NULL
        CHECK (earned_grade_points_milli >= 0),
    sgpa_milli INTEGER NOT NULL CHECK (sgpa_milli >= 0),
    verified INTEGER NOT NULL DEFAULT 0 CHECK (verified IN (0, 1)),
    source TEXT NOT NULL DEFAULT '',
    recorded_at TEXT NOT NULL
);

CREATE TABLE academic_events (
    id TEXT PRIMARY KEY,
    semester_id TEXT
        REFERENCES semesters(id) ON DELETE RESTRICT,
    course_id TEXT
        REFERENCES courses(id) ON DELETE RESTRICT,
    event_kind TEXT NOT NULL,
    title TEXT NOT NULL,
    starts_at TEXT NOT NULL,
    ends_at TEXT,
    all_day INTEGER NOT NULL DEFAULT 0 CHECK (all_day IN (0, 1)),
    recurrence_rule TEXT,
    reference_type TEXT,
    reference_id TEXT,
    status TEXT NOT NULL DEFAULT 'scheduled',
    source_entity_type TEXT,
    source_entity_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    CHECK (ends_at IS NULL OR ends_at >= starts_at)
);

-- ================================================================
-- Uniqueness and lookup indexes
-- ================================================================

CREATE INDEX semester_courses_course_ix
    ON semester_courses (course_id, semester_id);

CREATE INDEX course_aliases_course_ix
    ON course_aliases (course_id, provider);

CREATE INDEX course_relations_to_ix
    ON course_relations (to_course_id, relation_type);

CREATE INDEX topics_course_position_ix
    ON topics (course_id, position);

CREATE INDEX topic_aliases_topic_ix
    ON topic_aliases (topic_id);

CREATE INDEX note_metadata_lifecycle_ix
    ON note_metadata (trashed_at, archived_at, pinned_at);

CREATE INDEX note_tags_tag_ix
    ON note_tags (tag_id, note_id);

CREATE INDEX note_courses_course_ix
    ON note_courses (course_id, note_id);

CREATE INDEX note_topics_topic_ix
    ON note_topics (topic_id, note_id);

CREATE UNIQUE INDEX note_links_resolved_uq
    ON note_links (source_note_id, source_position, target_note_id)
    WHERE target_note_id IS NOT NULL;

CREATE UNIQUE INDEX note_links_unresolved_uq
    ON note_links (source_note_id, source_position, unresolved_target)
    WHERE target_note_id IS NULL;

CREATE INDEX note_links_target_ix
    ON note_links (target_note_id)
    WHERE target_note_id IS NOT NULL;

CREATE INDEX note_assessments_assessment_ix
    ON note_assessments (assessment_id, note_id);

CREATE UNIQUE INDEX resources_provider_external_id_uq
    ON resources (provider, external_id)
    WHERE external_id IS NOT NULL AND external_id <> '';

CREATE INDEX resources_type_status_title_ix
    ON resources (resource_type, status, title);

CREATE INDEX resource_courses_course_ix
    ON resource_courses (course_id, resource_id);

CREATE INDEX resource_topics_topic_ix
    ON resource_topics (topic_id, resource_id);

CREATE INDEX resource_notes_note_ix
    ON resource_notes (note_id, resource_id);

CREATE INDEX resource_assessments_assessment_ix
    ON resource_assessments (assessment_id, resource_id);

CREATE INDEX resource_progress_events_resource_time_ix
    ON resource_progress_events (resource_id, occurred_at DESC);

CREATE UNIQUE INDEX knowledge_documents_uri_uq
    ON knowledge_documents (canonical_uri)
    WHERE canonical_uri IS NOT NULL AND canonical_uri <> '';

CREATE UNIQUE INDEX knowledge_documents_path_key_uq
    ON knowledge_documents (path_key)
    WHERE path_key IS NOT NULL AND path_key <> '';

CREATE INDEX knowledge_documents_hash_ix
    ON knowledge_documents (content_hash);

CREATE INDEX resource_documents_document_ix
    ON resource_documents (document_id, resource_id);

CREATE INDEX knowledge_chunks_document_version_ix
    ON knowledge_chunks (document_id, extraction_version, ordinal);

CREATE INDEX knowledge_chunks_text_hash_ix
    ON knowledge_chunks (text_hash);

CREATE INDEX index_jobs_status_ix
    ON index_jobs (status, created_at);

CREATE INDEX assessments_course_due_status_ix
    ON assessments (course_id, due_on, status);

CREATE UNIQUE INDEX assessment_topics_resolved_uq
    ON assessment_topics (assessment_id, topic_id)
    WHERE topic_id IS NOT NULL;

CREATE UNIQUE INDEX assessment_topics_unresolved_uq
    ON assessment_topics (assessment_id, raw_label)
    WHERE topic_id IS NULL;

CREATE INDEX assessment_topics_topic_ix
    ON assessment_topics (topic_id, assessment_id)
    WHERE topic_id IS NOT NULL;

CREATE INDEX questions_assessment_ordinal_ix
    ON questions (assessment_id, ordinal);

CREATE INDEX question_topic_mappings_question_state_ix
    ON question_topic_mappings (question_id, state, rank);

CREATE INDEX question_topic_mappings_topic_ix
    ON question_topic_mappings (topic_id, question_id);

CREATE INDEX question_sources_question_ix
    ON question_sources (question_id);

CREATE INDEX question_attempts_question_time_ix
    ON question_attempts (question_id, occurred_at DESC);

CREATE INDEX mistake_events_attempt_ix
    ON mistake_events (attempt_id, created_at);

CREATE INDEX topic_progress_events_topic_time_ix
    ON topic_progress_events (topic_id, occurred_at DESC);

CREATE INDEX progress_snapshots_course_date_ix
    ON progress_snapshots (course_id, snapshot_date DESC);

CREATE INDEX learning_memory_entries_scope_ix
    ON learning_memory_entries (scope_type, scope_id, archived_at);

CREATE INDEX learning_memory_entries_topic_ix
    ON learning_memory_entries (topic_id, archived_at)
    WHERE topic_id IS NOT NULL;

CREATE INDEX study_plans_window_ix
    ON study_plans (starts_on, ends_on, status);

CREATE INDEX study_plan_items_plan_order_ix
    ON study_plan_items (plan_id, plan_date, ordinal);

CREATE INDEX study_plan_items_course_date_ix
    ON study_plan_items (course_id, plan_date)
    WHERE course_id IS NOT NULL;

CREATE INDEX study_plan_items_topic_date_ix
    ON study_plan_items (topic_id, plan_date)
    WHERE topic_id IS NOT NULL;

CREATE INDEX study_sessions_course_time_ix
    ON study_sessions (course_id, started_at DESC)
    WHERE course_id IS NOT NULL;

CREATE INDEX study_sessions_topic_time_ix
    ON study_sessions (topic_id, started_at DESC)
    WHERE topic_id IS NOT NULL;

CREATE INDEX grade_bands_scale_threshold_ix
    ON grade_bands (scale_id, minimum_bps DESC);

CREATE INDEX manual_grade_entries_semester_course_ix
    ON manual_grade_entries (semester_id, course_id, recorded_at DESC);

CREATE INDEX academic_events_time_ix
    ON academic_events (starts_at, ends_at);

CREATE INDEX academic_events_course_time_ix
    ON academic_events (course_id, starts_at)
    WHERE course_id IS NOT NULL;

CREATE INDEX academic_events_semester_time_ix
    ON academic_events (semester_id, starts_at)
    WHERE semester_id IS NOT NULL;

-- ================================================================
-- Stable read-model views
-- Complex academic formulas remain in Python domain engines.
-- ================================================================

CREATE VIEW active_courses_with_semester AS
SELECT
    c.id AS course_id,
    c.code,
    c.name AS course_name,
    c.status AS course_status,
    sc.semester_id,
    s.name AS semester_name,
    s.academic_year,
    sc.credits_milli,
    sc.instructor,
    sc.enrollment_status
FROM courses AS c
LEFT JOIN semester_courses AS sc
    ON sc.course_id = c.id
LEFT JOIN semesters AS s
    ON s.id = sc.semester_id
WHERE c.deleted_at IS NULL
  AND c.status = 'active';

CREATE VIEW open_assessments AS
SELECT
    a.id,
    a.course_id,
    a.assessment_type,
    a.title,
    a.due_on,
    a.due_time,
    a.status,
    a.weight_bps,
    a.max_points_milli,
    a.earned_points_milli
FROM assessments AS a
WHERE a.deleted_at IS NULL
  AND a.status NOT IN ('completed', 'cancelled', 'archived');

CREATE VIEW resource_latest_progress AS
SELECT
    r.id AS resource_id,
    r.title,
    r.resource_type,
    r.status AS resource_status,
    e.id AS progress_event_id,
    e.occurred_at,
    e.status AS progress_status,
    e.value,
    e.max_value,
    e.unit,
    e.position
FROM resources AS r
LEFT JOIN resource_progress_events AS e
    ON e.id = (
        SELECT e2.id
        FROM resource_progress_events AS e2
        WHERE e2.resource_id = r.id
        ORDER BY e2.occurred_at DESC, e2.id DESC
        LIMIT 1
    )
WHERE r.deleted_at IS NULL;

CREATE VIEW note_active_view AS
SELECT
    id,
    vault_id,
    relative_path,
    path_key,
    title,
    note_type,
    confidence,
    revision_status,
    pinned_at,
    source_hash,
    file_mtime_ns,
    frontmatter_extra_json,
    created_at,
    updated_at
FROM note_metadata
WHERE trashed_at IS NULL
  AND archived_at IS NULL;

CREATE VIEW question_latest_attempt AS
SELECT
    q.id AS question_id,
    q.assessment_id,
    q.ordinal,
    q.question_text,
    q.status AS question_status,
    a.id AS attempt_id,
    a.attempt_number,
    a.outcome,
    a.earned_marks_milli,
    a.max_marks_milli,
    a.occurred_at
FROM questions AS q
LEFT JOIN question_attempts AS a
    ON a.id = (
        SELECT a2.id
        FROM question_attempts AS a2
        WHERE a2.question_id = q.id
        ORDER BY a2.attempt_number DESC, a2.occurred_at DESC, a2.id DESC
        LIMIT 1
    )
WHERE q.deleted_at IS NULL;

CREATE VIEW course_assessment_weight_summary AS
SELECT
    c.id AS course_id,
    c.code,
    COUNT(a.id) AS assessment_count,
    COALESCE(SUM(a.weight_bps), 0) AS total_weight_bps
FROM courses AS c
LEFT JOIN assessments AS a
    ON a.course_id = c.id
   AND a.deleted_at IS NULL
GROUP BY c.id, c.code;
