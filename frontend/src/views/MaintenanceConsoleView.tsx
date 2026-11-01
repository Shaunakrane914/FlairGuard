import React, { useEffect, useState } from "react";
import { api } from "../api/client";
import type { WorkOrderRecord, AuditLogRecord } from "../types";
import {
  Wrench,
  CheckCircle,
  Clock,
  History,
  RefreshCw,
  Send,
  X,
} from "lucide-react";

interface Props {
  highlightOrderId?: string | null;
  namespace?: string;
}

export const MaintenanceConsoleView: React.FC<Props> = ({ highlightOrderId, namespace = "default" }) => {
  const [loadError,setLoadError]=useState<string|null>(null);
  const [orders, setOrders] = useState<WorkOrderRecord[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLogRecord[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedOrder, setSelectedOrder] = useState<WorkOrderRecord | null>(null);

  // Transition Modal State
  const [modalOpen, setModalOpen] = useState<boolean>(false);
  const [targetStatus, setTargetStatus] = useState<string>("ACKNOWLEDGED");
  const [transitionReason, setTransitionReason] = useState<string>("");
  const [resolutionNotes, setResolutionNotes] = useState<string>("");
  const [actionLoading, setActionLoading] = useState<boolean>(false);

  const loadData = async () => {
    setLoading(true);
    try {
      const [wo, logs] = await Promise.all([
        api.getWorkOrders(statusFilter === "ALL" ? undefined : statusFilter, namespace),
        api.getAuditLog(undefined, namespace, 50),
      ]);
      setLoadError(null);
      setOrders(wo);
      setAuditLogs(logs);

      if (highlightOrderId) {
        const found = wo.find((o) => o.work_order_id === highlightOrderId);
        if (found) setSelectedOrder(found);
      }
    } catch (err) {
      setLoadError(String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [statusFilter, namespace]);

  const openTransitionModal = (order: WorkOrderRecord, nextStatus: string) => {
    setSelectedOrder(order);
    setTargetStatus(nextStatus);
    setTransitionReason(nextStatus === "ACKNOWLEDGED" ? "Operator acknowledged historical replay order" : "");
    setResolutionNotes("");
    setModalOpen(true);
  };

  const executeTransition = async () => {
    if (!selectedOrder) return;
    setActionLoading(true);
    try {
      await api.transitionWorkOrder(
        selectedOrder.work_order_id,
        targetStatus,
        transitionReason,
        targetStatus === "CLOSED" ? resolutionNotes : undefined,
        selectedOrder.namespace
      );
      setModalOpen(false);
      await loadData();
    } catch (err: any) {
      alert("Transition failed: " + err.message);
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <div>
      <p className="scope-note">Orders belong to a replay namespace. Human review records an administrative action; it supplies no new failure label or physical repair outcome.</p>
      {loadError && <div role="alert" className="error-banner">{loadError}</div>}
      {/* Header & Status Filter Bar */}
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
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <Wrench size={22} color="var(--accent-amber)" />
          <div>
            <h2 style={{ fontSize: "1.2rem", fontWeight: 700 }}>Maintenance Work Order Console</h2>
            <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
              Persisted workflow ? Namespace: {namespace} ? Closure is not maintenance execution
            </div>
          </div>
        </div>

        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <span style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>Filter Status:</span>
          {["ALL", "OPEN", "ACKNOWLEDGED", "IN_PROGRESS", "CLOSED"].map((st) => (
            <button
              key={st}
              className={`btn btn-sm ${statusFilter === st ? "btn-primary" : "btn-secondary"}`}
              onClick={() => setStatusFilter(st)}
            >
              {st}
            </button>
          ))}
          <button className="btn btn-secondary btn-sm" onClick={loadData} disabled={loading}>
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} /> Refresh
          </button>
        </div>
      </div>

      {/* Work Orders Table */}
      <div className="panel">
        <div className="panel-header">
          <div className="panel-title">
            <Clock size={18} color="var(--accent-blue)" /> Persisted Work Orders ({orders.length})
          </div>
        </div>

        <div className="data-table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Work Order ID</th>
                <th>Engine ID</th>
                <th>Cycle</th>
                <th>Severity</th>
                <th>Priority</th>
                <th>Action Type</th>
                <th>Status</th>
                <th>Due / Review Cycle</th>
                <th>Decision Reason</th>
                <th>Workflow Actions</th>
              </tr>
            </thead>
            <tbody>
              {orders.length === 0 ? (
                <tr>
                  <td colSpan={10} style={{ textAlign: "center", color: "var(--text-muted)", padding: "2rem" }}>
                    No work orders found in SQLite with status: {statusFilter}.
                  </td>
                </tr>
              ) : (
                orders.map((wo) => (
                  <tr
                    key={wo.work_order_id}
                    style={{
                      background:
                        wo.work_order_id === highlightOrderId
                          ? "rgba(59, 130, 246, 0.15)"
                          : undefined,
                    }}
                  >
                    <td className="font-mono">
                      <strong>{wo.work_order_id.slice(0, 16)}...</strong>
                    </td>
                    <td className="font-mono">Engine #{wo.engine_id}</td>
                    <td className="font-mono">{wo.cycle}</td>
                    <td>
                      <span
                        className={`badge ${
                          wo.severity === "CRITICAL"
                            ? "badge-critical"
                            : wo.severity === "ESCALATE_HUMAN"
                            ? "badge-escalated"
                            : wo.severity === "HIGH"
                            ? "badge-warning"
                            : "badge-nominal"
                        }`}
                      >
                        {wo.severity}
                      </span>
                    </td>
                    <td>
                      <span className="badge badge-neutral">{wo.priority}</span>
                    </td>
                    <td>
                      <span style={{ fontSize: "0.78rem", fontWeight: 600 }}>{wo.action_type}</span>
                    </td>
                    <td>
                      <span
                        className={`badge ${
                          wo.status === "CLOSED"
                            ? "badge-nominal"
                            : wo.status === "IN_PROGRESS"
                            ? "badge-blue"
                            : wo.status === "ACKNOWLEDGED"
                            ? "badge-warning"
                            : "badge-critical"
                        }`}
                      >
                        {wo.status}
                      </span>
                    </td>
                    <td className="font-mono" style={{ fontSize: "0.78rem" }}>
                      {wo.due_cycle ? `Due: C${wo.due_cycle}` : wo.review_due_cycle ? `Rev: C${wo.review_due_cycle}` : "Immediate"}
                    </td>
                    <td style={{ fontSize: "0.75rem", color: "var(--text-secondary)", maxWidth: "200px" }}>
                      {wo.decision_reason}
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: "0.4rem" }}>
                        {wo.status === "OPEN" && (
                          <button
                            className="btn btn-secondary btn-sm"
                            onClick={() => openTransitionModal(wo, "ACKNOWLEDGED")}
                          >
                            Acknowledge
                          </button>
                        )}
                        {(wo.status === "OPEN" || wo.status === "ACKNOWLEDGED") && (
                          <button
                            className="btn btn-primary btn-sm"
                            onClick={() => openTransitionModal(wo, "IN_PROGRESS")}
                          >
                            Dispatch
                          </button>
                        )}
                        {wo.status === "IN_PROGRESS" && (
                          <button
                            className="btn btn-success btn-sm"
                            onClick={() => openTransitionModal(wo, "CLOSED")}
                          >
                            <CheckCircle size={12} /> Resolve
                          </button>
                        )}
                        {wo.status === "CLOSED" && (
                          <span style={{ fontSize: "0.75rem", color: "var(--accent-green)" }}>
                            Resolved
                          </span>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Immutable Audit Log Table */}
      <div className="panel">
        <div className="panel-header">
          <div className="panel-title">
            <History size={18} color="var(--accent-purple)" /> Immutable SQLite Audit Trail (Latest 50 Events)
          </div>
        </div>

        <div className="data-table-container" style={{ maxHeight: "320px", overflowY: "auto" }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Log ID</th>
                <th>Timestamp (UTC)</th>
                <th>Engine ID</th>
                <th>Cycle</th>
                <th>Event Type</th>
                <th>Associated Work Order</th>
                <th>Decision & Audit Reason</th>
              </tr>
            </thead>
            <tbody>
              {auditLogs.length === 0 ? (
                <tr>
                  <td colSpan={7} style={{ textAlign: "center", color: "var(--text-muted)", padding: "2rem" }}>
                    No audit records in the database.
                  </td>
                </tr>
              ) : (
                auditLogs.map((log) => (
                  <tr key={log.log_id}>
                    <td className="font-mono">#{log.log_id}</td>
                    <td className="font-mono" style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                      {new Date(log.timestamp).toLocaleString()}
                    </td>
                    <td className="font-mono">Engine #{log.engine_id}</td>
                    <td className="font-mono">{log.cycle}</td>
                    <td>
                      <span
                        className={`badge ${
                          log.event_type === "HUMAN_ESCALATION"
                            ? "badge-escalated"
                            : log.event_type === "WORK_ORDER_CREATED"
                            ? "badge-warning"
                            : log.event_type === "STATUS_CHANGED"
                            ? "badge-blue"
                            : "badge-neutral"
                        }`}
                      >
                        {log.event_type}
                      </span>
                    </td>
                    <td className="font-mono" style={{ fontSize: "0.75rem" }}>
                      {log.work_order_id ? `${log.work_order_id.slice(0, 14)}...` : "—"}
                    </td>
                    <td style={{ fontSize: "0.78rem" }}>{log.decision_reason}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* State Transition Modal */}
      {modalOpen && selectedOrder && (
        <div className="modal-overlay">
          <div className="modal-card">
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "1.25rem" }}>
              <h3 style={{ fontSize: "1.1rem", fontWeight: 700 }}>
                Transition Work Order to {targetStatus}
              </h3>
              <button
                onClick={() => setModalOpen(false)}
                style={{ background: "transparent", border: "none", color: "var(--text-muted)", cursor: "pointer" }}
              >
                <X size={18} />
              </button>
            </div>

            <div style={{ marginBottom: "1rem", fontSize: "0.85rem" }}>
              <div style={{ color: "var(--text-muted)", marginBottom: "0.3rem" }}>
                Target Order: <strong>{selectedOrder.work_order_id}</strong>
              </div>
              <div style={{ color: "var(--text-muted)" }}>
                Engine #{selectedOrder.engine_id} · Triggered at Cycle {selectedOrder.cycle}
              </div>
            </div>

            <div style={{ marginBottom: "1rem" }}>
              <label style={{ fontSize: "0.78rem", color: "var(--text-muted)", display: "block", marginBottom: "0.3rem" }}>
                Operator Reason
              </label>
              <textarea
                className="input-control"
                style={{ width: "100%", height: "70px", resize: "none" }}
                value={transitionReason}
                onChange={(e) => setTransitionReason(e.target.value)}
              />
            </div>

            {targetStatus === "CLOSED" && (
              <div style={{ marginBottom: "1rem" }}>
                <label style={{ fontSize: "0.78rem", color: "var(--text-muted)", display: "block", marginBottom: "0.3rem" }}>
                  Resolution Notes (Required to Close)
                </label>
                <textarea
                  className="input-control"
                  style={{ width: "100%", height: "70px", resize: "none" }}
                  value={resolutionNotes}
                  onChange={(e) => setResolutionNotes(e.target.value)}
                  placeholder="Details of physical repair, sensor swap, or clearance inspection..."
                />
              </div>
            )}

            <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem", marginTop: "1.5rem" }}>
              <button className="btn btn-secondary" onClick={() => setModalOpen(false)}>
                Cancel
              </button>
              <button className="btn btn-primary" onClick={executeTransition} disabled={actionLoading}>
                <Send size={14} /> Confirm Transition
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
