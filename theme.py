"""Theme loader and shared styling for InvoiceFlow.

Palette values live in colours.txt. The file uses semantic design tokens and
six-digit sRGB HEX values so the colours can be changed without editing Python.
"""
from configparser import ConfigParser
from pathlib import Path
import re

import streamlit as st

BASE_DIR = Path(__file__).resolve().parent
COLOUR_FILE = BASE_DIR / "colours.txt"
_REQUIRED = {
    "color_scheme", "background", "panel", "panel_alt", "text", "muted", "border",
    "accent", "accent_hover", "accent_text", "success", "success_bg", "warning",
    "warning_bg", "danger", "danger_bg", "input", "tab_bg", "tab_selected",
    "table_bg", "table_alt", "chart_bg", "chart_track",
    "chart_2", "chart_3", "chart_4", "risk_low", "risk_low_bg", "risk_moderate",
    "risk_moderate_bg", "risk_high", "risk_high_bg", "risk_critical",
    "risk_critical_bg", "shadow",
}
_HEX_KEYS = _REQUIRED - {"color_scheme", "shadow"}

def load_palettes(path=COLOUR_FILE):
    """Load and validate both palettes from the user-editable colours.txt file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Colour configuration not found: {path}")
    parser = ConfigParser(interpolation=None)
    parser.read(path, encoding="utf-8")
    palettes = {}
    for section, label in (("Dark", "Dark"), ("Light", "Light")):
        if not parser.has_section(section):
            raise ValueError(f"Missing [{section}] section in {path.name}")
        values = {key: value.strip() for key, value in parser.items(section)}
        missing = sorted(_REQUIRED - values.keys())
        if missing:
            raise ValueError(f"Missing colour tokens in [{section}]: {', '.join(missing)}")
        invalid = [key for key in _HEX_KEYS if not re.fullmatch(r"#[0-9A-Fa-f]{6}", values[key])]
        if invalid:
            raise ValueError(f"Invalid HEX values in [{section}]: {', '.join(invalid)}")
        if values["color_scheme"] not in ("light", "dark"):
            raise ValueError(f"color_scheme in [{section}] must be 'light' or 'dark'")
        palettes[label] = values
    return palettes

def inject_theme(theme_name):
    """Apply the selected palette to Streamlit, its widgets, tables and charts."""
    palettes = load_palettes()
    if theme_name not in palettes:
        raise ValueError(f"Unknown theme: {theme_name}")
    p = palettes[theme_name]
    css = f"""
    <style>
    :root {{
      color-scheme: {p['color_scheme']};
      --if-bg: {p['background']};
      --if-panel: {p['panel']};
      --if-panel-alt: {p['panel_alt']};
      --if-text: {p['text']};
      --if-muted: {p['muted']};
      --if-border: {p['border']};
      --if-accent: {p['accent']};
      --if-accent-hover: {p['accent_hover']};
      --if-accent-text: {p['accent_text']};
      --if-success: {p['success']};
      --if-success-bg: {p['success_bg']};
      --if-warning: {p['warning']};
      --if-warning-bg: {p['warning_bg']};
      --if-danger: {p['danger']};
      --if-danger-bg: {p['danger_bg']};
      --if-input: {p['input']};
      --if-tab-bg: {p['tab_bg']};
      --if-tab-selected: {p['tab_selected']};
      --if-table-bg: {p['table_bg']};
      --if-table-alt: {p['table_alt']};
      --if-table-head: {p['accent']};
      --if-table-head-text: {p['accent_text']};
      --if-chart-bg: {p['chart_bg']};
      --if-chart-track: {p['chart_track']};
      --if-chart-1: {p['accent']};
      --if-chart-2: {p['chart_2']};
      --if-chart-3: {p['chart_3']};
      --if-chart-4: {p['chart_4']};
      --if-risk-low: {p['risk_low']};
      --if-risk-low-bg: {p['risk_low_bg']};
      --if-risk-moderate: {p['risk_moderate']};
      --if-risk-moderate-bg: {p['risk_moderate_bg']};
      --if-risk-high: {p['risk_high']};
      --if-risk-high-bg: {p['risk_high_bg']};
      --if-risk-critical: {p['risk_critical']};
      --if-risk-critical-bg: {p['risk_critical_bg']};
      --if-shadow: {p['shadow']};
    }}

    html, body, [data-testid="stAppViewContainer"], .stApp {{
      background: var(--if-bg) !important;
      color: var(--if-text) !important;
      color-scheme: {p['color_scheme']} !important;
    }}
    .stApp {{ color: var(--if-text); }}
    [data-testid="stHeader"] {{ background: transparent !important; }}
    [data-testid="stSidebar"] {{
      background: var(--if-panel) !important;
      border-right: 1px solid var(--if-border);
    }}
    [data-testid="stSidebar"] > div:first-child {{ background: var(--if-panel) !important; }}
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] strong,
    [data-testid="stSidebar"] summary {{ color: var(--if-text) !important; }}
    .block-container {{ max-width: 1580px; padding-top: 1.65rem; padding-bottom: 3rem; }}
    h1, h2, h3, h4, h5, p, label, li, small, strong {{ color: var(--if-text); }}
    h1 {{ letter-spacing: -.045em; font-weight: 690 !important; }}
    h2, h3, h4 {{ letter-spacing: -.025em; font-weight: 640 !important; }}
    [data-testid="stCaptionContainer"] p,
    .stCaption, [data-testid="stCaption"] {{ color: var(--if-muted) !important; }}
    hr {{ border-color: var(--if-border) !important; }}

    [data-testid="stTabs"] {{ width: 100%; }}
    [data-testid="stTabs"] [role="tablist"] {{
      display: flex !important;
      align-items: stretch;
      justify-content: space-between;
      gap: .55rem;
      width: 100%;
      border-bottom: 1px solid var(--if-border);
      padding: 0 0 .35rem;
    }}
    [data-testid="stTabs"] button[role="tab"] {{
      flex: 1 1 0;
      min-width: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      padding: .78rem .48rem;
      color: var(--if-text) !important;
      opacity: 1 !important;
      background: var(--if-tab-bg) !important;
      border: 1px solid var(--if-border) !important;
      border-bottom: 2px solid transparent !important;
      border-radius: 9px 9px 0 0;
      font-size: .84rem;
      font-weight: 620;
      transition: background .15s ease, border-color .15s ease;
    }}
    [data-testid="stTabs"] button[role="tab"] *,
    [data-testid="stTabs"] button[role="tab"] p,
    [data-testid="stTabs"] button[role="tab"] span,
    [data-testid="stTabs"] button[role="tab"] div {{
      color: var(--if-text) !important;
      opacity: 1 !important;
    }}
    [data-testid="stTabs"] button[role="tab"]:hover {{
      background: var(--if-panel-alt) !important;
      border-color: var(--if-accent) !important;
    }}
    [data-testid="stTabs"] button[role="tab"][aria-selected="true"] {{
      color: var(--if-accent-text) !important;
      background: var(--if-accent) !important;
      border-color: var(--if-accent) !important;
      border-bottom: 3px solid var(--if-accent-hover) !important;
      box-shadow: 0 5px 14px color-mix(in srgb, var(--if-accent) 20%, transparent);
    }}
    [data-testid="stTabs"] button[role="tab"][aria-selected="true"] * {{ color: var(--if-accent-text) !important; }}
    [data-testid="stTabs"] [data-baseweb="tab-highlight"],
    [data-testid="stTabs"] [data-baseweb="tab-border"],
    [data-testid="stTabs"] [data-baseweb="tab-highlight"]::after {{ background: var(--if-accent) !important; border-color:var(--if-accent) !important; }}
    [data-testid="stTabs"] [role="tabpanel"] {{ padding-top: 1.25rem; }}

    [data-testid="stMetric"] {{
      background: linear-gradient(145deg,var(--if-panel),var(--if-panel-alt)) !important;
      border: 1px solid var(--if-border);
      border-top:2px solid var(--if-accent);
      padding: 1rem 1.05rem;
      border-radius: 13px;
      box-shadow: var(--if-shadow);
    }}
    [data-testid="stMetricLabel"] p {{ color: var(--if-accent) !important; font-size: .78rem; font-weight:700; }}
    [data-testid="stMetricValue"] {{ color: var(--if-text) !important; letter-spacing: -.04em; }}
    [data-testid="stDataFrame"] {{
      background: var(--if-table-bg) !important;
      border: 1px solid var(--if-border);
      border-radius: 11px;
      overflow: hidden;
      --gdg-bg-cell: var(--if-table-bg);
      --gdg-bg-cell-medium: var(--if-table-alt);
      --gdg-bg-header: var(--if-table-head);
      --gdg-bg-header-hovered: var(--if-accent-hover);
      --gdg-bg-header-has: var(--if-accent-hover);
      --gdg-text-dark: var(--if-text);
      --gdg-text-medium: var(--if-muted);
      --gdg-text-light: var(--if-muted);
      --gdg-text-bubble: var(--if-text);
      --gdg-text-header: var(--if-table-head-text);
      --gdg-text-header-selected: var(--if-table-head-text);
      --gdg-bg-icon-header: var(--if-accent);
      --gdg-fg-icon-header: var(--if-accent-text);
      --gdg-bg-bubble: var(--if-panel-alt);
      --gdg-bg-bubble-selected: var(--if-tab-selected);
      --gdg-bg-search-result: var(--if-tab-selected);
      --gdg-border-color: var(--if-border);
      --gdg-horizontal-border-color: var(--if-border);
      --gdg-link-color: var(--if-accent);
      --gdg-accent-color: var(--if-accent);
      --gdg-accent-fg: var(--if-accent-text);
    }}
    [data-testid="stDataFrame"] > div {{ background: var(--if-table-bg) !important; }}
    [data-testid="stTable"] {{ background: var(--if-table-bg) !important; border: 1px solid var(--if-border); border-radius: 11px; overflow: hidden; }}
    [data-testid="stTable"] table {{ width:100%; border-collapse:separate !important; border-spacing:0 !important; background:var(--if-table-bg) !important; color:var(--if-text) !important; }}
    [data-testid="stTable"] thead th,
    [data-testid="stTable"] th {{ background:var(--if-table-head) !important; color:var(--if-table-head-text) !important; border-color:var(--if-border) !important; font-weight:750 !important; }}
    [data-testid="stTable"] tbody tr:nth-child(even) td {{ background:var(--if-table-alt) !important; }}
    [data-testid="stTable"] tbody tr:hover td {{ background:var(--if-tab-selected) !important; }}
    [data-testid="stTable"] td {{ background:var(--if-table-bg) !important; color:var(--if-text) !important; border-color:var(--if-border) !important; }}

    [data-testid="stTextInput"] input,
    [data-testid="stTextArea"] textarea,
    [data-testid="stNumberInput"] input,
    [data-testid="stDateInput"] input {{
      background: var(--if-input) !important;
      color: var(--if-text) !important;
      border-color: var(--if-border) !important;
      border-radius: 8px !important;
      -webkit-text-fill-color: var(--if-text) !important;
      color-scheme: {p['color_scheme']};
    }}
    [data-testid="stDateInput"] [data-baseweb="input"],
    [data-testid="stDateInput"] [data-baseweb="input"] > div,
    [data-testid="stSelectbox"] [data-baseweb="select"],
    [data-testid="stSelectbox"] [data-baseweb="select"] > div,
    [data-testid="stMultiSelect"] [data-baseweb="select"],
    [data-testid="stMultiSelect"] [data-baseweb="select"] > div {{
      background: var(--if-input) !important;
      color: var(--if-text) !important;
      border-color: var(--if-border) !important;
      border-radius: 8px !important;
      box-shadow: none !important;
    }}
    [data-testid="stSelectbox"] [data-baseweb="select"] > div > div,
    [data-testid="stMultiSelect"] [data-baseweb="select"] > div > div,
    [data-testid="stDateInput"] [data-baseweb="input"] > div {{
      background: transparent !important;
      color: var(--if-text) !important;
    }}
    [data-testid="stSelectbox"] [data-baseweb="select"] *,
    [data-testid="stMultiSelect"] [data-baseweb="select"] *,
    [data-testid="stDateInput"] [data-baseweb="input"] * {{
      color: var(--if-text) !important;
      -webkit-text-fill-color: var(--if-text) !important;
      opacity: 1;
    }}
    [data-testid="stSelectbox"] [data-baseweb="select"] > div,
    [data-testid="stSelectbox"] [data-baseweb="select"] [role="combobox"],
    [data-testid="stMultiSelect"] [data-baseweb="select"] > div,
    [data-testid="stMultiSelect"] [data-baseweb="select"] [role="combobox"] {{
      background-color:var(--if-input) !important;
      color:var(--if-text) !important;
      border-color:var(--if-border) !important;
    }}
    [data-testid="stSelectbox"] [data-baseweb="select"] [role="combobox"] > div,
    [data-testid="stMultiSelect"] [data-baseweb="select"] [role="combobox"] > div {{
      background:transparent !important;
    }}
    [data-testid="stDateInput"] button,
    [data-testid="stDateInput"] svg,
    [data-testid="stSelectbox"] svg,
    [data-testid="stMultiSelect"] svg {{ color: var(--if-muted) !important; fill: var(--if-muted) !important; }}
    input:-webkit-autofill,
    input:-webkit-autofill:hover,
    input:-webkit-autofill:focus {{
      -webkit-text-fill-color: var(--if-text) !important;
      box-shadow: 0 0 0 1000px var(--if-input) inset !important;
      transition: background-color 9999s ease-out 0s;
    }}
    [data-baseweb="popover"], [data-baseweb="calendar"] {{
      background: var(--if-panel) !important;
      color: var(--if-text) !important;
      border-color: var(--if-border) !important;
    }}
    [data-baseweb="calendar"] * {{ color: var(--if-text) !important; }}
    [data-baseweb="calendar"] button {{ background: transparent !important; border-color: transparent !important; }}
    [data-baseweb="calendar"] button[aria-selected="true"],
    [data-baseweb="calendar"] button[aria-current="date"] {{
      background: var(--if-accent) !important;
      color: var(--if-accent-text) !important;
    }}
    [data-testid="stRadio"] label,
    [data-testid="stCheckbox"] label,
    [data-testid="stToggle"] label {{ color: var(--if-text) !important; opacity:1 !important; }}
    input[type="radio"], input[type="checkbox"] {{ accent-color: var(--if-accent) !important; }}

    [data-testid="stRadio"] label[data-baseweb="radio"] > div:first-of-type,
    [data-testid="stRadio"] [data-baseweb="radio"] > div:first-of-type {{
      width:1.05rem !important; height:1.05rem !important; min-width:1.05rem !important;
      border:2px solid var(--if-accent) !important; border-radius:50% !important;
      background:var(--if-panel) !important; box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--if-accent) 12%,transparent) !important;
    }}
    [data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) > div:first-of-type,
    [data-testid="stRadio"] [data-baseweb="radio"]:has(input:checked) > div:first-of-type,
    [data-testid="stRadio"] [role="radio"][aria-checked="true"] {{
      border-color:var(--if-accent) !important; background:var(--if-accent) !important;
    }}
    [data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) > div:first-of-type::after,
    [data-testid="stRadio"] [data-baseweb="radio"]:has(input:checked) > div:first-of-type::after {{
      content:""; display:block; width:.34rem; height:.34rem; margin:.21rem auto;
      border-radius:50%; background:var(--if-accent-text) !important;
    }}
    [data-testid="stRadio"] [role="radio"] {{ accent-color:var(--if-accent) !important; color:var(--if-accent) !important; }}
    [data-testid="stRadio"] [role="radio"] svg,
    [data-testid="stRadio"] [data-baseweb="radio"] svg {{ color:var(--if-accent) !important; fill:var(--if-accent) !important; }}
    [data-testid="stRadio"] [role="radio"] svg circle,
    [data-testid="stRadio"] [data-baseweb="radio"] svg circle {{ stroke:var(--if-accent) !important; }}
    [data-testid="stRadio"] [data-baseweb="radio"] input:checked ~ div svg circle {{ fill:var(--if-accent-text) !important; }}
    [data-testid="stCheckbox"] label[data-baseweb="checkbox"] > div:first-of-type,
    [data-testid="stCheckbox"] [data-baseweb="checkbox"] > div:first-of-type {{
      border:2px solid var(--if-accent) !important; border-radius:5px !important;
      background:var(--if-panel) !important; box-shadow:none !important;
    }}
    [data-testid="stCheckbox"] label[data-baseweb="checkbox"]:has(input:checked) > div:first-of-type,
    [data-testid="stCheckbox"] [data-baseweb="checkbox"]:has(input:checked) > div:first-of-type,
    [data-testid="stCheckbox"] [role="checkbox"][aria-checked="true"] {{
      background:var(--if-accent) !important; border-color:var(--if-accent) !important;
    }}
    [data-testid="stCheckbox"] [role="checkbox"] svg {{ color:var(--if-accent-text) !important; fill:var(--if-accent-text) !important; }}
    [data-testid="stSlider"] [role="slider"] {{ background: var(--if-accent) !important; border-color: var(--if-accent) !important; }}
    [data-testid="stSlider"] [data-baseweb="slider"] > div {{ background-color: var(--if-border) !important; }}
    [data-testid="stSlider"] [data-baseweb="slider"] > div > div {{ background-color: var(--if-accent) !important; }}
    [data-testid="stSegmentedControl"] button[aria-pressed="true"],
    [data-testid="stSegmentedControl"] [aria-checked="true"] {{
      background:var(--if-accent) !important; color:var(--if-accent-text) !important; border-color:var(--if-accent) !important;
    }}
    [data-testid="stSegmentedControl"] button[aria-pressed="true"] * {{ color:var(--if-accent-text) !important; }}

    [data-testid="stExpander"] {{
      border: 1px solid var(--if-border) !important;
      border-left:3px solid var(--if-accent) !important;
      border-radius: 10px !important;
      background: var(--if-panel) !important;
      overflow: hidden;
    }}
    [data-testid="stExpander"] details,
    [data-testid="stExpander"] details > summary,
    [data-testid="stExpander"] details > summary > span,
    [data-testid="stExpander"] [data-testid="stExpanderDetails"],
    [data-testid="stExpander"] [data-testid="stExpanderDetails"] > div {{
      background: var(--if-panel) !important;
      color: var(--if-text) !important;
      border-color: var(--if-border) !important;
    }}
    [data-testid="stExpander"] summary,
    [data-testid="stExpander"] summary span,
    [data-testid="stExpander"] summary p,
    [data-testid="stExpander"] summary svg {{
      color: var(--if-text) !important;
      fill: var(--if-text) !important;
      opacity: 1 !important;
    }}
    [data-testid="stExpander"] summary:hover {{ background: var(--if-panel-alt) !important; }}
    [data-testid="stAlert"] {{
      border-radius: 10px;
      background: var(--if-panel-alt) !important;
      border: 1px solid var(--if-border) !important;
      color: var(--if-text) !important;
    }}
    [data-testid="stAlert"] p, [data-testid="stAlert"] span {{ color: var(--if-text) !important; }}
    [data-testid="stMarkdownContainer"] pre,
    [data-testid="stCode"] {{
      background: var(--if-panel-alt) !important;
      border: 1px solid var(--if-border);
      border-radius: 9px;
    }}

    body [data-baseweb="popover"],
    body [data-baseweb="popover"] > div,
    body [data-baseweb="menu"],
    body [data-baseweb="menu"] ul,
    body [role="listbox"] {{
      background: var(--if-panel) !important;
      color: var(--if-text) !important;
      border: 1px solid var(--if-border) !important;
      color-scheme: {p['color_scheme']} !important;
    }}
    body [data-baseweb="menu"] li,
    body [data-baseweb="menu"] [role="option"],
    body [role="listbox"] [role="option"],
    body [role="option"] {{
      background: var(--if-panel) !important;
      color: var(--if-text) !important;
      -webkit-text-fill-color: var(--if-text) !important;
      opacity: 1 !important;
    }}
    body [data-baseweb="menu"] *, body [role="listbox"] * {{
      color: var(--if-text) !important;
      -webkit-text-fill-color: var(--if-text) !important;
    }}
    body [role="option"]:hover,
    body [role="option"][aria-selected="true"],
    body [data-baseweb="menu"] li:hover {{
      background: var(--if-tab-selected) !important;
      color: var(--if-text) !important;
    }}

    [data-testid="stSelectbox"] [data-baseweb="select"],
    [data-testid="stMultiSelect"] [data-baseweb="select"],
    [data-testid="stSelectbox"] [data-baseweb="select"] > div,
    [data-testid="stMultiSelect"] [data-baseweb="select"] > div,
    [data-testid="stSelectbox"] [data-baseweb="select"] [role="combobox"],
    [data-testid="stMultiSelect"] [data-baseweb="select"] [role="combobox"] {{
      background: var(--if-input) !important;
      color: var(--if-text) !important;
      border-color: var(--if-border) !important;
      box-shadow: none !important;
    }}
    [data-testid="stSelectbox"] [data-baseweb="select"] *,
    [data-testid="stMultiSelect"] [data-baseweb="select"] * {{
      color: var(--if-text) !important;
      -webkit-text-fill-color: var(--if-text) !important;
      background-color: transparent !important;
      opacity: 1 !important;
    }}
    select, select option {{
      background: var(--if-input) !important;
      color: var(--if-text) !important;
      color-scheme: {p['color_scheme']} !important;
    }}

    [data-testid="stNumberInput"] button,
    [data-testid="stDateInput"] button {{
      background: var(--if-panel-alt) !important;
      color: var(--if-text) !important;
      border-color: var(--if-border) !important;
      box-shadow: none !important;
    }}
    [data-testid="stNumberInput"] button svg,
    [data-testid="stDateInput"] button svg {{
      color: var(--if-text) !important;
      fill: var(--if-text) !important;
    }}
    [data-testid="stFileUploader"] section {{
      background: var(--if-panel-alt) !important;
      border: 1px dashed var(--if-accent) !important;
      border-radius: 10px !important;
      color: var(--if-text) !important;
    }}
    [data-testid="stFileUploader"] section *,
    [data-testid="stFileUploader"] section small,
    [data-testid="stFileUploader"] section span,
    [data-testid="stFileUploader"] section svg {{
      color: var(--if-text) !important;
      fill: currentColor;
      opacity: 1 !important;
    }}

    [data-testid="stFileUploader"] button,
    [data-testid="stFileUploader"] button[kind],
    [data-testid="stFileUploader"] [data-testid^="stBaseButton"] {{
      background: var(--if-accent) !important;
      color: var(--if-accent-text) !important;
      border: 1px solid var(--if-accent) !important;
      border-radius: 8px !important;
      box-shadow: none !important;
    }}
    [data-testid="stFileUploader"] button *,
    [data-testid="stFileUploader"] button span,
    [data-testid="stFileUploader"] button svg {{
      color: var(--if-accent-text) !important;
      fill: var(--if-accent-text) !important;
    }}
    .stButton > button, .stDownloadButton > button,
    [data-testid="stFormSubmitButton"] button,
    [data-testid="stBaseButton-secondary"] {{
      border-radius: 9px !important;
      border: 1px solid var(--if-border) !important;
      min-height: 2.55rem;
      font-weight: 620;
      background: var(--if-panel-alt) !important;
      color: var(--if-text) !important;
      box-shadow: none !important;
    }}
    .stButton > button *, .stDownloadButton > button *,
    [data-testid="stFormSubmitButton"] button *,
    [data-testid="stBaseButton-secondary"] * {{ color: inherit !important; }}
    .stButton > button:hover, .stDownloadButton > button:hover,
    [data-testid="stFormSubmitButton"] button:hover {{
      border-color: var(--if-accent) !important;
      background:var(--if-tab-selected) !important;
      color: var(--if-text) !important;
    }}
    input:focus, textarea:focus, [data-baseweb="select"]:focus-within {{
      border-color:var(--if-accent) !important;
      box-shadow:0 0 0 1px var(--if-accent) !important;
    }}
    .stButton > button[kind="primary"],
    .stDownloadButton > button[kind="primary"],
    [data-testid="stFormSubmitButton"] button[kind="primary"],
    [data-testid="stBaseButton-primary"] {{
      background: var(--if-accent) !important;
      color: var(--if-accent-text) !important;
      border-color: var(--if-accent) !important;
    }}
    .stButton > button[kind="primary"] *,
    [data-testid="stFormSubmitButton"] button[kind="primary"] *,
    [data-testid="stBaseButton-primary"] * {{ color: var(--if-accent-text) !important; }}
    .stButton > button[kind="primary"]:hover,
    [data-testid="stFormSubmitButton"] button[kind="primary"]:hover,
    [data-testid="stBaseButton-primary"]:hover {{
      background: var(--if-accent-hover) !important;
      color: var(--if-accent-text) !important;
    }}

    .if-brand {{ display:flex; align-items:center; gap:.8rem; padding:.35rem 0 1.25rem; border-bottom:2px solid var(--if-accent); margin-bottom:1.3rem; }}
    .if-mark {{ width:2.55rem; height:2.55rem; display:grid; place-items:center; border-radius:10px; background:var(--if-accent) !important; color:var(--if-accent-text) !important; font-size:.83rem; font-weight:850; letter-spacing:-.04em; box-shadow:0 5px 14px color-mix(in srgb, var(--if-accent) 28%, transparent); }}
    .if-brand-name {{ color:var(--if-text); font-weight:740; font-size:1.05rem; letter-spacing:-.035em; }}
    .if-brand-sub {{ color:var(--if-muted); font-size:.69rem; margin-top:.12rem; letter-spacing:.08em; text-transform:uppercase; }}
    .if-hero {{ padding:.45rem .85rem 1.05rem; display:flex; align-items:flex-end; justify-content:space-between; gap:1rem; border-left:4px solid var(--if-accent); border-bottom:1px solid var(--if-border); background:linear-gradient(105deg,var(--if-tab-selected),transparent 62%); border-radius:0 0 0 10px; margin-bottom:.35rem; }}
    .if-kicker {{ color:var(--if-accent) !important; font-size:.69rem; font-weight:850; letter-spacing:.16em; text-transform:uppercase; margin-bottom:.55rem; }}
    .if-hero-title {{ font-size:2.25rem; line-height:1.05; letter-spacing:-.055em; font-weight:780; color:var(--if-text); }}
    .if-hero-title::after {{ content:""; display:block; width:3rem; height:.22rem; margin-top:.48rem; border-radius:999px; background:var(--if-accent); }}
    .if-hero-copy {{ color:var(--if-muted); max-width:42rem; font-size:.91rem; margin-top:.55rem; line-height:1.55; }}
    .if-live-pill {{ white-space:nowrap; padding:.48rem .78rem; border:1px solid var(--if-accent); border-radius:999px; color:var(--if-text); background:var(--if-tab-selected); font-size:.73rem; font-weight:680; }}
    .if-section-head {{ display:flex; justify-content:space-between; align-items:baseline; gap:1rem; margin:.65rem 0 .85rem; padding:.35rem .65rem; border-left:3px solid var(--if-accent); background:linear-gradient(90deg,var(--if-tab-selected),transparent 72%); border-radius:0 7px 7px 0; }}
    .if-section-head h3 {{ margin:0; color:var(--if-text); font-size:1.04rem; }}
    .if-section-head span {{ color:var(--if-muted); font-size:.75rem; }}
    .if-card {{ background:var(--if-panel); border:1px solid var(--if-border); border-top:2px solid var(--if-accent); border-radius:13px; padding:1rem 1.1rem; box-shadow:var(--if-shadow); }}
    .if-card + .if-card {{ margin-top:.8rem; }}
    .if-card-label {{ color:var(--if-muted); font-size:.69rem; text-transform:uppercase; letter-spacing:.11em; font-weight:700; margin-bottom:.45rem; }}
    .if-card-value {{ color:var(--if-text); font-size:1.12rem; font-weight:650; letter-spacing:-.025em; overflow-wrap:anywhere; }}
    .if-card-note {{ color:var(--if-muted); font-size:.78rem; margin-top:.35rem; line-height:1.45; }}
    .if-status {{ display:flex; align-items:center; gap:.7rem; border:1px solid var(--if-border); border-left:4px solid var(--if-accent); background:var(--if-panel); border-radius:11px; padding:.85rem 1rem; margin:.5rem 0 1rem; }}
    .if-status.approved {{ border-left-color:var(--if-success); }}
    .if-status.awaiting {{ border-left-color:var(--if-warning); }}
    .if-status.rejected {{ border-left-color:var(--if-danger); }}
    .if-status-main {{ color:var(--if-text); font-size:1.03rem; font-weight:720; }}
    .if-status-sub {{ color:var(--if-muted); font-size:.76rem; margin-top:.16rem; }}
    .if-status-tag {{ margin-left:auto; color:var(--if-muted); font-size:.72rem; letter-spacing:.08em; text-transform:uppercase; }}
    .if-field-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:.55rem; }}
    .if-field {{ min-width:0; background:var(--if-panel-alt); border:1px solid var(--if-border); border-radius:9px; padding:.72rem .78rem; }}
    .if-field-label {{ color:var(--if-muted); font-size:.67rem; letter-spacing:.075em; text-transform:uppercase; margin-bottom:.28rem; }}
    .if-field-value {{ color:var(--if-text); font-size:.88rem; font-weight:610; overflow-wrap:anywhere; }}
    .if-pdf-frame {{ width:100%; height:100%; border:0; background:var(--if-panel); border-radius:8px; }}
    .if-pdf-shell {{ height:740px; background:var(--if-panel-alt); border:1px solid var(--if-border); border-radius:11px; padding:.55rem; overflow:hidden; }}
    .if-empty {{ border:1px dashed var(--if-border); border-radius:12px; padding:2rem 1.2rem; color:var(--if-muted); text-align:center; background:var(--if-panel); }}
    .if-empty strong {{ display:block; color:var(--if-text); font-size:.95rem; margin-bottom:.35rem; }}
    .if-muted {{ color:var(--if-muted); }}
    .if-admin-pill {{ border:1px solid var(--if-success); background:var(--if-success-bg); color:var(--if-success); padding:.35rem .6rem; border-radius:999px; font-size:.72rem; display:inline-block; }}
    .if-risk {{ display:inline-flex; align-items:center; width:max-content; margin-top:-.45rem; padding:.2rem .5rem; border-radius:999px; border:1px solid currentColor; font-size:.72rem; font-weight:680; line-height:1.25; }}
    .if-risk.low {{ color:var(--if-risk-low); background:var(--if-risk-low-bg); }}
    .if-risk.moderate {{ color:var(--if-risk-moderate); background:var(--if-risk-moderate-bg); }}
    .if-risk.high {{ color:var(--if-risk-high); background:var(--if-risk-high-bg); }}
    .if-risk.critical {{ color:var(--if-risk-critical); background:var(--if-risk-critical-bg); }}
    .if-risk.unscored {{ color:var(--if-muted); background:var(--if-panel-alt); }}

    .if-chart {{ background:var(--if-chart-bg); border:1px solid var(--if-border); border-radius:12px; padding:1rem 1.1rem; box-shadow:var(--if-shadow); }}
    .if-chart-row {{ display:grid; grid-template-columns:minmax(7rem, 25%) minmax(4rem, 1fr) minmax(4rem, 6rem); align-items:center; gap:.85rem; padding:.48rem 0; }}
    .if-chart-row + .if-chart-row {{ border-top:1px solid var(--if-border); }}
    .if-chart-label {{ color:var(--if-text); font-size:.8rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
    .if-chart-track {{ height:.62rem; background:var(--if-chart-track); border-radius:999px; overflow:hidden; }}
    .if-chart-fill {{ height:100%; min-width:0; border-radius:999px; }}
    .if-chart-value {{ color:var(--if-text); font-size:.78rem; font-variant-numeric:tabular-nums; text-align:right; white-space:nowrap; }}
    .if-chart-foot {{ color:var(--if-muted); font-size:.7rem; margin-top:.55rem; }}

    @media(max-width:1100px) {{
      [data-testid="stTabs"] [role="tablist"] {{ justify-content:flex-start; overflow-x:auto; }}
      [data-testid="stTabs"] button[role="tab"] {{ flex:0 0 auto; min-width:112px; }}
    }}
    @media(max-width:900px) {{
      .if-hero-title {{font-size:1.8rem}}
      .if-field-grid {{grid-template-columns:1fr}}
      .if-pdf-shell {{height:560px}}
      .if-hero {{align-items:flex-start; flex-direction:column}}
    }}
    @media(max-width:560px) {{
      .if-chart-row {{grid-template-columns:minmax(5rem, 28%) minmax(3rem, 1fr) minmax(3.2rem, 5rem); gap:.5rem;}}
    }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)
    return p
