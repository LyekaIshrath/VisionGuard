-- ====================================================================
-- VisionGuard Mission 06 — Privacy-First SaaS Database Migration
-- Target: PostgreSQL / Supabase
--
-- Security Guarantees:
-- 1. Row Level Security (RLS) enabled on all user-owned tables.
-- 2. Strict isolation: users can ONLY query/modify their own rows (auth.uid()).
-- 3. Privacy boundary: ZERO image, video, biometric, or landmark fields.
-- 4. Mathematical & timing constraints enforced at schema level.
-- ====================================================================

-- 1. Profiles Table (References auth.users)
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    display_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2. Monitoring Sessions Table
CREATE TABLE IF NOT EXISTS public.monitoring_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at TIMESTAMPTZ,
    duration_seconds INTEGER CHECK (duration_seconds IS NULL OR duration_seconds >= 0),
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'COMPLETED', 'INTERRUPTED')),
    posture_calibrated BOOLEAN NOT NULL DEFAULT false,
    alertness_calibrated BOOLEAN NOT NULL DEFAULT false,
    average_posture_score FLOAT CHECK (average_posture_score IS NULL OR (average_posture_score >= 0.0 AND average_posture_score <= 100.0)),
    average_alertness_score FLOAT CHECK (average_alertness_score IS NULL OR (average_alertness_score >= 0.0 AND average_alertness_score <= 100.0)),
    average_risk_score FLOAT CHECK (average_risk_score IS NULL OR (average_risk_score >= 0.0 AND average_risk_score <= 100.0)),
    good_posture_seconds FLOAT NOT NULL DEFAULT 0.0 CHECK (good_posture_seconds >= 0.0),
    posture_risk_seconds FLOAT NOT NULL DEFAULT 0.0 CHECK (posture_risk_seconds >= 0.0),
    alertness_risk_seconds FLOAT NOT NULL DEFAULT 0.0 CHECK (alertness_risk_seconds >= 0.0),
    moderate_risk_events INTEGER NOT NULL DEFAULT 0 CHECK (moderate_risk_events >= 0),
    high_risk_events INTEGER NOT NULL DEFAULT 0 CHECK (high_risk_events >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 3. Risk Events Table (Idempotent lifecycle events; zero raw frames/landmarks)
CREATE TABLE IF NOT EXISTS public.risk_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES public.monitoring_sessions(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    category TEXT NOT NULL CHECK (category IN ('POSTURE', 'ALERTNESS', 'COMBINED', 'SYSTEM')),
    event_status TEXT NOT NULL CHECK (event_status IN ('STARTED', 'RESOLVED')),
    risk_level TEXT NOT NULL CHECK (risk_level IN ('LOW', 'MODERATE', 'HIGH', 'UNKNOWN')),
    risk_score FLOAT CHECK (risk_score IS NULL OR (risk_score >= 0.0 AND risk_score <= 100.0)),
    reason_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
    message TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ,
    duration_seconds FLOAT CHECK (duration_seconds IS NULL OR duration_seconds >= 0.0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 4. User Preferences Table
CREATE TABLE IF NOT EXISTS public.user_preferences (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    browser_notifications_enabled BOOLEAN NOT NULL DEFAULT false,
    data_retention_days INTEGER CHECK (data_retention_days IS NULL OR data_retention_days > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_monitoring_sessions_user_started ON public.monitoring_sessions(user_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_risk_events_user_created ON public.risk_events(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_risk_events_session_created ON public.risk_events(session_id, created_at DESC);

-- Enable Row Level Security (RLS)
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.monitoring_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.risk_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_preferences ENABLE ROW LEVEL SECURITY;

-- Idempotent RLS Policies: Users can only SELECT, INSERT, UPDATE, DELETE their own data
DO $$
BEGIN
    -- Profiles policy
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'profiles' AND policyname = 'profiles_user_isolation') THEN
        CREATE POLICY profiles_user_isolation ON public.profiles
            FOR ALL USING (id = auth.uid()) WITH CHECK (id = auth.uid());
    END IF;

    -- Monitoring Sessions policy
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'monitoring_sessions' AND policyname = 'sessions_user_isolation') THEN
        CREATE POLICY sessions_user_isolation ON public.monitoring_sessions
            FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
    END IF;

    -- Risk Events policy
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'risk_events' AND policyname = 'risk_events_user_isolation') THEN
        CREATE POLICY risk_events_user_isolation ON public.risk_events
            FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
    END IF;

    -- User Preferences policy
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'user_preferences' AND policyname = 'user_prefs_user_isolation') THEN
        CREATE POLICY user_prefs_user_isolation ON public.user_preferences
            FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
    END IF;
END
$$;
