"""InvoiceFlow — invoice PDF to reasoned decision. Run with: streamlit run app.py"""
import base64
import html
import hashlib
import os
import secrets
import time
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

load_dotenv()

import db
import pipeline
from theme import inject_theme

db.init_db()
st.set_page_config(page_title="InvoiceFlow | Accounts Payable", layout="wide", initial_sidebar_state="expanded")

MANUAL_MINUTES = 3
STATUS_LABELS = {"APPROVE": "Approved", "HOLD": "Awaiting review", "REJECT": "Rejected"}
STATUS_OPTIONS = ["APPROVE", "HOLD", "REJECT"]
STAGE_LABELS = {"pending": "Queued", "running": "In progress", "done": "Complete", "error": "Error"}
CHECK_LABELS = {"pass": "Pass", "warn": "Warning", "fail": "Failed"}
ACTIVE_COLORS = None

for key, default in (("admin_authenticated", False), ("admin_user", ""), ("last", None),
                     ("last_pdf", None), ("last_filename", None)):
    if key not in st.session_state:
        st.session_state[key] = default

def admin_credentials():
    """Read initial username/password from deployment secrets; a website-set password hash takes precedence."""
    username = os.environ.get("INVOICEFLOW_ADMIN_USER", "admin")
    password = os.environ.get("INVOICEFLOW_ADMIN_PASSWORD", "admin")
    try:
        username = st.secrets.get("INVOICEFLOW_ADMIN_USER", username)
        password = st.secrets.get("INVOICEFLOW_ADMIN_PASSWORD", password)
    except Exception:
        pass
    return str(username), str(password)

def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 310000).hex()
    return f"{salt}${digest}"

def admin_password_matches(candidate):
    stored = db.get_setting("admin_password_hash")
    if stored:
        try:
            salt, expected = stored.split("$", 1)
            actual = password_hash(candidate, salt).split("$", 1)[1]
            return secrets.compare_digest(actual, expected)
        except ValueError:
            return False
    return secrets.compare_digest(candidate, admin_credentials()[1])

def admin_is_authenticated():
    return bool(st.session_state.get("admin_authenticated"))

def status_name(value):
    return STATUS_LABELS.get(value, str(value or "Unknown").title())

def status_class(value):
    return {"APPROVE": "approved", "HOLD": "awaiting", "REJECT": "rejected"}.get(value, "")

def record_status(r):
    return r.get("effective") or r.get("final_decision") or r.get("decision")

def risk_label(value):
    if value is None:
        return "Not scored"
    value = int(value)
    if value < 25:
        return "Low"
    if value < 50:
        return "Moderate"
    if value < 75:
        return "High"
    return "Critical"

def risk_class(value):
    if value is None:
        return "unscored"
    value = int(value)
    if value < 25:
        return "low"
    if value < 50:
        return "moderate"
    if value < 75:
        return "high"
    return "critical"

def render_bar_chart(series, value_format="count"):
    """Render a small horizontal chart using the active theme's semantic tokens."""
    if isinstance(series, pd.Series):
        items = [(str(label), value) for label, value in series.items()]
    elif isinstance(series, dict):
        items = [(str(label), value) for label, value in series.items()]
    else:
        items = list(series)

    cleaned = []
    for label, value in items:
        try:
            number = float(value) if value is not None and not pd.isna(value) else 0.0
        except (TypeError, ValueError):
            number = 0.0
        cleaned.append((str(label), max(0.0, number)))

    if not cleaned:
        st.caption("No chart data available.")
        return

    maximum = max((value for _, value in cleaned), default=0.0) or 1.0
    chart_colors = ["var(--if-chart-1)", "var(--if-chart-2)", "var(--if-chart-3)", "var(--if-chart-4)"]
    rows = []
    for index, (label, value) in enumerate(cleaned):
        width = max(0.0, min(100.0, value / maximum * 100.0))
        if value_format == "money":
            shown_value = f"{value:,.2f}"
        elif float(value).is_integer():
            shown_value = f"{int(value):,}"
        else:
            shown_value = f"{value:,.1f}"
        rows.append(
            '<div class="if-chart-row">'
            f'<div class="if-chart-label" title="{html.escape(label, quote=True)}">{html.escape(label)}</div>'
            f'<div class="if-chart-track"><div class="if-chart-fill" style="width:{width:.1f}%;background:{chart_colors[index % len(chart_colors)]}"></div></div>'
            f'<div class="if-chart-value">{shown_value}</div>'
            '</div>'
        )
    st.markdown(f'<div class="if-chart">{"".join(rows)}</div>', unsafe_allow_html=True)

def money(value, currency=""):
    if value is None or pd.isna(value):
        return "—"
    try:
        currency = "" if currency is None or pd.isna(currency) else str(currency).strip()
        amount = f"{float(value):,.2f}"
        return f"{amount} {currency}".strip()
    except (TypeError, ValueError):
        return str(value)

def style_dataframe(data):
    """Return a native HTML table styled from the active palette."""
    palette = ACTIVE_COLORS
    if isinstance(data, pd.DataFrame) and palette:
        styled = data.style.set_properties(**{
            "background-color": palette["table_bg"],
            "color": palette["text"],
            "border-color": palette["border"],
        }).set_table_styles([
            {"selector": "table", "props": [
                ("width", "100%"), ("border-collapse", "separate"),
                ("border-spacing", "0"), ("border", f"1px solid {palette['border']}"),
                ("border-radius", "9px"), ("overflow", "hidden"),
            ]},
            {"selector": "thead th, th.col_heading", "props": [
                ("background-color", palette["accent"]),
                ("color", palette["accent_text"]),
                ("font-weight", "750"),
                ("border-color", palette["border"]),
                ("padding", "0.7rem 0.75rem"),
            ]},
            {"selector": "tbody td", "props": [
                ("border-color", palette["border"]),
                ("padding", "0.62rem 0.75rem"),
            ]},
            {"selector": "tbody tr:nth-child(even) td", "props": [
                ("background-color", palette["table_alt"]),
            ]},
            {"selector": "tbody th", "props": [
                ("background-color", palette["accent"]),
                ("color", palette["accent_text"]),
                ("border-color", palette["border"]),
            ]},
        ])
        if "Utilisation" in data.columns:
            styled = styled.bar(subset=["Utilisation"], vmin=0, vmax=100, color=palette["accent"])
        return styled
    return data

def show_dataframe(data, **kwargs):
    """Display a theme-controlled table with a real HTML header (not a canvas grid)."""
    hide_index = kwargs.pop("hide_index", False)

    kwargs.pop("use_container_width", None)
    kwargs.pop("column_config", None)
    styled = style_dataframe(data)
    if hide_index and hasattr(styled, "hide"):
        styled = styled.hide(axis="index")
    return st.table(styled)

def safe_text(value):
    if value is None or value == "":
        return "—"
    return html.escape(str(value))

def section_heading(title, meta=""):
    st.markdown(
        f'<div class="if-section-head"><h3>{html.escape(title)}</h3><span>{html.escape(meta)}</span></div>',
        unsafe_allow_html=True,
    )

def status_banner(r):
    state = record_status(r)
    title = status_name(state)
    sub = f"Run #{r.get('run_id', r.get('id', '—'))}  ·  {r.get('filename') or 'Invoice'}"
    if r.get("final_decision"):
        sub += f"  ·  updated by {r.get('reviewer') or 'administrator'}"
    st.markdown(
        f'<div class="if-status {status_class(state)}"><div><div class="if-status-main">{html.escape(title)}</div>'
        f'<div class="if-status-sub">{html.escape(sub)}</div></div>'
        f'<div class="if-status-tag">{html.escape(str(state))}</div></div>',
        unsafe_allow_html=True,
    )

def render_pdf_preview(pdf_bytes, height=740):
    if not pdf_bytes:
        st.markdown('<div class="if-empty"><strong>Document preview unavailable</strong>No PDF is attached to this record.</div>',
                    unsafe_allow_html=True)
        return
    encoded = base64.b64encode(pdf_bytes).decode("ascii")
    frame = f"""
    <div class="if-pdf-shell" style="height:{height}px">
      <iframe class="if-pdf-frame" title="Invoice PDF preview"
        src="data:application/pdf;base64,{encoded}#toolbar=1&navpanes=0&view=FitH"></iframe>
    </div>
    """
    components.html(frame, height=height + 20, scrolling=False)

def render_field_grid(fields):
    cells = []
    for label, value in fields:
        cells.append(
            f'<div class="if-field"><div class="if-field-label">{html.escape(str(label))}</div>'
            f'<div class="if-field-value">{safe_text(value)}</div></div>'
        )
    st.markdown(f'<div class="if-field-grid">{"".join(cells)}</div>', unsafe_allow_html=True)

def render_extracted_information(r, compact=False):
    x = r.get("extracted") or {}
    if not x:
        st.markdown('<div class="if-empty"><strong>No extracted fields</strong>The extraction stage did not return structured invoice data.</div>',
                    unsafe_allow_html=True)
        return
    fields = [
        ("Vendor", x.get("vendor_name")),
        ("Invoice number", x.get("invoice_number")),
        ("Invoice date", x.get("invoice_date")),
        ("Due date", x.get("due_date")),
        ("PO reference", x.get("po_number") or (r.get("po") or {}).get("po_number")),
        ("Currency", x.get("currency")),
        ("Subtotal", money(x.get("subtotal"), x.get("currency"))),
        ("Tax", money(x.get("tax"), x.get("currency"))),
        ("Total due", money(x.get("total"), x.get("currency"))),
        ("Document type", (x.get("doc_type") or "invoice").replace("_", " ").title()),
    ]
    render_field_grid(fields[:6] if compact else fields)
    if not compact and x.get("line_items"):
        st.markdown("##### Line items")
        show_dataframe(pd.DataFrame(x["line_items"]), hide_index=True, use_container_width=True)
    if x.get("notes") and not compact:
        st.caption(f"Extraction note: {x['notes']}")

def render_rule_trail(r):
    checks = r.get("checks") or []
    if not checks:
        st.caption("No validation checks were returned for this run.")
        return
    rows = []
    for check in checks:
        rows.append({
            "Rule": check.get("id", "—"),
            "Check": check.get("name", "—"),
            "Result": CHECK_LABELS.get(check.get("status"), check.get("status", "—")),
            "Detail": check.get("detail", "—"),
        })
    show_dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

def render_run_facts(r):
    x = r.get("extracted") or {}
    po = r.get("po") or {}
    cols = st.columns(3)
    cols[0].metric("Risk score", f"{r.get('risk')}/100" if r.get("risk") is not None else "—")
    risk_text = f"{risk_label(r.get('risk'))} risk" if r.get("risk") is not None else "Not scored"
    cols[0].markdown(
        f'<span class="if-risk {risk_class(r.get("risk"))}">{html.escape(risk_text)}</span>',
        unsafe_allow_html=True,
    )
    cols[1].metric("Next owner", r.get("owner") or "—")
    cols[2].metric("Invoice total", money(x.get("total"), x.get("currency")))
    if r.get("reason"):
        st.markdown(f'<div class="if-card"><div class="if-card-label">Decision rationale</div><div class="if-card-value" style="font-size:.9rem;font-weight:500">{safe_text(r["reason"])}</div></div>',
                    unsafe_allow_html=True)
    if po:
        st.markdown("##### Purchase order match")
        pcols = st.columns(4)
        pcols[0].metric("PO reference", po.get("po_number") or "—")
        pcols[1].metric("PO amount", money(po.get("amount"), po.get("currency")))
        pcols[2].metric("Remaining before", money(po.get("remaining"), po.get("currency")))
        booked = po.get("po_amount") if po.get("po_amount") is not None else (x.get("total") or 0)
        after = (po.get("remaining") or 0) - booked if record_status(r) == "APPROVE" else po.get("remaining")
        pcols[3].metric("Remaining after", money(after, po.get("currency")))

def render_audit_details(r):
    if r.get("final_decision"):
        st.markdown("##### Administrative change")
        cols = st.columns(3)
        cols[0].metric("Current status", status_name(r.get("final_decision")))
        cols[1].metric("Changed by", r.get("reviewer") or "—")
        cols[2].metric("Changed at", r.get("reviewed_at") or "—")
        if r.get("review_note"):
            st.caption(f"Change note: {r['review_note']}")
    with st.expander("Processing trace and source text"):
        st.write(f"Extraction method: **{pipeline.METHODS.get(r.get('method'), r.get('method') or '—')}**")
        if r.get("stages"):
            show_dataframe(pd.DataFrame(r["stages"]), hide_index=True, use_container_width=True)
        if r.get("source_text"):
            st.text(r["source_text"])
        st.json(r.get("extracted") or {})

def render_saved_record_detail(r, show_pdf_note=True):
    status_banner(r)
    render_run_facts(r)
    section_heading("Extracted information", "Structured fields")
    render_extracted_information(r)
    with st.expander("Validation and purchase-order trail", expanded=False):
        render_rule_trail(r)
        po = r.get("po") or {}
        if po:
            st.json(po)
    render_audit_details(r)
    if show_pdf_note:
        st.caption("The PDF itself is shown in the processing workspace. Historical records retain extracted fields and audit data, not the uploaded file bytes.")

def render_workspace_result(r, pdf_bytes):
    status_banner(r)
    render_run_facts(r)
    left, right = st.columns([1.02, 0.98], gap="large")
    with left:
        section_heading("Document viewer", "Original PDF")
        render_pdf_preview(pdf_bytes, height=735)
    with right:
        section_heading("Extracted information", "Source fields")
        render_extracted_information(r)
        if r.get("reason"):
            st.markdown(f'<div class="if-card" style="margin-top:.9rem"><div class="if-card-label">Decision rationale</div><div class="if-card-value" style="font-size:.88rem;font-weight:500">{safe_text(r["reason"])}</div></div>',
                        unsafe_allow_html=True)
    with st.expander("Validation trail and processing details", expanded=False):
        render_rule_trail(r)
        render_audit_details(r)

def run_kwargs():
    return dict(tolerance=tol_pct / 100, tolerance_abs=float(tol_abs), engine=engine,
                line_tolerance=line_pct / 100, as_of=as_of)

def render_tracker(ph, state):
    rows = []
    for stage in pipeline.STAGES:
        value = state[stage]
        label = STAGE_LABELS.get(value["status"], value["status"])
        seconds = f" · {value['seconds']}s" if value.get("seconds") is not None else ""
        rows.append({"Stage": stage, "Status": label, "Details": value["detail"] + seconds})
    styled = style_dataframe(pd.DataFrame(rows)).hide(axis="index")
    ph.table(styled)

def run_live(pdf_bytes, name):
    box = st.container(border=True)
    box.markdown("#### Processing activity")
    ph = box.empty()
    state = {stage: {"status": "pending", "detail": "Waiting"} for stage in pipeline.STAGES}
    render_tracker(ph, state)
    result = None
    for event in pipeline.run_pipeline(pdf_bytes, name, **run_kwargs()):
        if event["type"] == "stage":
            state[event["stage"]] = event
            render_tracker(ph, state)
            if event["status"] != "running":
                time.sleep(0.22)
        else:
            result = event["result"]
    return result

def process_batch(files, label_prefix=""):
    """Run many PDFs back to back; returns result dictionaries."""
    bar = st.progress(0.0, text="Preparing batch")
    output = []
    for i, (name, data) in enumerate(files, 1):
        bar.progress((i - 1) / len(files), text=f"{label_prefix}Processing {name} ({i}/{len(files)})")
        for event in pipeline.run_pipeline(data, name, **run_kwargs()):
            if event["type"] == "result":
                output.append(event["result"])
    bar.progress(1.0, text=f"Completed · {len(output)} document(s)")
    return output

def records_by_status(runs, status):
    return [r for r in runs if record_status(r) == status]

def record_table(records):
    if not records:
        return pd.DataFrame(columns=["Run", "Date", "Vendor", "Invoice", "Total", "Risk", "Owner", "File"])
    return pd.DataFrame([{
        "Run": r.get("id"),
        "Date": r.get("created_at"),
        "Vendor": r.get("vendor") or "—",
        "Invoice": r.get("invoice_number") or "—",
        "Total": money(r.get("total"), r.get("currency")),
        "Risk": f"{r.get('risk')}/100" if r.get("risk") is not None else "—",
        "Owner": r.get("owner") or "—",
        "File": r.get("filename") or "—",
    } for r in records])

def render_status_override(r, key_prefix):
    if not admin_is_authenticated():
        st.info("Sign in from the Admin tab to change this record's status.")
        return
    current = record_status(r)
    st.markdown("##### Change record status")
    st.caption("Administrative changes are recorded with the signed-in username, timestamp and note. The original system decision remains available in the audit trail.")
    with st.form(f"{key_prefix}_status_form_{r.get('id')}"):
        selected = st.selectbox(
            "Set status to", STATUS_OPTIONS,
            index=STATUS_OPTIONS.index(current) if current in STATUS_OPTIONS else 0,
            format_func=status_name,
            key=f"{key_prefix}_status_value_{r.get('id')}",
        )
        note = st.text_area("Reason for change", placeholder="Record why this status is being updated", key=f"{key_prefix}_status_note_{r.get('id')}")
        submitted = st.form_submit_button("Save status change", type="primary", use_container_width=False)
    if submitted:
        if not note.strip():
            st.warning("Add a short reason before saving the status change.")
        elif selected == current:
            st.info("This record already has that status. No change was made.")
        else:
            db.review(r["id"], selected, note.strip(), st.session_state.get("admin_user") or "admin")
            db.log_admin_event(st.session_state.get("admin_user") or "admin", "Invoice status changed", r["id"], f"{current} -> {selected}; {note.strip()}")
            st.success(f"Record #{r['id']} updated to {status_name(selected).lower()}.")
            st.rerun()

def render_record_register(records, key_prefix, empty_title, empty_copy, show_approved_chart=False):
    if not records:
        st.markdown(f'<div class="if-empty"><strong>{html.escape(empty_title)}</strong>{html.escape(empty_copy)}</div>',
                    unsafe_allow_html=True)
        return
    df = record_table(records)
    show_dataframe(df, hide_index=True, use_container_width=True)
    if show_approved_chart:
        approved_df = pd.DataFrame(records)
        approved_df["booked_value"] = pd.to_numeric(approved_df.get("po_amount", approved_df.get("total")), errors="coerce").fillna(0)
        vendor_values = approved_df.groupby(approved_df["vendor"].fillna("Unidentified"))["booked_value"].sum().sort_values(ascending=False)
        if not vendor_values.empty:
            section_heading("Approved value by vendor", "Booked amount")
            render_bar_chart(vendor_values, value_format="money")
    ids = [r["id"] for r in records]
    selected_id = st.selectbox(
        "Open record", ids,
        format_func=lambda rid: f"Run #{rid} · {next((x.get('filename') or 'Invoice' for x in records if x['id'] == rid), 'Invoice')}",
        key=f"{key_prefix}_record_select",
    )
    selected_record = next(r for r in records if r["id"] == selected_id)
    st.divider()
    render_saved_record_detail(selected_record)
    st.divider()
    render_status_override(selected_record, key_prefix)

def admin_login_panel():
    if admin_is_authenticated():
        left, right = st.columns([4, 1])
        left.markdown(f'<span class="if-admin-pill">Signed in as {html.escape(st.session_state.get("admin_user", "admin"))}</span>',
                      unsafe_allow_html=True)
        if right.button("Sign out", use_container_width=True):
            st.session_state["admin_authenticated"] = False
            st.session_state["admin_user"] = ""
            st.rerun()
        return True
    with st.form("admin_login_form", clear_on_submit=False):
        st.markdown("##### Administrator sign in")
        username = st.text_input("Username", autocomplete="username")
        password = st.text_input("Password", type="password", autocomplete="current-password")
        submit = st.form_submit_button("Sign in", type="primary")
    if submit:
        expected_user, _expected_password = admin_credentials()
        valid_user = secrets.compare_digest(username.strip(), expected_user)
        valid_password = admin_password_matches(password)
        if valid_user and valid_password:
            st.session_state["admin_authenticated"] = True
            st.session_state["admin_user"] = username.strip()
            st.success("Administrator access granted.")
            st.rerun()
        st.error("The username or password is incorrect.")
    return False

with st.sidebar:
    st.markdown(
        '<div class="if-brand"><div class="if-mark">IF</div><div><div class="if-brand-name">InvoiceFlow</div>'
        '<div class="if-brand-sub">Accounts payable workspace</div></div></div>',
        unsafe_allow_html=True,
    )
    st.caption("Save time, automate repetitive tasks.")
    appearance = st.radio("Appearance", ["Dark", "Light"], horizontal=True, index=1,
                         label_visibility="visible")
    ACTIVE_COLORS = inject_theme(appearance)
    st.divider()
    with st.expander("Processing configuration", expanded=False):
        engine = st.radio("Extraction engine", list(pipeline.ENGINES), format_func=pipeline.ENGINES.get,
                          help="Offline rules require no API key. Auto mode falls back to offline rules if Gemini is unavailable.")
        if engine != "rules":
            key_in = st.text_input("Gemini API key", type="password", help="Enter a Gemini API key to enable cloud-assisted extraction.")
            if key_in:
                os.environ["GEMINI_API_KEY"] = key_in
            st.caption(f"Gemini active · {pipeline.MODEL}" if pipeline.gemini_available() else "No key detected; Auto mode uses offline rules.")
        else:
            st.caption("Offline : API key not required.")
        st.markdown("**Matching tolerances**")
        tol_pct = st.slider("PO balance tolerance (%)", 0.0, 10.0, float(db.get_setting("tol_pct", 2.0)), 0.5)
        tol_abs = st.slider("Absolute cap (currency units)", 0, 1000, int(float(db.get_setting("tol_abs", 250))), 10)
        line_pct = st.slider("Line unit price tolerance (%)", 0.0, 15.0, float(db.get_setting("line_pct", 3.0)), 0.5)
        as_of = st.date_input("Processing date", value=date.today())
    st.divider()
    if admin_is_authenticated():
        st.markdown(f'<span class="if-admin-pill">Administrator · {html.escape(st.session_state["admin_user"])}</span>', unsafe_allow_html=True)
    else:
        st.caption("Administrator controls are locked.")

st.markdown(
    '<div class="if-hero"><div><div class="if-kicker">Finance operations / invoice control</div>'
    '<div class="if-hero-title">InvoiceFlow</div><div class="if-hero-copy">Manage invoice verification, '
    'exception review and approval tracking in one workspace.</div></div>'
    '<div class="if-live-pill"> Invoice Processing </div></div>',
    unsafe_allow_html=True,
)

tab_workspace, tab_batch, tab_approved, tab_awaiting, tab_rejected, tab_insights, tab_procurement, tab_admin = st.tabs(
    ["Workspace", "Batch intake", "Approved", "Awaiting review", "Rejected", "Insights", "Procurement", "Admin"]
)

samples = sorted(Path("samples").glob("*.pdf"))

with tab_workspace:
    section_heading("Process an invoice", "Single document intake")
    mode = st.radio("Document source", ["Upload a PDF", "Use a sample invoice"], horizontal=True)
    pdf_bytes, filename = None, None
    if mode == "Upload a PDF":
        uploaded = st.file_uploader("Choose an invoice PDF", type=["pdf"], key="workspace_upload")
        if uploaded:
            pdf_bytes, filename = uploaded.getvalue(), uploaded.name
    elif samples:
        selected_sample = st.selectbox("Sample invoice", samples, format_func=lambda p: p.name)
        pdf_bytes, filename = selected_sample.read_bytes(), selected_sample.name
    else:
        st.info("No sample invoices are available. Upload a PDF to continue.")

    run_col, file_col = st.columns([1, 3])
    with run_col:
        run_clicked = st.button("Run invoice checks", type="primary", disabled=not pdf_bytes, use_container_width=True)
    with file_col:
        if pdf_bytes:
            st.caption(f"Selected document · {filename} · {len(pdf_bytes) / 1024:,.0f} KB")
        else:
            st.caption("Upload a PDF or choose a sample to begin.")

    if run_clicked and pdf_bytes:
        with st.spinner("Running extraction, validation and PO matching"):
            result = run_live(pdf_bytes, filename)
        st.session_state["last"] = result
        st.session_state["last_pdf"] = pdf_bytes
        st.session_state["last_filename"] = filename

    if pdf_bytes and st.session_state.get("last") and st.session_state.get("last_filename") == filename and st.session_state.get("last_pdf") == pdf_bytes:
        st.divider()
        render_workspace_result(st.session_state["last"], st.session_state.get("last_pdf"))
    elif pdf_bytes:
        st.divider()
        left, right = st.columns([1.02, .98], gap="large")
        with left:
            section_heading("Document viewer", "Original PDF")
            render_pdf_preview(pdf_bytes, height=700)
        with right:
            section_heading("Extracted information", "Appears after processing")
            st.markdown('<div class="if-empty"><strong>Ready for extraction</strong>Run the invoice checks to populate vendor details, invoice dates, PO references, amounts and line items here.</div>',
                        unsafe_allow_html=True)
    elif st.session_state.get("last"):
        st.info(f"Last processed document: {st.session_state.get('last_filename')}. Select it again to reopen the split document workspace.")

with tab_batch:
    section_heading("Batch intake", "Process multiple invoices with the same rules")
    st.caption("Upload several PDFs or replay the included sample set. Each document is stored in the same run history and appears in its status register.")
    batch_uploads = st.file_uploader("Select invoice PDFs", type=["pdf"], accept_multiple_files=True, key="batch_uploads")
    left, right = st.columns(2)
    process_uploaded = left.button("Process uploaded documents", type="primary", disabled=not batch_uploads, use_container_width=True)
    replay_samples = right.button("Replay all sample invoices", disabled=not samples, use_container_width=True)
    reset_before_replay = right.checkbox("Clear run history before replay", key="batch_clear_first")
    todo = None
    if process_uploaded:
        todo = [(file.name, file.getvalue()) for file in batch_uploads]
    elif replay_samples:
        if reset_before_replay:
            if admin_is_authenticated():
                db.clear_runs()
            else:
                st.warning("Sign in as administrator before clearing the existing run history. The sample batch was not started.")
                todo = None
        if not reset_before_replay or admin_is_authenticated():
            todo = [(path.name, path.read_bytes()) for path in samples]
    if todo:
        results = process_batch(todo)
        summary = pd.DataFrame([{
            "File": result.get("filename"),
            "System decision": status_name(result.get("decision")),
            "Vendor": (result.get("extracted") or {}).get("vendor_name"),
            "Invoice total": money((result.get("extracted") or {}).get("total"), (result.get("extracted") or {}).get("currency")),
            "Risk": result.get("risk"),
            "Follow-up owner": result.get("owner"),
        } for result in results])
        show_dataframe(summary, hide_index=True, use_container_width=True)
        approved_count = sum(result.get("decision") == "APPROVE" for result in results)
        st.success(f"{len(results)} documents processed. {approved_count} cleared automatically; {len(results) - approved_count} require a different outcome or review.")

runs = db.list_runs()
approved_records = records_by_status(runs, "APPROVE")
awaiting_records = records_by_status(runs, "HOLD")
rejected_records = records_by_status(runs, "REJECT")

with tab_approved:
    section_heading("Approved register", "Final status: approved")
    total_approved_value = sum(float(r.get("po_amount") if r.get("po_amount") is not None else (r.get("total") or 0))
                               for r in approved_records)
    a, b, c = st.columns(3)
    a.metric("Approved documents", len(approved_records))
    b.metric("Approved value", f"{total_approved_value:,.2f}")
    c.metric("Vendors represented", len({r.get("vendor") for r in approved_records if r.get("vendor")}))
    render_record_register(approved_records, "approved", "No approved invoices yet", "Invoices that reach or are changed to Approved will appear here.", show_approved_chart=True)

with tab_awaiting:
    section_heading("Awaiting review", "Final status: awaiting review")
    st.caption("This register includes new holds and any record an administrator has moved back into the awaiting state.")
    render_record_register(awaiting_records, "awaiting", "Nothing is waiting", "Invoices assigned Awaiting review will be listed here.")

with tab_rejected:
    section_heading("Rejected register", "Final status: rejected")
    st.caption("Rejected documents remain searchable in the register with their extraction data and decision history.")
    render_record_register(rejected_records, "rejected", "No rejected invoices", "Invoices assigned Rejected will be listed here.")

with tab_insights:
    section_heading("Operational insights", "Portfolio-level view")
    if not runs:
        st.markdown('<div class="if-empty"><strong>Insights will appear here</strong>Process invoices to build an operational view of approvals, review demand, rejected value and rule activity.</div>',
                    unsafe_allow_html=True)
    else:
        frame = pd.DataFrame(runs)
        frame["effective_status"] = frame.apply(lambda row: row.get("final_decision") or row.get("decision"), axis=1)
        frame["booked_value"] = pd.to_numeric(frame.get("po_amount", frame.get("total")), errors="coerce").fillna(0)
        count = len(frame)
        approved_count = int((frame["effective_status"] == "APPROVE").sum())
        awaiting_count = int((frame["effective_status"] == "HOLD").sum())
        rejected_count = int((frame["effective_status"] == "REJECT").sum())
        approved_value = frame.loc[frame.effective_status == "APPROVE", "booked_value"].sum()
        straight_through = int(((frame.decision == "APPROVE") & frame.final_decision.isna()).sum())
        metrics = st.columns(5)
        metrics[0].metric("Documents processed", count)
        metrics[1].metric("Approved", approved_count)
        metrics[2].metric("Awaiting review", awaiting_count)
        metrics[3].metric("Rejected", rejected_count)
        metrics[4].metric("Approved value", f"{approved_value:,.2f}")
        st.caption(f"Straight approvals: {straight_through / count:.0%} · Estimated AP time saved: {straight_through * MANUAL_MINUTES} minutes, based on {MANUAL_MINUTES} assumed manual minutes per invoice.")

        chart_left, chart_right = st.columns(2, gap="large")
        with chart_left:
            section_heading("Invoice outcomes", "Current status")
            outcomes = pd.Series({"Approved": approved_count, "Awaiting": awaiting_count, "Rejected": rejected_count})
            render_bar_chart(outcomes)
        with chart_right:
            section_heading("Approved value by vendor", "Current approved register")
            vendor_spend = frame[frame.effective_status == "APPROVE"].groupby(frame["vendor"].fillna("Unidentified"))["booked_value"].sum().sort_values(ascending=False)
            if vendor_spend.empty:
                st.caption("No approved value to chart yet.")
            else:
                render_bar_chart(vendor_spend, value_format="money")

        lower_left, lower_right = st.columns(2, gap="large")
        with lower_left:
            section_heading("Risk profile", "Risk score distribution")
            risk_values = pd.to_numeric(frame["risk"], errors="coerce").fillna(0)
            risk_bins = pd.cut(risk_values, [-1, 24, 49, 74, 100], labels=["Low", "Moderate", "High", "Critical"])
            render_bar_chart(risk_bins.value_counts().reindex(["Low", "Moderate", "High", "Critical"], fill_value=0))
        with lower_right:
            section_heading("Most frequent rule flags", "Warnings and failures")
            hits = {}
            for record in runs:
                for check in record.get("checks") or []:
                    if check.get("status") in ("fail", "warn"):
                        label = f"{check.get('id', '')} · {check.get('name', '')}"
                        hits[label] = hits.get(label, 0) + 1
            if hits:
                render_bar_chart(pd.Series(hits).sort_values(ascending=False).head(8))
            else:
                st.caption("No rule warnings or failures have been recorded.")

        section_heading("Approved purchase order utilisation", "Procurement position")
        po_frame = pd.DataFrame(db.list_pos())
        if not po_frame.empty:
            po_frame["Utilisation"] = (po_frame["invoiced"] / po_frame["amount"] * 100).clip(lower=0).round(1)
            show_dataframe(po_frame[["po_number", "vendor", "amount", "currency", "invoiced", "remaining", "Utilisation"]],
                         hide_index=True, use_container_width=True)

        with st.expander("Complete run history", expanded=False):
            history = frame[["id", "created_at", "filename", "vendor", "invoice_number", "po_used", "total", "currency", "decision", "final_decision", "effective_status", "risk", "owner", "method"]].copy()
            show_dataframe(history, hide_index=True, use_container_width=True)
            st.download_button("Export run history (CSV)", history.to_csv(index=False).encode("utf-8"),
                               "invoiceflow_run_history.csv", "text/csv")

with tab_procurement:
    section_heading("Procurement reference", "Vendor master and purchase order data")
    with st.expander("Rule assumptions and operating limits", expanded=False):
        assumptions_path = Path("ASSUMPTIONS.md")
        st.markdown(assumptions_path.read_text() if assumptions_path.exists() else "See README.md for the current rule assumptions.")
    vendor_data = pd.DataFrame(db.list_vendors())
    if not vendor_data.empty:
        if "bank_account" in vendor_data:
            vendor_data["bank_account"] = vendor_data["bank_account"].map(lambda value: f"••••{str(value)[-4:]}" if value else "")
        vendor_data["approved"] = vendor_data["approved"].map(bool)
    po_data = pd.DataFrame(db.list_pos())
    left, right = st.columns([.95, 1.5], gap="large")
    with left:
        section_heading("Vendor master", f"{len(vendor_data)} vendors")
        show_dataframe(vendor_data, hide_index=True, use_container_width=True)
    with right:
        section_heading("Purchase orders", f"{len(po_data)} purchase orders")
        show_dataframe(po_data, hide_index=True, use_container_width=True)
    line_left, line_right = st.columns(2, gap="large")
    with line_left:
        section_heading("PO line items", "Ordered quantities and prices")
        show_dataframe(pd.DataFrame(db.list_po_lines()), hide_index=True, use_container_width=True)
    with line_right:
        section_heading("Foreign exchange reference", "Mock rates · USD per unit")
        show_dataframe(pd.DataFrame(sorted(db.FX_RATES.items()), columns=["Currency", "USD per unit"]),
                     hide_index=True, use_container_width=True)

with tab_admin:
    section_heading("Administration", "Vendor permissions · procurement controls · workflow policy · audit")
    signed_in = admin_login_panel()
    st.divider()
    if signed_in or admin_is_authenticated():
        admin_tabs = st.tabs(["Overview & invoices", "Vendor access", "Purchase orders", "Workflow policy", "Audit log"])
        actor = st.session_state.get("admin_user") or "admin"

        with admin_tabs[0]:
            current_runs = db.list_runs()
            counts = st.columns(3)
            counts[0].metric("Approved", len(records_by_status(current_runs, "APPROVE")))
            counts[1].metric("Awaiting review", len(records_by_status(current_runs, "HOLD")))
            counts[2].metric("Rejected", len(records_by_status(current_runs, "REJECT")))
            if current_runs:
                ids = [record["id"] for record in current_runs]
                selected_id = st.selectbox("Select invoice", ids,
                    format_func=lambda rid: next(f"#{rid} · {record.get('filename') or 'Invoice'} · {status_name(record_status(record))}" for record in current_runs if record["id"] == rid),
                    key="admin_record_select")
                selected_record = next(record for record in current_runs if record["id"] == selected_id)
                left, right = st.columns([1.1, .9], gap="large")
                with left:
                    status_banner(selected_record); render_run_facts(selected_record)
                    section_heading("Invoice data", "Stored extraction"); render_extracted_information(selected_record, compact=False)
                with right:
                    st.markdown('<div class="if-card"><div class="if-card-label">Administrator authority</div><div class="if-card-value">Full status control</div><div class="if-card-note">Move this record between all workflow states. Every update is audited.</div></div>', unsafe_allow_html=True)
                    render_status_override(selected_record, "admin")
                    render_audit_details(selected_record)
            else:
                st.info("No invoice records yet. Process invoices in Workspace or Batch intake.")

        with admin_tabs[1]:
            vendors = db.list_vendors()
            st.caption("Allowed vendors can pass the approved vendor check. Blocked vendors are rejected by the invoice pipeline on their next processing run.")
            if vendors:
                vendor_names = [v["name"] for v in vendors]
                selected_vendor_name = st.selectbox("Choose vendor", vendor_names, key="admin_vendor_select")
                selected_vendor = next(v for v in vendors if v["name"] == selected_vendor_name)
                v1, v2, v3 = st.columns([2, 1, 1])
                v1.markdown(f"**{selected_vendor['name']}**")
                v2.write("Allowed" if selected_vendor.get("approved") else "Blocked")
                v3.write(f"Tax rate: {selected_vendor.get('tax_rate') if selected_vendor.get('tax_rate') is not None else '—'}")
                with st.form("admin_vendor_permission_form"):
                    permission = st.selectbox("Vendor permission", ["Allowed", "Blocked"], index=0 if selected_vendor.get("approved") else 1)
                    tax_rate = st.number_input("Expected tax rate (%)", min_value=0.0, max_value=100.0, value=float(selected_vendor.get("tax_rate") or 0.0), step=0.5)
                    save_vendor = st.form_submit_button("Save vendor policy", type="primary")
                if save_vendor:
                    db.set_vendor(selected_vendor_name, permission == "Allowed", tax_rate / 100 if tax_rate else None)
                    db.log_admin_event(actor, "Vendor permission updated", selected_vendor_name, permission)
                    st.success(f"{selected_vendor_name} is now {permission.lower()}."); st.rerun()
            st.divider(); section_heading("Add a vendor", "New vendors default to blocked")
            with st.form("admin_add_vendor_form", clear_on_submit=True):
                new_vendor = st.text_input("Company / vendor legal name")
                new_vendor_allowed = st.checkbox("Allow this vendor immediately", value=False)
                new_vendor_tax = st.number_input("Expected tax rate (%)", min_value=0.0, max_value=100.0, value=0.0, step=0.5)
                add_vendor = st.form_submit_button("Add vendor", type="primary")
            if add_vendor:
                if not new_vendor.strip(): st.error("Enter a vendor name.")
                else:
                    db.set_vendor(new_vendor, new_vendor_allowed, new_vendor_tax / 100 if new_vendor_tax else None)
                    db.log_admin_event(actor, "Vendor created", new_vendor, "Allowed" if new_vendor_allowed else "Blocked")
                    st.success("Vendor master updated."); st.rerun()
            show_dataframe(pd.DataFrame([{"Vendor":v["name"],"Permission":"Allowed" if v.get("approved") else "Blocked","Tax rate":v.get("tax_rate")} for v in db.list_vendors()]), hide_index=True, use_container_width=True)

        with admin_tabs[2]:
            pos = db.list_pos()
            st.caption("Create or amend purchase orders, and close/cancel orders so they cannot be matched for new invoices.")
            if pos:
                po_names = [p["po_number"] for p in pos]
                chosen_po = st.selectbox("Select purchase order", po_names, key="admin_po_select")
                po = next(p for p in pos if p["po_number"] == chosen_po)
                with st.form("admin_po_status_form"):
                    po_status = st.selectbox("PO status", ["OPEN", "CLOSED", "CANCELLED"], index=["OPEN","CLOSED","CANCELLED"].index(po.get("status") or "OPEN"))
                    update_po = st.form_submit_button("Update PO status", type="primary")
                if update_po:
                    db.update_po_status(chosen_po, po_status); db.log_admin_event(actor, "PO status changed", chosen_po, po_status)
                    st.success("Purchase order updated."); st.rerun()
            st.divider(); section_heading("Create / amend purchase order", "PO number must be unique")
            vendor_choices = [v["name"] for v in db.list_vendors()]
            with st.form("admin_create_po_form", clear_on_submit=True):
                po_number = st.text_input("PO number")
                po_vendor = st.selectbox("Vendor", vendor_choices) if vendor_choices else st.text_input("Vendor name")
                po_amount = st.number_input("PO amount", min_value=0.01, value=1000.0, step=100.0)
                po_currency = st.selectbox("Currency", sorted(db.FX_RATES.keys()), index=0)
                po_date = st.date_input("Issue date", value=date.today())
                po_state = st.selectbox("Initial status", ["OPEN", "CLOSED", "CANCELLED"])
                save_po = st.form_submit_button("Save purchase order", type="primary")
            if save_po:
                if not po_number.strip(): st.error("Enter a PO number.")
                else:
                    db.set_po(po_number, po_vendor, po_amount, po_currency, po_date.isoformat(), po_state)
                    db.log_admin_event(actor, "Purchase order saved", po_number, f"{po_vendor}; {po_amount} {po_currency}; {po_state}")
                    st.success("Purchase order saved."); st.rerun()
            show_dataframe(pd.DataFrame(db.list_pos()), hide_index=True, use_container_width=True)

        with admin_tabs[3]:
            section_heading("Processing policy", "Persisted defaults used by future invoice runs")
            st.warning("These values affect future processing only. Existing invoice decisions are not recalculated automatically.")
            with st.form("admin_policy_form"):
                p_tol = st.slider("PO balance tolerance (%)", 0.0, 10.0, float(db.get_setting("tol_pct", 2.0)), 0.5)
                p_abs = st.slider("Absolute cap (currency units)", 0, 1000, int(float(db.get_setting("tol_abs", 250))), 10)
                p_line = st.slider("Line unit-price tolerance (%)", 0.0, 15.0, float(db.get_setting("line_pct", 3.0)), 0.5)
                save_policy = st.form_submit_button("Save processing defaults", type="primary")
            if save_policy:
                db.set_setting("tol_pct", p_tol); db.set_setting("tol_abs", p_abs); db.set_setting("line_pct", p_line)
                db.log_admin_event(actor, "Processing policy updated", "global", f"PO {p_tol}%; cap {p_abs}; line {p_line}%")
                st.success("Defaults saved. They will be used by subsequent invoice runs.")
            st.divider(); section_heading("Administrator password", "Update administrator access")
            with st.form("admin_change_password_form", clear_on_submit=True):
                current_password = st.text_input("Current password", type="password")
                new_password = st.text_input("New password", type="password")
                confirm_password = st.text_input("Confirm new password", type="password")
                change_password = st.form_submit_button("Update administrator password", type="primary")
            if change_password:
                if not admin_password_matches(current_password):
                    st.error("Current password is incorrect.")
                elif len(new_password) < 12:
                    st.error("Use at least 12 characters for the new password.")
                elif new_password != confirm_password:
                    st.error("The new passwords do not match.")
                else:
                    db.set_setting("admin_password_hash", password_hash(new_password))
                    db.log_admin_event(actor, "Administrator password changed", "admin", "Password hash updated from the website")
                    st.success("Password updated. Use the new password at your next sign in.")
            st.divider(); section_heading("History controls", "Destructive action")
            confirm_wipe = st.checkbox("I understand this permanently clears the local run history", key="admin_confirm_wipe")
            if st.button("Clear all invoice history", type="secondary", disabled=not confirm_wipe):
                db.log_admin_event(actor, "Invoice history cleared", "all", "Administrator confirmed history reset")
                db.clear_runs()
                for key in ("last", "last_pdf", "last_filename"): st.session_state.pop(key, None)
                st.success("Invoice history cleared."); st.rerun()

        with admin_tabs[4]:
            section_heading("Administrative audit log", "Latest 500 changes")
            events = db.list_admin_events(500)
            if events:
                show_dataframe(pd.DataFrame(events), hide_index=True, use_container_width=True)
                csv = pd.DataFrame(events).to_csv(index=False).encode("utf-8")
                st.download_button("Export admin audit log", csv, "invoiceflow_admin_audit.csv", "text/csv")
            else:
                st.info("No administrative changes recorded yet.")
    else:
        st.markdown('<div class="if-empty"><strong>Administrator access required</strong>Sign in to unlock vendor permissions, PO controls, policy settings and invoice status management.</div>', unsafe_allow_html=True)
