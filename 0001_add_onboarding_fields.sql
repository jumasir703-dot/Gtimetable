-- Testy Timetables: onboarding fields
-- Run this against your existing PostgreSQL database (Render console or psql).
-- Adjust the table name "schools" if your tenant table is named differently.

ALTER TABLE schools
    ADD COLUMN IF NOT EXISTS language VARCHAR(10) NOT NULL DEFAULT 'en',
    ADD COLUMN IF NOT EXISTS onboarding_completed BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS onboarding_step VARCHAR(50) NOT NULL DEFAULT 'welcome',
    ADD COLUMN IF NOT EXISTS onboarding_started_at TIMESTAMP NULL,
    ADD COLUMN IF NOT EXISTS onboarding_completed_at TIMESTAMP NULL;

-- Existing schools that already have real data should not be dropped into
-- the wizard. Mark any school that already has teachers as "done" so current
-- users are not interrupted.
UPDATE schools
SET onboarding_completed = TRUE,
    onboarding_step = 'complete'
WHERE id IN (SELECT DISTINCT school_id FROM teachers);
