-- ====================================================================
-- VisionGuard V1 Physical Acceptance Hotfix — Alert Language Preference
-- Target: PostgreSQL / Supabase
--
-- Extends public.user_preferences with alert_language setting.
-- Allowed values: 'en', 'ta', 'en+ta'. Default: 'en'.
-- Preserves RLS, foreign keys, and existing user isolation.
-- ====================================================================

ALTER TABLE public.user_preferences
    ADD COLUMN IF NOT EXISTS alert_language TEXT NOT NULL DEFAULT 'en'
    CHECK (alert_language IN ('en', 'ta', 'en+ta'));
