import React, { useState } from "react";
import { MatlabView } from "./views/MatlabView";
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

export type NavTab = "fleet" | "diagnostics" | "scenario" | "scheduler" | "maintenance" | "evidence" | "reliability" | "matlab";

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<NavTab>((sessionStorage.getItem("flairguard_tab") as NavTab) || "fleet");
  const [selectedDataset, setSelectedDataset] = useState<string>(sessionStorage.getItem("flairguard_selected_dataset") || "FD002");
  const [selectedEngineId, setSelectedEngineId] = useState<number>(Number(sessionStorage.getItem("flairguard_selected_engine") || 15));
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

  React.useEffect(() => {sessionStorage.setItem("flairguard_selected_dataset",selectedDataset);sessionStorage.setItem("flairguard_selected_engine",String(selectedEngineId));}, [selectedDataset,selectedEngineId]);

  return (
    <div>
      <a className="skip-link" href="#workspace">Skip to workspace</a>
      <details className="operator-session" open><summary>Operator access</summary><label>
        Session API key <input type="password" aria-label="Operator API key"
          defaultValue={sessionStorage.getItem("flairguard_operator_key") || ""}
          onChange={(e) => sessionStorage.setItem("flairguard_operator_key",e.target.value)} />
      </label><small>Session storage only. Required for administrative actions.</small></details>
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

        <nav className="nav-tabs" aria-label="Primary navigation">
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
          <button className={`nav-tab ${activeTab === "matlab" ? "active" : ""}`} onClick={() => setActiveTab("matlab")}><ActivityIcon size={15}/> MATLAB analysis</button>
        </nav>

        <div className="header-meta">
          <div className="live-indicator">
            <div className="live-dot" />
            <span>Historical telemetry replay</span>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main id="workspace" className="main-content" tabIndex={-1}><div className="workspace-context"><span>FLEET RELIABILITY WORKSPACE</span><span>NASA C-MAPSS ? Research &amp; replay</span></div>
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
        {activeTab === "matlab" && <MatlabView />}
      </main>
    </div>
  );
};

