import React, { useEffect, useState } from "react";
import { api } from "../api/client";
import type { FleetKPIs, EngineSummary, HealthStatus, DatasetInfo } from "../types";
import { Activity, AlertTriangle, ShieldCheck, Cpu, HardDrive, ArrowRight, RefreshCw, Filter } from "lucide-react";

interface Props {
  onSelectEngine: (dataset: string, engineId: number) => void;
  onNavigateToReplay: (dataset: string, engineId: number) => void;
}

export const FleetOverviewView: React.FC<Props> = ({ onSelectEngine, onNavigateToReplay }) => {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [kpis, setKpis] = useState<FleetKPIs | null>(null);
  const [datasets, setDatasets] = useState<DatasetInfo[]>([]);
  const [engines, setEngines] = useState<EngineSummary[]>([]);
  const [selectedDataset, setSelectedDataset] = useState<string>("FD002");
  const [loadError,setLoadError]=useState<string|null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [searchTerm, setSearchTerm] = useState<string>("");

  const loadData = async () => {
    setLoading(true);
    try {
      const [h, k, d, e] = await Promise.all([
        api.getHealth(),
        api.getFleetKPIs(),
        api.getDatasets(),
        api.getEngines(selectedDataset, 60),
      ]);
      setLoadError(null);
      setHealth(h);
      setKpis(k);
      setDatasets(d);
      setEngines(e);
    } catch (err) {
      setLoadError(String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [selectedDataset]);

  const filteredEngines = engines.filter((e) =>
    e.engine_id.toString().includes(searchTerm.trim())
  );

  return (
    <div>
      {loadError && <div role="alert" className="error-banner">{loadError}</div>}
      {/* System Health Status Bar */}
      <div
        style={{
          background: "var(--bg-secondary)",
          padding: "0.75rem 1.25rem",
          borderRadius: "var(--radius-md)",
          border: "1px solid var(--border)",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "1.5rem",
          fontSize: "0.825rem",
        }}
      >
        <div style={{ display: "flex", gap: "1.5rem", alignItems: "center" }}>
          <span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <Activity size={15} color="var(--accent-green)" />
            <strong>Backend Status:</strong> {health?.status === "healthy" ? "Online" : "Connecting..."}
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <HardDrive size={15} color={health?.database_connected ? "var(--accent-cyan)" : "var(--accent-red)"} />
            <strong>SQLite Store:</strong> {health?.database_connected ? "Connected" : "Disconnected"}
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <Cpu size={15} color="var(--accent-purple)" />
            <strong>Active Bundles:</strong> {health?.models_loaded?.join(", ") || "None"}
          </span>
        </div>
        <button
          onClick={loadData}
          className="btn btn-secondary btn-sm"
          disabled={loading}
          title="Refresh Fleet Data"
        >
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      </div>

      {/* Fleet KPI Grid */}
      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-card-header">
            <span>Dataset engines</span>
            <Activity size={16} color="var(--accent-blue)" />
          </div>
          <div className="kpi-value">{kpis?.total_monitored_engines ?? "Unavailable"}</div>
          <div className="kpi-subtext">Available NASA dataset records; not a live monitored fleet</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-card-header">
            <span>Active Work Orders</span>
            <AlertTriangle size={16} color="var(--accent-amber)" />
          </div>
          <div className="kpi-value" style={{ color: "var(--accent-amber)" }}>
            {kpis?.active_work_orders ?? "Unavailable"}
          </div>
          <div className="kpi-subtext">Pending Dispatch or In-Progress</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-card-header">
            <span>Data Fault Escalations</span>
            <ShieldCheck size={16} color="var(--accent-purple)" />
          </div>
          <div className="kpi-value" style={{ color: "var(--accent-purple)" }}>
            {kpis?.open_escalations ?? "Unavailable"}
          </div>
          <div className="kpi-subtext">Telemetry Audited with Human Referral</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-card-header">
            <span>Champion Policy</span>
            <Cpu size={16} color="var(--accent-green)" />
          </div>
          <div className="kpi-value" style={{ fontSize: "1.25rem", color: "var(--accent-green)" }}>
            {kpis?.champion_policy ?? "Unavailable"}
          </div>
          <div className="kpi-subtext">Threshold: 20 cycles · Pinned saved model; historical replay</div>
        </div>
      </div>

      {/* Dataset Selection & Description */}
      <div className="panel">
        <div className="panel-header">
          <div className="panel-title">
            <Filter size={18} color="var(--accent-blue)" /> Fleet Selection & Operating Regimes
          </div>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            {datasets.map((d) => (
              <button
                key={d.id}
                className={`btn ${selectedDataset === d.id ? "btn-primary" : "btn-secondary"}`}
                onClick={() => setSelectedDataset(d.id)}
              >
                {d.id} ({d.operating_conditions === 1 ? "Single-Regime" : "6-Regimes Multi"})
              </button>
            ))}
          </div>
        </div>

        {datasets
          .filter((d) => d.id === selectedDataset)
          .map((d) => (
            <div
              key={d.id}
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
                gap: "1rem",
                background: "var(--bg-secondary)",
                padding: "1rem",
                borderRadius: "var(--radius-md)",
                fontSize: "0.825rem",
              }}
            >
              <div>
                <span style={{ color: "var(--text-muted)" }}>Operating Regimes:</span>{" "}
                <strong>{d.operating_conditions}</strong>
              </div>
              <div>
                <span style={{ color: "var(--text-muted)" }}>Fault Modes:</span>{" "}
                <strong>{d.fault_modes}</strong>
              </div>
              <div>
                <span style={{ color: "var(--text-muted)" }}>Training Engines:</span>{" "}
                <strong>{d.train_engines}</strong>
              </div>
              <div>
                <span style={{ color: "var(--text-muted)" }}>Test Trajectories:</span>{" "}
                <strong>{d.test_engines}</strong>
              </div>
              <div>
                <span style={{ color: "var(--text-muted)" }}>Telemetry Channels:</span>{" "}
                <strong>{d.sensors_count} Sensors + 3 Settings</strong>
              </div>
            </div>
          ))}
      </div>

      {/* Engine Status Table */}
      <div className="panel">
        <div className="panel-header">
          <div className="panel-title">
            <span>Fleet Turbofan Units ({filteredEngines.length})</span>
          </div>
          <div className="panel-actions">
            <input
              type="text"
              placeholder="Search by Engine ID..."
              className="input-control"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              style={{ width: "220px" }}
            />
          </div>
        </div>

        <div className="data-table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Engine Unit</th>
                <th>Dataset</th>
                <th>Cohort Split</th>
                <th>Observed Cycles</th>
                <th>Predicted RUL</th>
                <th>Health Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredEngines.map((eng) => (
                <tr key={`${eng.dataset}-${eng.engine_id}`}>
                  <td className="font-mono">
                    <strong>Engine #{eng.engine_id}</strong>
                  </td>
                  <td>
                    <span className="badge badge-blue">{eng.dataset}</span>
                  </td>
                  <td>
                    <span className="badge badge-neutral">{eng.split.toUpperCase()}</span>
                  </td>
                  <td className="font-mono">{eng.total_cycles} cycles</td>
                  <td className="font-mono">
                    {eng.last_predicted_rul != null ? (
                      <span
                        style={{
                          fontWeight: 600,
                          color:
                            eng.last_predicted_rul < 20
                              ? "var(--accent-red)"
                              : eng.last_predicted_rul < 45
                              ? "var(--accent-amber)"
                              : "var(--accent-green)",
                        }}
                      >
                        {eng.last_predicted_rul.toFixed(1)} cycles
                      </span>
                    ) : (
                      <span style={{ color: "var(--text-muted)" }}>Ready to Replay</span>
                    )}
                  </td>
                  <td>
                    <span
                      className={`badge ${
                        eng.current_status === "CRITICAL"
                          ? "badge-critical"
                          : ["HIGH","MEDIUM"].includes(eng.current_status)
                          ? "badge-warning"
                          : eng.current_status === "ESCALATE_HUMAN"
                          ? "badge-escalated"
                          : eng.current_status === "NOMINAL" ? "badge-nominal" : "badge-neutral"
                      }`}
                    >
                      {eng.current_status}
                    </span>
                  </td>
                  <td>
                    <div style={{ display: "flex", gap: "0.5rem" }}>
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => onSelectEngine(eng.dataset, eng.engine_id)}
                      >
                        Diagnostics
                      </button>
                      <button
                        className="btn btn-primary btn-sm"
                        disabled={!health?.models_loaded.includes(eng.dataset)}
                        title={health?.models_loaded.includes(eng.dataset) ? "Start saved-model replay" : "Browsing/research only: no active serving model"}
                        onClick={() => onNavigateToReplay(eng.dataset, eng.engine_id)}
                      >
                        Replay Lab <ArrowRight size={12} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

