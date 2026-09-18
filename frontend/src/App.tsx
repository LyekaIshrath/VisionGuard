import { useEffect, useState, useRef } from "react";
import {
  PostureStatus,
  AlertnessStatus,
  RiskLevel,
  CalibrationStatus,
  AlertnessCalibrationStatus,
  HumanStateData,
  SystemStatus,
  MonitoringState,
  RiskStatusResponse,
  RiskEvent,
  Intervention,
} from "./types";

import { Sidebar } from "./components/Sidebar";
import { Header } from "./components/Header";
import { SystemHealth } from "./components/SystemHealth";
import { LiveCameraCard } from "./components/LiveCameraCard";
import { RiskCard } from "./components/RiskCard";
import { PostureCard } from "./components/PostureCard";
import { AlertnessCard } from "./components/AlertnessCard";
import { InterventionBanner } from "./components/InterventionBanner";
import { EventTimeline } from "./components/EventTimeline";
import { CalibrationModal } from "./components/CalibrationModal";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import { AuthModal } from "./components/AuthModal";
import { SessionHistoryView } from "./components/SessionHistoryView";
import { AnalyticsView } from "./components/AnalyticsView";
import { PrivacyView } from "./components/PrivacyView";

const getApiBase = () => {
  if (window.location.port === "5173") {
    return "http://127.0.0.1:8000";
  }
  return "";
};

const getWsUrl = () => {
  const host =
    window.location.port === "5173" ? "127.0.0.1:8000" : window.location.host;
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${host}/api/v1/monitoring/ws`;
};

function DashboardInner() {
  const { token } = useAuth();
  const [authModalOpen, setAuthModalOpen] = useState<boolean>(false);
  // Navigation & Shell state
  const [activeSection, setActiveSection] = useState<string>("overview");
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(false);
  const [activeCalibrationModal, setActiveCalibrationModal] = useState<"posture" | "alertness" | null>(null);

  // Backend & Stream Connection states
  const [backendStatus, setBackendStatus] = useState<"connected" | "disconnected">("disconnected");
  const [wsStatus, setWsStatus] = useState<"connected" | "disconnected">("disconnected");
  const [monitoringState, setMonitoringState] = useState<MonitoringState>("STOPPED");
  const [cameraState, setCameraState] = useState<string>("NOT_CONFIGURED");
  const [framesReceived, setFramesReceived] = useState<number>(0);
  const [isStartingMonitoring, setIsStartingMonitoring] = useState(false);
  const [previewKey, setPreviewKey] = useState<number>(0);

  // Human state from perception stream
  const [humanState, setHumanState] = useState<HumanStateData>({
    timestamp: null,
    track_id: "visionguard-001",
    person_detected: false,
    face_detected: false,
    pose_detected: false,
    posture_status: "NOT_CALIBRATED",
    posture_score: null,
    alertness_status: "NOT_CALIBRATED",
    alertness_score: null,
    eye_state: null,
    eye_closure_duration: null,
    blink_rate: null,
    yawn_score: null,
    head_pitch: null,
    risk_level: null,
    risk_score: null,
    confidence: null,
  });

  // Posture Calibration state
  const [calibration, setCalibration] = useState<CalibrationStatus>({
    state: "IDLE",
    progress: 0,
    valid_samples: 0,
    required_samples: 40,
    quality: null,
    failure_reason: null,
  });

  // Alertness Calibration state
  const [alertnessCalib, setAlertnessCalib] = useState<AlertnessCalibrationStatus>({
    state: "IDLE",
    progress: 0,
    valid_samples: 0,
    required_samples: 40,
    quality: null,
    failure_reason: null,
  });

  // Risk & Intervention State
  const [riskStatus, setRiskStatus] = useState<RiskStatusResponse | null>(null);
  const [eventHistory, setEventHistory] = useState<RiskEvent[]>([]);
  const [activeIntervention, setActiveIntervention] = useState<Intervention | null>(null);

  // Browser Notification state & deduplication ref
  const [browserNotificationPerm, setBrowserNotificationPerm] = useState<NotificationPermission>(
    typeof Notification !== "undefined" ? Notification.permission : "default"
  );
  const lastNotifiedInterventionIdRef = useRef<string | null>(null);

  const [isActionInProgress, setIsActionInProgress] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);

  // --- Health and Status Polling ---
  useEffect(() => {
    checkHealth();
    fetchMonitoringStatus();
    fetchCalibrationStatus();
    fetchAlertnessCalibrationStatus();
    fetchRiskStatus();
    fetchRiskEvents();

    const interval = setInterval(() => {
      checkHealth();
      fetchMonitoringStatus();
      fetchRiskStatus();
      if (calibration.state === "COLLECTING") {
        fetchCalibrationStatus();
      }
      if (alertnessCalib.state === "COLLECTING") {
        fetchAlertnessCalibrationStatus();
      }
    }, 1500);

    return () => clearInterval(interval);
  }, [calibration.state, alertnessCalib.state]);

  // --- WebSocket Connection ---
  useEffect(() => {
    connectWebSocket();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, []);

  function connectWebSocket() {
    try {
      const url = getWsUrl();
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        setWsStatus("connected");
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "human_state" && msg.data) {
            setHumanState(msg.data);
            if (msg.data.active_intervention !== undefined) {
              setActiveIntervention(msg.data.active_intervention);
            }
          } else if (msg.type === "status" && msg.data) {
            if (msg.data.state) {
              setMonitoringState(msg.data.state);
            }
            if (msg.data.camera) {
              setCameraState(msg.data.camera);
            }
            if (typeof msg.data.frames_received === "number") {
              setFramesReceived(msg.data.frames_received);
            }
          }
        } catch {
          // Ignore unparseable message
        }
      };

      ws.onclose = () => {
        setWsStatus("disconnected");
        reconnectTimeoutRef.current = window.setTimeout(connectWebSocket, 3000);
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch {
      setWsStatus("disconnected");
      reconnectTimeoutRef.current = window.setTimeout(connectWebSocket, 3000);
    }
  }

  async function checkHealth() {
    try {
      const res = await fetch(`${getApiBase()}/health`);
      if (res.ok) {
        const data = await res.json();
        if (data.status === "READY") {
          setBackendStatus("connected");
          return;
        }
      }
      setBackendStatus("disconnected");
    } catch {
      setBackendStatus("disconnected");
    }
  }

  async function fetchMonitoringStatus() {
    try {
      const res = await fetch(`${getApiBase()}/api/v1/monitoring/status`);
      if (res.ok) {
        const data: SystemStatus = await res.json();
        setMonitoringState(data.state);
        setCameraState(data.camera);
        if (typeof data.frames_received === "number") {
          setFramesReceived(data.frames_received);
        }
      }
    } catch {
      // Handled gracefully
    }
  }

  async function fetchCalibrationStatus() {
    try {
      const res = await fetch(`${getApiBase()}/api/v1/posture/calibration/status`);
      if (res.ok) {
        const data: CalibrationStatus = await res.json();
        setCalibration(data);
      }
    } catch {
      // Handled gracefully
    }
  }

  async function fetchAlertnessCalibrationStatus() {
    try {
      const res = await fetch(`${getApiBase()}/api/v1/alertness/calibration/status`);
      if (res.ok) {
        const data: AlertnessCalibrationStatus = await res.json();
        setAlertnessCalib(data);
      }
    } catch {
      // Handled gracefully
    }
  }

  async function fetchRiskStatus() {
    try {
      const res = await fetch(`${getApiBase()}/api/v1/risk/status`);
      if (res.ok) {
        const data: RiskStatusResponse = await res.json();
        setRiskStatus(data);
        setActiveIntervention(data.active_intervention);

        // Handle Optional Browser Notification
        if (data.active_intervention && browserNotificationPerm === "granted") {
          const inv = data.active_intervention;
          if (inv.intervention_id !== lastNotifiedInterventionIdRef.current) {
            lastNotifiedInterventionIdRef.current = inv.intervention_id;
            try {
              new Notification(inv.title, {
                body: inv.message,
                icon: "/favicon.ico",
              });
            } catch (e) {
              console.error("Browser notification error", e);
            }
          }
        }
      }
    } catch {
      // Handled gracefully
    }
  }

  async function fetchRiskEvents() {
    try {
      const res = await fetch(`${getApiBase()}/api/v1/risk/events`);
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data.events)) {
          setEventHistory(data.events);
        }
      }
    } catch {
      // Handled gracefully
    }
  }

  async function clearRiskHistory() {
    try {
      await fetch(`${getApiBase()}/api/v1/risk/events/reset`, { method: "POST" });
      await fetchRiskEvents();
    } catch (e) {
      console.error("Clear risk history error", e);
    }
  }

  // Explicit user action for browser notification permission
  async function requestNotificationPermission() {
    if (typeof Notification === "undefined") {
      return;
    }
    try {
      const perm = await Notification.requestPermission();
      setBrowserNotificationPerm(perm);
    } catch (e) {
      console.error("Permission request error", e);
    }
  }

  // --- Monitoring Controls ---
  async function toggleMonitoring() {
    setIsStartingMonitoring(true);
    try {
      if (monitoringState === "STOPPED" || monitoringState === "CAMERA_ERROR") {
        const headers: Record<string, string> = {};
        if (token) {
          headers["Authorization"] = `Bearer ${token}`;
        }
        const res = await fetch(`${getApiBase()}/api/v1/monitoring/start`, {
          method: "POST",
          headers,
        });
        if (res.ok) {
          const data = await res.json();
          if (data.status === "STARTED" || data.status === "ALREADY_RUNNING") {
            setMonitoringState("RUNNING");
            setPreviewKey((k) => k + 1);
          } else if (data.status === "CAMERA_ERROR") {
            setMonitoringState("CAMERA_ERROR");
          }
        }
      } else {
        const res = await fetch(`${getApiBase()}/api/v1/monitoring/stop`, { method: "POST" });
        if (res.ok) {
          setMonitoringState("STOPPED");
        }
      }
      await fetchMonitoringStatus();
      await fetchRiskStatus();
      await fetchRiskEvents();
    } catch (e) {
      console.error("Monitoring toggle error", e);
    } finally {
      setIsStartingMonitoring(false);
    }
  }

  // --- Calibration Handlers ---
  async function startPostureCalibration() {
    setIsActionInProgress(true);
    try {
      const res = await fetch(`${getApiBase()}/api/v1/posture/calibration/start`, { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        setCalibration((prev) => ({
          ...prev,
          state: data.state || "COLLECTING",
          progress: 0,
          valid_samples: 0,
          failure_reason: null,
        }));
      } else {
        const err = await res.json();
        setCalibration((prev) => ({
          ...prev,
          state: "FAILED",
          failure_reason: err.detail || "Failed to start posture calibration",
        }));
      }
    } catch {
      setCalibration((prev) => ({
        ...prev,
        state: "FAILED",
        failure_reason: "Network error connecting to calibration service",
      }));
    } finally {
      setIsActionInProgress(false);
      fetchCalibrationStatus();
    }
  }

  async function resetPostureCalibration() {
    setIsActionInProgress(true);
    try {
      await fetch(`${getApiBase()}/api/v1/posture/calibration/reset`, { method: "POST" });
      await fetchCalibrationStatus();
    } catch (e) {
      console.error("Reset posture calibration error", e);
    } finally {
      setIsActionInProgress(false);
    }
  }

  async function startAlertnessCalibration() {
    setIsActionInProgress(true);
    try {
      const res = await fetch(`${getApiBase()}/api/v1/alertness/calibration/start`, { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        setAlertnessCalib((prev) => ({
          ...prev,
          state: data.state || "COLLECTING",
          progress: 0,
          valid_samples: 0,
          failure_reason: null,
        }));
      } else {
        const err = await res.json();
        setAlertnessCalib((prev) => ({
          ...prev,
          state: "FAILED",
          failure_reason: err.detail || "Failed to start alertness calibration",
        }));
      }
    } catch {
      setAlertnessCalib((prev) => ({
        ...prev,
        state: "FAILED",
        failure_reason: "Network error connecting to alertness calibration service",
      }));
    } finally {
      setIsActionInProgress(false);
      fetchAlertnessCalibrationStatus();
    }
  }

  async function resetAlertnessCalibration() {
    setIsActionInProgress(true);
    try {
      await fetch(`${getApiBase()}/api/v1/alertness/calibration/reset`, { method: "POST" });
      await fetchAlertnessCalibrationStatus();
    } catch (e) {
      console.error("Reset alertness calibration error", e);
    } finally {
      setIsActionInProgress(false);
    }
  }

  const canCalibratePosture =
    monitoringState === "RUNNING" &&
    humanState.person_detected &&
    humanState.pose_detected &&
    calibration.state !== "COLLECTING";

  const canCalibrateAlertness =
    monitoringState === "RUNNING" &&
    humanState.person_detected &&
    humanState.face_detected &&
    alertnessCalib.state !== "COLLECTING";

  const postureStatus: PostureStatus = humanState.posture_status || "NOT_CALIBRATED";
  const alertnessStatus: AlertnessStatus = humanState.alertness_status || "NOT_CALIBRATED";
  const overallRiskLevel: RiskLevel =
    riskStatus?.risk_level || (humanState.risk_level as RiskLevel) || "UNKNOWN";

  const handleNavigate = (sectionId: string) => {
    setActiveSection(sectionId);
    if (sectionId === "overview") {
      window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }
    const el = document.getElementById(sectionId);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  return (
    <div className="app-shell">
      <Sidebar
        activeSection={activeSection}
        onNavigate={handleNavigate}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />

      <div className="app-main-layout">
        <Header
          monitoringState={monitoringState}
          cameraState={cameraState}
          isStarting={isStartingMonitoring}
          onToggleMonitoring={toggleMonitoring}
          notificationPermission={browserNotificationPerm}
          onRequestNotifications={requestNotificationPermission}
          onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
          apiBase={getApiBase()}
          onOpenAuth={() => setAuthModalOpen(true)}
        />

        <SystemHealth
          monitoringState={monitoringState}
          cameraState={cameraState}
          backendConnected={backendStatus === "connected"}
          wsConnected={wsStatus === "connected"}
          framesReceived={framesReceived}
          humanState={humanState}
        />

        <main className="dashboard-content">
          {activeSection === "sessions-history" ? (
            <SessionHistoryView
              apiBase={getApiBase()}
              onOpenAuth={() => setAuthModalOpen(true)}
            />
          ) : activeSection === "analytics-section" ? (
            <AnalyticsView
              apiBase={getApiBase()}
              onOpenAuth={() => setAuthModalOpen(true)}
            />
          ) : activeSection === "privacy-section" ? (
            <PrivacyView
              apiBase={getApiBase()}
              onOpenAuth={() => setAuthModalOpen(true)}
            />
          ) : (
            <>
              {/* Top Primary Grid: Live Camera (60-65%) + Risk Intelligence (35-40%) */}
              <div className="primary-grid">
                <LiveCameraCard
                  monitoringState={monitoringState}
                  cameraState={cameraState}
                  previewKey={previewKey}
                  apiBase={getApiBase()}
                  humanState={humanState}
                />

                <RiskCard
                  riskStatus={riskStatus}
                  overallRiskLevel={overallRiskLevel}
                />
              </div>

              {/* Middle Grid: Posture & Alertness Side-by-Side */}
              <div className="telemetry-grid">
                <PostureCard
                  postureStatus={postureStatus}
                  postureScore={humanState.posture_score}
                  calibration={calibration}
                  canCalibrate={canCalibratePosture}
                  onOpenCalibration={() => setActiveCalibrationModal("posture")}
                />

                <AlertnessCard
                  alertnessStatus={alertnessStatus}
                  alertnessScore={humanState.alertness_score}
                  humanState={humanState}
                  calibration={alertnessCalib}
                  canCalibrate={canCalibrateAlertness}
                  onOpenCalibration={() => setActiveCalibrationModal("alertness")}
                />
              </div>

              {/* Active Intervention Strip */}
              <InterventionBanner intervention={activeIntervention} />

              {/* Recent Events Timeline */}
              <EventTimeline
                events={eventHistory}
                onClearHistory={clearRiskHistory}
              />
            </>
          )}
        </main>

        <footer className="app-footer">
          <div className="footer-left">
            <span>VisionGuard Pro • Real-Time Human Safety &amp; Wellness Intelligence</span>
          </div>
          <div className="footer-right">
            <span className="footer-status-pill">
              Backend: {backendStatus.toUpperCase()} &bull; WS: {wsStatus.toUpperCase()}
            </span>
          </div>
        </footer>
      </div>

      {/* Guided Calibration Modal */}
      {activeCalibrationModal && (
        <CalibrationModal
          type={activeCalibrationModal}
          isOpen={true}
          onClose={() => setActiveCalibrationModal(null)}
          status={activeCalibrationModal === "posture" ? calibration : alertnessCalib}
          isActionInProgress={isActionInProgress}
          onStart={activeCalibrationModal === "posture" ? startPostureCalibration : startAlertnessCalibration}
          onReset={activeCalibrationModal === "posture" ? resetPostureCalibration : resetAlertnessCalibration}
        />
      )}

      {/* SaaS Auth Modal */}
      <AuthModal
        isOpen={authModalOpen}
        onClose={() => setAuthModalOpen(false)}
      />
    </div>
  );
}

export function App() {
  return (
    <AuthProvider>
      <DashboardInner />
    </AuthProvider>
  );
}

export default App;
