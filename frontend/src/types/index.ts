export type WorkActivityState =
  | "ENGAGED"
  | "OBSERVING"
  | "ATTENTION_AWAY"
  | "AWAY"
  | "UNKNOWN"
  | "ACTIVE"
  | "LOW_ACTIVITY";

export type PostureStatus =
  | "NOT_CALIBRATED"
  | "GOOD"
  | "SLOUCHING"
  | "FORWARD_LEAN"
  | "LEFT_LEAN"
  | "RIGHT_LEAN"
  | "UNKNOWN";

export type AlertnessStatus =
  | "NOT_CALIBRATED"
  | "ALERT"
  | "POSSIBLE_DROWSINESS"
  | "UNKNOWN";

export type RiskLevel = "UNKNOWN" | "LOW" | "MODERATE" | "HIGH";

export type RiskCategory = "POSTURE" | "ALERTNESS" | "COMBINED" | "SYSTEM";

export type EventStatus = "STARTED" | "ONGOING" | "RESOLVED";

export type CalibrationState = "IDLE" | "COLLECTING" | "COMPLETED" | "FAILED";

export interface CalibrationStatus {
  state: CalibrationState;
  progress: number;
  valid_samples: number;
  required_samples: number;
  quality: "EXCELLENT" | "GOOD" | "ACCEPTABLE" | null;
  failure_reason: string | null;
}

export interface AlertnessCalibrationStatus {
  state: CalibrationState;
  progress: number;
  valid_samples: number;
  required_samples: number;
  quality: "EXCELLENT" | "GOOD" | "ACCEPTABLE" | null;
  failure_reason: string | null;
}

export interface DomainRiskState {
  category: RiskCategory;
  level: RiskLevel;
  score: number | null;
  is_valid: boolean;
  active_duration_sec: number;
  reasons: string[];
}

export interface Intervention {
  intervention_id: string;
  timestamp: string;
  category: RiskCategory;
  level: RiskLevel;
  title: string;
  message: string;
  type: "IN_APP" | "BROWSER_NOTIFICATION";
}

export interface RiskEvent {
  event_id: string;
  timestamp: string;
  category: RiskCategory;
  status: EventStatus;
  risk_level: RiskLevel;
  risk_score: number | null;
  message: string;
  reason_codes: string[];
  duration_sec: number;
}

export interface RiskStatusResponse {
  risk_level: RiskLevel;
  risk_score: number | null;
  posture_risk: DomainRiskState;
  alertness_risk: DomainRiskState;
  dominant_category: RiskCategory | null;
  active_reasons: string[];
  active_intervention: Intervention | null;
  confidence: number;
}

export interface HumanStateData {
  timestamp: string | null;
  track_id: string;
  person_detected: boolean;
  face_detected: boolean;
  pose_detected: boolean;
  posture_status: PostureStatus | null;
  posture_score: number | null;
  alertness_status: AlertnessStatus | null;
  alertness_score: number | null;
  eye_state: "OPEN" | "CLOSED" | "UNKNOWN" | null;
  eye_closure_duration: number | null;
  blink_rate: number | null;
  yawn_score: number | null;
  head_pitch: number | null;
  risk_level: RiskLevel | null;
  risk_score: number | null;
  posture_risk?: RiskLevel | null;
  alertness_risk?: RiskLevel | null;
  active_reasons?: string[];
  active_intervention?: Intervention | null;
  confidence: number | null;
  session_id?: string | null;
  monitoring_state?: string | null;
  activity_state?: WorkActivityState | null;
  activity_score?: number | null;
  activity_confidence?: number | null;
  activity_reason_codes?: string[];
  person_present?: boolean;
  blink_count?: number | null;
  longest_eye_closure?: number | null;
  valid_eye_tracking_seconds?: number | null;
  head_yaw?: number | null;
  head_roll?: number | null;
  neck_inclination?: number | null;
  keyboard_activity_count?: number | null;
  mouse_activity_count?: number | null;
  idle_seconds?: number | null;
  baseline_source?: string | null;
  capture_fps?: number | null;
  preview_fps?: number | null;
  inference_hz?: number | null;
  screen_activity_level?: "CHANGING" | "LOW_CHANGE" | "STATIC" | "UNKNOWN" | null;
  screen_change_score?: number | null;
  camera_state?: string | null;
  last_frame_age_ms?: number | null;
  eyes_closed?: boolean | null;
  mouse_click_count?: number | null;
  scroll_count?: number | null;
}

export type MonitoringState =
  | "STARTING"
  | "RUNNING"
  | "CAMERA_ERROR"
  | "NO_FRAMES"
  | "ERROR"
  | "STOPPED";

export interface SystemStatus {
  camera: string;
  state: MonitoringState;
  camera_index: number;
  backend?: string;
  frames_received?: number;
  capture_fps?: number;
  preview_fps?: number;
  inference_hz?: number;
}

export type CloudSyncStatus = "DISABLED" | "SYNCING" | "SYNCED" | "OFFLINE" | "ERROR";

export interface CloudStatusInfo {
  status: CloudSyncStatus;
  configured: boolean;
  cloud_session_id: string | null;
  local_session_id: string | null;
  message: string;
}

export interface SessionRecord {
  id: string;
  user_id: string;
  started_at: string;
  ended_at: string | null;
  duration_seconds: number;
  good_posture_seconds: number;
  posture_risk_seconds: number;
  alertness_risk_seconds: number;
  average_posture_score: number | null;
  average_alertness_score: number | null;
  risk_event_count: number;
  intervention_count: number;
  status: "ACTIVE" | "COMPLETED" | "INTERRUPTED";
  device_name?: string;
}

export interface RiskEventRecord {
  id: string;
  session_id?: string | null;
  user_id: string;
  timestamp: string;
  category: string;
  severity: string;
  reason: string;
  lifecycle: string;
  duration_seconds?: number | null;
  metadata?: Record<string, any>;
}

export interface AnalyticsSummary {
  total_sessions: number;
  total_monitored_seconds: number;
  total_good_posture_seconds: number;
  good_posture_percentage: number;
  average_posture_score: number | null;
  average_alertness_score: number | null;
  total_risk_events: number;
  total_interventions: number;
  moderate_risk_count: number;
  high_risk_count: number;
}


export type AlertChannel = "IN_APP" | "BROWSER_NOTIFICATION" | "VOICE";
export type AlertPriority = "LOW" | "NORMAL" | "HIGH";

export interface AlertAction {
  channel: AlertChannel;
  priority: AlertPriority;
  title: string;
  message: string;
  intervention_id: string;
  category: RiskCategory;
  level: RiskLevel;
}

export interface UserPreferences {
  user_id?: string;
  browser_notifications_enabled: boolean;
  voice_alerts_enabled: boolean;
  voice_volume: number;
  voice_rate: number;
  voice_pitch: number;
  quiet_mode_enabled: boolean;
  selected_voice: string | null;
  data_retention_days?: number;
  timezone?: string | null;
  alert_language?: "en" | "ta" | "en+ta";
  mobile_push_enabled?: boolean;
  notify_posture?: boolean;
  notify_alertness?: boolean;
  notify_extended_away?: boolean;
  notify_session_complete?: boolean;
}

// ==========================================
// MISSION 08 — PERSONAL INTELLIGENCE & REPORTS
// ==========================================

export type CoverageLevel = "COMPLETE" | "PARTIAL" | "UNAVAILABLE";

export interface ModalityCoverage {
  data_quality: CoverageLevel;
  sessions_with_known_exposure: number;
}

export interface CohortCoverage {
  sessions_total: number;
  posture: ModalityCoverage;
  alertness: ModalityCoverage;
}

export interface AnalyticsOverview {
  total_monitored_seconds: number;
  total_sessions: number;
  good_posture_seconds: number | null;
  good_posture_percentage: number | null;
  posture_risk_seconds: number | null;
  alertness_risk_seconds: number | null;
  posture_events_per_valid_observation_hour: number | null;
  alertness_events_per_valid_observation_hour: number | null;
  average_posture_score: number | null;
  average_alertness_score: number | null;
  total_risk_events: number;
  total_interventions: number;
  coverage: CohortCoverage;
}

export interface DailyTrendItem {
  date: string; // YYYY-MM-DD
  total_monitored_seconds: number;
  good_posture_seconds: number;
  valid_posture_seconds: number | null;
  good_posture_percentage: number | null;
  posture_events_per_valid_observation_hour: number | null;
  alertness_events_per_valid_observation_hour: number | null;
  average_posture_score: number | null;
  average_alertness_score: number | null;
  risk_event_count: number;
  intervention_count: number;
  coverage: CohortCoverage;
}

export interface TimeOfDayBucket {
  bucket: "MORNING" | "AFTERNOON" | "EVENING" | "NIGHT";
  label: string;
  monitored_exposure_seconds: number;
  risk_event_count: number;
  events_per_monitored_hour: number | null;
}

export type InsightType =
  | "POSITIVE_PATTERN"
  | "ATTENTION_PATTERN"
  | "INFORMATIONAL"
  | "INSUFFICIENT_DATA";

export interface Insight {
  id: string;
  type: InsightType;
  title: string;
  description: string;
  metric_reference?: string | null;
  recommended_action?: string | null;
}

export type GoalType =
  | "DAILY_MONITORING_MINUTES"
  | "GOOD_POSTURE_PERCENTAGE"
  | "MAX_POSTURE_RISK_EVENTS_PER_HOUR";

export interface PersonalGoal {
  id?: string;
  user_id?: string;
  goal_type: GoalType;
  target_value: number;
  created_at?: string;
  updated_at?: string;
  current_value?: number | null;
  progress_percentage?: number | null;
  achieved?: boolean | null;
}

export interface WeeklyReport {
  week_start: string;
  week_end: string;
  timezone: string;
  overview: AnalyticsOverview;
  daily_trends: DailyTrendItem[];
  time_of_day_patterns: TimeOfDayBucket[];
  insights: Insight[];
}

export interface SessionReport {
  session: SessionRecord;
  coverage: CohortCoverage;
  overview: AnalyticsOverview;
  event_breakdown: Record<string, number>;
  severity_breakdown: Record<string, number>;
  events: RiskEventRecord[];
}


export interface User {
  id: string;
  _id?: string;
  email?: string;
  display_name?: string;
  status?: string;
}
