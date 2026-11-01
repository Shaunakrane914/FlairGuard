// FlairGuard AI TypeScript Type Definitions

export interface HealthStatus {
  status: string;
  database_connected: boolean;
  models_loaded: string[];
  environment: string;
}

export interface DatasetInfo {
  id: string;
  description: string;
  operating_conditions: number;
  fault_modes: number;
  train_engines: number;
  test_engines: number;
  name: string;
  total_records: number;
  sensors_count: number;
}

export interface EngineSummary {
  engine_id: number;
  dataset: string;
  split: "train" | "test";
  total_cycles: number;
  last_observed_cycle: number;
  last_predicted_rul?: number | null;
  last_prediction_usable: boolean;
  current_status: string;
  active_work_order_id?: string | null;
}

export interface FleetKPIs {
  total_monitored_engines: number;
  active_work_orders: number;
  open_escalations: number;
  sensors_monitored: number;
  champion_policy: string;
}

export interface QualityDetails {
  is_valid: boolean;
  quality_code: string;
  details: Record<string, any>;
}

export interface TelemetryEvidence {
  cycle: number;
  telemetry: Record<string, number>;
  raw_telemetry?: Record<string, number>;
  is_perturbed?: boolean;
  prediction: number | null;
  usable: boolean;
  anomaly_score: number | null;
  persistence: number | null;
  decision: {
    status: string;
    event_id: string;
    work_order_id: string | null;
    severity: string;
    priority: string;
  };
  work_order_id: string | null;
  severity: string;
  action_type: string | null;
}

export interface ReplayState {
  session_id: string;
  dataset: string;
  engine_id: number;
  split: string;
  policy: string;
  current_cycle: number;
  total_trajectory_cycles: number;
  is_completed: boolean;
  active_fault?: {
    fault_type: string;
    channel: string;
    start_cycle: number;
    end_cycle: number;
    duration: number;
    magnitude: number;
  } | null;
  last_evidence?: TelemetryEvidence | null;
  active_work_order?: WorkOrderRecord | null;
}

export interface WorkOrderRecord {
  work_order_id: string;
  namespace: string;
  asset_id: string;
  engine_id: number;
  cycle: number;
  severity: "NORMAL" | "MEDIUM" | "HIGH" | "CRITICAL" | "ESCALATE_HUMAN";
  priority: "NORMAL" | "MEDIUM" | "HIGH" | "CRITICAL";
  review_required: boolean;
  status: "OPEN" | "ACKNOWLEDGED" | "IN_PROGRESS" | "CLOSED" | "CANCELLED";
  action_type: string;
  predicted_rul: number | null;
  uncertainty: number | null;
  anomaly_score: number | null;
  persistence_count: number;
  decision_reason: string;
  due_cycle: number | null;
  review_due_cycle: number | null;
  event_id: string;
  row_version: number;
  created_at: string;
  updated_at: string;
}

export interface AuditLogRecord {
  log_id: number;
  namespace: string;
  engine_id: number;
  cycle: number;
  event_type: string;
  work_order_id: string | null;
  event_id: string | null;
  decision_reason: string;
  telemetry_snapshot_json: string;
  timestamp: string;
}

export interface ModelListing {
  dataset: string;
  model_id: string;
  is_champion: boolean;
  algorithm: string;
  validation_rmse: number;
  validation_mae: number;
  nasa_score?: number;
  protocol_hash: string;
  bundle_sha256: string;
}

export interface RetrainResult {
  candidate_model: string;
  dataset: string;
  previous_rmse: number;
  new_rmse: number;
  improvement_pct: number;
  gate_passed: boolean;
  promoted_to_champion: boolean;
  message: string;
}

export interface BayState {
  bay_id: number;
  engine_id: number | null;
  cycles_remaining: number;
  status: "IDLE" | "OCCUPIED";
}

export interface QueuedEngineState {
  engine_id: number;
  dataset: string;
  requested_cycle: number;
  current_cycle: number;
  predicted_rul: number;
  uncertainty_sigma: number | null;
  urgency_score: number;
  waiting_cycles: number;
  status: string;
}

export interface FleetScheduleSnapshot {
  timestamp_cycle: number;
  num_bays: number;
  bays: BayState[];
  queue: QueuedEngineState[];
  active_policy: string;
  summary_message: string;
}

export interface SchedulingMetrics {
  policy: string;
  num_bays: number;
  service_duration: number;
  total_engines_evaluated: number;
  serviced_count: number;
  failure_count: number;
  mean_queue_wait_cycles: number;
  max_queue_wait_cycles: number;
  mean_wasted_cycles: number;
  bay_utilization_pct: number;
  total_fleet_cost: number;
  cost_breakdown: {
    failure_penalties: number;
    maintenance_executions: number;
    wasted_useful_life: number;
    queue_delays: number;
  };
  operational_recommendation: string;
}

