import React, { useState } from "react";
import { FleetOverviewView } from "./views/FleetOverviewView";
import { EngineDiagnosticsView } from "./views/EngineDiagnosticsView";
import { ScenarioLabView } from "./views/ScenarioLabView";
import { MaintenanceConsoleView } from "./views/MaintenanceConsoleView";
import { EvidenceCenterView } from "./views/EvidenceCenterView";
import {
  LayoutDashboard,
  Gauge,
  Sliders,
  Wrench,
  Award,
  Zap,
} from "lucide-react";

export type NavTab = "fleet" | "diagnostics" | "scenario" | "maintenance" | "evidence";

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<NavTab>("fleet");
  const [selectedDataset, setSelectedDataset] = useState<string>("FD002");
  const [selectedEngineId, setSelectedEngineId] = useState<number>(15);
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

  const handleNavigateToWorkOrders = (workOrderId?: string) => {
    if (workOrderId) setHighlightOrderId(workOrderId);
    setActiveTab("maintenance");
  };

  return (
    <div>
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
        </nav>

        <div className="header-meta">
          <div className="live-indicator">
            <div className="live-dot" />
            <span>Fleet Replay Live</span>
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

        {activeTab === "maintenance" && (
          <MaintenanceConsoleView highlightOrderId={highlightOrderId} />
        )}

        {activeTab === "evidence" && <EvidenceCenterView />}
      </main>
    </div>
  );
};

