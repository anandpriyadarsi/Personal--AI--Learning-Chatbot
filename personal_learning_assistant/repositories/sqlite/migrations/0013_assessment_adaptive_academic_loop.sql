-- Assessment Studio Phase F: Adaptive Academic Loop.
--
-- Recommendations are durable, reviewable evidence-to-action proposals.
-- They do not mutate mastery or schedules. Planner tasks are created only
-- after explicit user Apply.

CREATE UNIQUE INDEX planner_tasks_assessment_recovery_external_uq
    ON planner_tasks(external_id)
    WHERE source_import_id IS NULL
      AND external_id LIKE 'assessment-recovery:%';

CREATE TABLE assessment_recovery_recommendations (
    id TEXT PRIMARY KEY,
    evidence_fingerprint TEXT NOT NULL UNIQUE,
    course_id TEXT NOT NULL
        REFERENCES courses(id) ON DELETE RESTRICT,
    topic_id TEXT
        REFERENCES topics(id) ON DELETE RESTRICT,
    topic_label TEXT NOT NULL,
    source_kind TEXT NOT NULL DEFAULT 'assessment_intelligence'
        CHECK (source_kind = 'assessment_intelligence'),
    evidence_version TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    action_family TEXT NOT NULL
        CHECK (
            action_family IN (
                'evidence_check',
                'concept_rebuild',
                'procedure_rebuild',
                'recall_rebuild',
                'accuracy_rebuild',
                'speed_rebuild',
                'reasoning_rebuild'
            )
        ),
    action_plan_json TEXT NOT NULL,
    alex_prompt TEXT NOT NULL DEFAULT '',
    suggested_title TEXT NOT NULL,
    suggested_description TEXT NOT NULL DEFAULT '',
    suggested_priority TEXT NOT NULL
        CHECK (suggested_priority IN ('P0', 'P1', 'P2')),
    suggested_minutes INTEGER
        CHECK (suggested_minutes IS NULL OR suggested_minutes BETWEEN 0 AND 1440),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'accepted', 'applied', 'rejected', 'superseded')),
    planner_task_id TEXT
        REFERENCES planner_tasks(id) ON DELETE RESTRICT,
    applied_payload_json TEXT NOT NULL DEFAULT '{}',
    rejection_reason TEXT NOT NULL DEFAULT '',
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    accepted_at TEXT,
    applied_at TEXT,
    rejected_at TEXT,
    superseded_at TEXT
);

CREATE UNIQUE INDEX assessment_recovery_one_pending_topic_uq
    ON assessment_recovery_recommendations(course_id, COALESCE(topic_id, ''))
    WHERE status='pending';

CREATE INDEX assessment_recovery_status_created_ix
    ON assessment_recovery_recommendations(status, created_at DESC);

CREATE INDEX assessment_recovery_course_topic_ix
    ON assessment_recovery_recommendations(course_id, topic_id, created_at DESC);

CREATE TABLE assessment_recovery_recommendation_events (
    id TEXT PRIMARY KEY,
    recommendation_id TEXT NOT NULL
        REFERENCES assessment_recovery_recommendations(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL
        CHECK (
            event_type IN (
                'generated',
                'superseded',
                'accepted',
                'applied_to_planner',
                'rejected'
            )
        ),
    details_json TEXT NOT NULL DEFAULT '{}',
    occurred_at TEXT NOT NULL
);

CREATE INDEX assessment_recovery_events_recommendation_ix
    ON assessment_recovery_recommendation_events(recommendation_id, occurred_at);
