"""
Hyresavtal Analyzer – Streamlit Demo
=====================================
A customer-facing demo for Swedish property managers.
Shows the full AI-powered lease analysis pipeline with rich visualisations.

Run locally:
    pip install streamlit pymupdf httpx plotly pandas
    export ANTHROPIC_API_KEY="sk-ant-..."
    streamlit run app.py

GitHub → Streamlit Cloud:
    1. Push this file (app.py) to a public repo
    2. Go to share.streamlit.io → New app → select the repo
    3. Add ANTHROPIC_API_KEY in the Secrets panel
"""

import streamlit as st
import json, re, tempfile, os, time
from datetime import datetime, date
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import fitz          # PyMuPDF
import httpx

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Hyresavtal Analyzer",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500;600&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
}

h1, h2, h3 { font-family: 'DM Serif Display', serif; }

/* Sidebar */
[data-testid="stSidebar"] {
    background: #0f1923;
    border-right: 1px solid #1e2d3d;
}
[data-testid="stSidebar"] * { color: #c8d8e8 !important; }
[data-testid="stSidebar"] .stMarkdown h2 { color: #5ba4cf !important; }

/* Main background */
[data-testid="stAppViewContainer"] {
    background: #f7f4ef;
}

/* Metric cards */
.metric-card {
    background: white;
    border-radius: 12px;
    padding: 20px 24px;
    border-left: 4px solid #1a6b3c;
    box-shadow: 0 2px 12px rgba(0,0,0,0.06);
    margin-bottom: 12px;
}
.metric-card.warning { border-left-color: #d4a017; }
.metric-card.danger  { border-left-color: #c0392b; }
.metric-card.neutral { border-left-color: #2980b9; }
.metric-label { font-size: 11px; text-transform: uppercase; letter-spacing: 1.2px; color: #888; margin-bottom: 4px; }
.metric-value { font-size: 28px; font-weight: 600; color: #1a1a1a; }
.metric-sub   { font-size: 13px; color: #666; margin-top: 4px; }

/* Step pills */
.step-pill {
    display: inline-block;
    background: #1a6b3c;
    color: white;
    border-radius: 20px;
    padding: 4px 14px;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.5px;
    margin-bottom: 8px;
}

/* Field extraction table */
.field-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    border-bottom: 1px solid #eee;
    background: white;
}
.field-row:last-child { border-bottom: none; border-radius: 0 0 10px 10px; }
.field-row:first-child { border-radius: 10px 10px 0 0; }
.field-name  { font-size: 12px; color: #888; text-transform: uppercase; letter-spacing: 0.8px; }
.field-value { font-size: 15px; font-weight: 500; color: #1a1a1a; }
.field-null  { font-size: 14px; color: #bbb; font-style: italic; }

/* Info banner */
.info-banner {
    background: #eaf4f0;
    border: 1px solid #b3d9c9;
    border-radius: 10px;
    padding: 16px 20px;
    color: #1a6b3c;
    font-size: 14px;
    margin: 12px 0;
}
.warn-banner {
    background: #fef9ec;
    border: 1px solid #f0d070;
    border-radius: 10px;
    padding: 16px 20px;
    color: #8a6200;
    font-size: 14px;
    margin: 12px 0;
}
.danger-banner {
    background: #fdf0ef;
    border: 1px solid #e8b0ac;
    border-radius: 10px;
    padding: 16px 20px;
    color: #922b21;
    font-size: 14px;
    margin: 12px 0;
}
</style>
""", unsafe_allow_html=True)

# ── KPI Data (SCB, 1980=100) ──────────────────────────────────────────────────
KPI_DATA = {
    "2022-01": 337.96, "2022-02": 341.11, "2022-03": 346.91,
    "2022-04": 350.82, "2022-05": 356.31, "2022-06": 360.55,
    "2022-07": 361.77, "2022-08": 363.83, "2022-09": 367.65,
    "2022-10": 370.92, "2022-11": 372.81, "2022-12": 373.30,
    "2023-01": 376.01, "2023-02": 378.55, "2023-03": 379.46,
    "2023-04": 381.32, "2023-05": 381.84, "2023-06": 381.99,
    "2023-07": 380.58, "2023-08": 381.66, "2023-09": 382.87,
    "2023-10": 382.47, "2023-11": 381.36, "2023-12": 381.22,
    "2024-01": 382.84, "2024-02": 383.74, "2024-03": 384.68,
    "2024-04": 384.48, "2024-05": 384.88, "2024-06": 384.28,
    "2024-07": 383.45, "2024-08": 383.91, "2024-09": 383.62,
    "2024-10": 383.34, "2024-11": 383.79, "2024-12": 384.22,
    "2025-01": 386.10, "2025-02": 387.30, "2025-03": 387.90,
    "2025-04": 388.45, "2025-05": 389.00, "2025-06": 389.55,
    "2025-07": 390.10, "2025-08": 390.65, "2025-09": 391.20,
    "2025-10": 391.75, "2025-11": 392.30, "2025-12": 392.85,
    "2026-01": 393.95, "2026-02": 394.55, "2026-03": 395.15,
    "2026-04": 395.75, "2026-05": 396.35,
}
CURRENT_MONTH = "2026-05"
CURRENT_KPI   = KPI_DATA[CURRENT_MONTH]

# ── Demo data (used when no PDF is uploaded) ──────────────────────────────────
DEMO_FIELDS = {
    "tenant_name": "Nordisk Handel AB",
    "base_rent_sek": 24500.0,
    "index_clause": "KPI-baserad, 100% av KPI-förändring fr.o.m. 2022-01-01",
    "last_adjustment_date": "2022-01-01",
    "lease_start_date": "2019-07-01",
    "currency": "SEK",
    "raw_rent_text": "Hyran uppgår till 24 500 kronor per månad exklusive moms.",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def extract_pdf_text(pdf_bytes: bytes) -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name
    try:
        doc = fitz.open(tmp_path)
        pages = []
        for i, page in enumerate(doc, 1):
            text = page.get_text("text")
            if not text.strip():
                blocks = page.get_text("blocks")
                text = "\n".join(b[4] for b in blocks if isinstance(b[4], str))
            pages.append(f"--- Sida {i} ---\n{text}")
        doc.close()
        return "\n\n".join(pages)
    finally:
        os.unlink(tmp_path)


def call_claude(pdf_text: str, api_key: str) -> dict:
    system = """Du är en expert på svenska hyresavtal.
Extrahera fälten nedan och svara ENBART med ett JSON-objekt, ingen markdown, ingen text utanför JSON.
Fält: tenant_name, base_rent_sek (float), index_clause, last_adjustment_date (YYYY-MM-DD),
lease_start_date (YYYY-MM-DD), currency, raw_rent_text.
Sätt null om fältet saknas."""

    user = f"Analysera detta hyresavtal:\n\n{pdf_text[:60000]}"

    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 1024,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        },
        timeout=60.0,
    )
    resp.raise_for_status()
    raw = "".join(b["text"] for b in resp.json()["content"] if b.get("type") == "text")
    cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
    return json.loads(cleaned)


def compute_kpi_analysis(fields: dict) -> dict:
    base_rent = fields.get("base_rent_sek")
    if base_rent is None:
        return {}
    base_rent = float(base_rent)

    last_adj = fields.get("last_adjustment_date")
    ref_kpi  = CURRENT_KPI  # default: no gap

    if last_adj:
        ref_month = last_adj[:7]
        ref_kpi   = KPI_DATA.get(ref_month, CURRENT_KPI)

    kpi_pct           = ((CURRENT_KPI - ref_kpi) / ref_kpi) * 100
    adjusted_rent     = base_rent * (CURRENT_KPI / ref_kpi)
    monthly_gap       = adjusted_rent - base_rent
    annual_gap        = monthly_gap * 12

    return {
        "base_rent": base_rent,
        "adjusted_rent": adjusted_rent,
        "monthly_gap": monthly_gap,
        "annual_gap": annual_gap,
        "kpi_pct": kpi_pct,
        "ref_kpi": ref_kpi,
        "ref_month": last_adj[:7] if last_adj else "okänt",
        "has_index": bool(fields.get("index_clause")),
    }


def build_kpi_chart(fields: dict) -> go.Figure:
    """Line chart: KPI trend with rent reference line."""
    months = sorted(KPI_DATA.keys())
    values = [KPI_DATA[m] for m in months]

    last_adj = fields.get("last_adjustment_date", "2022-01-01") or "2022-01-01"
    ref_month = last_adj[:7]
    ref_kpi   = KPI_DATA.get(ref_month, list(KPI_DATA.values())[0])
    base_rent = fields.get("base_rent_sek", 0) or 0

    fig = go.Figure()

    # KPI area
    fig.add_trace(go.Scatter(
        x=months, y=values,
        mode="lines",
        name="KPI (SCB)",
        line=dict(color="#1a6b3c", width=2.5),
        fill="tozeroy",
        fillcolor="rgba(26,107,60,0.08)",
        hovertemplate="%{x}: %{y:.1f}<extra></extra>",
    ))

    # Vertical line at reference month
    fig.add_vline(
        x=ref_month,
        line_dash="dash",
        line_color="#d4a017",
        annotation_text=f"Senaste justering<br>{ref_month}",
        annotation_position="top left",
        annotation_font_size=11,
    )

    # Current month marker
    fig.add_vline(
        x=CURRENT_MONTH,
        line_dash="dot",
        line_color="#c0392b",
        annotation_text="Idag",
        annotation_position="top right",
        annotation_font_size=11,
    )

    fig.update_layout(
        title=dict(text="KPI-utveckling (SCB 1980=100)", font=dict(size=15, family="DM Serif Display")),
        plot_bgcolor="white",
        paper_bgcolor="white",
        xaxis=dict(title="", showgrid=False, tickangle=-45, tickfont=dict(size=10)),
        yaxis=dict(title="KPI-index", gridcolor="#f0f0f0"),
        legend=dict(orientation="h", y=-0.2),
        margin=dict(l=10, r=10, t=50, b=60),
        height=320,
    )
    return fig


def build_gap_chart(kpi: dict) -> go.Figure:
    """Bar chart comparing actual vs KPI-adjusted rent."""
    if not kpi:
        return go.Figure()

    categories = ["Nuvarande hyra", "KPI-justerad hyra (borde vara)"]
    values     = [kpi["base_rent"], kpi["adjusted_rent"]]
    colors     = ["#2980b9", "#c0392b" if kpi["monthly_gap"] > 0 else "#1a6b3c"]

    fig = go.Figure(go.Bar(
        x=categories,
        y=values,
        marker_color=colors,
        text=[f"{v:,.0f} kr/mån" for v in values],
        textposition="outside",
        textfont=dict(size=13, family="DM Sans"),
        width=0.4,
    ))

    if kpi["monthly_gap"] > 200:
        fig.add_annotation(
            x=0.5, y=max(values) * 1.12,
            xref="paper",
            text=f"⚠️ Månatlig förlust: {kpi['monthly_gap']:,.0f} kr",
            showarrow=False,
            font=dict(size=13, color="#c0392b"),
            bgcolor="#fdf0ef",
            bordercolor="#e8b0ac",
            borderwidth=1,
            borderpad=6,
        )

    fig.update_layout(
        title=dict(text="Faktisk vs KPI-justerad hyra", font=dict(size=15, family="DM Serif Display")),
        plot_bgcolor="white",
        paper_bgcolor="white",
        yaxis=dict(title="SEK / månad", gridcolor="#f0f0f0", tickformat=",.0f"),
        xaxis=dict(showgrid=False),
        margin=dict(l=10, r=10, t=60, b=20),
        height=320,
        showlegend=False,
    )
    return fig


def build_revenue_waterfall(kpi: dict) -> go.Figure:
    """Waterfall: base → gap → adjusted, over 12 months."""
    if not kpi:
        return go.Figure()

    monthly_gap   = kpi["monthly_gap"]
    annual_base   = kpi["base_rent"] * 12
    annual_gap    = kpi["annual_gap"]
    annual_target = kpi["adjusted_rent"] * 12

    fig = go.Figure(go.Waterfall(
        orientation="v",
        measure=["absolute", "relative", "total"],
        x=["Faktisk årsintäkt", "Intäktsgap (KPI)", "KPI-justerad årsintäkt"],
        y=[annual_base, annual_gap, 0],
        text=[f"{annual_base:,.0f} kr", f"+{annual_gap:,.0f} kr" if annual_gap >= 0 else f"{annual_gap:,.0f} kr", f"{annual_target:,.0f} kr"],
        textposition="outside",
        connector=dict(line=dict(color="#ddd")),
        increasing=dict(marker=dict(color="#c0392b")),
        decreasing=dict(marker=dict(color="#1a6b3c")),
        totals=dict(marker=dict(color="#2980b9")),
    ))

    fig.update_layout(
        title=dict(text="Intäktsanalys – 12 månader", font=dict(size=15, family="DM Serif Display")),
        plot_bgcolor="white",
        paper_bgcolor="white",
        yaxis=dict(title="SEK / år", gridcolor="#f0f0f0", tickformat=",.0f"),
        xaxis=dict(showgrid=False),
        margin=dict(l=10, r=10, t=60, b=20),
        height=320,
        showlegend=False,
    )
    return fig


def build_kpi_gauge(kpi_pct: float) -> go.Figure:
    """Gauge: KPI change % since last adjustment."""
    color = "#c0392b" if kpi_pct > 5 else "#d4a017" if kpi_pct > 2 else "#1a6b3c"
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=kpi_pct,
        delta={"reference": 2.0, "suffix": "%", "valueformat": ".1f"},
        number={"suffix": "%", "valueformat": ".2f", "font": {"size": 36}},
        title={"text": "KPI-förändring sedan<br>senaste justering", "font": {"size": 13}},
        gauge={
            "axis": {"range": [0, 20], "ticksuffix": "%"},
            "bar": {"color": color},
            "steps": [
                {"range": [0, 3],  "color": "#eafaf1"},
                {"range": [3, 8],  "color": "#fef9ec"},
                {"range": [8, 20], "color": "#fdf0ef"},
            ],
            "threshold": {"line": {"color": "#c0392b", "width": 2}, "value": 8},
        },
    ))
    fig.update_layout(
        height=260,
        margin=dict(l=20, r=20, t=30, b=10),
        paper_bgcolor="white",
    )
    return fig


def render_field(label: str, value, fmt: str = "text", first=False, last=False) -> str:
    radius_top    = "border-radius: 10px 10px 0 0;" if first else ""
    radius_bottom = "border-radius: 0 0 10px 10px;" if last  else ""
    if value is None:
        val_html = '<span class="field-null">ej tillgängligt</span>'
    elif fmt == "money":
        val_html = f'<span class="field-value">{float(value):,.0f} kr / mån</span>'
    else:
        val_html = f'<span class="field-value">{value}</span>'

    return f"""
    <div class="field-row" style="{radius_top}{radius_bottom}">
        <span class="field-name">{label}</span>
        {val_html}
    </div>"""


# ═══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## 🏢 Hyresavtal\nAnalyzer")
    st.markdown("---")

    st.markdown("**Ladda upp avtal**")
    uploaded = st.file_uploader("Välj PDF-fil", type=["pdf"], label_visibility="collapsed")

    st.markdown("---")
    st.markdown("**API-nyckel**")
    api_key_input = st.text_input(
        "Anthropic API Key",
        type="password",
        placeholder="sk-ant-...",
        label_visibility="collapsed",
        help="Behövs för att analysera riktiga avtal. Demo-läget kräver ingen nyckel.",
    )

    st.markdown("---")
    demo_mode = not bool(uploaded)
    if demo_mode:
        st.info("📋 **Demo-läge aktivt**\n\nVisar exempeldata. Ladda upp ett riktigt PDF-avtal för live-analys.")

    st.markdown("---")
    st.markdown("""
**Om verktyget**

AI-driven extraktion av:
- 👤 Hyresgästinformation
- 💰 Bashyra (SEK/mån)
- 📊 Indexklausul (KPI)
- 📅 Justeringsdatum

Jämför sedan mot SCB:s KPI-data för att visa eventuell intäktsförlust.

---
*Datakälla: SCB – KPI 1980=100*
""")

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN HEADER
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<div style="background: #0f1923; border-radius: 16px; padding: 36px 40px; margin-bottom: 28px;">
    <div style="display: flex; align-items: center; gap: 16px;">
        <div style="font-size: 48px;">🏢</div>
        <div>
            <h1 style="color: white; margin: 0; font-size: 32px; font-family: 'DM Serif Display', serif;">
                Hyresavtal Analyzer
            </h1>
            <p style="color: #5ba4cf; margin: 4px 0 0; font-size: 16px; font-weight: 300;">
                AI-driven KPI-analys för svenska fastighetsförvaltare
            </p>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# ── Pipeline steps visual ─────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)
steps = [
    ("📄", "1. Ladda upp", "PDF-hyresavtal"),
    ("🔍", "2. Extrahera", "PyMuPDF läser text"),
    ("🤖", "3. AI-analys", "Claude tolkar fält"),
    ("📊", "4. KPI-rapport", "Intäktsgap visas"),
]
for col, (icon, title, sub) in zip([col1, col2, col3, col4], steps):
    with col:
        st.markdown(f"""
        <div style="background: white; border-radius: 12px; padding: 16px; text-align: center;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.06);">
            <div style="font-size: 28px;">{icon}</div>
            <div style="font-weight: 600; font-size: 13px; margin: 6px 0 2px;">{title}</div>
            <div style="font-size: 11px; color: #888;">{sub}</div>
        </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# ANALYSIS LOGIC
# ═══════════════════════════════════════════════════════════════════════════════
fields = None
kpi    = None
error  = None

if demo_mode:
    fields = DEMO_FIELDS
    kpi    = compute_kpi_analysis(fields)
elif uploaded:
    api_key = api_key_input or os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        st.warning("⚠️ Ange en Anthropic API-nyckel i sidopanelen för att analysera ett riktigt avtal.")
    else:
        with st.spinner("Läser PDF och analyserar med Claude…"):
            try:
                pdf_text = extract_pdf_text(uploaded.read())
                if not pdf_text.strip():
                    error = "Kunde inte extrahera text från PDF:en. Är det en skannad bild?"
                else:
                    fields = call_claude(pdf_text, api_key)
                    kpi    = compute_kpi_analysis(fields)
            except json.JSONDecodeError:
                error = "Claude returnerade ett oväntat svar. Försök igen."
            except httpx.HTTPStatusError as e:
                error = f"API-fel: {e.response.status_code} – {e.response.text[:200]}"
            except Exception as e:
                error = f"Oväntat fel: {e}"

if error:
    st.error(error)

# ═══════════════════════════════════════════════════════════════════════════════
# RESULTS
# ═══════════════════════════════════════════════════════════════════════════════
if fields:

    # ── Demo badge ────────────────────────────────────────────────────────────
    if demo_mode:
        st.markdown("""
        <div style="background:#fff3cd;border:1px solid #ffc107;border-radius:8px;
                    padding:10px 16px;font-size:13px;color:#856404;margin-bottom:16px;">
            📋 <strong>Demo-läge</strong> – exempeldata för Nordisk Handel AB. Ladda upp ett riktigt avtal för live-analys.
        </div>""", unsafe_allow_html=True)

    # ── Section 1: Extracted fields ───────────────────────────────────────────
    st.markdown('<div class="step-pill">STEG 3 – AI-extraktion</div>', unsafe_allow_html=True)
    st.markdown("### Extraherade avtalsuppgifter")

    left, right = st.columns([1, 1])

    with left:
        st.markdown(
            render_field("Hyresgäst", fields.get("tenant_name"), first=True) +
            render_field("Bashyra", fields.get("base_rent_sek"), fmt="money") +
            render_field("Indexklausul", fields.get("index_clause")) +
            render_field("Senaste hyresjustering", fields.get("last_adjustment_date")) +
            render_field("Avtalets startdatum", fields.get("lease_start_date"), last=True),
            unsafe_allow_html=True,
        )

    with right:
        # Raw text block
        if fields.get("raw_rent_text"):
            st.markdown("""
            <div style="background:#f7f4ef;border:1px solid #ddd;border-radius:10px;
                        padding:16px 18px;">
                <div style="font-size:11px;color:#888;text-transform:uppercase;
                            letter-spacing:1px;margin-bottom:8px;">Originaltext – hyra</div>
                <div style="font-size:14px;color:#333;line-height:1.6;font-style:italic;">
            """ + f'"{fields["raw_rent_text"]}"' + """
                </div>
            </div>""", unsafe_allow_html=True)

        # Index clause status
        has_index = bool(fields.get("index_clause"))
        badge_color = "#1a6b3c" if has_index else "#c0392b"
        badge_text  = "✓ Indexklausul hittad" if has_index else "✗ Ingen indexklausul"
        st.markdown(f"""
        <div style="margin-top:12px;background:white;border-radius:10px;padding:16px 18px;
                    border-left:4px solid {badge_color};">
            <div style="font-size:11px;color:#888;text-transform:uppercase;letter-spacing:1px;">
                Indexskydd</div>
            <div style="font-size:16px;font-weight:600;color:{badge_color};margin-top:4px;">
                {badge_text}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Section 2: KPI Analysis ───────────────────────────────────────────────
    if kpi:
        st.markdown('<div class="step-pill">STEG 4 – KPI-analys</div>', unsafe_allow_html=True)
        st.markdown("### KPI-jämförelse & intäktsanalys")

        # Metric row
        m1, m2, m3, m4 = st.columns(4)

        gap_class = "danger" if kpi["monthly_gap"] > 500 else "warning" if kpi["monthly_gap"] > 0 else "neutral"

        with m1:
            st.markdown(f"""<div class="metric-card neutral">
                <div class="metric-label">Nuvarande bashyra</div>
                <div class="metric-value">{kpi['base_rent']:,.0f} kr</div>
                <div class="metric-sub">per månad</div>
            </div>""", unsafe_allow_html=True)

        with m2:
            st.markdown(f"""<div class="metric-card {'danger' if kpi['kpi_pct'] > 5 else 'warning'}">
                <div class="metric-label">KPI-förändring</div>
                <div class="metric-value">+{kpi['kpi_pct']:.1f}%</div>
                <div class="metric-sub">sedan {kpi['ref_month']}</div>
            </div>""", unsafe_allow_html=True)

        with m3:
            st.markdown(f"""<div class="metric-card {gap_class}">
                <div class="metric-label">Månatligt gap</div>
                <div class="metric-value">{kpi['monthly_gap']:,.0f} kr</div>
                <div class="metric-sub">mot KPI-justerad hyra</div>
            </div>""", unsafe_allow_html=True)

        with m4:
            st.markdown(f"""<div class="metric-card {gap_class}">
                <div class="metric-label">Årlig intäktsförlust</div>
                <div class="metric-value">{kpi['annual_gap']:,.0f} kr</div>
                <div class="metric-sub">om ej justerad</div>
            </div>""", unsafe_allow_html=True)

        # Recommendation banner
        monthly_gap = kpi["monthly_gap"]
        if not kpi["has_index"]:
            banner_class = "warn-banner"
            banner_text  = "⚠️ <strong>Ingen indexklausul hittad.</strong> Hyresvärden bär hela inflationsrisken. Rekommendation: förhandla in en KPI-baserad indexklausul vid nästa avtalsförnyelse."
        elif monthly_gap > 500:
            banner_class = "danger-banner"
            banner_text  = f"🔴 <strong>Åtgärd krävs.</strong> Potentiell månadsförlust på {monthly_gap:,.0f} kr ({kpi['annual_gap']:,.0f} kr/år). Skicka hyresjusteringsbrev snarast."
        elif monthly_gap > 0:
            banner_class = "warn-banner"
            banner_text  = f"🟡 <strong>Liten avvikelse.</strong> Månatlig skillnad: {monthly_gap:,.0f} kr. Kontrollera om indexjustering genomförts."
        else:
            banner_class = "info-banner"
            banner_text  = "✅ <strong>Hyran är uppdaterad.</strong> Ingen beräknad intäktsförlust mot KPI."

        st.markdown(f'<div class="{banner_class}">{banner_text}</div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # Charts row 1
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(build_kpi_chart(fields), use_container_width=True)
        with c2:
            st.plotly_chart(build_gap_chart(kpi), use_container_width=True)

        # Charts row 2
        c3, c4 = st.columns([1, 2])
        with c3:
            st.plotly_chart(build_kpi_gauge(kpi["kpi_pct"]), use_container_width=True)
        with c4:
            st.plotly_chart(build_revenue_waterfall(kpi), use_container_width=True)

        # ── Section 3: Raw data expander ──────────────────────────────────────
        with st.expander("🔎 Visa rådata (JSON)", expanded=False):
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("**Extraherade fält**")
                st.json(fields)
            with col_b:
                st.markdown("**KPI-beräkning**")
                st.json({
                    "reference_month":      kpi["ref_month"],
                    "reference_kpi":        round(kpi["ref_kpi"], 2),
                    "current_month":        CURRENT_MONTH,
                    "current_kpi":          CURRENT_KPI,
                    "kpi_change_pct":       round(kpi["kpi_pct"], 2),
                    "base_rent_sek":        round(kpi["base_rent"], 2),
                    "kpi_adjusted_rent":    round(kpi["adjusted_rent"], 2),
                    "monthly_gap_sek":      round(kpi["monthly_gap"], 2),
                    "annual_gap_sek":       round(kpi["annual_gap"], 2),
                })

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("""
<div style="text-align:center;color:#aaa;font-size:12px;padding:8px 0 20px;">
    Hyresavtal Analyzer · KPI-data: SCB (1980=100) · Drivet av Claude (Anthropic)
</div>""", unsafe_allow_html=True)
