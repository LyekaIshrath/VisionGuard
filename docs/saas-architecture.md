# VisionGuard SaaS Architecture & Privacy Model

## 1. Architectural Philosophy: Local-First Privacy Edge

VisionGuard is designed from the ground up as a **privacy-first edge vision platform**. The core intelligence pipeline executes 100% locally on the user's workstation or device.

```
+-------------------------------------------------------------------------+
|                        LOCAL DEVICE (PHYSICAL MACHINE)                  |
|                                                                         |
|  [Webcam] -> [WebcamSource] -> [PerceptionEngine]                       |
|                                        |                                |
|                        MediaPipe Pose & Face Mesh                       |
|                                        |                                |
|                        +---------------+---------------+                |
|                        |                               |                |
|                 [HumanState]                 [OverlayRenderer]          |
|                        |                               |                |
|          +-------------+-------------+      [Annotated MJPEG Preview]   |
|          |                           |                 |                |
|   [PostureEngine]             [AlertnessEngine]   [Dashboard Video]     |
|          |                           |                                  |
|          +-------------+-------------+                                  |
|                        |                                                |
|                   [RiskEngine]                                          |
|                        |                                                |
|              [InterventionEngine]                                       |
|                        |                                                |
|           [Local In-App Audio/Visual Alert]                             |
|                        |                                                |
|             (Real-time path ends here)                                  |
+------------------------+------------------------------------------------+
                         |
               (Downstream Side Effect)
                         |
                         v
              [SessionAggregator]
                         |
           (Time-weighted derived metrics)
                         |
                         v
             [CloudPersistenceService]
                         |
             (PostgREST / HTTPS async)
                         |
                         v
+-------------------------------------------------------------------------+
|                        SUPABASE / POSTGRESQL CLOUD                      |
|                                                                         |
|  - profiles                                                             |
|  - monitoring_sessions (aggregated duration & score averages)           |
|  - risk_events (lifecycle STARTED/RESOLVED telemetry events)            |
|  - user_preferences                                                     |
|                                                                         |
|  [Row Level Security: auth.uid() == user_id]                            |
+-------------------------------------------------------------------------+
```

---

## 2. Strict Privacy Boundary

### Never Persisted or Transmitted to Cloud:
- Raw video frames
- Annotated camera frames
- JPEG/video buffers
- Full facial landmark coordinates
- Full body pose landmark coordinates
- Biometric templates
- Face embeddings / identity tokens
- User webcam recordings

### What IS Persisted:
- User profile (`id`, `display_name`, timestamps)
- Monitoring session summary:
  - Session start/end UTC timestamps
  - Total duration (calculated via monotonic time)
  - Calibration flags (`posture_calibrated`, `alertness_calibrated`)
  - Time-weighted average posture, alertness, and risk scores (0-100)
  - Time elapsed in good posture, posture risk, and alertness risk
  - Counts of moderate and high risk events
- Risk events:
  - Event ID, Session ID, User ID
  - Category (`POSTURE`, `ALERTNESS`, `COMBINED`, `SYSTEM`)
  - Risk level (`LOW`, `MODERATE`, `HIGH`, `UNKNOWN`) and score
  - Event status (`STARTED`, `RESOLVED`)
  - Reason codes (e.g. `["SLOUCHING"]`)
  - Human-readable message
  - Start/Resolved timestamps and duration in seconds

---

## 3. Cryptographic Authentication & Token Verification

1. **Client Auth**: Handled by official `@supabase/supabase-js` using standard Supabase Auth (email + password).
2. **Backend Authentication**: Every protected endpoint requires `Authorization: Bearer <access_token>`.
3. **Cryptographic Validation**: The backend cryptographically validates the token's signature, issuer (`iss`), expiration (`exp`), audience (`aud`), and subject (`sub`), deriving the verified `user_id`. Client-supplied user IDs in request bodies are rejected or strictly ignored.
4. **Row-Level Security (RLS)**: Normal CRUD queries against PostgreSQL/PostgREST pass the authenticated user's JWT, making database-level RLS (`user_id = auth.uid()`) the definitive security boundary.

---

## 4. Offline Resilience & Fault Tolerance

Local monitoring never depends on cloud availability:
- If Supabase is unconfigured, network drops, or database writes fail:
  - Camera capture continues uninterrupted.
  - MediaPipe inference continues uninterrupted.
  - Posture, alertness, and risk calculations continue uninterrupted.
  - Local in-app interventions fire without latency.
- The system truthfully reports its synchronization state:
  - `DISABLED`: Cloud credentials unconfigured.
  - `SYNCING`: Persistence operation in progress.
  - `SYNCED`: Last synchronization succeeded.
  - `OFFLINE`: Network or host unreachable.
  - `ERROR`: Operational or database error.

---

## 5. Idempotent Risk Event Lifecycle

Risk events maintain stable IDs:
- **STARTED**: When an intervention condition is met, an event is created with `event_status: STARTED`.
- **RESOLVED**: When the risk condition normalizes, the existing event is updated with `event_status: RESOLVED`, `resolved_at`, and `duration_seconds`.
- Database upsert logic uses `ON CONFLICT (id) DO UPDATE` to prevent duplicate events on network retries.

---

## 6. Data Deletion Controls ("Delete My VisionGuard Data")

Users maintain full control over their telemetry:
- **Delete Session**: Cascading deletion of a specific monitoring session and all associated risk events owned by `auth.uid()`.
- **Delete My VisionGuard Data**: Purges all monitoring sessions, risk events, and preferences belonging to the user, while preserving the user's authentication account.
