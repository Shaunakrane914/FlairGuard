import React, { useState, useEffect } from "react";
import { api } from "../api/client";
import {
  FleetScheduleSnapshot,
  SchedulingMetrics,
} from "../types";
import {
  Warehouse,
  RotateCcw,
  CheckCircle,
  Clock,
  TrendingUp,
  Cpu,
  Layers,
} from "lucide-react";

export const FleetSchedulerView: React.FC = () => {
  // Controls
  const [selectedDataset, setSelectedDataset] = useState<string>("FD002");
  const [numBays, setNumBays] = useState<number>(3);
  const [serviceDuration, setServiceDuration] = useState<number>(4);
  const [targetCycle, setTargetCycle] = useState<number>(120);
  const [activePolicy, setActivePolicy] = useState<string>("RISK_AWARE");
  const [engineLimit, setEngineLimit] = useState<number>(30);

  // Data states
  const [snapshot, setSnapshot] = useState<FleetScheduleSnapshot | null>(null);
  const [comparisonMetrics, setComparisonMetrics] = useState<SchedulingMetrics[]>([]);
  const [loadingSnapshot, setLoadingSnapshot] = useState<boolean>(true);
  const [loadingSimulation, setLoadingSimulation] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Load snapshot
  const loadSnapshot = async () => {
    setLoadingSnapshot(true);
    setErrorMsg(null);
    try {
      const snap = await api.getSchedulerSnapshot(
        selectedDataset,
        numBays,
        serviceDuration,
        targetCycle,
        activePolicy,
        engineLimit
      );
      setSnapshot(snap);
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to load depot snapshot");
    } finally {
      setLoadingSnapshot(false);
    }
  };

  // Run full 4-policy simulation
  const runSimulation = async () => {
    setLoadingSimulation(true);
    setErrorMsg(null);
    try {
      const results = await api.simulateScheduler({
        dataset: selectedDataset,
        num_bays: numBays,
        service_duration: serviceDuration,
        engine_limit: engineLimit,
        service_threshold_rul: 25.0,
      });
      setComparisonMetrics(results);
    } catch (err: any) {
      setErrorMsg(err.message || "Simulation failed");
    } finally {
      setLoadingSimulation(false);
    }
  };

  useEffect(() => {
    loadSnapshot();
    runSimulation();
  }, [selectedDataset, numBays, serviceDuration, activePolicy]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      {/* View Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700, margin: 0, display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <Warehouse size={24} color="#3b82f6" />
            Depot Maintenance Capacity & Scheduling Optimizer
          </h1>
          <p style={{ margin: "0.25rem 0 0", color: "#64748b", fontSize: "0.875rem" }}>
            Resource-constrained hangar bay scheduling. Compares dispatch policies (FCFS vs EDF vs RUL Priority vs Risk-Optimal) to prevent queue-induced in-flight failures.
          </p>
        </div>

        <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
          <button
            onClick={() => {
              loadSnapshot();
              runSimulation();
            }}
            disabled={loadingSnapshot || loadingSimulation}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.4rem",
              padding: "0.5rem 1rem",
              borderRadius: "6px",
              backgroundColor: "#2563eb",
              color: "#fff",
              border: "none",
              cursor: "pointer",
              fontWeight: 600,
              fontSize: "0.875rem",
            }}
          >
            <RotateCcw size={15} />
            Refresh Depot State
          </button>
        </div>
      </div>

      {errorMsg && (
        <div style={{ padding: "0.75rem 1rem", backgroundColor: "#fef2f2", color: "#b91c1c", borderRadius: "6px", border: "1px solid #fecaca", fontSize: "0.875rem" }}>
          {errorMsg}
        </div>
      )}

      {/* Configuration Controls Bar */}
      <div style={{ backgroundColor: "#fff", border: "1px solid #e2e8f0", borderRadius: "8px", padding: "1.25rem", display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "1rem", alignItems: "flex-end" }}>
        <div>
          <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, color: "#475569", marginBottom: "0.25rem" }}>
            NASA Fleet Subset
          </label>
          <select
            value={selectedDataset}
            onChange={(e) => setSelectedDataset(e.target.value)}
            style={{ width: "100%", padding: "0.5rem", borderRadius: "6px", border: "1px solid #cbd5e1", fontSize: "0.875rem" }}
          >
            <option value="FD001">FD001 (Single Regime, 1 Fault)</option>
            <option value="FD002">FD002 (6 Regimes, 1 Fault)</option>
            <option value="FD003">FD003 (Single Regime, 2 Faults)</option>
            <option value="FD004">FD004 (6 Regimes, 2 Faults)</option>
          </select>
        </div>

        <div>
          <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, color: "#475569", marginBottom: "0.25rem" }}>
            Depot Hangar Bays: <strong>{numBays} Bays</strong>
          </label>
          <input
            type="range"
            min={1}
            max={5}
            step={1}
            value={numBays}
            onChange={(e) => setNumBays(parseInt(e.target.value, 10))}
            style={{ width: "100%" }}
          />
        </div>

        <div>
          <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, color: "#475569", marginBottom: "0.25rem" }}>
            Service Lead Duration: <strong>{serviceDuration} Cycles</strong>
          </label>
          <input
            type="range"
            min={1}
            max={8}
            step={1}
            value={serviceDuration}
            onChange={(e) => setServiceDuration(parseInt(e.target.value, 10))}
            style={{ width: "100%" }}
          />
        </div>

        <div>
          <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, color: "#475569", marginBottom: "0.25rem" }}>
            Operational Horizon: <strong>Cycle {targetCycle}</strong>
          </label>
          <input
            type="range"
            min={50}
            max={250}
            step={10}
            value={targetCycle}
            onChange={(e) => {
              setTargetCycle(parseInt(e.target.value, 10));
              loadSnapshot();
            }}
            style={{ width: "100%" }}
          />
        </div>

        <div>
          <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, color: "#475569", marginBottom: "0.25rem" }}>
            Fleet Engine Cohort: <strong>{engineLimit} Engines</strong>
          </label>
          <input
            type="range"
            min={10}
            max={60}
            step={5}
            value={engineLimit}
            onChange={(e) => setEngineLimit(parseInt(e.target.value, 10))}
            style={{ width: "100%" }}
          />
        </div>

        <div>
          <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, color: "#475569", marginBottom: "0.25rem" }}>
            Active Dispatch Policy
          </label>
          <select
            value={activePolicy}
            onChange={(e) => setActivePolicy(e.target.value)}
            style={{ width: "100%", padding: "0.5rem", borderRadius: "6px", border: "1px solid #cbd5e1", fontSize: "0.875rem" }}
          >
            <option value="RISK_AWARE">RISK_AWARE (FlairGuard Champion)</option>
            <option value="RUL_PRIORITY">RUL_PRIORITY (Lowest Point RUL)</option>
            <option value="EDF">EDF (Earliest Deadline First)</option>
            <option value="FCFS">FCFS (First-Come, First-Served)</option>
          </select>
        </div>
      </div>

      {/* Depot Hangar Bays Status Board */}
      <div style={{ backgroundColor: "#fff", border: "1px solid #e2e8f0", borderRadius: "8px", padding: "1.25rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
          <div>
            <h2 style={{ fontSize: "1.1rem", fontWeight: 700, margin: 0, display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <Layers size={18} color="#2563eb" />
              Live Depot Hangar Status (Cycle {targetCycle})
            </h2>
            <div style={{ fontSize: "0.8rem", color: "#64748b", marginTop: "0.2rem" }}>
              {snapshot?.summary_message || "Monitoring bay throughput and queue..."}
            </div>
          </div>
        </div>

        {/* Hangar Bays Grid */}
        <div style={{ display: "grid", gridTemplateColumns: `repeat(${numBays}, 1fr)`, gap: "1rem" }}>
          {snapshot?.bays.map((bay) => {
            const isOccupied = bay.status === "OCCUPIED";
            const progressPct = isOccupied
              ? Math.round(((serviceDuration - bay.cycles_remaining) / serviceDuration) * 100)
              : 0;

            return (
              <div
                key={bay.bay_id}
                style={{
                  border: isOccupied ? "2px solid #3b82f6" : "1px dashed #cbd5e1",
                  borderRadius: "8px",
                  padding: "1.25rem",
                  backgroundColor: isOccupied ? "#eff6ff" : "#f8fafc",
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.75rem",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontWeight: 700, fontSize: "0.95rem", color: "#1e293b" }}>
                    Bay #{bay.bay_id}
                  </span>
                  <span
                    style={{
                      padding: "0.2rem 0.5rem",
                      borderRadius: "9999px",
                      fontSize: "0.75rem",
                      fontWeight: 600,
                      backgroundColor: isOccupied ? "#dbeafe" : "#e2e8f0",
                      color: isOccupied ? "#1d4ed8" : "#475569",
                    }}
                  >
                    {bay.status}
                  </span>
                </div>

                {isOccupied ? (
                  <>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                      <Cpu size={16} color="#2563eb" />
                      <span style={{ fontWeight: 700, fontSize: "1.1rem", color: "#0f172a" }}>
                        Engine #{bay.engine_id}
                      </span>
                    </div>

                    <div>
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem", color: "#475569", marginBottom: "0.25rem" }}>
                        <span>Service Progress</span>
                        <span>{progressPct}% ({bay.cycles_remaining} cycles remaining)</span>
                      </div>
                      <div style={{ width: "100%", height: "8px", backgroundColor: "#bfdbfe", borderRadius: "9999px", overflow: "hidden" }}>
                        <div style={{ width: `${progressPct}%`, height: "100%", backgroundColor: "#2563eb", borderRadius: "9999px" }} />
                      </div>
                    </div>
                  </>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "1rem 0", color: "#94a3b8" }}>
                    <CheckCircle size={24} color="#10b981" />
                    <span style={{ fontSize: "0.8rem", marginTop: "0.4rem", fontWeight: 500 }}>
                      Bay Idle & Ready
                    </span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Prioritized Maintenance Queue Table */}
      <div style={{ backgroundColor: "#fff", border: "1px solid #e2e8f0", borderRadius: "8px", padding: "1.25rem" }}>
        <h2 style={{ fontSize: "1.1rem", fontWeight: 700, margin: "0 0 1rem 0", display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <Clock size={18} color="#f59e0b" />
          Depot Waiting Queue ({snapshot?.queue.length || 0} Engines Awaiting Bay)
        </h2>

        {snapshot?.queue && snapshot.queue.length > 0 ? (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.875rem", textAlign: "left" }}>
              <thead>
                <tr style={{ borderBottom: "2px solid #e2e8f0", color: "#475569" }}>
                  <th style={{ padding: "0.6rem 0.75rem" }}>Priority Rank</th>
                  <th style={{ padding: "0.6rem 0.75rem" }}>Engine ID</th>
                  <th style={{ padding: "0.6rem 0.75rem" }}>Requested Cycle</th>
                  <th style={{ padding: "0.6rem 0.75rem" }}>Est. RUL</th>
                  <th style={{ padding: "0.6rem 0.75rem" }}>Uncertainty (σ)</th>
                  <th style={{ padding: "0.6rem 0.75rem" }}>Wait Delay</th>
                  <th style={{ padding: "0.6rem 0.75rem" }}>Urgency Score</th>
                  <th style={{ padding: "0.6rem 0.75rem" }}>Next Action</th>
                </tr>
              </thead>
              <tbody>
                {snapshot.queue.map((item, idx) => (
                  <tr key={item.engine_id} style={{ borderBottom: "1px solid #f1f5f9" }}>
                    <td style={{ padding: "0.6rem 0.75rem" }}>
                      <span style={{ fontWeight: 700, color: idx === 0 ? "#2563eb" : "#475569" }}>
                        #{idx + 1}
                      </span>
                    </td>
                    <td style={{ padding: "0.6rem 0.75rem", fontWeight: 600 }}>Engine #{item.engine_id}</td>
                    <td style={{ padding: "0.6rem 0.75rem" }}>Cycle {item.requested_cycle}</td>
                    <td style={{ padding: "0.6rem 0.75rem", color: item.predicted_rul < 15 ? "#dc2626" : "#475569", fontWeight: 600 }}>
                      {item.predicted_rul} cycles
                    </td>
                    <td style={{ padding: "0.6rem 0.75rem" }}>±{item.uncertainty_sigma}</td>
                    <td style={{ padding: "0.6rem 0.75rem", color: item.waiting_cycles > 5 ? "#d97706" : "#475569" }}>
                      {item.waiting_cycles} cycles
                    </td>
                    <td style={{ padding: "0.6rem 0.75rem", fontWeight: 600 }}>{item.urgency_score}</td>
                    <td style={{ padding: "0.6rem 0.75rem" }}>
                      {idx === 0 ? (
                        <span style={{ padding: "0.2rem 0.5rem", borderRadius: "4px", backgroundColor: "#dbeafe", color: "#1d4ed8", fontSize: "0.75rem", fontWeight: 600 }}>
                          Next in Bay
                        </span>
                      ) : (
                        <span style={{ color: "#64748b", fontSize: "0.75rem" }}>Queued</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div style={{ textAlign: "center", padding: "2rem", color: "#64748b" }}>
            <CheckCircle size={32} color="#10b981" style={{ margin: "0 auto 0.5rem" }} />
            <p style={{ margin: 0, fontWeight: 500 }}>No engines currently waiting in depot queue.</p>
            <span style={{ fontSize: "0.8rem", color: "#94a3b8" }}>All degraded engines have been serviced or are currently occupying bays.</span>
          </div>
        )}
      </div>

      {/* Comparative Policy Benchmark Table */}
      <div style={{ backgroundColor: "#fff", border: "1px solid #e2e8f0", borderRadius: "8px", padding: "1.25rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
          <div>
            <h2 style={{ fontSize: "1.1rem", fontWeight: 700, margin: 0, display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <TrendingUp size={18} color="#10b981" />
              Comparative Policy Performance (Rigorous Counterfactual Evaluation)
            </h2>
            <p style={{ fontSize: "0.8rem", color: "#64748b", margin: "0.25rem 0 0" }}>
              Evaluated on {engineLimit} engines from {selectedDataset} under constrained depot capacity ({numBays} bays, {serviceDuration} cycles service lead-time).
            </p>
          </div>
        </div>

        {loadingSimulation ? (
          <div style={{ textAlign: "center", padding: "2rem", color: "#64748b" }}>
            Computing 4-policy constrained lifecycle simulation...
          </div>
        ) : comparisonMetrics.length > 0 ? (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.875rem", textAlign: "left" }}>
              <thead>
                <tr style={{ borderBottom: "2px solid #e2e8f0", color: "#475569" }}>
                  <th style={{ padding: "0.6rem 0.75rem" }}>Dispatch Policy</th>
                  <th style={{ padding: "0.6rem 0.75rem" }}>Total Fleet Cost</th>
                  <th style={{ padding: "0.6rem 0.75rem" }}>Failures Incurred</th>
                  <th style={{ padding: "0.6rem 0.75rem" }}>Serviced Engines</th>
                  <th style={{ padding: "0.6rem 0.75rem" }}>Bay Utilization</th>
                  <th style={{ padding: "0.6rem 0.75rem" }}>Mean Queue Wait</th>
                  <th style={{ padding: "0.6rem 0.75rem" }}>Max Queue Wait</th>
                  <th style={{ padding: "0.6rem 0.75rem" }}>Status & Recommendation</th>
                </tr>
              </thead>
              <tbody>
                {comparisonMetrics.map((m, idx) => {
                  const isChampion = m.policy === "RISK_AWARE" || idx === 0;
                  return (
                    <tr
                      key={m.policy}
                      style={{
                        borderBottom: "1px solid #f1f5f9",
                        backgroundColor: isChampion ? "#f0fdf4" : "transparent",
                      }}
                    >
                      <td style={{ padding: "0.6rem 0.75rem", fontWeight: 700 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                          {m.policy}
                          {isChampion && (
                            <span style={{ backgroundColor: "#dcfce7", color: "#166534", fontSize: "0.7rem", padding: "0.1rem 0.4rem", borderRadius: "9999px", fontWeight: 700 }}>
                              Champion
                            </span>
                          )}
                        </div>
                      </td>
                      <td style={{ padding: "0.6rem 0.75rem", fontWeight: 700, color: isChampion ? "#15803d" : "#0f172a" }}>
                        {m.total_fleet_cost.toFixed(2)}
                      </td>
                      <td style={{ padding: "0.6rem 0.75rem", color: m.failure_count > 0 ? "#dc2626" : "#16a34a", fontWeight: 700 }}>
                        {m.failure_count}
                      </td>
                      <td style={{ padding: "0.6rem 0.75rem" }}>{m.serviced_count} / {m.total_engines_evaluated}</td>
                      <td style={{ padding: "0.6rem 0.75rem" }}>{m.bay_utilization_pct}%</td>
                      <td style={{ padding: "0.6rem 0.75rem" }}>{m.mean_queue_wait_cycles} cyc</td>
                      <td style={{ padding: "0.6rem 0.75rem" }}>{m.max_queue_wait_cycles} cyc</td>
                      <td style={{ padding: "0.6rem 0.75rem", fontSize: "0.75rem", color: isChampion ? "#166534" : "#64748b" }}>
                        {m.operational_recommendation}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>
    </div>
  );
};
