// FlairGuard AI API Client

import type {
  HealthStatus,
  DatasetInfo,
  EngineSummary,
  FleetKPIs,
  ReplayState,
  WorkOrderRecord,
  AuditLogRecord,
  ModelListing,
  RetrainResult,
} from "../types";

const BASE_URL = "/api/v1";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
    ...options,
  });

  if (!res.ok) {
    let errorDetail = `HTTP ${res.status} ${res.statusText}`;
    try {
      const errJson = await res.json();
      if (errJson.detail) {
        errorDetail = typeof errJson.detail === "string" ? errJson.detail : JSON.stringify(errJson.detail);
      }
    } catch {
      // ignore
    }
    throw new Error(errorDetail);
  }

  return res.json();
}

export const api = {
  // Health
  getHealth: () => request<HealthStatus>("/health"),

  // Fleet
  getDatasets: () => request<DatasetInfo[]>("/fleet/datasets"),
  getFleetKPIs: () => request<FleetKPIs>("/fleet/kpis"),
  getEngines: (dataset: string = "FD002", limit: number = 50) =>
    request<EngineSummary[]>(`/fleet/engines?dataset=${dataset}&limit=${limit}`),

  getEngineTrajectory: (engineId: number, dataset: string = "FD002", split: string = "test", limit: number = 150) =>
    request<{
      engine_id: number;
      dataset: string;
      split: string;
      total_cycles: number;
      trajectory: Array<Record<string, number>>;
    }>(`/fleet/engines/${engineId}/trajectory?dataset=${dataset}&split=${split}&limit=${limit}`),

  // Direct Prediction
  predict: (data: {
    dataset: string;
    engine_id: number;
    cycle: number;
    settings: number[];
    sensors: Record<string, number>;
  }) =>
    request<any>("/predict", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // Replay & Simulation Lab
  startReplay: (data: {
    dataset: string;
    engine_id: number;
    split?: string;
    policy?: string;
    namespace?: string;
  }) =>
    request<ReplayState>("/replay/start", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  stepReplay: (sessionId: string, stepCount: number = 1) =>
    request<ReplayState>(`/replay/${sessionId}/step`, {
      method: "POST",
      body: JSON.stringify({ step_count: stepCount }),
    }),

  injectFault: (
    sessionId: string,
    fault: {
      fault_type: string;
      channel: string;
      start_cycle: number;
      duration: number;
      magnitude: number;
    }
  ) =>
    request<{ message: string; active_fault: any }>(`/replay/${sessionId}/inject-fault`, {
      method: "POST",
      body: JSON.stringify(fault),
    }),

  resetReplay: (sessionId: string) =>
    request<ReplayState>(`/replay/${sessionId}/reset`, {
      method: "POST",
    }),

  // Work Orders & Maintenance
  getWorkOrders: (status?: string, namespace?: string) => {
    const params = new URLSearchParams();
    if (status) params.append("status", status);
    if (namespace) params.append("namespace", namespace);
    const qs = params.toString() ? `?${params.toString()}` : "";
    return request<WorkOrderRecord[]>(`/work-orders${qs}`);
  },

  transitionWorkOrder: (
    workOrderId: string,
    targetStatus: string,
    reason: string,
    resolutionNotes?: string,
    namespace?: string
  ) => {
    const qs = namespace ? `?namespace=${encodeURIComponent(namespace)}` : "";
    return request<WorkOrderRecord>(`/work-orders/${workOrderId}/transition${qs}`, {
      method: "POST",
      body: JSON.stringify({
        target_status: targetStatus,
        reason,
        resolution_notes: resolutionNotes,
      }),
    });
  },

  // Audit Log
  getAuditLog: (engineId?: number, namespace?: string, limit: number = 100) => {
    const params = new URLSearchParams();
    if (engineId) params.append("engine_id", engineId.toString());
    if (namespace) params.append("namespace", namespace);
    params.append("limit", limit.toString());
    return request<AuditLogRecord[]>(`/audit-log?${params.toString()}`);
  },

  // MLOps
  getModels: () => request<ModelListing[]>("/models"),
  retrainModel: (dataset: string = "FD002", challenger: string = "LightGBM") =>
    request<RetrainResult>("/models/retrain", {
      method: "POST",
      body: JSON.stringify({ dataset, challenger_model: challenger, reveal_batch_size: 15 }),
    }),
  rollbackModel: (dataset: string) =>
    request<{ status: string; message: string; rollback_details: any }>("/models/rollback", {
      method: "POST",
      body: JSON.stringify({ dataset }),
    }),
  getTrainingJobs: (limit: number = 20) =>
    request<any[]>(`/models/jobs?limit=${limit}`),

  // Scientific Evidence (Artifact-backed)
  getEvidenceBenchmarks: () =>
    request<Array<{
      model_name: string;
      dataset: string;
      split: string;
      engine_count: number;
      mae: number;
      rmse: number;
      nasa_score?: number;
      status: string;
      source_artifact: string;
    }>>("/evidence/benchmarks"),

  getEvidencePolicies: () =>
    request<Array<{
      dataset: string;
      policy: string;
      policy_kind: string;
      mean_cost_per_engine: number;
      failure_rate_pct: number;
      inspection_rate_pct: number;
      mean_wasted_cycles: number;
      scientific_finding: string;
      governance_status: string;
    }>>("/evidence/policies"),

  getEvidenceProvenance: () =>
    request<Array<{
      dataset: string;
      run_id: string;
      protocol_hash: string;
      data_sha256: string;
      bundle_sha256: string;
      selected_model: string;
      independent_evaluator_verified: boolean;
    }>>("/evidence/provenance"),
};
