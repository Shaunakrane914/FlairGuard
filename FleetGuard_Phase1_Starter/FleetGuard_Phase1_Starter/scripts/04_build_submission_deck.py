"""FlairGuard AI: Generate professional Round 1 Submission Deck for Tata Elxsi Teliport S4.

Adheres strictly to Case Study 1 evaluation criteria:
- Problem Understanding & Closed-loop Architecture
- Data Engineering & Causal Features (no data leakage)
- ML Model Selection & Real Benchmarking (Ridge, RF, HistGB, LightGBM)
- Lightweight Non-LLM Triage Agent & Automated Work Orders
- MLOps Retraining Loop & Roadmap
"""
from pathlib import Path
import pptx
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT.parent.parent / "1790163819038-Teliport S4_Case Study and Submission Template" / "Teliport S4_Submission Template.pptx"
OUTPUT_PATH = ROOT.parent.parent / "1790163819038-Teliport S4_Case Study and Submission Template" / "FlairGuard_AI_Round1_Submission.pptx"
RESULTS_DIR = ROOT / "results"

DARK_BLUE = RGBColor(16, 44, 87)
ACCENT_BLUE = RGBColor(53, 162, 159)
TEXT_DARK = RGBColor(30, 30, 30)
WHITE = RGBColor(255, 255, 255)
LIGHT_BG = RGBColor(245, 247, 250)
BORDER_GRAY = RGBColor(218, 224, 233)


def add_header(slide, title_text, category_text="CASE STUDY 1: ACTG - PREDICTIVE MAINTENANCE"):
    """Standardized header for slide consistency."""
    # Category tag
    tag_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.4), Inches(10), Inches(0.4))
    tf_tag = tag_box.text_frame
    tf_tag.word_wrap = True
    p_tag = tf_tag.paragraphs[0]
    p_tag.text = category_text.upper()
    p_tag.font.size = Pt(10)
    p_tag.font.bold = True
    p_tag.font.color.rgb = ACCENT_BLUE

    # Title
    title_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.7), Inches(11.5), Inches(0.8))
    tf_title = title_box.text_frame
    tf_title.word_wrap = True
    p_title = tf_title.paragraphs[0]
    p_title.text = title_text
    p_title.font.size = Pt(22)
    p_title.font.bold = True
    p_title.font.color.rgb = DARK_BLUE


def add_card(slide, left, top, width, height, title, body_bullets, header_bg=DARK_BLUE):
    """Add a clean, structured information card."""
    # Outer card shape
    card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
    card.fill.solid()
    card.fill.fore_color.rgb = LIGHT_BG
    card.line.color.rgb = BORDER_GRAY
    card.line.width = Pt(1)

    # Card header box
    h_box = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, Inches(0.45))
    h_box.fill.solid()
    h_box.fill.fore_color.rgb = header_bg
    h_box.line.fill.background()
    p_h = h_box.text_frame.paragraphs[0]
    p_h.text = title
    p_h.font.bold = True
    p_h.font.size = Pt(12)
    p_h.font.color.rgb = WHITE
    p_h.alignment = PP_ALIGN.LEFT

    # Card content text
    tb = slide.shapes.add_textbox(left + Inches(0.15), top + Inches(0.5), width - Inches(0.3), height - Inches(0.6))
    tf = tb.text_frame
    tf.word_wrap = True
    for i, bullet in enumerate(body_bullets):
        p = tf.add_paragraph() if i > 0 else tf.paragraphs[0]
        p.text = f"• {bullet}"
        p.font.size = Pt(10)
        p.font.color.rgb = TEXT_DARK
        p.space_after = Pt(4)


def build_deck():
    prs = pptx.Presentation(TEMPLATE_PATH) if TEMPLATE_PATH.exists() else pptx.Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    blank_layout = prs.slide_layouts[6]

    # Clear placeholder slide 2 if present
    while len(prs.slides) > 1:
        rId = prs.slides._sldIdLst[1].rId
        prs.part.drop_rel(rId)
        del prs.slides._sldIdLst[1]

    # --- SLIDE 1: Title Slide ---
    slide1 = prs.slides[0]
    for shape in list(slide1.shapes):
        if shape.has_text_frame and "Case Study" in shape.text_frame.text:
            shape.text_frame.text = "Case Study 1: ACTG — Predictive Maintenance"
        elif shape.has_text_frame and "Team" in shape.text_frame.text:
            shape.text_frame.text = "FlairGuard AI: Closed-Loop Self-Healing Telemetry\nTata Elxsi Teliport S4"

    # --- SLIDE 2: System Architecture & Workflow ---
    s2 = prs.slides.add_slide(blank_layout)
    add_header(s2, "End-to-End System Architecture: Closed-Loop Fleet Maintenance")
    
    add_card(s2, Inches(0.8), Inches(1.6), Inches(2.7), Inches(5.3), "1. Data Engineering", [
        "NASA C-MAPSS Telemetry Ingestion (21 Sensors + 3 Settings).",
        "Strict causality: Group-wise rolling means (w=5, 20) with no future lookahead.",
        "Engine ID isolation: 80/20 train/validation disjoint split.",
        "Zero-variance sensor filtering (sensors 1, 5, 10, 16, 18, 19 in FD001)."
    ])
    add_card(s2, Inches(3.7), Inches(1.6), Inches(2.7), Inches(5.3), "2. Predictive ML Engine", [
        "Dual-engine approach: Degradation Anomaly Detection + RUL Regression.",
        "Piecewise Linear RUL Target: Capped at 125 cycles (healthy vs wear phases).",
        "Benchmarked 4 Models: Ridge, Random Forest, HistGradientBoosting, LightGBM.",
        "Validation-only selection: Official NASA test set evaluated strictly once."
    ])
    add_card(s2, Inches(6.6), Inches(1.6), Inches(2.7), Inches(5.3), "3. Non-LLM Triage Agent", [
        "Lightweight, deterministic rule engine running with sub-millisecond latency.",
        "Risk matrix: Combines RUL prediction + anomaly persistence.",
        "Automated Severity Assignment: P1 Critical (RUL < 15), P2 High (15-30), P3 Medium (30-50).",
        "Generates CMMS work orders with duplicate suppression & audit logs."
    ])
    add_card(s2, Inches(9.5), Inches(1.6), Inches(2.9), Inches(5.3), "4. MLOps & Continuous Loop", [
        "Experiment tracking: MAE, RMSE, and NASA PHM08 asymmetric loss.",
        "Automated retraining trigger on fleet data distribution drift.",
        "Human-in-the-Loop exception handling for borderline confidence.",
        "Modular architecture ready for multi-regime scaling (FD002–FD004)."
    ])

    # --- SLIDE 3: Data Engineering & Feature Integrity ---
    s3 = prs.slides.add_slide(blank_layout)
    add_header(s3, "Data Engineering: Causal Integrity & Leakage Prevention")

    add_card(s3, Inches(0.8), Inches(1.6), Inches(5.6), Inches(5.3), "Causal Feature Engineering Principles", [
        "Elimination of Lookahead Bias: In operational fleets, future cycles do not exist. Features at cycle 't' are computed strictly from historical cycles (1 to t) for that engine.",
        "Causal Rolling Statistics: Rolling window aggregations (w=5, 20) capture degradation acceleration without leaking future engine state.",
        "Group-Disjoint Splits: Standard random row splitting causes severe engine data leakage. FlairGuard groups strictly by engine_id (80 fit / 20 validation engines).",
        "Defensive Ingestion: Validates monotonic cycles, schema completeness, and verifies non-negative finite telemetry across all engines."
    ])
    add_card(s3, Inches(6.8), Inches(1.6), Inches(5.6), Inches(5.3), "Physics-Informed Preprocessing", [
        "Piecewise Linear Degradation: Real turbofans do not degrade linearly from day one. Wear initiates after initial cycles; RUL target is capped at 125 cycles during training.",
        "Regime & Sensor Invariance: Flat sensors with negligible variance in single-operating conditions are pruned to prevent ill-conditioned covariance matrices in linear models.",
        "Uncapped Official Testing: Test ground truth remains unclipped (evaluating up to 140+ cycles) to ensure honest, unadulterated NASA benchmark metrics.",
        "Automated Property Testing: 8 pytest unit tests enforce strict causality, engine isolation, and reproducible metrics."
    ])

    # --- SLIDE 4: ML Benchmarking & Empirical Results ---
    s4 = prs.slides.add_slide(blank_layout)
    add_header(s4, "Empirical ML Benchmarking on NASA C-MAPSS FD001")

    # Add results table
    table_shape = s4.shapes.add_table(5, 4, Inches(0.8), Inches(1.6), Inches(6.0), Inches(2.4))
    table = table_shape.table
    table.columns[0].width = Inches(2.2)
    table.columns[1].width = Inches(1.2)
    table.columns[2].width = Inches(1.2)
    table.columns[3].width = Inches(1.4)

    headers = ["Model", "FD001 MAE", "FD001 RMSE", "NASA PHM08 Score"]
    for col_idx, h in enumerate(headers):
        cell = table.cell(0, col_idx)
        cell.text = h
        cell.fill.solid()
        cell.fill.fore_color.rgb = DARK_BLUE
        for p in cell.text_frame.paragraphs:
            p.font.bold = True
            p.font.size = Pt(10)
            p.font.color.rgb = WHITE

    rows_data = [
        ["Ridge (L2 Baseline)", "15.16", "19.63", "686.84"],
        ["Random Forest", "13.95", "19.35", "768.57"],
        ["HistGradientBoosting", "13.71", "18.69", "618.46"],
        ["LightGBM (Selected)", "13.56", "18.61", "606.02"],
    ]
    for row_idx, r in enumerate(rows_data, start=1):
        for col_idx, val in enumerate(r):
            cell = table.cell(row_idx, col_idx)
            cell.text = val
            for p in cell.text_frame.paragraphs:
                p.font.size = Pt(10)
                if row_idx == 4:
                    p.font.bold = True
                    p.font.color.rgb = DARK_BLUE

    # Add insight box below table
    add_card(s4, Inches(0.8), Inches(4.3), Inches(6.0), Inches(2.6), "Benchmark Analysis & Model Selection", [
        "LightGBM achieved the best overall performance with MAE of 13.56 cycles, RMSE of 18.61 cycles, and lowest NASA Score of 606.02.",
        "NASA PHM08 Metric: Heavily penalizes late predictions (predicting engine will survive longer than it does). LightGBM minimized catastrophic late failures.",
        "Zero Test Peeking: Selection was governed entirely by held-out validation engine scores; official test set was evaluated strictly once for final reporting."
    ])

    # Add Plot image on right
    chart_path = RESULTS_DIR / "benchmark_metrics_comparison.png"
    if chart_path.exists():
        s4.shapes.add_picture(str(chart_path), Inches(7.1), Inches(1.6), width=Inches(5.4))

    # --- SLIDE 5: Lightweight Triage Agent & Action Execution ---
    s5 = prs.slides.add_slide(blank_layout)
    add_header(s5, "Lightweight Non-LLM Triage Agent & Closed-Loop Actions")

    add_card(s5, Inches(0.8), Inches(1.6), Inches(5.6), Inches(5.3), "Deterministic Decision Logic (No LLM Required)", [
        "Why Non-LLM? Telemetry decision loops require sub-second deterministic reliability, zero hallucination risk, and strict auditability under regulatory standards.",
        "Multi-Tier Severity Triage:\n  • Critical (P1): RUL <= 15 cycles or persistent high-magnitude sensor anomaly. Generates immediate maintenance work order with expedited parts routing.\n  • High (P2): 15 < RUL <= 30 cycles. Schedules priority servicing within 48 hours.\n  • Medium (P3): 30 < RUL <= 50 cycles. Alerts fleet maintenance planner for routine scheduling.\n  • Nominal (P4): RUL > 50 cycles. Continuous monitoring status.",
        "Work Order Deduplication: Prevents alert flooding by maintaining active work order hash states per engine."
    ])

    add_card(s5, Inches(6.8), Inches(1.6), Inches(5.6), Inches(5.3), "Human-in-the-Loop & Auditability", [
        "Automated CMMS Work Order Schema: Generates structured JSON/PDF work order containing engine ID, current cycle, predicted RUL, primary degrading sensor, and assigned technician role.",
        "Exception Escalation: When anomaly detector flags high divergence but regression predicts healthy RUL (model conflict), the agent escalates to senior reliability engineers for manual inspection.",
        "Audit Trail: Complete decision logs recorded with timestamp, model version, and exact input telemetry snapshot for full traceability.",
        "Closed-Loop Resolution: Fleet supervisor confirms or closes work order, providing ground truth feedback to the MLOps retraining pool."
    ])

    # --- SLIDE 6: MLOps, Retraining Trigger & Multi-Regime Scaling ---
    s6 = prs.slides.add_slide(blank_layout)
    add_header(s6, "MLOps Architecture & Multi-Regime Scaling Strategy")

    add_card(s6, Inches(0.8), Inches(1.6), Inches(5.6), Inches(5.3), "MLOps Pipeline & Continuous Retraining", [
        "Model Registry & Versioning: Tracks candidate model weights, hyperparameters, and experiment artifacts across iterations.",
        "Drift Monitoring: Monitors Kolmogorov-Smirnov test statistics on incoming sensor streams against baseline distributions.",
        "Automated Retraining Trigger: Automatically initiates retraining pipeline when:\n  • New run-to-failure engines reach maintenance completion.\n  • Feature drift score exceeds critical tolerance thresholds.\n  • Model validation error degrades past predetermined bounds.",
        "Production Serving: Lightweight serialized LightGBM artifacts deliver inference in under 5 milliseconds per telemetry snapshot."
    ])

    add_card(s6, Inches(6.8), Inches(1.6), Inches(5.6), Inches(5.3), "Roadmap for FD002–FD004 (Multi-Regime Telemetry)", [
        "FD001 vs Multi-Regime Challenge: FD001 has 1 operating condition and 1 fault mode. FD002 & FD004 have 6 operating conditions, causing sensor values to swing based on altitude/Mach rather than wear.",
        "Regime-Aware Normalization: K-Means operating condition clustering on settings (altitude, Mach, throttle) followed by cluster-specific standard scaling.",
        "Ensemble Scaling: Dual-mode degradations (HPC & fan degradation in FD003/FD004) handled via multi-head gradient boosting or temporal sequence models (GRU/LSTM).",
        "Interactive Monitoring UI: Streamlit fleet dashboard for real-time fleet health visibility and work-order management (Round 2 PoC)."
    ])

    prs.save(OUTPUT_PATH)
    print(f"Professional Round 1 Presentation saved successfully to:\n{OUTPUT_PATH}")


if __name__ == "__main__":
    build_deck()

