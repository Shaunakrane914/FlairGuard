import React, { useState } from "react";
import { FleetOverviewView } from "./views/FleetOverviewView";
import { EngineDiagnosticsView } from "./views/EngineDiagnosticsView";
import { ScenarioLabView } from "./views/ScenarioLabView";
import { FleetSchedulerView } from "./views/FleetSchedulerView";
import { MaintenanceConsoleView } from "./views/MaintenanceConsoleView";
import { ReliabilityView } from "./views/ReliabilityView";
import { EvidenceCenterView } from "./views/EvidenceCenterView";
import {
  LayoutDashboard,
  Gauge,
  Sliders,
  Warehouse,
  Wrench,
  Award,
  Zap,
  Activity as ActivityIcon,
} from "lucide-react";

export type NavTab = "fleet" | "diagnostics" | "scenario" | "scheduler" | "maintenance" | "evidence" | "reliability";

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<NavTab>((sessionStorage.getItem("flairguard_tab") as NavTab) || "fleet");
  const [selectedDataset, setSelectedDataset] = useState<string>("FD002");
  const [selectedEngineId, setSelectedEngineId] = useState<number>(15);
  const [namespace, setNamespace] = useState(sessionStorage.getItem("flairguard_namespace") || "default");
  const [highlightOrderId, setHighlightOrderId] = useState<string | null>(null);

  const handleSelectEngineForDiagnostics = (dataset: string, engineId: number) => {
    setSelectedDataset(dataset);
    setSelectedEngineId(engineId);
    setActiveTab("diagnostics");
  };

  const handleNavigateToReplay = (dataset: string, engineId: number) => {
    setSelectedDataset(dataset);
    setSelectedEngineId(engineId);
    setActiveTab("scenario");
  };

  const handleNavigateToWorkOrders = (workOrderId?: string, replayNamespace?: string) => {
    if (workOrderId) setHighlightOrderId(workOrderId);
    if (replayNamespace) {setNamespace(replayNamespace);sessionStorage.setItem("flairguard_namespace", replayNamespace);}
    setActiveTab("maintenance");
  };

  React.useEffect(() => {sessionStorage.setItem("flairguard_tab", activeTab);}, [activeTab]);

  return (
    <div>
      <label style={{display:"block",padding:"0.5rem 1rem",fontSize:"0.8rem"}}>
        Operator key (this browser session only): <input type="password" aria-label="Operator API key"
          defaultValue={sessionStorage.getItem("flairguard_operator_key") || ""}
          onChange={(e) => sessionStorage.setItem("flairguard_operator_key",e.target.value)} />
      </label>
      {/* Top Navigation Bar */}
      <header className="app-header">
        <div className="brand-section">
          <div className="brand-logo">
            <Zap size={22} color="#3b82f6" fill="#3b82f6" />
            <span>FlairGuard AI</span>
          </div>
          <span className="brand-badge">TELIPORT S4</span>
          <span className="case-study-tag">Case Study 1: Connected Fleet Reliability</span>
        </div>

        <nav className="nav-tabs">
          <button
            className={`nav-tab ${activeTab === "fleet" ? "active" : ""}`}
            onClick={() => setActiveTab("fleet")}
          >
            <LayoutDashboard size={15} /> Fleet Overview
          </button>
          <button
            className={`nav-tab ${activeTab === "diagnostics" ? "active" : ""}`}
            onClick={() => setActiveTab("diagnostics")}
          >
            <Gauge size={15} /> Diagnostics
          </button>
          <button
            className={`nav-tab ${activeTab === "scenario" ? "active" : ""}`}
            onClick={() => setActiveTab("scenario")}
          >
            <Sliders size={15} /> Scenario Lab
          </button>
          <button
            className={`nav-tab ${activeTab === "scheduler" ? "active" : ""}`}
            onClick={() => setActiveTab("scheduler")}
          >
            <Warehouse size={15} /> Depot Scheduler
          </button>
          <button
            className={`nav-tab ${activeTab === "maintenance" ? "active" : ""}`}
            onClick={() => setActiveTab("maintenance")}
          >
            <Wrench size={15} /> Maintenance
          </button>
          <button
            className={`nav-tab ${activeTab === "evidence" ? "active" : ""}`}
            onClick={() => setActiveTab("evidence")}
          >
            <Award size={15} /> Evidence Center
          </button>
          <button className={`nav-tab ${activeTab === "reliability" ? "active" : ""}`} onClick={() => setActiveTab("reliability")}>
            <ActivityIcon /> Reliability research
          </button>
        </nav>

        <div className="header-meta">
          <div className="live-indicator">
            <div className="live-dot" />
            <span>Historical telemetry replay</span>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="main-content">
        {activeTab === "fleet" && (
          <FleetOverviewView
            onSelectEngine={handleSelectEngineForDiagnostics}
            onNavigateToReplay={handleNavigateToReplay}
          />
        )}

        {activeTab === "diagnostics" && (
          <EngineDiagnosticsView
            initialDataset={selectedDataset}
            initialEngineId={selectedEngineId}
            onNavigateToReplay={handleNavigateToReplay}
          />
        )}

        {activeTab === "scenario" && (
          <ScenarioLabView
            initialDataset={selectedDataset}
            initialEngineId={selectedEngineId}
            onNavigateToWorkOrders={handleNavigateToWorkOrders}
          />
        )}

        {activeTab === "scheduler" && <FleetSchedulerView />}

        {activeTab === "maintenance" && (
          <MaintenanceConsoleView highlightOrderId={highlightOrderId} namespace={namespace} />
        )}

        {activeTab === "evidence" && <EvidenceCenterView />}
        {activeTab === "reliability" && <ReliabilityView />}
      </main>
    </div>
  );
};

