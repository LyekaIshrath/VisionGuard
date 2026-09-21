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
import { onAuthExpired } from "./services/apiClient";
import { SessionHistoryView } from "./components/SessionHistoryView";
import { AnalyticsView } from "./components/AnalyticsView";
import { ReportsView } from "./components/ReportsView";
import { PrivacyView } from "./components/PrivacyView";
import { SettingsView } from "./components/SettingsView";
import { AlertProvider, useAlerts } from "./contexts/AlertContext";
import { StatusCenterModal } from "./components/StatusCenterModal";
import { WorkMonitorView } from "./components/WorkMonitorView";
import { ReportModal } from "./components/ReportModal";

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
  const { user } = useAuth();
  const { token } = useAuth();
  const { handleIntervention, handleResolution, resetSession } = useAlerts();
  const [authModalOpen, setAuthModalOpen] = useState<boolean>(false);
  const [authExpiredNotice, setAuthExpiredNotice] = useState<boolean>(false);

  useEffect(() => {
    return onAuthExpired(() => {
      setAuthExpiredNotice(true);
    });
  }, []);
  const [statusCenterOpen, setStatusCenterOpen] = useState<boolean>(false);
  // Navigation & Shell state
  const [activeSection, setActiveSection] = useState<string>("overview");
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(false);
  const [activeCalibrationModal, setActiveCalibrationModal] = useState<"posture" | "alertness" | null>(null);
  const [reportModalOpen, setReportModalOpen] = useState<boolean>(false);
  const [latestReport, setLatestReport] = useState<any>(null);
  const [sessionElapsedSec, setSessionElapsedSec] = useState<number>(0);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const reportId = params.get("report") || params.get("session_id");
    if (reportId) {
      setLatestReport({ session_id: reportId, id: reportId });
      setReportModalOpen(true);
    }
  }, []);

  // Backend & Stream Connection states
  const [backendStatus, setBackendStatus] = useState<"connected" | "disconnected">("disconnected");
  const [wsStatus, setWsStatus] = useState<"connected" | "disconnected">("disconnected");
  const [monitoringState, setMonitoringState] = useState<MonitoringState>("STOPPED");
  const monitoringStateRef = useRef<MonitoringState>("STOPPED");
  useEffect(() => {
    monitoringStateRef.current = monitoringState;
  }, [monitoringState]);

  useEffect(() => {
    let interval: any = null;
    if (monitoringState === "RUNNING") {
      interval = setInterval(() => {
        setSessionElapsedSec((prev) => prev + 1);
      }, 1000);
    } else {
      setSessionElapsedSec(0);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [monitoringState]);
  const [cameraState, setCameraState] = useState<string>("NOT_CONFIGURED");
  const [framesReceived, setFramesReceived] = useState<number>(0);
  const [isStartingMonitoring, setIsStartingMonitoring] = useState(false);
  const [previewKey, setPreviewKey] = useState<number>(0);

  // Human state from perception stream
  const STOPPED_HUMAN_STATE: HumanStateData = {
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
};

  const [humanState, setHumanState] = useState<HumanStateData>(STOPPED_HUMAN_STATE);

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
        fetchRiskEvents();
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "human_state" && msg.data) {
            if (monitoringStateRef.current === "STOPPED") {
              return;
            }
            if (monitoringStateRef.current !== "RUNNING") {
              setMonitoringState("RUNNING");
              monitoringStateRef.current = "RUNNING";
            }
            setHumanState(msg.data);
            if (Array.isArray(msg.data.recent_events)) {
              setEventHistory(prev => {
                const existingIds = new Set(prev.map(e => e.event_id || `${e.timestamp}_${e.category}_${e.status}`));
                const incoming = (msg.data.recent_events as RiskEvent[]).filter(e => {
                  const key = e.event_id || `${e.timestamp}_${e.category}_${e.status}`;
                  return !existingIds.has(key);
                });
                if (incoming.length === 0) return prev;
                const merged = [...incoming, ...prev];
                merged.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
                return merged.slice(0, 50);
              });
            }
            if (msg.data.active_intervention !== undefined) {
              setActiveIntervention(msg.data.active_intervention);
              if (msg.data.active_intervention) {
                handleIntervention(msg.data.active_intervention);
              }
            }
            if (msg.data.posture_status === "GOOD") {
              handleResolution("POSTURE");
            }
            if (msg.data.alertness_status === "ALERT") {
              handleResolution("ALERTNESS");
            }
          } else if (msg.type === "status" && msg.data) {
            if (msg.data.state) {
              const raw = msg.data.state as string;
              const mapped: MonitoringState = (raw === "MONITORING" || raw === "RUNNING") ? "RUNNING" : (raw as MonitoringState);
              setMonitoringState(mapped);
              monitoringStateRef.current = mapped;
              if (mapped === "STOPPED") {
                setCameraState("STANDBY");
                setHumanState(STOPPED_HUMAN_STATE);
              }
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
        const raw = data.state as string;
        const mapped: MonitoringState = (raw === "MONITORING" || raw === "RUNNING") ? "RUNNING" : (data.state as MonitoringState) || "STOPPED";
        setMonitoringState(mapped);
        monitoringStateRef.current = mapped;
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

        if (data.active_intervention) {
          handleIntervention(data.active_intervention);
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
          if (data.status === "STARTED" || data.status === "ALREADY_RUNNING" || data.status === "MONITORING") {
            setMonitoringState("RUNNING");
            monitoringStateRef.current = "RUNNING";
            setPreviewKey((k) => k + 1);
          } else if (data.status === "CAMERA_ERROR") {
            setMonitoringState("CAMERA_ERROR");
            monitoringStateRef.current = "CAMERA_ERROR";
          }
        }
      } else {
        const res = await fetch(`${getApiBase()}/api/v1/monitoring/stop`, { method: "POST" });
        if (res.ok) {
          const data = await res.json();
          setMonitoringState("STOPPED");
          monitoringStateRef.current = "STOPPED";
          setCameraState("STANDBY");
          setHumanState(STOPPED_HUMAN_STATE);
          setActiveIntervention(null);
          resetSession();
          if (data && (data.session_summary || data.report)) {
            setLatestReport(data.session_summary || data);
            setReportModalOpen(true);
          }
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
    window.scrollTo({ top: 0, behavior: "smooth" });
    if (sectionId !== "overview" && sectionId !== "work-monitor") {
      setTimeout(() => {
        const el = document.getElementById(sectionId);
        if (el) {
          el.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      }, 50);
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
        {authExpiredNotice && !user && (
        <div style={{
          background: "rgba(239, 68, 68, 0.15)",
          border: "1px solid rgba(239, 68, 68, 0.4)",
          color: "#fca5a5",
          padding: "0.75rem 1.5rem",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          fontSize: "0.875rem"
        }}>
          <span>
            <strong>Cloud Session Expired:</strong> Syncing is paused. Local monitoring, posture analysis, alertness detection, and alerts remain fully active.
          </span>
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => { setAuthExpiredNotice(false); setAuthModalOpen(true); }}
            style={{ marginLeft: "1rem" }}
          >
            Sign In to Resume Sync
          </button>
        </div>
      )}
      <Header
          monitoringState={monitoringState}
          cameraState={cameraState}
          isStarting={isStartingMonitoring}
          onToggleMonitoring={toggleMonitoring}
          onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
          apiBase={getApiBase()}
          onOpenAuth={() => setAuthModalOpen(true)}
          onOpenStatus={() => setStatusCenterOpen(true)}
        />

        <SystemHealth
          onOpenStatus={() => setStatusCenterOpen(true)}
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
          ) : activeSection === "reports-section" ? (
            <ReportsView />
          ) : activeSection === "privacy-section" ? (
            <PrivacyView
              apiBase={getApiBase()}
              onOpenAuth={() => setAuthModalOpen(true)}
            />
          ) : activeSection === "settings-section" ? (
            <SettingsView
              apiBase={getApiBase()}
              onOpenPostureCalibration={() => setActiveCalibrationModal("posture")}
              onOpenAlertnessCalibration={() => setActiveCalibrationModal("alertness")}
              canCalibratePosture={canCalibratePosture}
              canCalibrateAlertness={canCalibrateAlertness}
              postureCalibrated={calibration.state === "COMPLETED"}
              alertnessCalibrated={alertnessCalib.state === "COMPLETED"}
            />
          ) : activeSection === "work-monitor" ? (
            <WorkMonitorView
              monitoringState={monitoringState}
              cameraState={cameraState}
              humanState={humanState}
              previewKey={previewKey}
              apiBase={getApiBase()}
              sessionElapsedSec={sessionElapsedSec}
              latestReport={latestReport}
              onOpenReport={() => setReportModalOpen(true)}
              eventHistory={eventHistory}
              onClearHistory={clearRiskHistory}
              onToggleMonitoring={toggleMonitoring}
              isStarting={isStartingMonitoring}
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
                  isRunning={monitoringState === "RUNNING"}
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
                  isRunning={monitoringState === "RUNNING"}
                />

                <AlertnessCard
                  alertnessStatus={alertnessStatus}
                  alertnessScore={humanState.alertness_score}
                  humanState={humanState}
                  calibration={alertnessCalib}
                  canCalibrate={canCalibrateAlertness}
                  onOpenCalibration={() => setActiveCalibrationModal("alertness")}
                  isRunning={monitoringState === "RUNNING"}
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
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => setStatusCenterOpen(true)}
              style={{ fontSize: "11px", padding: "4px 10px" }}
              title="Open System Status Center"
              id="btn-status-center"
            >
              System Status
            </button>
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

      {/* Work Session Final Report Modal */}
      {reportModalOpen && (
        <ReportModal
          report={latestReport}
          onClose={() => setReportModalOpen(false)}
        />
      )}

      {/* System Status Center */}
      <StatusCenterModal
        isOpen={statusCenterOpen}
        onClose={() => setStatusCenterOpen(false)}
        monitoringState={monitoringState}
        cameraState={cameraState}
        backendConnected={backendStatus === "connected"}
        wsConnected={wsStatus === "connected"}
        framesReceived={framesReceived}
        apiBase={getApiBase()}
        appVersion="1.0.0"
      />

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
      <AlertProvider apiBase={getApiBase()}>
        <DashboardInner />
      </AlertProvider>
    </AuthProvider>
  );
}

export default App;
