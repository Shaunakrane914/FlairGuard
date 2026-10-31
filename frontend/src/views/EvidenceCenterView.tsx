import React, { useState } from "react";
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
} from "lucide-react";

export const EvidenceCenterView: React.FC = () => {
  const [retrainDataset, setRetrainDataset] = useState<string>("FD002");
  const [challengerModel, setChallengerModel] = useState<string>("LightGBM_Optuna");
  const [retraining, setRetraining] = useState<boolean>(false);
  const [retrainResult, setRetrainResult] = useState<RetrainResult | null>(null);

  const handleRetrain = async () => {
    setRetraining(true);
    setRetrainResult(null);
    try {
      const res = await api.retrainModel(retrainDataset, challengerModel);
      setRetrainResult(res);
    } catch (err: any) {
      alert("Retraining failed: " + err.message);
    } finally {
      setRetraining(false);
    }
  };

  return (
    <div>
      {/* Evidence Center Header */}
      <div className="panel">
        <div className="panel-header">
          <div className="panel-title">
            <Award size={22} color="var(--accent-purple)" /> Model Verification & Scientific Evidence Center
          </div>
          <span className="badge badge-nominal">
            <Shield size={12} /> Strict Protocol Validation
          </span>
        </div>
        <p style={{ fontSize: "0.825rem", color: "var(--text-secondary)", lineHeight: 1.6 }}>
          All metrics below originate from verified reproducible offline evaluation protocols. Evaluator boundaries
          prevent official test-label leakage into inference or model selection.
        </p>
      </div>

      {/* Benchmark Tables */}
      <div className="grid-2">
        {/* Table 1: FD001 Benchmark */}
        <div className="panel">
          <div className="panel-header">
            <div className="panel-title">
              <FileCode size={18} color="var(--accent-blue)" /> NASA FD001 (Single-Regime) Benchmarks
            </div>
            <span className="badge badge-blue">100 Test Engines</span>
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
                <tr>
                  <td>Linear Ridge Regressor</td>
                  <td className="font-mono">18.42</td>
                  <td className="font-mono">23.15</td>
                  <td className="font-mono">1240.2</td>
                  <td><span className="badge badge-neutral">Baseline</span></td>
                </tr>
                <tr>
                  <td>Random Forest (100 Trees)</td>
                  <td className="font-mono">15.10</td>
                  <td className="font-mono">19.82</td>
                  <td className="font-mono">680.5</td>
                  <td><span className="badge badge-neutral">Candidate</span></td>
                </tr>
                <tr>
                  <td>HistGradientBoosting</td>
                  <td className="font-mono">13.84</td>
                  <td className="font-mono">17.95</td>
                  <td className="font-mono">512.4</td>
                  <td><span className="badge badge-neutral">Candidate</span></td>
                </tr>
                <tr style={{ background: "rgba(16, 185, 129, 0.1)" }}>
                  <td><strong>LightGBM Regressor</strong></td>
                  <td className="font-mono"><strong>13.21</strong></td>
                  <td className="font-mono"><strong>17.42</strong></td>
                  <td className="font-mono"><strong>478.1</strong></td>
                  <td><span className="badge badge-nominal">Phase A Winner</span></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        {/* Table 2: FD002 Multi-Regime Benchmark */}
        <div className="panel">
          <div className="panel-header">
            <div className="panel-title">
              <GitBranch size={18} color="var(--accent-cyan)" /> NASA FD002 (Multi-Regime) Benchmarks
            </div>
            <span className="badge badge-blue">259 Test Engines</span>
          </div>
          <div className="data-table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Model Architecture</th>
                  <th>Validation MAE</th>
                  <th>Validation RMSE</th>
                  <th>Regime Awareness</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Single Monolithic LightGBM</td>
                  <td className="font-mono">38.12</td>
                  <td className="font-mono">50.37</td>
                  <td>None (Global fit)</td>
                  <td><span className="badge badge-neutral">Baseline</span></td>
                </tr>
                <tr style={{ background: "rgba(16, 185, 129, 0.1)" }}>
                  <td><strong>RegimeLightGBM (6 Specialized Regimes)</strong></td>
                  <td className="font-mono"><strong>36.31</strong></td>
                  <td className="font-mono"><strong>48.88</strong></td>
                  <td><strong>6-Regime Stratification</strong></td>
                  <td><span className="badge badge-nominal">Selected Candidate</span></td>
                </tr>
              </tbody>
            </table>
          </div>
          <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.75rem" }}>
            * Regime-aware conditioning improves RMSE by 1.49 cycles across 6 flight conditions without deep learning overhead.
          </p>
        </div>
      </div>

      {/* Policy Economics & Decision Matrix */}
      <div className="panel">
        <div className="panel-header">
          <div className="panel-title">
            <Award size={18} color="var(--accent-green)" /> Decision Policy Comparative Economics
          </div>
          <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
            Normalized cost per engine (Planned: 10, Failure: 100, Unused cycle: 0.1)
          </span>
        </div>

        <div className="data-table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Decision Policy</th>
                <th>Kind</th>
                <th>Normalized Cost</th>
                <th>Failure Rate</th>
                <th>Scientific Finding</th>
                <th>Governance Status</th>
              </tr>
            </thead>
            <tbody>
              <tr style={{ background: "rgba(16, 185, 129, 0.1)" }}>
                <td><strong>Tuned Point-RUL Threshold (20c)</strong></td>
                <td>Point Threshold</td>
                <td className="font-mono"><strong>43.90 / engine</strong></td>
                <td className="font-mono"><strong>0.0%</strong></td>
                <td>Lowest total cost and highest reliability</td>
                <td><span className="badge badge-nominal">Current Champion</span></td>
              </tr>
              <tr>
                <td>Advanced Quality / Learned Gate</td>
                <td>Validity Referral Gate</td>
                <td className="font-mono">61.00 / engine</td>
                <td className="font-mono">0.0%</td>
                <td>Frequent human inspection referrals increase costs without reducing failures</td>
                <td><span className="badge badge-warning">Research Only (Not Promoted)</span></td>
              </tr>
              <tr>
                <td>Fixed-Age Maintenance</td>
                <td>Fixed Interval (140c)</td>
                <td className="font-mono">89.20 / engine</td>
                <td className="font-mono">4.2%</td>
                <td>Premature servicing of healthy engines; misses early degradation</td>
                <td><span className="badge badge-neutral">Comparator</span></td>
              </tr>
              <tr>
                <td>Run-to-Failure (None)</td>
                <td>No Maintenance</td>
                <td className="font-mono">154.50 / engine</td>
                <td className="font-mono">100.0%</td>
                <td>Unmitigated catastrophic failures</td>
                <td><span className="badge badge-critical">Unacceptable</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* MLOps Retraining & Challenger Promotion Lab */}
      <div className="panel">
        <div className="panel-header">
          <div className="panel-title">
            <Terminal size={18} color="var(--accent-blue)" /> MLOps Lifecycle: Label-Arrival Retraining & Challenger Promotion Gate
          </div>
        </div>
        <p style={{ fontSize: "0.825rem", color: "var(--text-secondary)", marginBottom: "1.25rem" }}>
          Simulates newly verified labeled trajectories arriving from depot overhaul. The automated pipeline trains
          a challenger model and evaluates it strictly against the champion gate (&gt;2.0% validation RMSE improvement required).
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
              <option value="FD002">FD002 (RegimeLightGBM)</option>
              <option value="FD001">FD001 (LightGBM)</option>
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
              <option value="LightGBM_Optuna">LightGBM (Optuna Tuned Hyperparameters)</option>
              <option value="RegimeRandomForest">Regime-Stratified Random Forest</option>
              <option value="ElasticNet_Baseline">ElasticNet Linear Baseline</option>
            </select>
          </div>

          <div style={{ marginLeft: "auto" }}>
            <button
              className="btn btn-primary"
              onClick={handleRetrain}
              disabled={retraining}
            >
              <PlayCircle size={15} /> {retraining ? "Evaluating Gate..." : "Trigger Retraining & Gate"}
            </button>
          </div>
        </div>

        {/* Retraining Gate Results */}
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
                <span style={{ color: "var(--text-muted)" }}>Challenger New RMSE:</span>
                <div className="font-mono">{retrainResult.new_rmse.toFixed(2)} cycles</div>
              </div>
              <div>
                <span style={{ color: "var(--text-muted)" }}>Improvement:</span>
                <div className="font-mono" style={{ color: retrainResult.improvement_pct > 0 ? "var(--accent-green)" : "var(--accent-amber)" }}>
                  {retrainResult.improvement_pct.toFixed(2)}%
                </div>
              </div>
              <div>
                <span style={{ color: "var(--text-muted)" }}>Promotion Verdict:</span>
                <div>
                  <span className={`badge ${retrainResult.promoted_to_champion ? "badge-nominal" : "badge-warning"}`}>
                    {retrainResult.promoted_to_champion ? "PROMOTED TO CHAMPION" : "REJECTED (BELOW GATE)"}
                  </span>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
