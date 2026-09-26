-- Assessment Studio Phase A: reusable course-scoped assessment templates.
-- Templates are configuration, not real assessments or attempts.
-- Phase B+ will import authored assessment packages into canonical assessments.

CREATE TABLE assessment_templates (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE RESTRICT,
    name TEXT NOT NULL COLLATE NOCASE,
    assessment_type TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'exam' CHECK (mode IN ('exam', 'practice')),
    description TEXT NOT NULL DEFAULT '',
    instructions TEXT NOT NULL DEFAULT '',
    duration_minutes INTEGER NOT NULL CHECK (duration_minutes > 0),
    total_marks_milli INTEGER CHECK (total_marks_milli IS NULL OR total_marks_milli >= 0),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
    provenance TEXT NOT NULL DEFAULT 'user',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deactivated_at TEXT,
    UNIQUE (course_id, name)
);

CREATE TABLE assessment_template_topics (
    template_id TEXT NOT NULL REFERENCES assessment_templates(id) ON DELETE CASCADE,
    topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE RESTRICT,
    position INTEGER NOT NULL DEFAULT 0 CHECK (position >= 0),
    PRIMARY KEY (template_id, topic_id)
);

CREATE TABLE assessment_template_patterns (
    id TEXT PRIMARY KEY,
    template_id TEXT NOT NULL REFERENCES assessment_templates(id) ON DELETE CASCADE,
    position INTEGER NOT NULL CHECK (position > 0),
    question_type TEXT NOT NULL,
    question_count INTEGER NOT NULL CHECK (question_count > 0),
    marks_each_milli INTEGER NOT NULL CHECK (marks_each_milli >= 0),
    negative_marks_milli INTEGER NOT NULL DEFAULT 0
        CHECK (negative_marks_milli >= 0 AND negative_marks_milli <= marks_each_milli),
    scoring_policy TEXT NOT NULL DEFAULT 'standard',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (template_id, position)
);

CREATE INDEX assessment_templates_course_active_ix
    ON assessment_templates(course_id, is_active, name);
CREATE INDEX assessment_template_topics_topic_ix
    ON assessment_template_topics(topic_id, template_id);
CREATE INDEX assessment_template_patterns_template_ix
    ON assessment_template_patterns(template_id, position);
