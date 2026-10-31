"""FlairGuard AI: Generate Official Single-Slide Round 1 Submission for Tata Elxsi Teliport S4.

Key Design Principles:
- Single-slide PDF (Page count = 1).
- Distinctive focus: Reliable predictive-maintenance decisions under imperfect telemetry.
- Preserves official Teliport and Tata Elxsi logos from the provided template.
- Adheres strictly to evidence integrity (no claims of physical repair, commercial savings, or gate superiority).
- Retains tuned point-RUL policy as validated champion.
- Clearly states verified versus planned capabilities.
"""
from pathlib import Path
import pptx
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE
import comtypes.client
import fitz  # PyMuPDF

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT.parent.parent / "1790163819038-Teliport S4_Case Study and Submission Template" / "Teliport S4_Submission Template.pptx"
PPTX_OUT = ROOT.parent.parent / "1790163819038-Teliport S4_Case Study and Submission Template" / "FlairGuard_Round1_SingleSlide_Submission.pptx"
PDF_OUT = PPTX_OUT.with_suffix(".pdf")
IMAGE_OUT = ROOT / "results" / "singleslide_preview.png"

# Palette
DARK_NAVY = RGBColor(16, 44, 87)       # #102C57
TEAL_ACCENT = RGBColor(15, 118, 110)   # #0F766E
TEXT_BODY = RGBColor(31, 41, 55)       # #1F2937
WHITE = RGBColor(255, 255, 255)
CARD_BG = RGBColor(248, 250, 252)      # #F8FAFC
CARD_BORDER = RGBColor(203, 213, 225)  # #CBD5E1


def create_single_slide_submission():
    prs = pptx.Presentation(TEMPLATE_PATH)
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    # In the template, Slide 2 contains the official Teliport S4 and Tata Elxsi logos.
    # We want exactly ONE slide. So we delete Slide 1, leaving Slide 2 as our sole slide.
    rId_slide1 = prs.slides._sldIdLst[0].rId
    prs.part.drop_rel(rId_slide1)
    del prs.slides._sldIdLst[0]

    slide = prs.slides[0]

    # Clean up default placeholder text boxes while preserving picture logos
    for shape in list(slide.shapes):
        if shape.has_text_frame:
            # Remove default empty title and content placeholders
            sp_elem = shape.element
            sp_elem.getparent().remove(sp_elem)

    # Verify logos are present
    print(f"Preserved shapes on slide: {len(slide.shapes)}")

    # --- Header Area (between logos) ---
    header_box = slide.shapes.add_textbox(Inches(2.40), Inches(0.10), Inches(8.80), Inches(0.95))
    tf = header_box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0

    # Line 1: Track & Case Study
    p1 = tf.paragraphs[0]
    p1.text = "CASE STUDY 1: ACTG — PREDICTIVE MAINTENANCE (SELF-HEALING MACHINES)"
    p1.font.size = Pt(9.5)
    p1.font.bold = True
    p1.font.color.rgb = TEAL_ACCENT
    p1.space_after = Pt(1)

    # Line 2: Project Title
    p2 = tf.add_paragraph()
    p2.text = "FlairGuard AI: Connected Fleet Reliability Platform"
    p2.font.size = Pt(19)
    p2.font.bold = True
    p2.font.color.rgb = DARK_NAVY
    p2.space_after = Pt(2)

    # Line 3: Core Objective & Team Details
    p3 = tf.add_paragraph()
    p3.text = "Focus: Reliable Predictive-Maintenance Decisions Under Imperfect Telemetry  |  Team: FlairGuard  |  NASA C-MAPSS Benchmark"
    p3.font.size = Pt(9.5)
    p3.font.color.rgb = TEXT_BODY

    # --- 6-Card Grid (2 Rows x 3 Columns) ---
    col_w = Inches(3.95)
    row_h = Inches(2.88)
    lefts = [Inches(0.45), Inches(4.69), Inches(8.93)]
    tops = [Inches(1.15), Inches(4.22)]

    cards_data = [
        # Row 1, Col 1
        {
            "col": 0, "row": 0,
            "title": "1. End-to-End System Architecture",
            "bullets": [
                "Closed-Loop Pipeline: Streaming Ingestion -> Quality Audit -> Causal Features -> Dual ML Engine -> Deterministic Triage -> Persistent Work Orders.",
                "Telemetry Quality First: Evaluates physical sensor envelope, flatlining, and cycle monotonicity before allowing automated decisions.",
                "Sub-10ms Latency: Lightweight non-LLM decision logic ensures deterministic execution suitable for connected fleet operations.",
                "Verified vs Planned: Ingestion, causal features, triage, and SQLite store verified in Python (67 tests). FastAPI backend and operator dashboard planned for Round 2."
            ]
        },
        # Row 1, Col 2
        {
            "col": 1, "row": 0,
            "title": "2. C-MAPSS Data & Causal Features",
            "bullets": [
                "Multi-Regime Coverage: Evaluated on NASA C-MAPSS FD001 (single condition) and FD002 (6 operating conditions across altitude/Mach).",
                "Strict Causal Features: Rolling stats (w=5, 20) computed strictly on past cycles (1 <= tau <= t). Zero lookahead bias or data leakage.",
                "Regime Normalization: K-means operating condition clustering on flight settings with cluster-level standard scaling for FD002.",
                "Target Formulation: Piecewise linear degradation target capped at 125 cycles during training; official test evaluation remains uncapped."
            ]
        },
        # Row 1, Col 3
        {
            "col": 2, "row": 0,
            "title": "3. ML Modeling & Champion Policy",
            "bullets": [
                "Model Benchmarking: Ridge, Random Forest, HistGB, and LightGBM evaluated via 5-fold group-disjoint cross-validation (zero engine leakage).",
                "Validated Champion: Tuned Point-RUL Policy remains our validated operational champion. Advanced validity gates are maintained as experimental.",
                "Empirical FD001 Score: LightGBM achieved official test MAE of 13.56 cycles, RMSE of 18.61 cycles, and NASA score of 606.02.",
                "Empirical FD002 Score: Regime-aware normalization improved FD002 test RMSE from 50.37 to 48.88 cycles under multi-operating conditions."
            ]
        },
        # Row 2, Col 1
        {
            "col": 0, "row": 1,
            "title": "4. Deterministic Triage & Work Orders",
            "bullets": [
                "Explainable Decision Rules: Non-LLM deterministic policy evaluates RUL point predictions, uncertainty bands, and anomaly persistence.",
                "Actionable Severities: Critical (RUL <= 15 cyc), High (RUL <= 35 cyc, persistence >= 2), Medium (RUL <= 55 cyc), and Nominal (RUL > 55 cyc).",
                "Persistent SQLite Store: Idempotent work orders prevent alert storms via duplicate suppression; escalates severity as wear progresses.",
                "Full Audit Trail: Immutable logging of engine ID, cycle, severity, decision rationale, and raw telemetry snapshot for regulatory review."
            ]
        },
        # Row 2, Col 2
        {
            "col": 1, "row": 1,
            "title": "5. Handling Imperfect Telemetry & Conflict",
            "bullets": [
                "Fault Separation: Explicitly separates data acquisition defects (stuck sensors, missing data, out-of-bounds values) from physical wear.",
                "Persistence Filtering: Configurable consecutive-cycle filter (K=3) reduces nominal early-life false alarms by 75% on C-MAPSS FD001.",
                "Evidence Conflict Escalation: When high anomaly persistence conflicts with optimistic RUL (> 60 cyc), ticket routes to human review.",
                "Unchecked Autonomy Guard: When sensor quality fails near maintenance thresholds, system refuses blind action and safely escalates (ESCALATE_HUMAN)."
            ]
        },
        # Row 2, Col 3
        {
            "col": 2, "row": 1,
            "title": "6. MLOps Lifecycle & Feasibility Evidence",
            "bullets": [
                "Verified Test Foundation: 67 passing unit and property tests verifying engine isolation, causal invariance, deduplication, and crash recovery.",
                "Continuous Learning: Retraining triggered on verified newly completed run-to-failure engines; promotion gated by validation criteria.",
                "Fault Isolation: Synthetic fault-injection sessions are strictly sandboxed from normal training data and operational model state.",
                "Scope Honesty: System models simulated degradation wear; does not claim physical engine repair or verified commercial cost savings."
            ]
        },
    ]

    for card in cards_data:
        left = lefts[card["col"]]
        top = tops[card["row"]]

        # Outer background card
        card_shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, col_w, row_h)
        card_shape.fill.solid()
        card_shape.fill.fore_color.rgb = CARD_BG
        card_shape.line.color.rgb = CARD_BORDER
        card_shape.line.width = Pt(1)

        # Header banner
        h_banner = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, col_w, Inches(0.32))
        h_banner.fill.solid()
        h_banner.fill.fore_color.rgb = DARK_NAVY
        h_banner.line.fill.background()
        p_h = h_banner.text_frame.paragraphs[0]
        p_h.text = card["title"]
        p_h.font.bold = True
        p_h.font.size = Pt(10)
        p_h.font.color.rgb = WHITE
        p_h.alignment = PP_ALIGN.LEFT

        # Content text box
        tb = slide.shapes.add_textbox(left + Inches(0.10), top + Inches(0.35), col_w - Inches(0.20), row_h - Inches(0.40))
        tf_c = tb.text_frame
        tf_c.word_wrap = True
        tf_c.margin_left = tf_c.margin_top = tf_c.margin_right = tf_c.margin_bottom = 0

        for idx, bullet in enumerate(card["bullets"]):
            p = tf_c.add_paragraph() if idx > 0 else tf_c.paragraphs[0]
            # Split leading label if any
            p.text = f"• {bullet}"
            p.font.size = Pt(7.8)
            p.font.color.rgb = TEXT_BODY
            p.space_after = Pt(3)

    prs.save(PPTX_OUT)
    print(f"Saved PPTX single-slide presentation to: {PPTX_OUT}")


def export_and_verify_pdf():
    # Convert PPTX to PDF via PowerPoint COM
    powerpoint = comtypes.client.CreateObject("Powerpoint.Application")
    deck = powerpoint.Presentations.Open(str(PPTX_OUT.resolve()), WithWindow=False)
    deck.SaveAs(str(PDF_OUT.resolve()), 32)  # 32 = ppSaveAsPDF
    deck.Close()
    powerpoint.Quit()

    print(f"Exported PDF to: {PDF_OUT}")

    # Inspect PDF with PyMuPDF
    doc = fitz.open(PDF_OUT)
    page_count = len(doc)
    print(f"PDF Page Count: {page_count} (Must be exactly 1)")

    if page_count != 1:
        raise ValueError(f"CRITICAL: PDF has {page_count} pages; expected exactly 1 page!")

    page = doc[0]
    pix = page.get_pixmap(dpi=150)
    IMAGE_OUT.parent.mkdir(parents=True, exist_ok=True)
    pix.save(str(IMAGE_OUT))
    print(f"Rendered PDF page 1 preview to: {IMAGE_OUT} ({pix.width}x{pix.height})")

    # Text extraction check
    text = page.get_text()
    print("\n--- Visual Verification Check ---")
    print(f"Length of extracted text: {len(text)} characters")
    required_keywords = [
        "CASE STUDY 1: ACTG — PREDICTIVE MAINTENANCE",
        "FlairGuard AI: Connected Fleet Reliability Platform",
        "Reliable Predictive-Maintenance Decisions Under Imperfect Telemetry",
        "1. End-to-End System Architecture",
        "2. C-MAPSS Data & Causal Features",
        "3. ML Modeling & Champion Policy",
        "4. Deterministic Triage & Work Orders",
        "5. Handling Imperfect Telemetry & Conflict",
        "6. MLOps Lifecycle & Feasibility Evidence",
        "Tuned Point-RUL Policy",
        "67 passing unit and property tests"
    ]
    for kw in required_keywords:
        status = "FOUND" if kw in text else "MISSING"
        print(f"  [{status}] {kw}")
        if status == "MISSING":
            raise ValueError(f"Missing required keyword in single-slide PDF: {kw}")

    print("\nVisual verification: ALL REQUIRED ELEMENTS VERIFIED PRESENT.")


if __name__ == "__main__":
    create_single_slide_submission()
    export_and_verify_pdf()

