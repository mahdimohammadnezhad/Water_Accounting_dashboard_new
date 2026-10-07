"""Water accounting dashboard (Persian / English). Run:  streamlit run app.py  (or double-click run_dashboard.bat)"""
import copy
import json
import sys
import traceback
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
from wa import charts, ui  # noqa: E402
from wa.build import get_base, is_fresh  # noqa: E402
from wa.config import GROUP_LABELS, GROUP_ORDER, list_configs, load_config, signature  # noqa: E402
from wa.engine import compute, restrict_members  # noqa: E402
from wa.i18n import LANGS, msg, num, t, term, year as fyear  # noqa: E402
from wa.table import LAYOUTS, build_table, color_legend, filt, to_excel_bytes, to_html  # noqa: E402
from wa.text import natural_key  # noqa: E402

st.set_page_config(page_title="Water Accounting / حسابداری آب", page_icon="💧", layout="wide",
                   initial_sidebar_state="expanded")
lang = st.session_state.get("lang", "fa")
st.markdown(ui.css(lang), unsafe_allow_html=True)
T = lambda key, **kw: t(key, lang, **kw)  # noqa: E731
L = lambda s: term(s, lang)  # noqa: E731


def basin_name(c):
    return c["basin"].get("name_en") if lang == "en" and c["basin"].get("name_en") else c["basin"]["name"]


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


def multiselect_all(label, options, fmt=None, key=None):
    sel = st.multiselect(label, options, format_func=fmt or str, placeholder=T("all"), key=key)
    return list(sel) if sel else list(options)


def side_section(title):
    st.markdown(f"<div class='wa-side-sec'>{title}</div>", unsafe_allow_html=True)


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


def add_basin_panel():
    with st.expander(T("add_basin")):
        st.caption(T("add_help"))
        folder = st.text_input(T("add_folder"), placeholder=r"D:\data\Neyshabur")
        name = st.text_input(T("add_name"))
        if st.button(T("add_btn"), width="stretch", disabled=not folder):
            from wa.detect import scan, slug, write_config
            try:
                with st.spinner("..."):
                    logs = []
                    cfg_new, notes = scan(folder.strip().strip('"'), name=name or None, log=logs.append)
                    path = write_config(cfg_new, folder.strip().strip('"'), slug(Path(folder.strip().strip('"')).name))
                st.success(T("add_done", path=path.name))
                for n in notes:
                    st.warning(n)
                st.code("\n".join(logs))
                st.session_state["basin_pick"] = str(path)
                st.rerun()
            except Exception as e:  # noqa: BLE001
                st.error(T("add_fail", err=e))


# ----------------------------------------------------------------------------- sidebar
with st.sidebar:
    st.radio(T("language"), list(LANGS), format_func=LANGS.get, horizontal=True, key="lang")
    st.markdown(f"<div class='wa-side-title'>💧 {T('settings')}</div>", unsafe_allow_html=True)
    cfg_paths = [str(p) for p in list_configs()]
    if not cfg_paths:
        st.error(T("no_config"))
        add_basin_panel()
        st.stop()
    cfgs = {}
    for p in cfg_paths:
        try:
            cfgs[p] = load_config(p)
        except Exception as e:  # noqa: BLE001
            st.error(f"{Path(p).name}: {e}")
    side_section(T("sec_area"))
    pick = st.session_state.get("basin_pick")
    cfg_path = st.selectbox(T("basin"), list(cfgs), format_func=lambda p: basin_name(cfgs[p]),
                            index=list(cfgs).index(pick) if pick in cfgs else 0)
    cfg = cfgs[cfg_path]
    try:
        sig = signature(cfg)
        if not is_fresh(cfg):
            with st.spinner(T("building")):
                load_base(cfg_path, sig, force=True)
        base = load_base(cfg_path, sig)
    except Exception as e:  # noqa: BLE001
        st.error(f"{T('build_error')} {e}")
        with st.expander("traceback"):
            st.code(traceback.format_exc())
        add_basin_panel()
        st.stop()
    meta = base["meta"]
    sb_label = cfg["spatial"]["sub_basin_label"]
    years = meta["years"] or sorted(set(base["W"].year.dropna()))
    if not years:
        st.error(msg({"fa": "هیچ داده‌ای برای این حوضه خوانده نشد (بخش «داده‌ها و کنترل کیفیت» را ببینید).",
                      "en": "No data could be read for this basin (see the data & quality tab)."}, lang))
        for w in meta["report"]["warnings"]:
            st.warning(msg(w, lang))
        st.stop()
    year = st.selectbox(T("year"), years, index=len(years) - 1)

    side_section(T("sec_spatial"))
    modes = [m for m, ok in (("attribute", meta.get("has_county_attr", True)),
                             ("geo", meta.get("has_county_geo", True))) if ok] or ["geo"]
    default_mode = cfg["county_mode_default"] if cfg["county_mode_default"] in modes else modes[0]
    mode = st.radio(T("county_basis"), modes, index=modes.index(default_mode),
                    format_func=lambda m: T("basis_attr") if m == "attribute" else T("basis_geo"),
                    help=T("county_basis_help"))
    all_sbs = meta["sub_basins"] + sorted(set(base["W"].sub_basin.dropna()) - set(meta["sub_basins"]), key=natural_key)
    sbs = multiselect_all(T("sub_basin"), all_sbs, fmt=lambda s: L(sb_label.format(id=s)))
    ccol = "county_attr" if mode == "attribute" else "county_geo"
    all_counties = sorted(set(base["W"][ccol].dropna()) | set(base["RES"].county_geo.dropna()))
    counties = multiselect_all(T("county"), all_counties, fmt=L, key=f"ct_{mode}")

    side_section(T("sec_use"))
    uses_cfg = copy.deepcopy(meta.get("uses") or cfg["uses"])
    uses_all = [u["name"] for u in uses_cfg]
    uses_sel = multiselect_all(T("use"), uses_all, fmt=L)
    groups = multiselect_all(T("source_type"), GROUP_ORDER, fmt=lambda g: L(GROUP_LABELS[g]))

    side_section(T("sec_table"))
    layout = st.selectbox(T("layout"), list(LAYOUTS), format_func=lambda k: T(f"layout_{k}"))
    restrict = False
    if layout == "excel" and any(u.get("members") for u in uses_cfg):
        restrict = st.checkbox(T("restrict"), value=True, help=T("restrict_help"))
    cf = st.toggle(T("cf"), value=True)
    log_scale = st.toggle(T("log"), value=True, disabled=not cf, help=T("log_help"))
    with st.expander(T("coef_box")):
        st.caption(T("coef_caption"))
        for u in uses_cfg:
            c1, c2 = st.columns(2)
            u["return_coef"] = c1.number_input(f"{L(u['name'])} — {T('coef')}", 0.0, 1.0, float(u["return_coef"]),
                                               0.05, key=f"coef_{cfg['basin']['key']}_{u['name']}")
            u["river_fraction"] = c2.number_input(T("river_share"), 0.0, 1.0, float(u["river_fraction"]), 0.05,
                                                  key=f"riv_{cfg['basin']['key']}_{u['name']}")
    st.divider()
    if st.button(T("reload"), width="stretch"):
        st.cache_data.clear()
        with st.spinner(T("rebuilding")):
            load_base(cfg_path, sig, force=True)
        st.cache_data.clear()
        st.rerun()
    add_basin_panel()
    st.markdown(f"<div class='wa-note'>{T('built_at')}: {num(meta['built_at'], lang)}</div>", unsafe_allow_html=True)

# ----------------------------------------------------------------------------- compute
uses_json = json.dumps(uses_cfg, ensure_ascii=False, sort_keys=True)
W, RET, RES = run_engine(cfg_path, sig, mode, uses_json)
tbl, totals = build_table(base, cfg, uses_cfg, W, RET, RES, year, sbs, counties, uses_sel, layout, groups, restrict)

cells = base["cells"]
geo_counties = counties if mode == "geo" else [c for c in counties if c in set(cells.county)]
share = float(cells[cells.sub_basin.isin(sbs) & cells.county.isin(geo_counties)].share.sum())
ind = base["indicators"].set_index("year") if len(base["indicators"]) else pd.DataFrame()
num_cols = ["renew_surface", "renew_ground", "renew_total", "nonrenewable", "gw_available"]
ind_y = ind.loc[year, num_cols].astype(float) * share if year in ind.index else None
full_sb, full_ct = len(sbs) == len(all_sbs), len(counties) == len(all_counties)

# ----------------------------------------------------------------------------- banner + KPI cards
SEP = "، " if lang == "fa" else ", "
chips = [T("chip_year", y=fyear(year, lang)),
         T("chip_all_sb") if full_sb else T("chip_sb", x=SEP.join(L(sb_label.format(id=s)) for s in sbs)),
         T("chip_all_ct") if full_ct else T("chip_ct", x=SEP.join(L(c) for c in counties)),
         T("chip_attr") if mode == "attribute" else T("chip_geo"), T(f"layout_{layout}")]
st.markdown(ui.hero(T("hero_title"), f"{basin_name(cfg)} — {T('unit_sub')}", chips), unsafe_allow_html=True)

unit = T("unit_short")
if ind_y is not None and ind_y.notna().any():
    note = T("note_simaye", y=fyear(year, lang)) + ("" if share > 0.999 else
                                                    " — " + T("note_area", p=num(share * 100, lang, "{:.0f}")))
    st.markdown(f"<div class='wa-sec-title'>{T('sec_resources')}</div>" + ui.cards([
        {"label": T("renew_total"), "value": ind_y.renew_total, "color": "#0e7490", "icon": "🌧️", "note": note},
        {"label": T("renew_surface"), "value": ind_y.renew_surface, "color": "#0284c7", "icon": "🏞️", "note": note},
        {"label": T("renew_ground"), "value": ind_y.renew_ground, "color": "#b45309", "icon": "💧", "note": note},
        {"label": T("nonrenew"), "value": ind_y.nonrenewable, "color": "#dc2626", "icon": "⚠️", "note": T("note_ds")},
    ], lang, unit), unsafe_allow_html=True)
neg = totals["balance"] < 0
st.markdown(f"<div class='wa-sec-title'>{T('sec_uses')}</div>" + ui.cards([
    {"label": T("withdrawal"), "value": totals["withdrawal"], "color": "#2563eb", "icon": "🚰",
     "note": T("note_withdrawal")},
    {"label": T("return"), "value": totals["return"], "color": "#0d9488", "icon": "↩️", "note": T("note_return")},
    {"label": T("consumption"), "value": totals["consumption"], "color": "#7c3aed", "icon": "🔥",
     "note": T("note_consumption")},
    {"label": T("balance"), "value": totals["balance"], "color": "#dc2626" if neg else "#059669", "icon": "⚖️",
     "note": T("note_balance"), "tone": "neg" if neg else "pos"},
], lang, unit), unsafe_allow_html=True)

tab_map, tab_table, tab_charts, tab_trend, tab_matrix, tab_qc = st.tabs(
    [T("tab_map"), T("tab_table"), T("tab_charts"), T("tab_trend"), T("tab_matrix"), T("tab_qc")])
Wsel = restrict_members(filt(W, year, sbs, counties, uses_sel), uses_cfg, restrict)
Wsel = Wsel[Wsel.source_group.isin(groups)]

# ----------------------------------------------------------------------------- tab: table
with tab_table:
    if cf:
        st.markdown(ui.legend(color_legend(lang)), unsafe_allow_html=True)
    st.markdown(f"<div class='wa-wrap'>{to_html(tbl, cf, log_scale, lang)}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='wa-note'>{T('table_note')}</div>", unsafe_allow_html=True)
    if share < 0.999 and ind_y is not None:
        st.caption(T("area_caption", p=num(share * 100, lang, "{:.1f}") + "%"))
    if restrict and totals["omitted"] > 1e-3:
        st.info(T("omitted", v=num(totals["omitted"], lang, "{:,.2f}")))
    missing_geo = sorted(set(counties) - set(cells.county))
    if mode == "attribute" and not full_ct and missing_geo:
        st.warning(T("attr_warning", x=SEP.join(L(c) for c in missing_geo)))
    c1, c2, _ = st.columns([1, 1, 2])
    c1.download_button(T("dl_table"), to_excel_bytes({"منابع و مصارف": tbl}, T("table_title", y=year, b=basin_name(cfg)),
                                                     lang),
                       file_name=f"water_balance_{cfg['basin']['key']}_{year}.xlsx", width="stretch")
    c2.download_button(T("dl_csv"), Wsel.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"withdrawals_{cfg['basin']['key']}_{year}.csv", width="stretch")

# ----------------------------------------------------------------------------- tab: charts
with tab_charts:
    if Wsel.empty:
        st.info(T("no_data"))
    else:
        fig = charts.sankey(Wsel, uses_all, lang)
        if fig:
            st.plotly_chart(fig, width="stretch")
        c1, c2 = st.columns([3, 2])
        c1.plotly_chart(charts.bar_use_by_group(Wsel, uses_all, lang), width="stretch")
        coef = {u["name"]: u["return_coef"] for u in uses_cfg}
        cons = {u: v * (1 - coef.get(u, 0)) for u, v in Wsel.groupby("use").value.sum().items()}
        fig = charts.consumption_donut({u: cons.get(u, 0) for u in uses_sel}, uses_all, lang)
        if fig:
            c2.plotly_chart(fig, width="stretch")

# ----------------------------------------------------------------------------- tab: trends
with tab_trend:
    yt = yearly_totals(cfg_path, sig, mode, uses_json, tuple(years), tuple(sbs), tuple(counties), tuple(uses_sel),
                       layout, tuple(groups), restrict)
    Wall = restrict_members(filt(W, None, sbs, counties, uses_sel), uses_cfg, restrict)
    Wall = Wall[Wall.source_group.isin(groups) & Wall.year.isin(years)]
    by = Wall.pivot_table(index="year", columns="use", values="value", aggfunc="sum").reindex(years).fillna(0)
    c1, c2 = st.columns(2)
    c1.plotly_chart(charts.trend_withdrawals(by, uses_all, lang), width="stretch")
    c2.plotly_chart(charts.trend_balance(yt, lang), width="stretch")
    if len(ind):
        st.plotly_chart(charts.trend_indicators((ind[num_cols].astype(float) * share).reset_index(), lang),
                        width="stretch")
    show = yt[["resources", "withdrawal", "return", "consumption", "balance"]].rename(columns={
        "resources": T("resources"), "withdrawal": T("withdrawal_s"), "return": T("return_s"),
        "consumption": T("consumption"), "balance": T("balance")})
    st.dataframe(shade(show.style.format("{:,.2f}"), T("balance"), None, diverging=True), width="stretch")

# ----------------------------------------------------------------------------- tab: sub-basin x county
with tab_matrix:
    st.markdown(f"<div class='wa-note'>{T('matrix_note')}</div>", unsafe_allow_html=True)
    lab = Wsel.sub_basin.map(lambda s: sb_label.format(id=s))
    m = Wsel.assign(sb=lab).pivot_table(index="sb", columns="county", values="value", aggfunc="sum").fillna(0)
    c1, c2 = st.columns(2)
    if len(m):
        m = m.loc[sorted(m.index, key=lambda s: natural_key(s.split()[-1]))]
        m.loc[T("total")] = m.sum()
        m[T("total")] = m.sum(axis=1)
        c1.plotly_chart(charts.heatmap(m, T("matrix_title", y=year), lang), width="stretch")
    am = cells.assign(sb=cells.sub_basin.map(lambda s: sb_label.format(id=s))).pivot_table(
        index="sb", columns="county", values="area_km2", aggfunc="sum").fillna(0)
    fig = charts.heatmap(am.round(1), T("area_title"), lang, fmt=",.1f", scale="Greens")
    if fig:
        c2.plotly_chart(fig, width="stretch")
    det = Wsel.assign(sb=lab, grp=Wsel.source_group.map(GROUP_LABELS)).pivot_table(
        index=["sb", "county", "grp"], columns="use", values="value", aggfunc="sum").fillna(0)
    if len(det):
        det = det[[u for u in uses_all if u in det.columns]]
        det["جمع"] = det.sum(axis=1)
        det.index.names = ["زیرحوضه", "شهرستان", "نوع منبع"]
        shown = det.rename(index=L, columns=L)
        shown.index.names = [L(n) for n in det.index.names]
        st.markdown(f"**{T('detail_title')}**")
        st.dataframe(shade(shown.style.format("{:,.3f}"), L("جمع"), "37,99,235"), width="stretch", height=420)
        st.download_button(T("dl_detail"), to_excel_bytes({"زیرحوضه-شهرستان": det}, T("chip_year", y=year), lang),
                           file_name=f"subbasin_county_{cfg['basin']['key']}_{year}.xlsx")

# ----------------------------------------------------------------------------- tab: map
with tab_map:
    # three-way review mode: switches the related layers on and the others off (layers stay individually toggleable)
    LAYER_KEYS = ["sb", "ct", "ctx_sa", "ctx_ct", "wells", "dams"]
    ss = st.session_state
    if not ss.get("map_mode"):
        ss["map_mode"] = ss.get("_map_mode_last", "combined")
    for k, v in charts.MODE_LAYERS[ss["map_mode"]].items():
        ss.setdefault(f"lyr_{k}", v)

    def _apply_mode():
        m = ss.get("map_mode")
        if m:
            ss["_map_mode_last"] = m
            for k, v in charts.MODE_LAYERS[m].items():
                ss[f"lyr_{k}"] = v

    c1, c2 = st.columns([3, 2])
    with c1:
        st.segmented_control(T("map_mode"), charts.MAP_MODES, format_func=lambda m: T(f"mode_{m}"), key="map_mode",
                             on_change=_apply_mode, width="stretch")
    with c2:
        basemap = st.radio(T("basemap"), charts.BASEMAPS, format_func=lambda b: T(f"bm_{b}"), horizontal=True)
    map_mode = ss.get("map_mode") or ss.get("_map_mode_last", "combined")
    shapes = base["shapes"]
    available = {"ctx_sa": bool(shapes.get("context_study_areas")), "ctx_ct": bool(shapes.get("context_counties")),
                 "ct": bool(shapes.get("counties"))}
    lc = st.columns(len(LAYER_KEYS))
    layers = {k: lc[i].checkbox(T(f"lyr_{k}"), key=f"lyr_{k}", disabled=not available.get(k, True))
              for i, k in enumerate(LAYER_KEYS)}
    wells = base["wells"].assign(county=base["wells"][ccol])
    wy = wells[(wells.year == year) & wells.sub_basin.isin(sbs) & wells.county.isin(counties) &
               wells.use.isin(uses_sel)]
    if "gw" not in groups:
        wy = wy.iloc[0:0]
    st.plotly_chart(charts.basin_map(shapes, sbs, counties, wy, base["dams"], uses_all, sb_label, basemap, lang,
                                     map_mode, layers),
                    width="stretch", config={"scrollZoom": True})
    st.markdown(f"<div class='wa-note'>{T('map_note')}</div>", unsafe_allow_html=True)

# ----------------------------------------------------------------------------- tab: QC
with tab_qc:
    rep = meta["report"]
    for w in rep["warnings"]:
        st.warning(msg(w, lang))
    simaye = base["simaye"]
    if len(simaye):
        st.markdown(f"**{T('qc_simaye')}**")
        cols = {"year": ("سال آبی", "Water year"), "renew_total": ("تجدیدپذیر کل", "Renewable total"),
                "renew_surface": ("سطحی (رواناب)", "Surface (runoff)"), "renew_ground": ("زیرزمینی (نفوذ)", "Groundwater"),
                "delta_s_reported": ("تغییر ذخیره (گزارش‌شده)", "Storage change (reported)"),
                "delta_s": ("ΔS به‌کاررفته", "ΔS used"), "transfer_in": ("آب انتقالی", "Transfer in"),
                "file": ("فایل PDF", "PDF file"), "page": ("صفحه", "Page")}
        sel = [c for c in cols if c in simaye]
        st.dataframe(simaye[sel].rename(columns={c: cols[c][lang == "en"] for c in sel}).fillna(""),
                     width="stretch", hide_index=True)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**{T('qc_dams')}**")
        dm = base["dams"].drop(columns=["x", "y"], errors="ignore").copy()
        for c in ("dam", "sub_basin", "county", "location_county"):
            if c in dm:
                dm[c] = dm[c].map(L)
        st.dataframe(dm, width="stretch", hide_index=True)
    with c2:
        st.markdown(f"**{T('qc_info')}**")
        st.json(rep["info"], expanded=False)
    if len(base["dam_stats"]):
        st.markdown(f"**{T('qc_dam_stats')}**")
        st.dataframe(base["dam_stats"], width="stretch", height=260, hide_index=True)
    st.markdown(f"**{T('qc_base')}**")
    c1, c2, c3 = st.columns(3)
    c1.download_button(T("dl_w"), W.to_csv(index=False).encode("utf-8-sig"), "withdrawals_all.csv")
    c2.download_button(T("dl_r"), RET.to_csv(index=False).encode("utf-8-sig"), "returns_all.csv")
    c3.download_button(T("dl_res"), RES.to_csv(index=False).encode("utf-8-sig"), "resources_all.csv")
    st.caption(T("qc_caption", t=meta["built_at"], s=meta["seconds"]))
