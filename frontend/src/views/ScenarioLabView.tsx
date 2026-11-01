import React, { useState, useEffect, useRef } from "react";
import { api } from "../api/client";
import type { ReplayState, TelemetryEvidence } from "../types";
import {
  Play,
  Pause,
  RotateCcw,
  Zap,
  Sliders,
  AlertOctagon,
  CheckCircle,
  FileText,
  Activity,
  Layers,
} from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  ReferenceLine,
} from "recharts";

interface Props {
  initialDataset?: string;
  initialEngineId?: number;
  onNavigateToWorkOrders: (workOrderId?: string, namespace?: string) => void;
}

export const ScenarioLabView: React.FC<Props> = ({
  initialDataset = "FD002",
  initialEngineId = 15,
  onNavigateToWorkOrders,
}) => {
  // Session Configuration
  const [dataset, setDataset] = useState<string>(initialDataset);
  const [engineId, setEngineId] = useState<number>(initialEngineId);
  const [policy, setPolicy] = useState<string>("point");
  const [replayState, setReplayState] = useState<ReplayState | null>(null);
  const [historyTrace, setHistoryTrace] = useState<TelemetryEvidence[]>([]);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(false);

  const [sessionError, setSessionError] = useState<string | null>(null);
  const [sessionNamespace, setSessionNamespace] = useState<string>("default");

  // Fault Injection Configuration
  const [faultType, setFaultType] = useState<string>("stuck_sensor");
  const [faultChannel, setFaultChannel] = useState<string>("sensor_11");
  const [faultStart, setFaultStart] = useState<number>(25);
  const [faultDuration, setFaultDuration] = useState<number>(15);
  const [faultMagnitude, setFaultMagnitude] = useState<number>(1.0);
  const [faultNotice, setFaultNotice] = useState<string | null>(null);

  const generationRef = useRef(0);
  const advancingRef = useRef(false);
  const playTimerRef = useRef<number | null>(null);

  // Start new isolated replay session
  const startSession = async () => {
    const generation=++generationRef.current;
    setReplayState(null);
    setLoading(true);
    setIsPlaying(false);
    if (playTimerRef.current) clearInterval(playTimerRef.current);

    try {
      setSessionError(null);
      const cacheKey = `flairguard_replay_${dataset}_${engineId}_${policy}`;
      const saved = sessionStorage.getItem(cacheKey);
      let state: ReplayState;
      if (saved) {
        try { state = await api.getReplay(saved); }
        catch { sessionStorage.removeItem(cacheKey); state = await api.startReplay({dataset, engine_id:engineId, split:"test", policy}); }
      } else {state = await api.startReplay({dataset,engine_id:engineId,split:"test",policy});}
      sessionStorage.setItem(cacheKey,state.session_id);
      const exported = await api.exportReplay(state.session_id);
      if(generation!==generationRef.current)return;
      setSessionNamespace(exported.namespace);
      sessionStorage.setItem("flairguard_namespace",exported.namespace);
      setHistoryTrace(exported.events.map((e:any) => ({cycle:e.cycle,prediction:e.prediction.prediction,
        usable:e.prediction.usable,anomaly_score:e.prediction.anomaly_score})));
      setReplayState(state);
      setFaultNotice(null);
    } catch (err: any) {
      setSessionError("Replay unavailable: " + err.message);
    } finally {
      if(generation===generationRef.current)setLoading(false);
    }
  };

  useEffect(() => {
    startSession();
    return () => {
      if (playTimerRef.current) clearInterval(playTimerRef.current);
    };
  }, [dataset, engineId, policy]);

  // Step simulation forward
  const stepSession = async (stepCount: number) => {
    if (!replayState || advancingRef.current) return;
    advancingRef.current = true;
    try {
      const updated = await api.stepReplay(replayState.session_id, stepCount);
      setReplayState(updated);
      if (updated.last_evidence) {
        setHistoryTrace((prev) => [...prev, updated.last_evidence!]);
      }
      if (updated.is_completed) {
        setIsPlaying(false);
      }
    } catch (err: any) {
      setSessionError("Step failed: " + err.message);
      setIsPlaying(false);
    } finally { advancingRef.current = false; }
  };

  // Play / Pause loop
  useEffect(() => {
    if (isPlaying) {
      playTimerRef.current = window.setInterval(() => {
        stepSession(1);
      }, 350);
    } else {
      if (playTimerRef.current) clearInterval(playTimerRef.current);
    }
    return () => {
      if (playTimerRef.current) clearInterval(playTimerRef.current);
    };
  }, [isPlaying, replayState?.session_id]);

  // Inject synthetic fault
  const handleInjectFault = async () => {
    if (!replayState) return;
    try {
      const res = await api.injectFault(replayState.session_id, {
        fault_type: faultType,
        channel: faultChannel,
        start_cycle: faultStart,
        duration: faultDuration,
        magnitude: faultMagnitude,
      });
      setFaultNotice(
        `Fault Armed: ${faultType.toUpperCase()} on ${faultChannel} from cycle ${faultStart} to ${
          faultStart + faultDuration
        }`
      );
      setReplayState((prev) => (prev ? { ...prev, active_fault: res.injected_fault } : null));
    } catch (err: any) {
      setSessionError("Fault injection failed: " + err.message);
    }
  };

  const handleReset = async () => {
    if (!replayState) return;
    setIsPlaying(false);
    try {
      const res = await api.resetReplay(replayState.session_id);
      setReplayState(res);
      const exported=await api.exportReplay(res.session_id);
      setSessionNamespace(exported.namespace);
      sessionStorage.setItem("flairguard_namespace",exported.namespace);
      setHistoryTrace([]);
      setFaultNotice(null);
    } catch (err: any) {
      console.error(err);
    }
  };

  const chartData = historyTrace.map((t) => ({
    cycle: t.cycle,
    predicted_rul: t.prediction,
    usable: t.usable ? 1 : 0,
    anomaly_score: t.anomaly_score,
  }));

  const latestEvidence = replayState?.last_evidence;

  return (
    <div>
      {sessionError && <div role="alert" className="error-banner">{sessionError}</div>}
      <p className="scope-note">Historical replay. Sensor faults alter measurements only. Acknowledgement and closure record workflow; they do not repair an aircraft.</p>
      <div data-testid="replay-identity" className="scope-note">Session {replayState?.session_id || "unavailable"} | Namespace {sessionNamespace} | Cycle {replayState?.current_cycle ?? 0}</div>
      {/* Session Controls Header */}
      <div className="panel">
        <div className="panel-header" style={{ marginBottom: "1rem" }}>
          <div className="panel-title">
            <Sliders size={20} color="var(--accent-blue)" /> Scenario & Reliability Simulation Lab
          </div>
          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
            <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Policy:</span>
            <select
              className="select-control"
              aria-label="Replay policy" value={policy}
              onChange={(e) => setPolicy(e.target.value)}
            >
              <option value="point">Champion Point-RUL Policy</option>
              <option value="quality_gate">Experimental Quality Gate</option>
              <option value="fixed">Fixed-Age Maintenance Baseline</option>
              <option value="none">Run-to-Failure (None)</option>
            </select>

            <select
              className="select-control"
              aria-label="Replay dataset" value={dataset}
              onChange={(e) => setDataset(e.target.value)}
            >
              <option value="FD002">FD002 (Multi-Regime)</option>
              <option value="FD001">FD001 (Single-Regime)</option>
            </select>

            <input
              type="number"
              className="input-control"
              style={{ width: "80px" }}
              aria-label="Replay engine" value={engineId}
              min={1}
              max={dataset === "FD002" ? 259 : 100}
              onChange={(e) => setEngineId(parseInt(e.target.value) || 1)}
            />

            <button className="btn btn-secondary btn-sm" onClick={startSession} disabled={loading}>
              <RotateCcw size={13} /> Reconnect replay
            </button>
          </div>
        </div>

        {/* Live Replay Player Bar */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            background: "var(--bg-secondary)",
            padding: "0.85rem 1.25rem",
            borderRadius: "var(--radius-md)",
            border: "1px solid var(--border)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
            <button
              className={`btn ${isPlaying ? "btn-danger" : "btn-primary"}`}
              onClick={() => setIsPlaying(!isPlaying)}
              disabled={loading || !replayState || replayState.is_completed}
            >
              {isPlaying ? <Pause size={15} /> : <Play size={15} />}
              {isPlaying ? "Pause Stream" : "Auto-Play"}
            </button>
            <button
              className="btn btn-secondary"
              onClick={() => stepSession(1)}
              disabled={loading || !replayState || isPlaying || replayState.is_completed}
            >
              +1 Cycle
            </button>
            <button
              className="btn btn-secondary"
              onClick={() => stepSession(5)}
              disabled={loading || !replayState || isPlaying || replayState.is_completed}
            >
              +5 Cycles
            </button>
            <button
              className="btn btn-secondary"
              onClick={() => stepSession(20)}
              disabled={loading || !replayState || isPlaying || replayState.is_completed}
            >
              +20 Cycles
            </button>
            <button className="btn btn-secondary" onClick={handleReset}>
              <RotateCcw size={14} /> Reset
            </button>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "1.5rem" }}>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Current Progress</div>
              <div className="font-mono" style={{ fontSize: "1.1rem", fontWeight: 700 }}>
                Cycle {replayState?.current_cycle ?? 0} / {replayState?.total_trajectory_cycles ?? 0}
              </div>
            </div>

            {replayState?.active_work_order ? (
              <button
                className="btn btn-danger"
                onClick={() => onNavigateToWorkOrders(replayState.active_work_order?.work_order_id, sessionNamespace)}
              >
                <FileText size={14} /> Active Work Order ({replayState.active_work_order.severity})
              </button>
            ) : (
              <span className="badge badge-nominal">
                <CheckCircle size={12} /> Normal Monitoring
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Main Grid: Fault Injector & Real-time Causal Chart */}
      <div className="grid-3">
        {/* Left: Real-time RUL Decay & Threshold Curve */}
        <div className="panel">
          <div className="panel-header">
            <div className="panel-title">
              <Activity size={18} color="var(--accent-green)" /> Causal RUL Estimation & Maintenance Boundary
            </div>
            <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
              Threshold: RUL ≤ 20 triggers Work Order Schedule
            </span>
          </div>

          <div style={{ height: "300px", width: "100%" }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#232d42" />
                <XAxis dataKey="cycle" stroke="#64748b" />
                <YAxis stroke="#64748b" domain={[0, 130]} />
                <Tooltip
                  contentStyle={{ background: "#111622", borderColor: "#232d42", borderRadius: "8px" }}
                />
                <ReferenceLine
                  y={20}
                  stroke="#ef4444"
                  strokeDasharray="4 4"
                  label={{ value: "Action Threshold (20c)", fill: "#ef4444", fontSize: 11 }}
                />
                <Line
                  type="monotone"
                  dataKey="predicted_rul"
                  name="Predicted RUL"
                  stroke="#3b82f6"
                  strokeWidth={2.5}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Telemetry Snapshot at Current Cycle */}
          {latestEvidence && (
            <div
              style={{
                marginTop: "1.25rem",
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))",
                gap: "0.75rem",
                background: "var(--bg-secondary)",
                padding: "0.85rem",
                borderRadius: "var(--radius-md)",
                fontSize: "0.78rem",
              }}
            >
              <div>
                <span style={{ color: "var(--text-muted)" }}>Predicted RUL:</span>
                <div className="font-mono" style={{ fontWeight: 700, fontSize: "0.95rem" }}>
                  {latestEvidence.prediction != null ? `${latestEvidence.prediction.toFixed(1)} c` : "Warmup"}
                </div>
              </div>
              <div>
                <span style={{ color: "var(--text-muted)" }}>Auditor Usable:</span>
                <div>
                  <span className={`badge ${latestEvidence.usable ? "badge-nominal" : "badge-critical"}`}>
                    {latestEvidence.usable ? "USABLE" : "AUDIT FAULT"}
                  </span>
                </div>
              </div>
              <div>
                <span style={{ color: "var(--text-muted)" }}>Anomaly Score:</span>
                <div className="font-mono">
                  {latestEvidence.anomaly_score != null ? latestEvidence.anomaly_score.toFixed(3) : "N/A"}
                </div>
              </div>
              <div>
                <span style={{ color: "var(--text-muted)" }}>Policy Proposal:</span>
                <div style={{ fontWeight: 600 }}>{latestEvidence.action_type || "MONITOR"}</div>
              </div>
              <div>
                <span style={{ color: "var(--text-muted)" }}>Severity:</span>
                <div>
                  <span
                    className={`badge ${
                      latestEvidence.severity === "CRITICAL"
                        ? "badge-critical"
                        : latestEvidence.severity === "ESCALATE_HUMAN"
                        ? "badge-escalated"
                        : "badge-nominal"
                    }`}
                  >
                    {latestEvidence.severity}
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Right: Controlled Synthetic Fault Injection Box */}
        <div className="panel">
          <div className="panel-header">
            <div className="panel-title">
              <Zap size={18} color="var(--accent-amber)" /> Controlled Fault Injection
            </div>
          </div>
          <p style={{ fontSize: "0.78rem", color: "var(--text-secondary)", marginBottom: "1rem" }}>
            Inject synthetic telemetry corruptions without modifying raw NASA files to test auditor and
            escalation gates.
          </p>

          <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
            <div>
              <label style={{ fontSize: "0.75rem", color: "var(--text-muted)", display: "block" }}>
                Fault Mechanism
              </label>
              <select
                className="select-control"
                style={{ width: "100%" }}
                aria-label="Fault mechanism" value={faultType}
                onChange={(e) => setFaultType(e.target.value)}
              >
                <option value="stuck_sensor">Stuck Sensor (Frozen Values)</option>
                <option value="sensor_drift">Sensor Drift (Linear Bias Ramp)</option>
                <option value="missing_data">Missing Telemetry (NaN Drop)</option>
                <option value="gaussian_noise">High-Variance Noise Injection</option>
              </select>
            </div>

            <div>
              <label style={{ fontSize: "0.75rem", color: "var(--text-muted)", display: "block" }}>
                Target Sensor Channel
              </label>
              <select
                className="select-control"
                style={{ width: "100%" }}
                aria-label="Fault channel" value={faultChannel}
                onChange={(e) => setFaultChannel(e.target.value)}
              >
                <option value="sensor_11">Sensor 11 (Static Pressure - Active)</option>
                <option value="sensor_3">Sensor 3 (HPC Outlet Temp)</option>
                <option value="sensor_4">Sensor 4 (LPT Outlet Temp)</option>
                <option value="sensor_9">Sensor 9 (Core Speed)</option>
              </select>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.5rem" }}>
              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-muted)", display: "block" }}>
                  Onset Cycle
                </label>
                <input
                  type="number"
                  className="input-control"
                  style={{ width: "100%" }}
                  aria-label="Fault onset" value={faultStart}
                  onChange={(e) => setFaultStart(parseInt(e.target.value) || 20)}
                />
              </div>
              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-muted)", display: "block" }}>
                  Duration
                </label>
                <input
                  type="number"
                  className="input-control"
                  style={{ width: "100%" }}
                  aria-label="Fault duration" value={faultDuration}
                  onChange={(e) => setFaultDuration(parseInt(e.target.value) || 10)}
                />
              </div>
              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-muted)", display: "block" }}>
                  Magnitude
                </label>
                <input
                  type="number"
                  step="0.5"
                  className="input-control"
                  style={{ width: "100%" }}
                  aria-label="Fault magnitude" value={faultMagnitude}
                  onChange={(e) => setFaultMagnitude(parseFloat(e.target.value) || 1.0)}
                />
              </div>
            </div>

            <button className="btn btn-primary" onClick={handleInjectFault} style={{ marginTop: "0.5rem" }}>
              <Zap size={14} /> Arm Fault Injection
            </button>

            {faultNotice && (
              <div
                style={{
                  background: "rgba(245, 158, 11, 0.15)",
                  border: "1px solid rgba(245, 158, 11, 0.3)",
                  color: "#fbbf24",
                  padding: "0.75rem",
                  borderRadius: "var(--radius-sm)",
                  fontSize: "0.75rem",
                  display: "flex",
                  alignItems: "center",
                  gap: "0.5rem",
                }}
              >
                <AlertOctagon size={16} />
                <span>{faultNotice}</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Trajectory Step-by-Step Causal Trace Table */}
      <div className="panel">
        <div className="panel-header">
          <div className="panel-title">
            <Layers size={18} color="var(--accent-purple)" /> Step-by-Step Causal Trace Ledger ({historyTrace.length})
          </div>
        </div>

        <div className="data-table-container" style={{ maxHeight: "300px", overflowY: "auto" }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Cycle</th>
                <th>Telemetry Source</th>
                <th>Usable</th>
                <th>Predicted RUL</th>
                <th>Anomaly Score</th>
                <th>Persistence</th>
                <th>Action Type</th>
                <th>Severity</th>
                <th>Work Order ID</th>
              </tr>
            </thead>
            <tbody>
              {historyTrace.length === 0 ? (
                <tr>
                  <td colSpan={9} style={{ textAlign: "center", color: "var(--text-muted)", padding: "2rem" }}>
                    Simulation not started. Click "+1 Cycle" or "Auto-Play" above.
                  </td>
                </tr>
              ) : (
                [...historyTrace].reverse().map((ev) => (
                  <tr key={ev.cycle}>
                    <td className="font-mono">
                      <strong>Cycle {ev.cycle}</strong>
                    </td>
                    <td>
                      <span className={`badge ${ev.is_perturbed ? "badge-warning" : "badge-blue"}`}>
                        {ev.is_perturbed ? "SYNTHETIC FAULT" : "NASA RAW"}
                      </span>
                    </td>
                    <td>
                      <span className={`badge ${ev.usable ? "badge-nominal" : "badge-critical"}`}>
                        {ev.usable ? "PASS" : "FAIL"}
                      </span>
                    </td>
                    <td className="font-mono">
                      {ev.prediction != null ? `${ev.prediction.toFixed(1)} cycles` : "Warm-up"}
                    </td>
                    <td className="font-mono">
                      {ev.anomaly_score != null ? ev.anomaly_score.toFixed(3) : "—"}
                    </td>
                    <td className="font-mono">{ev.persistence ?? 0}</td>
                    <td>
                      <span style={{ fontWeight: 600 }}>{ev.action_type || "MONITOR"}</span>
                    </td>
                    <td>
                      <span
                        className={`badge ${
                          ev.severity === "CRITICAL"
                            ? "badge-critical"
                            : ev.severity === "ESCALATE_HUMAN"
                            ? "badge-escalated"
                            : "badge-nominal"
                        }`}
                      >
                        {ev.severity}
                      </span>
                    </td>
                    <td className="font-mono">
                      {ev.work_order_id ? (
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => onNavigateToWorkOrders(ev.work_order_id!, sessionNamespace)}
                        >
                          {ev.work_order_id.slice(0, 12)}...
                        </button>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
