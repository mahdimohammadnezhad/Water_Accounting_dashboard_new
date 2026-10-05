"""HTML/CSS pieces of the dashboard (RTL, Vazirmatn, cards, banner)."""
from html import escape

FA_DIGITS = str.maketrans("0123456789.,", "۰۱۲۳۴۵۶۷۸۹٫٬")


def fa(x, fmt="{:,.1f}"):
    """Number -> Persian digits. Values like '1402-03' are wrapped in an LTR isolate so they don't flip in RTL."""
    if x is None:
        return "—"
    s = (fmt.format(x) if isinstance(x, (int, float)) else str(x)).translate(FA_DIGITS)
    return s if isinstance(x, (int, float)) else ltr_numbers(s)


def ltr_numbers(s):
    import re
    return re.sub(r"([۰-۹0-9][۰-۹0-9٫٬.,:/\- ]*[۰-۹0-9])", "\u2066\\1\u2069", s)


CSS = """
<style>
@font-face { font-family: 'Vazirmatn'; src: url('app/static/fonts/Vazirmatn-Variable.woff2') format('woff2');
             font-weight: 100 900; font-display: swap; }
html, body, .stApp, button, input, textarea, select, label, p, li, h1, h2, h3, h4, h5, h6, span, div {
  font-family: 'Vazirmatn', Tahoma, sans-serif; }
.stApp, section[data-testid="stSidebar"], [data-testid="stMain"] { direction: rtl; text-align: right; }
[data-testid="stPlotlyChart"], .js-plotly-plot, [data-testid="stDataFrame"], [data-testid="stJson"] { direction: ltr; }
[data-testid="stMainBlockContainer"] { padding-top: 3.2rem; max-width: 1700px; }
header[data-testid="stHeader"] { background: transparent; }
[data-testid="stAppDeployButton"] { display: none; }
[data-testid="stSidebarHeader"] { height: 0.5rem; }
section[data-testid="stSidebar"] { border-left: 1px solid #dbe5ef; border-right: none; }
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] { padding-top: 0.6rem; }
.wa-side-title { font-weight: 800; font-size: 1.15rem; color: #0b3a5b; margin: 0 0 .2rem 0; }
.wa-side-sec { font-weight: 700; font-size: .86rem; color: #0e7490; margin: .9rem 0 .2rem 0;
               border-bottom: 1px solid #e2e8f0; padding-bottom: .25rem; }

/* banner */
.wa-hero { background: linear-gradient(120deg, #0b3a5b 0%, #0e7490 60%, #14b8a6 100%); color: #fff;
           border-radius: 16px; padding: 18px 26px; margin-bottom: 14px; box-shadow: 0 6px 20px rgba(11,58,91,.18);
           position: relative; overflow: hidden; }
.wa-hero:after { content: ""; position: absolute; left: -60px; top: -60px; width: 220px; height: 220px;
                 border-radius: 50%; background: rgba(255,255,255,.07); }
.wa-hero h1 { color: #fff; font-size: 1.65rem; font-weight: 800; margin: 0 0 4px 0; padding: 0; }
.wa-hero .sub { opacity: .92; font-size: .98rem; }
.wa-chips { margin-top: 10px; display: flex; flex-wrap: wrap; gap: 6px; }
.wa-chip { background: rgba(255,255,255,.16); border: 1px solid rgba(255,255,255,.28); border-radius: 999px;
           padding: 2px 12px; font-size: .82rem; white-space: nowrap; }

/* KPI cards */
.wa-sec-title { font-weight: 700; color: #334155; font-size: .95rem; margin: 6px 2px 6px 0; }
.wa-cards { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 10px; }
.wa-card { background: #fff; border: 1px solid #e2e8f0; border-radius: 14px; padding: 12px 16px;
           box-shadow: 0 1px 3px rgba(15,23,42,.06); border-top: 4px solid var(--c); }
.wa-card .lbl { color: #64748b; font-size: .84rem; font-weight: 600; display: flex; gap: 6px; align-items: center; }
.wa-card .val { font-size: 1.7rem; font-weight: 800; color: #0f172a; line-height: 1.5; }
.wa-card .val small { font-size: .78rem; font-weight: 500; color: #94a3b8; margin-right: 4px; }
.wa-card .note { font-size: .76rem; color: #94a3b8; }
.wa-card.neg .val { color: #b42318; } .wa-card.pos .val { color: #047857; }
@media (max-width: 1100px) { .wa-cards { grid-template-columns: repeat(2, minmax(0, 1fr)); } }

/* tabs */
.stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid #dbe5ef; }
.stTabs [data-baseweb="tab"] { font-weight: 600; padding: 8px 14px; border-radius: 10px 10px 0 0; }
.stTabs [aria-selected="true"] { background: #e6f2f6; color: #0b3a5b; }

/* balance table */
.wa-legend { display: flex; flex-wrap: wrap; gap: 14px; font-size: .8rem; color: #475569; margin: 4px 0 8px 0; }
.wa-legend span.sw { display: inline-block; width: 34px; height: 10px; border-radius: 3px; margin-left: 5px;
                     vertical-align: middle; }
.wa-wrap { overflow: auto; max-height: 74vh; border: 1px solid #d6e0ea; border-radius: 12px; background: #fff;
           box-shadow: 0 1px 3px rgba(15,23,42,.05); }
table.wa-table { border-collapse: separate; border-spacing: 0; font-size: 12.5px; direction: rtl;
                 width: max-content; color: #1e293b; }
table.wa-table th, table.wa-table td { border-bottom: 1px solid #e5ebf1; border-left: 1px solid #e5ebf1;
                 padding: 5px 9px; white-space: nowrap; text-align: center; }
table.wa-table td { background: #fff; font-variant-numeric: tabular-nums; direction: ltr; min-width: 58px; }
table.wa-table thead th { position: sticky; z-index: 3; background: #0b3a5b; color: #fff; font-weight: 600; }
table.wa-table thead tr:nth-child(1) th { top: 0; }
table.wa-table thead tr:nth-child(2) th { top: 30px; }
table.wa-table thead tr:nth-child(3) th { top: 60px; }
table.wa-table thead tr:nth-child(4) th { top: 90px; }
table.wa-table thead th { height: 30px; box-sizing: border-box; }
table.wa-table tbody th { background: #f8fafc; text-align: right; font-weight: 700; position: sticky; z-index: 2; }
table.wa-table tbody th.level0 { right: 0; min-width: 96px; max-width: 96px; }
table.wa-table tbody th.level1 { right: 96px; min-width: 150px; }
table.wa-table thead th.blank, table.wa-table thead th.index_name { position: sticky; right: 0; z-index: 4; }
.wa-note { color: #64748b; font-size: .84rem; line-height: 1.9; }
</style>
"""


def hero(title, subtitle, chips):
    c = "".join(f'<span class="wa-chip">{escape(x)}</span>' for x in chips)
    return f'<div class="wa-hero"><h1>{escape(title)}</h1><div class="sub">{escape(subtitle)}</div>' \
           f'<div class="wa-chips">{c}</div></div>'


def cards(items):
    """items: list of dicts {label, value, color, icon?, note?, tone?}"""
    out = []
    for it in items:
        tone = it.get("tone", "")
        note = f'<div class="note">{escape(it["note"])}</div>' if it.get("note") else '<div class="note">&nbsp;</div>'
        out.append(f'<div class="wa-card {tone}" style="--c:{it["color"]}"><div class="lbl">{it.get("icon", "")} '
                   f'{escape(it["label"])}</div><div class="val">{fa(it["value"])}<small>م.م.م</small></div>{note}</div>')
    return f'<div class="wa-cards">{"".join(out)}</div>'


def legend(items):
    return '<div class="wa-legend">' + "".join(
        f'<div><span class="sw" style="background:{bg}"></span>{escape(t)}</div>' for t, bg in items) + "</div>"
