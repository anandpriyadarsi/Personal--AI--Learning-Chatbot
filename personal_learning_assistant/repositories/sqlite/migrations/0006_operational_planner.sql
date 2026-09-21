-- Phase 7.5.13: Operational Planner — tasks, calendar, month plan, daily/weekly reviews.
-- Existing academic entities remain authoritative where they already fit.
-- This migration adds only feature-owned operational-planning state.

CREATE TABLE month_plan_imports (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    source_filename TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    title TEXT NOT NULL,
    starts_on TEXT NOT NULL,
    ends_on TEXT NOT NULL,
    timezone TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('previewed', 'active', 'superseded', 'rejected')),
    created_at TEXT NOT NULL,
    approved_at TEXT,
    superseded_at TEXT,
    CHECK (ends_on >= starts_on)
);

CREATE UNIQUE INDEX month_plan_imports_source_hash_uq
    ON month_plan_imports (source_sha256);

CREATE UNIQUE INDEX month_plan_imports_one_active_plan_uq
    ON month_plan_imports (plan_id)
    WHERE status = 'active';

CREATE INDEX month_plan_imports_plan_status_ix
    ON month_plan_imports (plan_id, status, created_at DESC);

CREATE TABLE month_plan_import_items (
    id TEXT PRIMARY KEY,
    import_id TEXT NOT NULL
        REFERENCES month_plan_imports(id) ON DELETE CASCADE,
    external_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    entity_snapshot_hash TEXT NOT NULL DEFAULT '',
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (import_id, external_id, entity_type)
);

CREATE INDEX month_plan_import_items_entity_ix
    ON month_plan_import_items (entity_type, entity_id);

CREATE TABLE planner_tasks (
    id TEXT PRIMARY KEY,
    source_import_id TEXT
        REFERENCES month_plan_imports(id) ON DELETE SET NULL,
    external_id TEXT,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    priority TEXT NOT NULL DEFAULT 'P1'
        CHECK (priority IN ('P0', 'P1', 'P2')),
    course_id TEXT
        REFERENCES courses(id) ON DELETE RESTRICT,
    topic_id TEXT
        REFERENCES topics(id) ON DELETE RESTRICT,
    assessment_id TEXT
        REFERENCES assessments(id) ON DELETE RESTRICT,
    estimated_minutes INTEGER
        CHECK (estimated_minutes IS NULL OR estimated_minutes >= 0),
    due_on TEXT,
    preferred_day TEXT,
    preferred_window TEXT,
    rollover_policy TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'backlog'
        CHECK (
            status IN (
                'backlog', 'planned', 'scheduled', 'in_progress',
                'completed', 'skipped', 'archived'
            )
        ),
    manual_revision INTEGER NOT NULL DEFAULT 0 CHECK (manual_revision >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    archived_at TEXT
);

CREATE UNIQUE INDEX planner_tasks_import_external_uq
    ON planner_tasks (source_import_id, external_id)
    WHERE source_import_id IS NOT NULL AND external_id IS NOT NULL;

CREATE INDEX planner_tasks_open_priority_due_ix
    ON planner_tasks (status, priority, due_on);

CREATE INDEX planner_tasks_course_ix
    ON planner_tasks (course_id, status, due_on);

CREATE TABLE routine_templates (
    id TEXT PRIMARY KEY,
    source_import_id TEXT
        REFERENCES month_plan_imports(id) ON DELETE SET NULL,
    external_id TEXT,
    title TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'routine',
    priority TEXT NOT NULL DEFAULT 'P1'
        CHECK (priority IN ('P0', 'P1', 'P2')),
    recurrence_rule TEXT NOT NULL,
    active_from TEXT,
    active_to TEXT,
    start_time TEXT,
    end_time TEXT,
    duration_minutes INTEGER
        CHECK (duration_minutes IS NULL OR duration_minutes >= 0),
    preferred_window TEXT,
    preferred_location TEXT,
    condition_text TEXT NOT NULL DEFAULT '',
    excluded_dates_json TEXT NOT NULL DEFAULT '[]',
    additional_dates_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'paused', 'archived')),
    manual_revision INTEGER NOT NULL DEFAULT 0 CHECK (manual_revision >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX routine_templates_import_external_uq
    ON routine_templates (source_import_id, external_id)
    WHERE source_import_id IS NOT NULL AND external_id IS NOT NULL;

CREATE INDEX routine_templates_status_ix
    ON routine_templates (status, active_from, active_to);

CREATE TABLE daily_agendas (
    id TEXT PRIMARY KEY,
    agenda_date TEXT NOT NULL UNIQUE,
    day_mode TEXT NOT NULL DEFAULT 'normal'
        CHECK (day_mode IN ('minimum_viable', 'normal', 'high_capacity')),
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'approved', 'active', 'closed')),
    generated_at TEXT NOT NULL,
    approved_at TEXT,
    closed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE daily_agenda_items (
    id TEXT PRIMARY KEY,
    agenda_id TEXT NOT NULL
        REFERENCES daily_agendas(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    item_kind TEXT NOT NULL
        CHECK (item_kind IN ('fixed', 'routine', 'task', 'study', 'manual')),
    source_type TEXT NOT NULL DEFAULT '',
    source_id TEXT,
    title TEXT NOT NULL,
    priority TEXT
        CHECK (priority IS NULL OR priority IN ('P0', 'P1', 'P2')),
    starts_at TEXT,
    ends_at TEXT,
    planned_minutes INTEGER
        CHECK (planned_minutes IS NULL OR planned_minutes >= 0),
    actual_minutes INTEGER
        CHECK (actual_minutes IS NULL OR actual_minutes >= 0),
    status TEXT NOT NULL DEFAULT 'planned'
        CHECK (status IN ('planned', 'in_progress', 'completed', 'skipped', 'moved')),
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE (agenda_id, ordinal),
    CHECK (ends_at IS NULL OR starts_at IS NULL OR ends_at >= starts_at)
);

CREATE INDEX daily_agenda_items_agenda_status_ix
    ON daily_agenda_items (agenda_id, status, ordinal);

CREATE INDEX daily_agenda_items_source_ix
    ON daily_agenda_items (source_type, source_id);

CREATE TABLE task_rollover_events (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL
        REFERENCES planner_tasks(id) ON DELETE RESTRICT,
    from_date TEXT NOT NULL,
    to_date TEXT,
    decision TEXT NOT NULL
        CHECK (decision IN ('carry', 'reschedule', 'backlog', 'drop', 'complete')),
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX task_rollover_events_task_ix
    ON task_rollover_events (task_id, created_at DESC);

CREATE TABLE daily_reviews (
    agenda_id TEXT PRIMARY KEY
        REFERENCES daily_agendas(id) ON DELETE CASCADE,
    learned TEXT NOT NULL DEFAULT '',
    biggest_confusion TEXT NOT NULL DEFAULT '',
    coding_completed INTEGER NOT NULL DEFAULT 0 CHECK (coding_completed IN (0, 1)),
    coding_independent INTEGER NOT NULL DEFAULT 0 CHECK (coding_independent IN (0, 1)),
    data_science_ai_assistance_level INTEGER
        CHECK (
            data_science_ai_assistance_level IS NULL
            OR data_science_ai_assistance_level BETWEEN 0 AND 7
        ),
    energy_1_to_5 INTEGER
        CHECK (energy_1_to_5 IS NULL OR energy_1_to_5 BETWEEN 1 AND 5),
    sleep_target TEXT NOT NULL DEFAULT '',
    tomorrow_first_task TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE weekly_reviews (
    id TEXT PRIMARY KEY,
    week_start TEXT NOT NULL,
    week_end TEXT NOT NULL,
    planned_items INTEGER NOT NULL DEFAULT 0 CHECK (planned_items >= 0),
    completed_items INTEGER NOT NULL DEFAULT 0 CHECK (completed_items >= 0),
    planned_focus_minutes INTEGER NOT NULL DEFAULT 0 CHECK (planned_focus_minutes >= 0),
    actual_focus_minutes INTEGER NOT NULL DEFAULT 0 CHECK (actual_focus_minutes >= 0),
    carry_forward_count INTEGER NOT NULL DEFAULT 0 CHECK (carry_forward_count >= 0),
    missed_deadline_count INTEGER NOT NULL DEFAULT 0 CHECK (missed_deadline_count >= 0),
    what_worked TEXT NOT NULL DEFAULT '',
    what_failed TEXT NOT NULL DEFAULT '',
    remove_next_week TEXT NOT NULL DEFAULT '',
    next_priority_1 TEXT NOT NULL DEFAULT '',
    next_priority_2 TEXT NOT NULL DEFAULT '',
    next_priority_3 TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    closed_at TEXT,
    UNIQUE (week_start, week_end),
    CHECK (week_end >= week_start)
);

CREATE INDEX weekly_reviews_period_ix
    ON weekly_reviews (week_start, week_end);
