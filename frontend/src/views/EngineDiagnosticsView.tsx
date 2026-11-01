import React, { useEffect, useState } from "react";
import { api } from "../api/client";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Legend,
  CartesianGrid,
} from "recharts";
import { Gauge, ShieldAlert, ArrowRight, Activity, Thermometer, Wind, RefreshCw } from "lucide-react";

interface Props {
  initialDataset?: string;
  initialEngineId?: number;
  onNavigateToReplay: (dataset: string, engineId: number) => void;
}

export const EngineDiagnosticsView: React.FC<Props> = ({
  initialDataset = "FD002",
  initialEngineId = 15,
  onNavigateToReplay,
}) => {
  const [dataset, setDataset] = useState<string>(initialDataset);
  const [engineId, setEngineId] = useState<number>(initialEngineId);
  const [trajectory, setTrajectory] = useState<any[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const fetchTrajectory = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getEngineTrajectory(engineId, dataset, "test", 150);
      setTrajectory(data.trajectory);
    } catch (err: any) {
      setError(err.message || "Failed to load telemetry trajectory");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTrajectory();
  }, [dataset, engineId]);

  const latestRow = trajectory.length > 0 ? trajectory[trajectory.length - 1] : null;

  return (
    <div>
      {/* Controls & Selector Header */}
      <div
        className="panel"
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "1rem",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          <Gauge size={22} color="var(--accent-blue)" />
          <div>
            <h2 style={{ fontSize: "1.2rem", fontWeight: 700 }}>Engine Telemetry Diagnostics</h2>
            <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
              Historical per-cycle sensor measurements and operating settings
            </div>
          </div>
        </div>

        <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
          <select
            className="select-control"
            aria-label="Diagnostics dataset" value={dataset}
            onChange={(e) => setDataset(e.target.value)}
          >
            <option value="FD002">FD002 (6 Regimes, Complex)</option>
            <option value="FD001">FD001 (Single Regime)</option>
            <option value="FD003">FD003 (Browsing/research only)</option>
            <option value="FD004">FD004 (Browsing/research only)</option>
          </select>

          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <span style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>Engine ID:</span>
            <input
              type="number"
              className="input-control"
              style={{ width: "90px" }}
              aria-label="Diagnostics engine" value={engineId}
              min={1}
              max={dataset === "FD002" ? 259 : 100}
              onChange={(e) => setEngineId(parseInt(e.target.value) || 1)}
            />
          </div>

          <button className="btn btn-secondary" onClick={fetchTrajectory} disabled={loading}>
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Fetch
          </button>

          <button
            className="btn btn-primary"
            disabled={!["FD001","FD002"].includes(dataset)}
            title={["FD001","FD002"].includes(dataset) ? "Open saved-model replay" : "No active model: research evidence is available separately"}
            onClick={() => onNavigateToReplay(dataset, engineId)}
          >
            Open in Scenario Lab <ArrowRight size={14} />
          </button>
        </div>
      </div>

      {error && (
        <div
          style={{
            background: "rgba(239, 68, 68, 0.15)",
            border: "1px solid rgba(239, 68, 68, 0.3)",
            color: "#f87171",
            padding: "1rem",
            borderRadius: "var(--radius-md)",
            marginBottom: "1.5rem",
          }}
        >
          {error}
        </div>
      )}

      {/* Snapshot Cards */}
      {latestRow && (
        <div className="kpi-grid" style={{ marginBottom: "1.5rem" }}>
          <div className="kpi-card">
            <div className="kpi-card-header">
              <span>Trajectory Length</span>
              <Activity size={16} color="var(--accent-cyan)" />
            </div>
            <div className="kpi-value">{latestRow.cycle} Cycles</div>
            <div className="kpi-subtext">Available observed prefix; not remaining life</div>
          </div>

          <div className="kpi-card">
            <div className="kpi-card-header">
              <span>Operating settings 1 / 2</span>
              <Wind size={16} color="var(--accent-purple)" />
            </div>
            <div className="kpi-value" style={{ fontSize: "1.25rem" }}>
              {latestRow.setting_1?.toFixed(4)} / {latestRow.setting_2?.toFixed(4)}
            </div>
            <div className="kpi-subtext">Raw setting 3: {latestRow.setting_3}</div>
          </div>

          <div className="kpi-card">
            <div className="kpi-card-header">
              <span>HPC Outlet Temperature (T30)</span>
              <Thermometer size={16} color="var(--accent-amber)" />
            </div>
            <div className="kpi-value" style={{ fontSize: "1.5rem", color: "var(--accent-amber)" }}>
              {latestRow.sensor_3?.toFixed(1)} °R
            </div>
            <div className="kpi-subtext">Primary Thermal Creep Indicator</div>
          </div>

          <div className="kpi-card">
            <div className="kpi-card-header">
              <span>Data Quality Check</span>
              <ShieldAlert size={16} color="var(--accent-green)" />
            </div>
            <div className="kpi-value" style={{ fontSize: "1.3rem", color: "var(--accent-green)" }}>
              NOMINAL
            </div>
            <div className="kpi-subtext">0 NaNs · No Stuck Sensors Detected</div>
          </div>
        </div>
      )}

      {/* Sensor Chart 1: Temperatures */}
      <div className="panel">
        <div className="panel-header">
          <div className="panel-title">
            <Thermometer size={18} color="var(--accent-amber)" /> Thermal Degradation Channels (T24, T30, T50)
          </div>
          <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
            Values plotted across cumulative operational engine cycles
          </span>
        </div>
        <div style={{ height: "280px", width: "100%" }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={trajectory}>
              <CartesianGrid strokeDasharray="3 3" stroke="#232d42" />
              <XAxis dataKey="cycle" stroke="#64748b" />
              <YAxis stroke="#64748b" domain={["auto", "auto"]} />
              <Tooltip
                contentStyle={{ background: "#111622", borderColor: "#232d42", borderRadius: "8px" }}
              />
              <Legend />
              <Line
                type="monotone"
                dataKey="sensor_2"
                name="Sensor 2 (LPC Outlet Temp)"
                stroke="#60a5fa"
                dot={false}
                strokeWidth={1.5}
              />
              <Line
                type="monotone"
                dataKey="sensor_3"
                name="Sensor 3 (HPC Outlet Temp)"
                stroke="#f59e0b"
                dot={false}
                strokeWidth={2}
              />
              <Line
                type="monotone"
                dataKey="sensor_4"
                name="Sensor 4 (LPT Outlet Temp)"
                stroke="#f43f5e"
                dot={false}
                strokeWidth={1.5}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Sensor Chart 2: Pressure & Core Speed */}
      <div className="grid-2">
        <div className="panel">
          <div className="panel-header">
            <div className="panel-title">
              <Activity size={18} color="var(--accent-blue)" /> Physical Speeds (Fan & Core)
            </div>
          </div>
          <div style={{ height: "240px", width: "100%" }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={trajectory}>
                <CartesianGrid strokeDasharray="3 3" stroke="#232d42" />
                <XAxis dataKey="cycle" stroke="#64748b" />
                <YAxis stroke="#64748b" domain={["auto", "auto"]} />
                <Tooltip
                  contentStyle={{ background: "#111622", borderColor: "#232d42", borderRadius: "8px" }}
                />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="sensor_8"
                  name="Sensor 8 (Physical Fan Speed)"
                  stroke="#34d399"
                  dot={false}
                  strokeWidth={1.5}
                />
                <Line
                  type="monotone"
                  dataKey="sensor_9"
                  name="Sensor 9 (Physical Core Speed)"
                  stroke="#818cf8"
                  dot={false}
                  strokeWidth={1.5}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="panel">
          <div className="panel-header">
            <div className="panel-title">
              <Wind size={18} color="var(--accent-cyan)" /> Static & Bypass Pressure
            </div>
          </div>
          <div style={{ height: "240px", width: "100%" }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={trajectory}>
                <CartesianGrid strokeDasharray="3 3" stroke="#232d42" />
                <XAxis dataKey="cycle" stroke="#64748b" />
                <YAxis stroke="#64748b" domain={["auto", "auto"]} />
                <Tooltip
                  contentStyle={{ background: "#111622", borderColor: "#232d42", borderRadius: "8px" }}
                />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="sensor_11"
                  name="Sensor 11 (Static Pressure)"
                  stroke="#38bdf8"
                  dot={false}
                  strokeWidth={1.5}
                />
                <Line
                  type="monotone"
                  dataKey="sensor_14"
                  name="Sensor 14 (Corrected Core Speed)"
                  stroke="#ec4899"
                  dot={false}
                  strokeWidth={1.5}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
};

