export interface ActivityInterval {
  interval_id?: string;
  session_id?: string;
  user_id?: string;
  state: "ENGAGED" | "OBSERVING" | "ATTENTION_AWAY" | "AWAY" | "UNKNOWN" | string;
  start_time: string;
  end_time: string;
  duration_seconds: number;
  signals_summary?: Record<string, any>;
}

export interface TimelineEvent {
  event_id?: string;
  session_id?: string;
  timestamp: string;
  type?: string;
  event_type?: string;
  category?: string;
  severity?: string;
  message?: string;
  reason?: string;
  lifecycle?: string;
  duration_seconds?: number;
  metadata?: Record<string, any>;
  data?: Record<string, any>;
}

export interface SessionDocument {
  id?: string;
  session_id: string;
  user_id?: string;
  status?: string;
  started_at?: string;
  ended_at?: string;
  duration_seconds: number;
  device_name?: string;
  activity_summary?: {
    engaged_seconds?: number;
    observing_seconds?: number;
    attention_away_seconds?: number;
    away_seconds?: number;
    unknown_seconds?: number;
    engaged_pct?: number;
    observing_pct?: number;
    attention_away_pct?: number;
    away_pct?: number;
    unknown_pct?: number;
  };
  presence_summary?: {
    present_seconds?: number;
    away_seconds?: number;
    unknown_seconds?: number;
    present_pct?: number;
    away_pct?: number;
    unknown_pct?: number;
    away_episodes?: number;
    longest_away_seconds?: number;
  };
  head_summary?: {
    facing_workstation_seconds?: number;
    facing_workstation_pct?: number;
    attention_away_seconds?: number;
    attention_away_episodes?: number;
    attention_away_duration_seconds?: number;
  };
  computer_summary?: {
    keyboard_events?: number;
    mouse_movements?: number;
    mouse_clicks?: number;
    scroll_count?: number;
    longest_idle_seconds?: number;
    keystrokes?: number;
    mouse_moves?: number;
    clicks?: number;
    scrolls?: number;
  };
  screen_summary?: {
    screen_active_seconds?: number;
    changing_seconds?: number;
    changing_pct?: number;
    low_change_seconds?: number;
    low_change_pct?: number;
    static_seconds?: number;
    static_pct?: number;
    unknown_seconds?: number;
    unknown_pct?: number;
  };
  posture_summary?: {
    good_posture_seconds?: number;
    slouching_seconds?: number;
    forward_lean_seconds?: number;
    left_lean_seconds?: number;
    right_lean_seconds?: number;
    unknown_posture_seconds?: number;
    valid_posture_seconds?: number;
    posture_risk_seconds?: number;
    good_pct?: number;
    slouching_pct?: number;
    forward_lean_pct?: number;
    left_lean_pct?: number;
    right_lean_pct?: number;
    unknown_pct?: number;
  };
  eye_summary?: {
    blink_count?: number;
    total_blinks?: number;
    blink_rate?: number | null;
    blink_rate_per_min?: number | null;
    valid_eye_tracking_seconds?: number;
    valid_eye_observation_pct?: number;
    longest_closure_seconds?: number;
    longest_eye_closure_seconds?: number;
  };
  good_posture_seconds?: number;
  valid_posture_seconds?: number;
  posture_risk_seconds?: number;
  alertness_risk_seconds?: number;
  average_posture_score?: number | null;
  average_alertness_score?: number | null;
  intervention_count?: number;
  risk_event_count?: number;
  timeline?: TimelineEvent[];
  timeline_events?: TimelineEvent[];
  events?: TimelineEvent[];
  activity_intervals?: ActivityInterval[];
}
