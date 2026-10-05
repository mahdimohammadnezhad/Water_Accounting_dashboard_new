"""داشبورد هوشمند حسابداری آب — اجرا:  streamlit run app.py  (یا دوبار کلیک روی run_dashboard.bat)"""
import copy
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
from wa import charts, ui  # noqa: E402
from wa.build import get_base, is_fresh  # noqa: E402
from wa.config import GROUP_LABELS, GROUP_ORDER, list_configs, load_config, signature  # noqa: E402
from wa.engine import compute, restrict_members  # noqa: E402
from wa.table import COLOR_LEGEND, LAYOUTS, build_table, filt, to_excel_bytes, to_html  # noqa: E402
from wa.text import natural_key  # noqa: E402

st.set_page_config(page_title="داشبورد حسابداری آب", page_icon="💧", layout="wide",
                   initial_sidebar_state="expanded")
st.markdown(ui.CSS, unsafe_allow_html=True)


# ----------------------------------------------------------------------------- cached data
@st.cache_data(show_spinner=False)
def load_base(cfg_path, sig, force=False):
    return get_base(load_config(cfg_path), force=force, log=lambda *_: None)


@st.cache_data(show_spinner=False)
def run_engine(cfg_path, sig, mode, uses_json):
    cfg = load_config(cfg_path)
    return compute(load_base(cfg_path, sig), cfg, json.loads(uses_json), mode)


@st.cache_data(show_spinner=False)
def yearly_totals(cfg_path, sig, mode, uses_json, years, sbs, counties, uses_sel, layout, groups, restrict):
    cfg = load_config(cfg_path)
    base = load_base(cfg_path, sig)
    uses = json.loads(uses_json)
    W, RET, RES = run_engine(cfg_path, sig, mode, uses_json)
    rows = {}
    for y in years:
        _, tot = build_table(base, cfg, uses, W, RET, RES, y, list(sbs), list(counties), list(uses_sel),
                             layout, list(groups), restrict)
        rows[y] = tot
    return pd.DataFrame(rows).T


def multiselect_all(label, options, fmt=None, help=None):
    sel = st.multiselect(label, options, format_func=fmt or str, placeholder="همه", help=help)
    return list(sel) if sel else list(options)


def shade(styler, col, rgb, diverging=False):
    """Colour a dataframe column by magnitude (no matplotlib needed)."""
    vals = styler.data[col].abs()
    vmax = float(vals.max()) if len(vals) else 0

    def f(v):
        if vmax <= 0 or pd.isna(v) or abs(v) < 1e-9:
            return ""
        c = ("220,38,38" if v < 0 else "5,150,105") if diverging else rgb
        return f"background-color: rgba({c},{0.1 + 0.6 * abs(v) / vmax:.2f})"

    return styler.map(f, subset=[col])


def side_section(title):
    st.markdown(f"<div class='wa-side-sec'>{title}</div>", unsafe_allow_html=True)


# ----------------------------------------------------------------------------- sidebar
cfg_paths = list_configs()
if not cfg_paths:
    st.error("هیچ فایل پیکربندی در پوشه configs پیدا نشد.")
    st.stop()
cfgs = {str(p): load_config(p) for p in cfg_paths}

with st.sidebar:
    st.markdown("<div class='wa-side-title'>💧 تنظیمات نمایش</div>", unsafe_allow_html=True)
    side_section("🗂️ محدوده و سال")
    cfg_path = st.selectbox("حوضه / محدوده مطالعاتی", list(cfgs), format_func=lambda p: cfgs[p]["basin"]["name"])
    cfg = cfgs[cfg_path]
    sig = signature(cfg)
    if not is_fresh(cfg):
        with st.spinner("در حال خواندن فایل‌های ورودی و ساخت داده‌ها (فقط بار اول یا پس از تغییر فایل‌ها) ..."):
            load_base(cfg_path, sig, force=True)
    base = load_base(cfg_path, sig)
    meta = base["meta"]
    sb_label = cfg["spatial"]["sub_basin_label"]
    years = meta["years"]
    year = st.selectbox("سال آبی", years, index=len(years) - 1)

    side_section("📍 تقسیمات مکانی")
    mode = st.radio("مبنای تعیین شهرستان", ["attribute", "geo"],
                    index=0 if cfg["county_mode_default"] == "attribute" else 1,
                    format_func=lambda m: {"attribute": "ستون شهرستان در آمار",
                                           "geo": "شیپ‌فایل شهرستان‌ها (مکانی)"}[m],
                    help="ستون شهرستان: همان شهرستانی که در آمار چاه‌ها ثبت شده است. "
                         "مکانی: شهرستان از روی موقعیت چاه روی shahrestan.shp تعیین می‌شود.")
    all_sbs = meta["sub_basins"] + sorted(set(base["W"].sub_basin) - set(meta["sub_basins"]), key=natural_key)
    sbs = multiselect_all("زیرحوضه", all_sbs, fmt=lambda s: sb_label.format(id=s))
    ccol = "county_attr" if mode == "attribute" else "county_geo"
    all_counties = sorted(set(base["W"][ccol].dropna()) | set(base["RES"].county_geo.dropna()))
    counties = multiselect_all("شهرستان", all_counties)

    side_section("💧 کاربری و منبع")
    uses_cfg = copy.deepcopy(cfg["uses"])
    uses_all = [u["name"] for u in uses_cfg]
    uses_sel = multiselect_all("کاربری", uses_all)
    groups = multiselect_all("نوع منبع", GROUP_ORDER, fmt=lambda g: GROUP_LABELS[g])

    side_section("🧮 جدول")
    layout = st.selectbox("چیدمان ستون‌ها", list(LAYOUTS), format_func=LAYOUTS.get)
    restrict = False
    if layout == "excel":
        restrict = st.checkbox("فقط شهرستان‌های تعریف‌شده برای شرب و صنعت", value=True,
                               help="در قالب اکسل ستون‌های شرب و صنعت فقط برای شهرستان‌های فهرست‌شده در پیکربندی "
                                    "ساخته می‌شوند؛ با برداشتن تیک بقیه شهرستان‌ها هم ستون می‌گیرند.")
    cf = st.toggle("قالب‌بندی شرطی (رنگ بر اساس اندازه)", value=True)
    log_scale = st.toggle("مقیاس رنگ لگاریتمی", value=True, disabled=not cf,
                          help="با مقیاس لگاریتمی، اعداد کوچک هم رنگ قابل تشخیص می‌گیرند.")
    with st.expander("⚙️ ضرایب برگشت (قابل ویرایش)"):
        st.caption("تغییرات فوراً در همه جداول و نمودارها اعمال می‌شود.")
        for u in uses_cfg:
            c1, c2 = st.columns(2)
            u["return_coef"] = c1.number_input(f"{u['name']} — ضریب", 0.0, 1.0, float(u["return_coef"]), 0.05,
                                               key=f"coef_{cfg['basin']['key']}_{u['name']}")
            u["river_fraction"] = c2.number_input("سهم رودخانه", 0.0, 1.0, float(u["river_fraction"]), 0.05,
                                                  key=f"riv_{cfg['basin']['key']}_{u['name']}")
    st.divider()
    if st.button("🔄 خواندن دوباره فایل‌های ورودی", width="stretch"):
        st.cache_data.clear()
        with st.spinner("در حال ساخت دوباره داده‌ها ..."):
            load_base(cfg_path, sig, force=True)
        st.cache_data.clear()
        st.rerun()
    st.markdown(f"<div class='wa-note'>آخرین ساخت داده: {ui.fa(meta['built_at'])}</div>", unsafe_allow_html=True)

# ----------------------------------------------------------------------------- compute
uses_json = json.dumps(uses_cfg, ensure_ascii=False, sort_keys=True)
W, RET, RES = run_engine(cfg_path, sig, mode, uses_json)
t, totals = build_table(base, cfg, uses_cfg, W, RET, RES, year, sbs, counties, uses_sel, layout, groups, restrict)

cells = base["cells"]
geo_counties = counties if mode == "geo" else [c for c in counties if c in set(cells.county)]
share = float(cells[cells.sub_basin.isin(sbs) & cells.county.isin(geo_counties)].share.sum())
ind = base["indicators"].set_index("year")
num_cols = ["renew_surface", "renew_ground", "renew_total", "nonrenewable", "gw_available"]
ind_y = ind.loc[year, num_cols].astype(float) * share if year in ind.index else None
full_sb, full_ct = len(sbs) == len(all_sbs), len(counties) == len(all_counties)

# ----------------------------------------------------------------------------- banner + KPI cards
chips = [f"سال آبی {year}",
         "همه زیرحوضه‌ها" if full_sb else "زیرحوضه: " + "، ".join(sbs),
         "همه شهرستان‌ها" if full_ct else "شهرستان: " + "، ".join(counties),
         "شهرستان بر اساس " + ("آمار" if mode == "attribute" else "شیپ‌فایل"),
         LAYOUTS[layout]]
st.markdown(ui.hero("داشبورد حسابداری منابع و مصارف آب", cfg["basin"]["name"] + " — واحد: میلیون مترمکعب",
                    [ui.fa(c) for c in chips]), unsafe_allow_html=True)

if ind_y is not None:
    src_note = f"سیمای آب {ui.fa(year)}" + ("" if share > 0.999 else f" — {ui.fa(share * 100, '{:.0f}')}٪ مساحت")
    st.markdown("<div class='wa-sec-title'>منابع آب (سیمای آب)</div>" + ui.cards([
        {"label": "آب تجدیدپذیر کل", "value": ind_y.renew_total, "color": "#0e7490", "icon": "🌧️", "note": src_note},
        {"label": "تجدیدپذیر سطحی (رواناب)", "value": ind_y.renew_surface, "color": "#0284c7", "icon": "🏞️",
         "note": src_note},
        {"label": "تجدیدپذیر زیرزمینی (نفوذ)", "value": ind_y.renew_ground, "color": "#b45309", "icon": "💧",
         "note": src_note},
        {"label": "غیرتجدیدپذیر (کسری مخزن)", "value": ind_y.nonrenewable, "color": "#dc2626", "icon": "⚠️",
         "note": "قرینه تغییر ذخیره آبخوان (\u2066−ΔS\u2069)"},
    ]), unsafe_allow_html=True)
st.markdown("<div class='wa-sec-title'>مصارف و بیلان (جدول زیر)</div>" + ui.cards([
    {"label": "برداشت کل", "value": totals["withdrawal"], "color": "#2563eb", "icon": "🚰",
     "note": "سد + چاه + انتقالی + تصفیه‌خانه"},
    {"label": "آب برگشتی", "value": totals["return"], "color": "#0d9488", "icon": "↩️", "note": "ضریب برگشت × برداشت"},
    {"label": "مصرف (C)", "value": totals["consumption"], "color": "#7c3aed", "icon": "🔥", "note": "برداشت − برگشت"},
    {"label": "کنترل بیلان (B)", "value": totals["balance"], "color": "#dc2626" if totals["balance"] < 0 else "#059669",
     "icon": "⚖️", "note": "منابع در دسترس − مصرف", "tone": "neg" if totals["balance"] < 0 else "pos"},
]), unsafe_allow_html=True)

tabs = st.tabs(["📋 جدول منابع و مصارف", "📊 نمودارها", "📈 روند سالانه", "🧩 زیرحوضه × شهرستان", "🗺️ نقشه",
                "🔎 داده‌ها و کنترل کیفیت"])
Wsel = restrict_members(filt(W, year, sbs, counties, uses_sel), uses_cfg, restrict)
Wsel = Wsel[Wsel.source_group.isin(groups)]

# ----------------------------------------------------------------------------- tab: table
with tabs[0]:
    if cf:
        st.markdown(ui.legend(COLOR_LEGEND), unsafe_allow_html=True)
    st.markdown(f"<div class='wa-wrap'>{to_html(t, cf, log_scale)}</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='wa-note'>سطرها منابع‌اند و ستون‌ها کاربری × تفکیک × (برداشت | برگشت). برگشتی در سطرهای «بازه رودخانه» "
        "و «آبخوان» نشان می‌دهد آب برگشتی هر کاربری به کجا رفته است؛ در سطر «مجموع» برگشت کل = ضریب × برداشت است. "
        "«تصفیه خانه» سهمی از برگشت شرب است و در کنترل بیلان شمرده نمی‌شود. "
        "کنترل بیلان = حجم در دسترس سدها، آب زیرزمینی و انتقالی − مصارف.</div>", unsafe_allow_html=True)
    if restrict and totals["omitted"] > 1e-3:
        st.info(f"{ui.fa(totals['omitted'], '{:,.2f}')} م.م.م برداشت شرب/صنعت شهرستان‌هایی که در قالب اکسل ستون ندارند "
                f"(مثل نیشابور و فریمان) کنار گذاشته شده است. برای دیدن آن تیک «فقط شهرستان‌های تعریف‌شده» را بردارید.")
    if mode == "attribute" and not full_ct and set(counties) - set(cells.county):
        st.warning("حجم در دسترس آب زیرزمینی به تفکیک شهرستان از روی شیپ‌فایل شهرستان‌ها محاسبه می‌شود و این "
                   "شیپ‌فایل طرقبه-شاندیز و گلبهار را ندارد؛ برای این شهرستان‌ها ستون G آب زیرزمینی صفر است.")
    c1, c2, _ = st.columns([1, 1, 2])
    c1.download_button("⬇️ دانلود جدول (Excel)",
                       to_excel_bytes({"منابع و مصارف": t}, f"منابع و مصارف سال آبی {year} — {cfg['basin']['name']}"),
                       file_name=f"water_balance_{cfg['basin']['key']}_{year}.xlsx", width="stretch")
    c2.download_button("⬇️ داده جزئی برداشت‌ها (CSV)", Wsel.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"withdrawals_{cfg['basin']['key']}_{year}.csv", width="stretch")

# ----------------------------------------------------------------------------- tab: charts
with tabs[1]:
    if Wsel.empty:
        st.info("برای فیلترهای انتخابی برداشتی ثبت نشده است.")
    else:
        fig = charts.sankey(Wsel, uses_all)
        if fig:
            st.plotly_chart(fig, width="stretch")
        c1, c2 = st.columns([3, 2])
        c1.plotly_chart(charts.bar_use_by_group(Wsel, uses_sel), width="stretch")
        coef = {u["name"]: u["return_coef"] for u in uses_cfg}
        cons = {u: v * (1 - coef[u]) for u, v in Wsel.groupby("use").value.sum().items()}
        fig = charts.consumption_donut({u: cons.get(u, 0) for u in uses_sel}, uses_all)
        if fig:
            c2.plotly_chart(fig, width="stretch")

# ----------------------------------------------------------------------------- tab: trends
with tabs[2]:
    yt = yearly_totals(cfg_path, sig, mode, uses_json, tuple(years), tuple(sbs), tuple(counties), tuple(uses_sel),
                       layout, tuple(groups), restrict)
    Wall = restrict_members(filt(W, None, sbs, counties, uses_sel), uses_cfg, restrict)
    Wall = Wall[Wall.source_group.isin(groups)]
    by = Wall.pivot_table(index="year", columns="use", values="value", aggfunc="sum").reindex(years).fillna(0)
    c1, c2 = st.columns(2)
    c1.plotly_chart(charts.trend_withdrawals(by, uses_all), width="stretch")
    c2.plotly_chart(charts.trend_balance(yt), width="stretch")
    if len(ind):
        st.plotly_chart(charts.trend_indicators((ind[num_cols].astype(float) * share).reset_index()), width="stretch")
    show = yt[["resources", "withdrawal", "return", "consumption", "balance"]].rename(columns={
        "resources": "منابع در دسترس", "withdrawal": "برداشت", "return": "برگشت",
        "consumption": "مصرف (C)", "balance": "کنترل بیلان (B)"})
    st.dataframe(shade(show.style.format("{:,.2f}"), "کنترل بیلان (B)", None, diverging=True), width="stretch")

# ----------------------------------------------------------------------------- tab: sub-basin x county
with tabs[3]:
    st.markdown("<div class='wa-note'>سهم هر شهرستان از هر زیرحوضه: مجموع برداشت (منابع و کاربری‌های انتخابی) و مساحت."
                "</div>", unsafe_allow_html=True)
    lab = Wsel.sub_basin.map(lambda s: sb_label.format(id=s))
    m = Wsel.assign(sb=lab).pivot_table(index="sb", columns="county", values="value", aggfunc="sum").fillna(0)
    c1, c2 = st.columns(2)
    if len(m):
        m = m.loc[sorted(m.index, key=lambda s: natural_key(s.split()[-1]))]
        m.loc["جمع"] = m.sum()
        m["جمع"] = m.sum(axis=1)
        c1.plotly_chart(charts.heatmap(m, f"برداشت سال {year} (م.م.م)"), width="stretch")
    am = cells.assign(sb=cells.sub_basin.map(lambda s: sb_label.format(id=s))).pivot_table(
        index="sb", columns="county", values="area_km2", aggfunc="sum").fillna(0)
    fig = charts.heatmap(am.round(1), "مساحت (کیلومترمربع، از شیپ‌فایل‌ها)", fmt=",.1f", scale="Greens")
    if fig:
        c2.plotly_chart(fig, width="stretch")
    det = Wsel.assign(sb=lab, grp=Wsel.source_group.map(GROUP_LABELS)).pivot_table(
        index=["sb", "county", "grp"], columns="use", values="value", aggfunc="sum").fillna(0)
    if len(det):
        det = det[[u for u in uses_all if u in det.columns]]
        det["جمع"] = det.sum(axis=1)
        det.index.names = ["زیرحوضه", "شهرستان", "نوع منبع"]
        st.markdown("**جزئیات: زیرحوضه × شهرستان × نوع منبع × کاربری**")
        st.dataframe(shade(det.style.format("{:,.3f}"), "جمع", "37,99,235"), width="stretch", height=420)
        st.download_button("⬇️ دانلود این جدول (Excel)", to_excel_bytes({"زیرحوضه-شهرستان": det}, f"سال آبی {year}"),
                           file_name=f"subbasin_county_{cfg['basin']['key']}_{year}.xlsx")

# ----------------------------------------------------------------------------- tab: map
with tabs[4]:
    c1, c2 = st.columns([2, 3])
    basemap = c1.radio("نقشه پایه", list(charts.BASEMAPS), format_func=charts.BASEMAPS.get, horizontal=True)
    with c2:
        k1, k2, k3, k4 = st.columns(4)
        show_sb = k1.checkbox("زیرحوضه‌ها", True)
        show_ct = k2.checkbox("مرز شهرستان‌ها", True)
        show_w = k3.checkbox("چاه‌ها", True)
        show_d = k4.checkbox("سدها", True)
    wells = base["wells"].assign(county=base["wells"][ccol])
    wy = wells[(wells.year == year) & wells.sub_basin.isin(sbs) & wells.county.isin(counties) &
               wells.use.isin(uses_sel)]
    if "gw" not in groups:
        wy = wy.iloc[0:0]
    st.plotly_chart(charts.basin_map(base["shapes"], sbs, wy, base["dams"], uses_all, sb_label, basemap,
                                     show_sb, show_ct, show_w, show_d),
                    width="stretch", config={"scrollZoom": True})
    st.markdown("<div class='wa-note'>نقشه پایه OpenStreetMap و ماهواره‌ای (Esri) به اینترنت نیاز دارند؛ حالت «ساده» "
                "بدون اینترنت کار می‌کند. با کلیک روی نام‌ها در راهنمای نقشه می‌توانید هر لایه را خاموش/روشن کنید.</div>",
                unsafe_allow_html=True)

# ----------------------------------------------------------------------------- tab: QC
with tabs[5]:
    rep = meta["report"]
    for w in rep["warnings"]:
        st.warning(w)
    st.markdown("**جدول بیلان سیمای آب (خوانده‌شده از PDFها)**")
    simaye = base["simaye"]
    if len(simaye):
        cols = {"year": "سال آبی", "renew_total": "تجدیدپذیر کل", "renew_surface": "سطحی (رواناب)",
                "renew_ground": "زیرزمینی (نفوذ)", "delta_s_reported": "تغییر ذخیره (گزارش‌شده)",
                "delta_s": "ΔS به‌کاررفته", "doosti_transfer": "انتقالی سد دوستی", "file": "فایل PDF",
                "page": "صفحه", "derived": "توضیح"}
        st.dataframe(simaye[[c for c in cols if c in simaye]].rename(columns=cols).fillna(""), width="stretch",
                     hide_index=True)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**سدها و موقعیت آنها**")
        st.dataframe(base["dams"].rename(columns={
            "dam": "سد", "sub_basin": "زیرحوضه", "location_county": "شهرستان (موقعیت نقطه)",
            "county": "شهرستان (آمار سد)", "lon": "طول جغرافیایی", "lat": "عرض جغرافیایی"}).drop(
            columns=["x", "y"], errors="ignore"), width="stretch", hide_index=True)
    with c2:
        st.markdown("**جزئیات ورود داده**")
        st.json(rep["info"], expanded=False)
    st.markdown("**آمار سدها (Amar_SAD)**")
    ds = base["dam_stats"].rename(columns={
        "raw_name": "نام در فایل", "location": "موقعیت", "begin": "حجم ابتدای سال", "inflow": "ورودی",
        "end": "حجم انتهای سال", "year": "سال آبی", "dam": "سد", "sub_basin": "زیرحوضه", "county": "شهرستان"})
    st.dataframe(ds, width="stretch", height=260, hide_index=True)
    st.markdown("**داده‌های پایه (همه سال‌ها)**")
    c1, c2, c3 = st.columns(3)
    c1.download_button("⬇️ برداشت‌ها (CSV)", W.to_csv(index=False).encode("utf-8-sig"), "withdrawals_all.csv")
    c2.download_button("⬇️ آب برگشتی (CSV)", RET.to_csv(index=False).encode("utf-8-sig"), "returns_all.csv")
    c3.download_button("⬇️ منابع در دسترس (CSV)", RES.to_csv(index=False).encode("utf-8-sig"), "resources_all.csv")
    st.caption(f"ساخت داده: {meta['built_at']} ({meta['seconds']} ثانیه). مقایسه با اکسل نمونه: python validate_excel.py")
