-- ====================================================================
-- VisionGuard Mission 08 - Personal Intelligence, Goals & Reports Migration
-- Target: PostgreSQL / Supabase
--
-- Guarantees:
-- 1. Valid exposure denominators are NULLABLE with NO DEFAULT so historical
--    rows remain UNKNOWN (NULL) and distinguishable from known zero (0.0).
-- 2. Timezone column is NULLABLE with NO DEFAULT (NULL = unsaved).
-- 3. personal_goals table with explicit per-operation RLS policies.
-- 4. Zero updates performed on historical sessions.
-- ====================================================================

-- 1. Extend monitoring_sessions with NULLABLE valid observation denominators
ALTER TABLE public.monitoring_sessions
    ADD COLUMN IF NOT EXISTS valid_posture_seconds FLOAT NULL
        CHECK (valid_posture_seconds IS NULL OR valid_posture_seconds >= 0.0),
    ADD COLUMN IF NOT EXISTS valid_alertness_seconds FLOAT NULL
        CHECK (valid_alertness_seconds IS NULL OR valid_alertness_seconds >= 0.0);

-- 2. Extend user_preferences with NULLABLE timezone
ALTER TABLE public.user_preferences
    ADD COLUMN IF NOT EXISTS timezone TEXT NULL;

-- 3. Create personal_goals Table
CREATE TABLE IF NOT EXISTS public.personal_goals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    goal_type TEXT NOT NULL CHECK (goal_type IN (
        'DAILY_MONITORING_MINUTES',
        'GOOD_POSTURE_PERCENTAGE',
        'MAX_POSTURE_RISK_EVENTS_PER_HOUR'
    )),
    target_value FLOAT NOT NULL CHECK (target_value > 0.0),
    period TEXT NOT NULL DEFAULT 'DAILY' CHECK (period IN ('DAILY', 'WEEKLY')),
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT unique_user_goal_type UNIQUE (user_id, goal_type)
);

-- Index for personal goals query performance
CREATE INDEX IF NOT EXISTS idx_personal_goals_user ON public.personal_goals(user_id);

-- Enable RLS
ALTER TABLE public.personal_goals ENABLE ROW LEVEL SECURITY;

-- Explicit RLS Policies for personal_goals
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'personal_goals' AND policyname = 'goals_select_isolation') THEN
        CREATE POLICY goals_select_isolation ON public.personal_goals
            FOR SELECT USING (user_id = auth.uid());
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'personal_goals' AND policyname = 'goals_insert_isolation') THEN
        CREATE POLICY goals_insert_isolation ON public.personal_goals
            FOR INSERT WITH CHECK (user_id = auth.uid());
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'personal_goals' AND policyname = 'goals_update_isolation') THEN
        CREATE POLICY goals_update_isolation ON public.personal_goals
            FOR UPDATE USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'personal_goals' AND policyname = 'goals_delete_isolation') THEN
        CREATE POLICY goals_delete_isolation ON public.personal_goals
            FOR DELETE USING (user_id = auth.uid());
    END IF;
END
$$;

-- Table Grants
GRANT ALL ON TABLE public.personal_goals TO anon, authenticated;
