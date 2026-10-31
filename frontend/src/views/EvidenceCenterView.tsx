import React, { useState, useEffect } from "react";
import { api } from "../api/client";
import type { RetrainResult } from "../types";
import {
  Award,
  Shield,
  FileCode,
  GitBranch,
  PlayCircle,
  CheckCircle,
  XCircle,
  Terminal,
  RotateCcw,
  RefreshCw,
  Lock,
} from "lucide-react";

export const EvidenceCenterView: React.FC = () => {
  const [retrainDataset, setRetrainDataset] = useState<string>("FD001");
  const [challengerModel, setChallengerModel] = useState<string>("LightGBM");
  const [retraining, setRetraining] = useState<boolean>(false);
  const [retrainResult, setRetrainResult] = useState<RetrainResult | null>(null);
  const [rollbackNotice, setRollbackNotice] = useState<string | null>(null);

  // Dynamic Artifact Evidence States
  const [benchmarks, setBenchmarks] = useState<any[]>([]);
  const [policies, setPolicies] = useState<any[]>([]);
  const [provenance, setProvenance] = useState<any[]>([]);
  const [trainingJobs, setTrainingJobs] = useState<any[]>([]);
  const [evidenceLoading, setEvidenceLoading] = useState<boolean>(true);

  const loadEvidence = async () => {
    setEvidenceLoading(true);
    try {
      const [b, p, prov, jobs] = await Promise.all([
        api.getEvidenceBenchmarks(),
        api.getEvidencePolicies(),
        api.getEvidenceProvenance(),
        api.getTrainingJobs(10),
      ]);
      setBenchmarks(b);
      setPolicies(p);
      setProvenance(prov);
      setTrainingJobs(jobs);
    } catch (err) {
      console.error("Failed to load evidence:", err);
    } finally {
      setEvidenceLoading(false);
    }
  };

  useEffect(() => {
    loadEvidence();
  }, []);

  const handleRetrain = async () => {
    setRetraining(true);
    setRetrainResult(null);
    setRollbackNotice(null);
    try {
      const res = await api.retrainModel(retrainDataset, challengerModel);
      setRetrainResult(res);
      await loadEvidence();
    } catch (err: any) {
      alert("Retraining failed: " + err.message);
    } finally {
      setRetraining(false);
    }
  };

  const handleRollback = async () => {
    try {
      const res = await api.rollbackModel(retrainDataset);
      setRollbackNotice(res.message);
      setRetrainResult(null);
      await loadEvidence();
    } catch (err: any) {
      alert("Rollback failed: " + err.message);
    }
  };

  const fd001Benchmarks = benchmarks.filter((b) => b.dataset === "FD001");
  const fd002Benchmarks = benchmarks.filter((b) => b.dataset === "FD002");

  return (
    <div>
      {/* Evidence Center Header */}
      <div className="panel">
        <div className="panel-header">
          <div className="panel-title">
            <Award size={22} color="var(--accent-purple)" /> Model Verification & Scientific Evidence Center
          </div>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <span className="badge badge-nominal">
              <Shield size={12} /> Artifact-Backed Truth
            </span>
            <button className="btn btn-secondary btn-sm" onClick={loadEvidence} disabled={evidenceLoading}>
              <RefreshCw size={12} className={evidenceLoading ? "animate-spin" : ""} /> Refresh
            </button>
          </div>
        </div>
        <p style={{ fontSize: "0.825rem", color: "var(--text-secondary)", lineHeight: 1.6 }}>
          Every metric, policy cost, and model parameter below is dynamically resolved from frozen disk artifacts
          (<code>independent_score.json</code>, <code>selection.json</code>, and <code>policy_costs.csv</code>).
          Zero hardcoded or invented dashboard numbers.
        </p>
      </div>

      {/* Cryptographic Provenance Bar */}
      {provenance.length > 0 && (
        <div
          style={{
            background: "var(--bg-secondary)",
            padding: "0.85rem 1.25rem",
            borderRadius: "var(--radius-md)",
            border: "1px solid var(--border)",
            marginBottom: "1.5rem",
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
            gap: "1rem",
            fontSize: "0.78rem",
          }}
        >
          {provenance.map((pr) => (
            <div key={pr.dataset}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginBottom: "0.2rem" }}>
                <Lock size={13} color="var(--accent-cyan)" />
                <strong>{pr.dataset} Protocol Signature ({pr.run_id})</strong>
              </div>
              <div className="font-mono" style={{ color: "var(--text-muted)", fontSize: "0.72rem" }}>
                Protocol: {pr.protocol_hash.slice(0, 16)}...
              </div>
              <div className="font-mono" style={{ color: "var(--text-muted)", fontSize: "0.72rem" }}>
                Bundle SHA: {pr.bundle_sha256.slice(0, 16)}...
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Benchmark Tables */}
      <div className="grid-2">
        {/* Table 1: FD001 Benchmark */}
        <div className="panel">
          <div className="panel-header">
            <div className="panel-title">
              <FileCode size={18} color="var(--accent-blue)" /> NASA FD001 Benchmarks (from independent_score.json)
            </div>
            <span className="badge badge-blue">Evaluated Split</span>
          </div>
          <div className="data-table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Model Algorithm</th>
                  <th>MAE</th>
                  <th>RMSE</th>
                  <th>NASA Score</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {fd001Benchmarks.length === 0 ? (
                  <tr><td colSpan={5} style={{ textAlign: "center", color: "var(--text-muted)" }}>Loading evidence...</td></tr>
                ) : (
                  fd001Benchmarks.map((b) => (
                    <tr
                      key={b.model_name}
                      style={{
                        background: b.model_name === "LightGBM" ? "rgba(16, 185, 129, 0.1)" : undefined,
                      }}
                    >
                      <td><strong>{b.model_name}</strong></td>
                      <td className="font-mono">{b.mae.toFixed(2)}</td>
                      <td className="font-mono">{b.rmse.toFixed(2)}</td>
                      <td className="font-mono">{b.nasa_score?.toFixed(1) ?? "—"}</td>
                      <td>
                        <span className={`badge ${b.model_name === "LightGBM" ? "badge-nominal" : "badge-neutral"}`}>
                          {b.status}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Table 2: FD002 Multi-Regime Benchmark */}
        <div className="panel">
          <div className="panel-header">
            <div className="panel-title">
              <GitBranch size={18} color="var(--accent-cyan)" /> NASA FD002 Benchmarks (from selection.json)
            </div>
            <span className="badge badge-blue">5-Fold OOF Validation</span>
          </div>
          <div className="data-table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Model Architecture</th>
                  <th>Validation MAE</th>
                  <th>Validation RMSE</th>
                  <th>PHM08 Score</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {fd002Benchmarks.length === 0 ? (
                  <tr><td colSpan={5} style={{ textAlign: "center", color: "var(--text-muted)" }}>Loading evidence...</td></tr>
                ) : (
                  fd002Benchmarks.map((b) => (
                    <tr
                      key={b.model_name}
                      style={{
                        background: b.model_name === "RegimeLightGBM" ? "rgba(16, 185, 129, 0.1)" : undefined,
                      }}
                    >
                      <td><strong>{b.model_name}</strong></td>
                      <td className="font-mono">{b.mae.toFixed(2)}</td>
                      <td className="font-mono">{b.rmse.toFixed(2)}</td>
                      <td className="font-mono">{b.nasa_score?.toFixed(1) ?? "—"}</td>
                      <td>
                        <span className={`badge ${b.model_name === "RegimeLightGBM" ? "badge-nominal" : "badge-neutral"}`}>
                          {b.status}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Policy Economics & Decision Matrix */}
      <div className="panel">
        <div className="panel-header">
          <div className="panel-title">
            <Award size={18} color="var(--accent-green)" /> Decision Policy Comparative Economics (from policy_costs.csv)
          </div>
          <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
            Normalized cost per engine across all evaluated scenarios
          </span>
        </div>

        <div className="data-table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Dataset</th>
                <th>Decision Policy</th>
                <th>Mean Cost / Engine</th>
                <th>Failure Rate</th>
                <th>Inspection Rate</th>
                <th>Wasted Cycles</th>
                <th>Scientific Finding</th>
                <th>Governance Status</th>
              </tr>
            </thead>
            <tbody>
              {policies.length === 0 ? (
                <tr><td colSpan={8} style={{ textAlign: "center", color: "var(--text-muted)" }}>Loading policy ledgers...</td></tr>
              ) : (
                policies.map((p, idx) => (
                  <tr
                    key={`${p.dataset}-${p.policy}-${idx}`}
                    style={{
                      background: p.policy === "POINT" ? "rgba(16, 185, 129, 0.08)" : undefined,
                    }}
                  >
                    <td><span className="badge badge-blue">{p.dataset}</span></td>
                    <td><strong>{p.policy}</strong></td>
                    <td className="font-mono"><strong>{p.mean_cost_per_engine.toFixed(3)}</strong></td>
                    <td className="font-mono">{p.failure_rate_pct.toFixed(2)}%</td>
                    <td className="font-mono">{p.inspection_rate_pct.toFixed(2)}%</td>
                    <td className="font-mono">{p.mean_wasted_cycles.toFixed(2)}</td>
                    <td style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>{p.scientific_finding}</td>
                    <td>
                      <span className={`badge ${p.governance_status.includes("Champion") ? "badge-nominal" : p.governance_status.includes("Research") || p.governance_status.includes("Negative") ? "badge-warning" : "badge-neutral"}`}>
                        {p.governance_status}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Real MLOps Retraining & Challenger Promotion Lab */}
      <div className="panel">
        <div className="panel-header">
          <div className="panel-title">
            <Terminal size={18} color="var(--accent-blue)" /> Supervised Retraining & Model Governance Pipeline
          </div>
        </div>
        <p style={{ fontSize: "0.825rem", color: "var(--text-secondary)", marginBottom: "1.25rem" }}>
          Trains genuine scikit-learn / LightGBM models on labeled arrivals, evaluates on strictly held-out validation engines,
          logs actual metrics to MLflow, and executes atomic serving hot-reload only when beating champion threshold (&gt;2.0%).
        </p>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "1rem",
            background: "var(--bg-secondary)",
            padding: "1rem",
            borderRadius: "var(--radius-md)",
            border: "1px solid var(--border)",
            marginBottom: "1rem",
            flexWrap: "wrap",
          }}
        >
          <div>
            <label style={{ fontSize: "0.75rem", color: "var(--text-muted)", display: "block" }}>
              Target Dataset
            </label>
            <select
              className="select-control"
              value={retrainDataset}
              onChange={(e) => setRetrainDataset(e.target.value)}
            >
              <option value="FD001">FD001 (Single-Regime)</option>
              <option value="FD002">FD002 (Multi-Regime)</option>
            </select>
          </div>

          <div>
            <label style={{ fontSize: "0.75rem", color: "var(--text-muted)", display: "block" }}>
              Challenger Architecture
            </label>
            <select
              className="select-control"
              value={challengerModel}
              onChange={(e) => setChallengerModel(e.target.value)}
            >
              <option value="LightGBM">LightGBM Regressor (Tuned Leaves & Trees)</option>
              <option value="HistGradientBoosting">HistGradientBoosting Regressor</option>
              <option value="RandomForest">Random Forest Regressor</option>
              <option value="Ridge">Linear Ridge (alpha=100.0)</option>
            </select>
          </div>

          <div style={{ marginLeft: "auto", display: "flex", gap: "0.5rem" }}>
            <button
              className="btn btn-primary"
              onClick={handleRetrain}
              disabled={retraining}
            >
              <PlayCircle size={15} /> {retraining ? "Fitting & Evaluating..." : "Train Challenger & Run Gate"}
            </button>
            <button
              className="btn btn-secondary"
              onClick={handleRollback}
              title="Restore previous serving champion"
            >
              <RotateCcw size={14} /> Rollback
            </button>
          </div>
        </div>

        {rollbackNotice && (
          <div
            style={{
              background: "rgba(59, 130, 246, 0.15)",
              border: "1px solid rgba(59, 130, 246, 0.3)",
              color: "#60a5fa",
              padding: "0.85rem",
              borderRadius: "var(--radius-md)",
              fontSize: "0.825rem",
              marginBottom: "1rem",
            }}
          >
            {rollbackNotice}
          </div>
        )}

        {/* Real Retraining Outcome */}
        {retrainResult && (
          <div
            style={{
              background: retrainResult.promoted_to_champion
                ? "rgba(16, 185, 129, 0.15)"
                : "rgba(245, 158, 11, 0.15)",
              border: `1px solid ${
                retrainResult.promoted_to_champion ? "rgba(16, 185, 129, 0.3)" : "rgba(245, 158, 11, 0.3)"
              }`,
              padding: "1.25rem",
              borderRadius: "var(--radius-md)",
              fontSize: "0.85rem",
              marginBottom: "1.5rem",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
              {retrainResult.promoted_to_champion ? (
                <CheckCircle size={18} color="var(--accent-green)" />
              ) : (
                <XCircle size={18} color="var(--accent-amber)" />
              )}
              <strong>{retrainResult.message}</strong>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "1rem", marginTop: "0.75rem" }}>
              <div>
                <span style={{ color: "var(--text-muted)" }}>Champion Previous RMSE:</span>
                <div className="font-mono">{retrainResult.previous_rmse.toFixed(2)} cycles</div>
              </div>
              <div>
                <span style={{ color: "var(--text-muted)" }}>Challenger Actual RMSE:</span>
                <div className="font-mono">{retrainResult.new_rmse.toFixed(2)} cycles</div>
              </div>
              <div>
                <span style={{ color: "var(--text-muted)" }}>Measured Improvement:</span>
                <div className="font-mono" style={{ color: retrainResult.improvement_pct > 0 ? "var(--accent-green)" : "var(--accent-amber)" }}>
                  {retrainResult.improvement_pct.toFixed(2)}%
                </div>
              </div>
              <div>
                <span style={{ color: "var(--text-muted)" }}>Serving Status:</span>
                <div>
                  <span className={`badge ${retrainResult.promoted_to_champion ? "badge-nominal" : "badge-warning"}`}>
                    {retrainResult.promoted_to_champion ? "SERVING ATOMICALLY UPDATED" : "CHAMPION RETAINED"}
                  </span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* SQLite Persistent Training Jobs Ledger */}
        {trainingJobs.length > 0 && (
          <div>
            <h4 style={{ fontSize: "0.9rem", marginBottom: "0.5rem", color: "var(--text-secondary)" }}>
              Durable Training Jobs Ledger (SQLite <code>training_jobs</code>)
            </h4>
            <div className="data-table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Job ID</th>
                    <th>Dataset</th>
                    <th>Challenger</th>
                    <th>Status</th>
                    <th>Gate Passed</th>
                    <th>Promoted</th>
                    <th>Challenger RMSE</th>
                    <th>Timestamp</th>
                  </tr>
                </thead>
                <tbody>
                  {trainingJobs.map((j) => (
                    <tr key={j.job_id}>
                      <td className="font-mono"><strong>{j.job_id}</strong></td>
                      <td><span className="badge badge-blue">{j.dataset}</span></td>
                      <td className="font-mono">{j.challenger_algorithm}</td>
                      <td>
                        <span className={`badge ${j.status === "COMPLETED" ? "badge-nominal" : j.status === "FAILED" ? "badge-critical" : "badge-warning"}`}>
                          {j.status}
                        </span>
                      </td>
                      <td>{j.gate_passed ? "Yes" : "No"}</td>
                      <td>
                        <span className={`badge ${j.promoted ? "badge-nominal" : "badge-neutral"}`}>
                          {j.promoted ? "PROMOTED" : "REJECTED"}
                        </span>
                      </td>
                      <td className="font-mono">{j.new_rmse ? j.new_rmse.toFixed(2) : "—"}</td>
                      <td className="font-mono" style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                        {new Date(j.created_at).toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
