-- ====================================================================
-- VisionGuard Mission 07 — Smart Notifications & Voice Alert Preferences
-- Target: PostgreSQL / Supabase
--
-- Extends public.user_preferences with voice and notification settings.
-- Preserves RLS, foreign keys, and existing table isolation.
-- ====================================================================

ALTER TABLE public.user_preferences
    ADD COLUMN IF NOT EXISTS voice_alerts_enabled BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS voice_volume FLOAT NOT NULL DEFAULT 0.8 CHECK (voice_volume >= 0.0 AND voice_volume <= 1.0),
    ADD COLUMN IF NOT EXISTS voice_rate FLOAT NOT NULL DEFAULT 1.0 CHECK (voice_rate >= 0.5 AND voice_rate <= 2.0),
    ADD COLUMN IF NOT EXISTS voice_pitch FLOAT NOT NULL DEFAULT 1.0 CHECK (voice_pitch >= 0.5 AND voice_pitch <= 2.0),
    ADD COLUMN IF NOT EXISTS quiet_mode_enabled BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS selected_voice TEXT;
