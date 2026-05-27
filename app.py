"""
FermentGuard — Streamlit dashboard for honey vinegar fermentation monitoring
with submerged generator support.

Run with: streamlit run app.py
"""

import streamlit as st
from datetime import datetime, date
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from database import (
    init_db,
    create_batch,
    add_measurement,
    get_all_batches,
    get_batch,
    update_batch_status,
    get_measurements_for_batch,
    get_latest_measurement,
    delete_measurement,
    seed_demo_data,
    batch_exists,
)
from utils import (
    OPTIMAL_RANGES,
    check_reading_alerts,
    estimate_acidity_progress,
    generate_simulation_batch,
    df_to_csv_bytes,
    format_timestamp,
    get_status_color,
)

# =============================================================================
# PAGE CONFIG & INIT
# =============================================================================
st.set_page_config(
    page_title="FermentGuard",
    page_icon="🍯",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": "https://github.com/fermentguard/fermentguard",
        "Report a bug": None,
        "About": "FermentGuard v1.0 — Practical monitoring for small-batch honey vinegar.",
    },
)

# Initialize DB and seed demo data on first run
init_db()
seed_demo_data()

# Session state
if "simulation_mode" not in st.session_state:
    st.session_state.simulation_mode = True
if "selected_batch" not in st.session_state:
    st.session_state.selected_batch = None
if "last_added" not in st.session_state:
    st.session_state.last_added = None


# =============================================================================
# HELPERS
# =============================================================================
def refresh_batches():
    return get_all_batches()


def nice_metric(label: str, value: str, delta: str = "", help_text: str = ""):
    """Compact metric card."""
    st.metric(label=label, value=value, delta=delta, help=help_text)


def render_alert_badge(alert: dict):
    """Render a single alert as colored pill."""
    level = alert.get("level", "info")
    msg = alert.get("msg", "")
    if level == "warning":
        st.warning(msg, icon="⚠️")
    elif level == "info":
        st.info(msg, icon="ℹ️")
    else:
        st.write(msg)


def create_trend_figure(df: pd.DataFrame, batch_label: str) -> go.Figure:
    """Multi-panel interactive Plotly figure for pH, DO, and Temperature."""
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No data yet for this batch", x=0.5, y=0.5, showarrow=False)
        fig.update_layout(height=420)
        return fig

    # Ensure datetime
    df = df.copy()
    df["measured_at"] = pd.to_datetime(df["measured_at"])

    # Create 3-row subplot (shared x-axis)
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.065,
        subplot_titles=("pH (acidity progress)", "Dissolved Oxygen (%)", "Temperature (°C)"),
        row_heights=[0.36, 0.32, 0.32],
    )

    # pH
    fig.add_trace(
        go.Scatter(
            x=df["measured_at"],
            y=df["pH"],
            mode="lines+markers",
            name="pH",
            line=dict(color="#E85D04", width=2.5),
            marker=dict(size=7, color="#E85D04"),
            hovertemplate="%{x|%b %d %H:%M}<br>pH: %{y:.2f}<extra></extra>",
        ),
        row=1, col=1
    )
    # Target band for pH
    fig.add_hrect(
        y0=OPTIMAL_RANGES["pH"]["min"], y1=OPTIMAL_RANGES["pH"]["max"],
        fillcolor="rgba(46, 139, 87, 0.12)", line_width=0,
        row=1, col=1
    )
    fig.add_hline(y=OPTIMAL_RANGES["pH"]["target"], line_dash="dash", line_color="#2E8B57",
                  annotation_text="target", row=1, col=1)

    # DO
    fig.add_trace(
        go.Scatter(
            x=df["measured_at"],
            y=df["dissolved_oxygen"],
            mode="lines+markers",
            name="DO %",
            line=dict(color="#219EBC", width=2.5),
            marker=dict(size=6, color="#219EBC"),
            hovertemplate="%{x|%b %d %H:%M}<br>DO: %{y:.1f}%<extra></extra>",
        ),
        row=2, col=1
    )
    fig.add_hrect(
        y0=OPTIMAL_RANGES["dissolved_oxygen"]["min"],
        y1=OPTIMAL_RANGES["dissolved_oxygen"]["max"],
        fillcolor="rgba(33, 158, 188, 0.12)", line_width=0,
        row=2, col=1
    )

    # Temperature
    fig.add_trace(
        go.Scatter(
            x=df["measured_at"],
            y=df["temperature_C"],
            mode="lines+markers",
            name="Temp °C",
            line=dict(color="#8B5CF6", width=2.5),
            marker=dict(size=6, color="#8B5CF6"),
            hovertemplate="%{x|%b %d %H:%M}<br>Temp: %{y:.1f}°C<extra></extra>",
        ),
        row=3, col=1
    )
    fig.add_hrect(
        y0=OPTIMAL_RANGES["temperature_C"]["min"],
        y1=OPTIMAL_RANGES["temperature_C"]["max"],
        fillcolor="rgba(139, 92, 246, 0.12)", line_width=0,
        row=3, col=1
    )

    fig.update_layout(
        height=520,
        margin=dict(l=50, r=30, t=50, b=30),
        showlegend=False,
        hovermode="x unified",
        plot_bgcolor="rgba(248, 249, 250, 0.6)",
        paper_bgcolor="white",
    )
    fig.update_xaxes(showgrid=True, gridwidth=0.5, gridcolor="#E9ECEF")
    fig.update_yaxes(showgrid=True, gridwidth=0.5, gridcolor="#E9ECEF")

    # Add batch label
    fig.add_annotation(
        text=f"<b>{batch_label}</b>",
        x=0.02, y=0.98, xref="paper", yref="paper",
        showarrow=False, font=dict(size=13, color="#495057"),
        align="left"
    )
    return fig


# =============================================================================
# SIDEBAR
# =============================================================================
with st.sidebar:
    st.title("🍯 FermentGuard")
    st.caption("Honey Vinegar • Submerged Generator")

    st.divider()

    # Simulation toggle
    st.session_state.simulation_mode = st.toggle(
        "Simulation Mode",
        value=st.session_state.simulation_mode,
        help="Enable one-click realistic data injection for testing without hardware.",
    )
    if st.session_state.simulation_mode:
        st.success("Simulation enabled — use the button in main panel to add test data.", icon="🧪")

    st.divider()

    # Batch management
    st.subheader("Batches")
    batches = refresh_batches()

    if batches:
        batch_options = {f"{b['batch_id']}  ·  {b['start_date']}" : b['batch_id'] for b in batches}
        selected_display = st.selectbox(
            "Focus batch",
            options=list(batch_options.keys()),
            index=0,
            help="This batch will be shown in detail charts and used for new log entries / simulation.",
        )
        st.session_state.selected_batch = batch_options[selected_display]
    else:
        st.info("No batches yet. Create one below.")
        st.session_state.selected_batch = None

    # Quick create new batch
    with st.expander("➕ New Batch", expanded=not bool(batches)):
        with st.form("new_batch_form", clear_on_submit=True):
            new_id = st.text_input("Batch ID", value=f"HV-{datetime.now().strftime('%Y%m%d')}-01", max_chars=40)
            new_start = st.date_input("Start Date", value=date.today())
            new_desc = st.text_area("Description (optional)", height=70, placeholder="Honey type, volume, mother source...")
            submitted = st.form_submit_button("Create Batch", use_container_width=True)
            if submitted:
                if new_id.strip() and not batch_exists(new_id.strip()):
                    if create_batch(new_id.strip(), new_start.isoformat(), new_desc.strip()):
                        st.success(f"Created {new_id}")
                        st.session_state.selected_batch = new_id.strip()
                        st.rerun()
                    else:
                        st.error("Could not create batch (duplicate ID?)")
                else:
                    st.error("Batch ID required and must be unique.")

    # Status management for current batch
    if st.session_state.selected_batch:
        current = get_batch(st.session_state.selected_batch)
        if current:
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Mark Complete", use_container_width=True):
                    update_batch_status(st.session_state.selected_batch, "complete")
                    st.rerun()
            with col2:
                if st.button("Archive", use_container_width=True):
                    update_batch_status(st.session_state.selected_batch, "archived")
                    st.session_state.selected_batch = None
                    st.rerun()

    st.divider()
    st.caption("Data stored locally in `fermentguard.db`")
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.rerun()

    st.divider()
    st.markdown(
        """
        **Optimal Ranges (submerged)**
        - pH: 3.2 – 4.2
        - Temp: 24 – 30 °C
        - DO: 25 – 65 %
        - Aeration: 0.3 – 1.8 L/min
        """
    )


# =============================================================================
# HEADER
# =============================================================================
st.title("FermentGuard")
st.markdown("**Real-time monitoring & logging for honey-based vinegar fermentation** — submerged generator workflow")

# Top summary row
batches = refresh_batches()
active_batches = [b for b in batches if b["status"] == "active"]

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Active Batches", len(active_batches), help="Currently tracked fermentations")
with col2:
    total_logs = sum(b.get("log_count", 0) for b in batches)
    st.metric("Total Log Entries", total_logs)
with col3:
    if st.session_state.selected_batch:
        latest = get_latest_measurement(st.session_state.selected_batch)
        if latest and latest.get("pH"):
            st.metric("Current pH (focused)", f"{latest['pH']:.2f}")
        else:
            st.metric("Current pH (focused)", "—")
    else:
        st.metric("Current pH (focused)", "—")
with col4:
    st.metric("Simulation Mode", "ON" if st.session_state.simulation_mode else "OFF")


st.divider()


# =============================================================================
# LOG ENTRY FORM
# =============================================================================
st.header("📝 Add Log Entry")

if not st.session_state.selected_batch:
    st.info("Select or create a batch in the sidebar first.")
else:
    batch_meta = get_batch(st.session_state.selected_batch)
    st.caption(f"Logging to **{st.session_state.selected_batch}** (started {batch_meta['start_date']})")

    with st.form("log_entry_form", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns(4)

        with c1:
            default_ph = 3.85 if (latest := get_latest_measurement(st.session_state.selected_batch)) and latest.get("pH") else 4.35
            ph_val = st.number_input("pH", min_value=2.5, max_value=6.5, value=round(default_ph, 2), step=0.01, format="%.2f")
        with c2:
            default_do = 42.0 if latest and latest.get("dissolved_oxygen") else 48.0
            do_val = st.number_input("Dissolved Oxygen (%)", min_value=5.0, max_value=95.0, value=round(default_do, 1), step=0.5)
        with c3:
            default_temp = 27.2 if latest and latest.get("temperature_C") else 27.0
            temp_val = st.number_input("Temperature (°C)", min_value=18.0, max_value=35.0, value=round(default_temp, 1), step=0.1)
        with c4:
            default_aer = 0.75 if latest and latest.get("aeration_rate") else 0.9
            aer_val = st.number_input("Aeration Rate (L/min)", min_value=0.0, max_value=4.0, value=round(default_aer, 2), step=0.05)

        notes = st.text_area("Notes / Observations", height=85, placeholder="Smell, clarity, foam, mother condition, adjustments...")

        log_time = st.text_input(
            "Measured At (YYYY-MM-DD HH:MM)",
            value=datetime.now().strftime("%Y-%m-%d %H:%M"),
            help="Use 24h format. Change only if backfilling historical data.",
        )

        submitted = st.form_submit_button("💾 Save Log Entry", type="primary", use_container_width=True)

        if submitted:
            try:
                new_id = add_measurement(
                    batch_id=st.session_state.selected_batch,
                    measured_at=log_time,
                    pH=ph_val,
                    dissolved_oxygen=do_val,
                    temperature_C=temp_val,
                    aeration_rate=aer_val,
                    notes=notes,
                )
                st.session_state.last_added = new_id
                st.success(f"Log entry saved (#{new_id})", icon="✅")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to save: {e}")

    # Quick simulation injection (only when simulation mode on)
    if st.session_state.simulation_mode and st.session_state.selected_batch:
        sim_col1, sim_col2 = st.columns([3, 1])
        with sim_col1:
            st.caption("No real hardware yet? Inject realistic multi-day data instantly.")
        with sim_col2:
            if st.button("🧪 Simulate 8 Days of Data", use_container_width=True, type="secondary"):
                sim_logs = generate_simulation_batch(
                    st.session_state.selected_batch,
                    get_batch(st.session_state.selected_batch)["start_date"],
                    num_days=8,
                )
                added = 0
                for log in sim_logs:
                    add_measurement(**log)
                    added += 1
                st.success(f"Added {added} simulated readings.")
                st.rerun()


# =============================================================================
# DASHBOARD MAIN VIEW
# =============================================================================
st.header("📊 Batch Dashboard")

if not batches:
    st.warning("No batches found. Create one in the sidebar.")
else:
    # Overview table
    st.subheader("All Batches Overview")

    overview_df = pd.DataFrame([
        {
            "Batch": b["batch_id"],
            "Started": b["start_date"],
            "Status": b["status"].upper(),
            "Logs": b["log_count"],
            "Last Entry": format_timestamp(b["last_log"]) if b["last_log"] else "—",
            "Latest pH": f"{b['latest_pH']:.2f}" if b.get("latest_pH") else "—",
            "Latest Temp": f"{b['latest_temp']:.1f}°C" if b.get("latest_temp") else "—",
        }
        for b in batches
    ])

    st.dataframe(
        overview_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Status": st.column_config.TextColumn("Status", width="small"),
            "Logs": st.column_config.NumberColumn("Logs", width="small"),
        },
    )

    st.divider()

    # Focused batch deep dive
    if st.session_state.selected_batch:
        focus_id = st.session_state.selected_batch
        focus_meta = get_batch(focus_id)
        focus_df = get_measurements_for_batch(focus_id)

        st.subheader(f"🔍 {focus_id}")
        st.caption(focus_meta.get("description", ""))

        # Summary metrics + progress
        m1, m2, m3, m4 = st.columns(4)

        latest = get_latest_measurement(focus_id) or {}
        progress = estimate_acidity_progress(focus_df)

        with m1:
            nice_metric("Current pH", f"{latest.get('pH', '—')}", help_text="Lower = more acetic acid")
        with m2:
            nice_metric("Est. Progress", f"{progress['progress_percent']}%", help_text=progress["interpretation"])
        with m3:
            nice_metric("Days Tracked", str(progress.get("days_elapsed", "—")))
        with m4:
            nice_metric("Log Count", str(len(focus_df)))

        # Alerts for latest reading
        if latest:
            alerts = check_reading_alerts(latest)
            if alerts:
                st.markdown("**Status Alerts**")
                for a in alerts[:3]:
                    render_alert_badge(a)
            else:
                st.success("All key parameters within good operating ranges.", icon="✅")

        # Charts
        st.markdown("#### Trend Charts")
        fig = create_trend_figure(focus_df, focus_id)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": True})

        # Data table + export
        st.markdown("#### Recent Measurements")
        if not focus_df.empty:
            # Prepare nice display table (newest first)
            display_df = focus_df.sort_values("measured_at", ascending=False).copy()
            display_df["measured_at"] = display_df["measured_at"].dt.strftime("%Y-%m-%d %H:%M")
            display_df = display_df[["measured_at", "pH", "dissolved_oxygen", "temperature_C", "aeration_rate", "notes", "id"]]

            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "measured_at": "Timestamp",
                    "pH": st.column_config.NumberColumn("pH", format="%.2f"),
                    "dissolved_oxygen": st.column_config.NumberColumn("DO %", format="%.1f"),
                    "temperature_C": st.column_config.NumberColumn("Temp °C", format="%.1f"),
                    "aeration_rate": st.column_config.NumberColumn("Aeration", format="%.2f"),
                },
            )

            # CSV Export
            csv_bytes = df_to_csv_bytes(focus_df)
            st.download_button(
                label=f"⬇️ Export {focus_id} as CSV ({len(focus_df)} rows)",
                data=csv_bytes,
                file_name=f"{focus_id}_fermentguard_export.csv",
                mime="text/csv",
                use_container_width=False,
            )

            # Danger zone - delete last entry (useful for mistakes)
            with st.expander("⚠️ Data correction"):
                if st.button("Delete most recent entry (irreversible)", type="secondary"):
                    last_id = int(focus_df.sort_values("measured_at", ascending=False).iloc[0]["id"])
                    delete_measurement(last_id)
                    st.warning("Last entry deleted.")
                    st.rerun()
        else:
            st.info("No measurements recorded yet for this batch.")

    else:
        st.info("Select a batch in the sidebar to view detailed trends and export.")

    # Multi-batch comparison (bonus)
    if len(batches) > 1:
        with st.expander("📈 Compare Multiple Batches (pH overlay)"):
            compare_ids = st.multiselect(
                "Select batches to overlay",
                options=[b["batch_id"] for b in batches],
                default=[b["batch_id"] for b in batches[:2]],
            )
            if compare_ids:
                all_data = []
                for bid in compare_ids:
                    d = get_measurements_for_batch(bid)
                    if not d.empty:
                        d["batch"] = bid
                        all_data.append(d)
                if all_data:
                    cmp_df = pd.concat(all_data)
                    fig_cmp = px.line(
                        cmp_df,
                        x="measured_at",
                        y="pH",
                        color="batch",
                        markers=True,
                        title="pH Comparison Across Batches",
                        labels={"measured_at": "Date", "pH": "pH"},
                    )
                    fig_cmp.update_layout(height=380)
                    st.plotly_chart(fig_cmp, use_container_width=True)


# =============================================================================
# FOOTER / TIPS
# =============================================================================
st.divider()

with st.expander("📖 Quick Tips for Submerged Honey Vinegar"):
    st.markdown(
        """
        - **pH drop** is your primary real-time proxy for acetic acid formation. Target finished vinegar is typically **3.3–3.6**.
        - Keep **temperature 25–28 °C** for fastest, cleanest acetobacter activity.
        - **Aeration** is critical early (higher DO), then can be reduced once pH < 3.8 to avoid over-oxidation.
        - Always taste + titrate (or use a vinegar acidity test kit) before bottling — this dashboard is a monitoring aid.
        - Raw honey batches often finish in 12–25 days depending on temperature, aeration, and starting alcohol level.
        - Record notes on smell (clean vinegar vs nail polish) and mother health.
        """
    )

st.caption(
    "FermentGuard • Local SQLite only • Not a substitute for proper food safety practices • "
    "Made for small-batch producers"
)
