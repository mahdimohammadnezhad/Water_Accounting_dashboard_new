"""Management dashboard (Persian / English): the decisions a manager needs, each within three clicks.

    streamlit run manager.py        (or double-click run_dashboard.bat on the `management` branch)

Status (0 clicks): is the aquifer being depleted, how much, and who consumes the water.
Areas (1 click): where consumption is concentrated.  Options (1 click): every management option compared;
a custom package in 2-3 clicks.  Outlook (1 click): the cut needed to stop the decline by the horizon.
The expert dashboard (app.py) keeps every detail: sources-and-uses table, uncertainty, coefficients, etc.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
from wa import demand, mgmt, ui  # noqa: E402
from wa.build import get_base, is_fresh  # noqa: E402
from wa.config import list_configs, load_config, signature  # noqa: E402
from wa.engine import compute  # noqa: E402
from wa.i18n import LANGS, num, term  # noqa: E402
from wa.i18n import year as fyear  # noqa: E402

st.set_page_config(page_title="داشبورد مدیریتی آب / Water management", page_icon=":material/water_drop:",
                   layout="wide", initial_sidebar_state="collapsed")
ss = st.session_state
lang = ss.get("lang") or "fa"

M = {
    "title": ("داشبورد مدیریتی منابع آب", "Water Management Dashboard"),
    "subtitle": ("{b} — خلاصه برای تصمیم‌گیری (حجم‌ها به میلیون مترمکعب)", "{b} — decision summary (volumes in million m³)"),
    "basin": ("محدوده مطالعاتی", "Study area"),
    "year": ("سال آبی", "Water year"),
    "area": ("محدوده بررسی", "Area"),
    "area_all": ("کل محدوده مطالعاتی", "Whole study area"),
    "lang": ("زبان / Language", "Language / زبان"),
    "tab_status": (":material/monitor_heart: وضعیت", ":material/monitor_heart: Status"),
    "tab_areas": (":material/map: مناطق", ":material/map: Areas"),
    "tab_options": (":material/tune: گزینه‌های مدیریتی", ":material/tune: Management options"),
    "tab_future": (":material/trending_up: آینده", ":material/trending_up: Outlook"),
    "badge_bad": ("هشدار", "Warning"), "badge_good": ("پایدار", "Stable"),
    "st_bad": ("در سال آبی {y}، ذخیره آبخوان {d} میلیون مترمکعب کم شد.",
               "In water year {y} the aquifer lost {d} million m³ of storage."),
    "st_good": ("در سال آبی {y}، ذخیره آبخوان کم نشد.", "In water year {y} the aquifer did not lose storage."),
    "st_cons": ("مصرف {c} میلیون مترمکعب بود، برابر {p}٪ آب تجدیدپذیر همان سال ({r}).",
                "Consumption was {c} million m³, {p}% of that year's renewable water ({r})."),
    "st_years": ("آبخوان در {n} سال از {m} سال گذشته افت داشته است.", "The aquifer lost storage in {n} of the last {m} years."),
    "st_nodata": ("برای این سال جدول سیمای آب نیست.", "There is no Simaye Ab table for this year."),
    "gap": ("مصرف ثبت‌شده کمتر از آب تجدیدپذیر است ولی آبخوان افت کرده؛ یعنی بخشی از برداشت‌ها ثبت نمی‌شود یا آب "
            "برگشتی کمتر از فرض است. کنتورگذاری و کنترل برداشت اولویت دارد.",
            "Recorded consumption is below the renewable water, yet the aquifer declined: part of the abstraction is "
            "not recorded or return flows are lower than assumed. Metering and abstraction control come first."),
    "k_renew": ("آب تجدیدپذیر", "Renewable water"), "k_renew_n": ("میانگین {n} سال: {m}", "{n}-year mean: {m}"),
    "k_cons": ("مصرف", "Consumption"), "k_cons_n": ("{p}٪ آب تجدیدپذیر", "{p}% of renewable water"),
    "k_def": ("افت آبخوان (سیمای آب)", "Aquifer storage loss (Simaye Ab)"),
    "k_def_n": ("مجموع {n} سال: {s}", "{n}-year total: {s}"),
    "k_agri": ("سهم کشاورزی از مصرف", "Agriculture's share of consumption"),
    "k_agri_n": ("{v} میلیون مترمکعب", "{v} million m³"),
    "unit": ("م.م.م", "MCM"), "pct": ("٪", "%"), "mm": ("میلی‌متر", "mm"), "mpeople": ("میلیون نفر", "million"),
    "lbl_renew": ("آب تجدیدپذیر", "Renewable water"), "lbl_cons": ("مصرف", "Consumption"),
    "lbl_def": ("افت آبخوان", "Aquifer storage loss"), "lbl_unit": ("میلیون مترمکعب", "million m³"),
    "trend_all": ("آبخوان در همه {m} سال افت داشته است", "The aquifer lost storage in all {m} years"),
    "trend_some": ("آبخوان در {n} سال از {m} سال افت داشته است", "The aquifer lost storage in {n} of {m} years"),
    "uses_title": ("{u} {p}٪ مصرف آب را دارد", "{u} accounts for {p}% of water consumption"),
    "areas_lead": ("{s} با {c} میلیون مترمکعب ({p}٪ کل) بیشترین مصرف را دارد؛ معادل {d} میلی‌متر آب در سال روی مساحت آن.",
                   "{s} consumes the most: {c} million m³ ({p}% of the total), {d} mm of water per year over its area."),
    "areas_map": ("مصرف به ازای مساحت هر زیرحوضه (میلی‌متر در سال)", "Consumption per area of each sub-basin (mm per year)"),
    "rank_sb": ("مصرف هر زیرحوضه", "Consumption by sub-basin"),
    "rank_ct": ("مصرف هر شهرستان (بر اساس آمار)", "Consumption by county (as recorded)"),
    "areas_note": ("این صفحه همیشه کل محدوده را در سال انتخاب‌شده نشان می‌دهد.",
                   "This page always shows the whole study area for the selected year."),
    "o_base": ("وضع موجود", "Present situation"),
    "o_agri20": ("کاهش ۲۰٪ برداشت کشاورزی", "Cut irrigation abstraction by 20%"),
    "o_illegal": ("بستن همه چاه‌های غیرمجاز", "Close all illegal wells"),
    "o_reuse": ("مصرف ۵۰٪ پساب در کشاورزی", "Reuse 50% of effluent in agriculture"),
    "o_combo": ("بسته ترکیبی: ۱۵٪ کشاورزی + نیمی از غیرمجاز + پساب", "Package: −15% irrigation + half of illegal + reuse"),
    "o_drought": ("ریسک: خشکسالی (۳۰٪ آب کمتر)", "Risk: drought (30% less water)"),
    "o_custom": ("بسته دلخواه", "Your package"),
    "opt_stop": ("«{o}» افت آبخوان را متوقف می‌کند: به‌جای افت {b} میلیون مترمکعب در سال، ذخیره آبخوان حدود {a} "
                 "میلیون مترمکعب در سال افزایش می‌یابد.",
                 "“{o}” stops the aquifer decline: instead of losing {b} million m³ a year, storage rises by about {a} "
                 "million m³ a year."),
    "opt_best": ("بهترین گزینه «{o}» است: افت آبخوان را {p}٪ کم می‌کند (از {b} به {a} میلیون مترمکعب در سال).",
                 "The best option is “{o}”: it cuts the aquifer loss by {p}% (from {b} to {a} million m³ per year)."),
    "opt_title": ("افت آبخوان پس از هر گزینه (میانگین سال‌ها)", "Aquifer storage loss after each option (mean of the years)"),
    "opt_axis": ("افت آبخوان (م.م.م در سال) — منفی یعنی بازیابی", "Aquifer storage loss (MCM/yr) — negative means recovery"),
    "opt_now": ("وضع موجود", "Present"),
    "c_option": ("گزینه", "Option"), "c_cons": ("مصرف (م.م.م)", "Consumption (MCM)"),
    "c_def": ("افت آبخوان (م.م.م)", "Aquifer loss (MCM)"), "c_cut": ("کاهش افت", "Loss reduced"),
    "c_years": ("سال‌های با افت", "Years with loss"),
    "cut_more": ("{p}٪ افت بیشتر", "{p}% more loss"), "cut_rec": ("{p}٪ (بازیابی)", "{p}% (recovery)"),
    "custom": ("ساخت بسته دلخواه", "Build your own package"),
    "cu_agri": ("کاهش برداشت کشاورزی (٪)", "Irrigation abstraction cut (%)"),
    "cu_illegal": ("بستن چاه‌های غیرمجاز (٪ برداشت آن‌ها)", "Illegal wells closed (% of their abstraction)"),
    "cu_reuse": ("مصرف پساب در کشاورزی (٪ خروجی تصفیه‌خانه)", "Effluent reused in agriculture (% of plant output)"),
    "cu_gain": ("با این بسته افت آبخوان متوقف می‌شود: ذخیره حدود {a} میلیون مترمکعب در سال افزایش می‌یابد (به‌جای افت {b}).",
                "With this package the decline stops: storage rises by about {a} million m³ a year (instead of losing {b})."),
    "cu_result": ("با این بسته، میانگین افت آبخوان {a} میلیون مترمکعب در سال می‌شود ({p}٪ کمتر از وضع موجود).",
                  "With this package the mean aquifer loss becomes {a} million m³ per year ({p}% less than now)."),
    "opt_note": ("هر گزینه روی همه سال‌های {y1} تا {y2} اعمال و میانگین گرفته شده است؛ برآورد مرتبه اول و بدون مدل آب زیرزمینی.",
                 "Each option is applied to every year from {y1} to {y2} and averaged; a first-order estimate "
                 "without a groundwater model."),
    "f_rate": ("نرخ رشد جمعیت (٪ در سال)", "Population growth (% per year)"),
    "f_h": ("افق", "Horizon"),
    "f_lead": ("برای توقف افت آبخوان تا {h}، مصرف باید حدود {c} میلیون مترمکعب در سال کم شود؛ یعنی {p}٪ مصرف فعلی کشاورزی.",
               "To stop the aquifer decline by {h}, consumption must fall by about {c} million m³ per year, i.e. {p}% "
               "of today's agricultural consumption."),
    "f_ok": ("با این فرض‌ها مصرف تا {h} از حد مصرف پایدار ({s} میلیون مترمکعب) بیشتر نمی‌شود.",
             "With these assumptions consumption stays below the sustainable level ({s} million m³) up to {h}."),
    "f_pop": ("جمعیت {y}", "Population {y}"), "f_pop_n": ("امروز ({y}): {v}", "today ({y}): {v}"),
    "f_cons": ("مصرف {y} با ادامه وضع موجود", "Consumption {y}, business as usual"),
    "f_cons_n": ("امروز: {v}", "today: {v}"),
    "f_sust": ("حد مصرف پایدار", "Sustainable consumption"),
    "f_sust_n": ("میانگین مصرف − میانگین افت آبخوان", "mean consumption − mean aquifer loss"),
    "f_cut": ("کاهش لازم تا {y}", "Cut needed by {y}"), "f_cut_n": ("{p}٪ مصرف کشاورزی", "{p}% of agricultural use"),
    "f_title": ("مصرف گذشته و آینده در برابر حد مصرف پایدار", "Past and future consumption against the sustainable level"),
    "f_past": ("مصرف گذشته", "Past consumption"),
    "f_bau": ("ادامه وضع موجود (رشد جمعیت و صنعت)", "Business as usual (population and industry growth)"),
    "f_renew": ("میانگین آب تجدیدپذیر", "Mean renewable water"), "f_sustl": ("حد مصرف پایدار", "Sustainable level"),
    "f_note": ("حد مصرف پایدار = میانگین مصرف سال‌های گذشته منهای میانگین افت آبخوان. فرض‌ها: رشد صنعت {g}٪ در سال، "
               "کشاورزی و سرانه ثابت. نوار آبی دامنه رشد جمعیت ±{b} واحد درصد است.",
               "Sustainable level = mean past consumption minus the mean aquifer loss. Assumptions: industry "
               "+{g}%/yr, agriculture and per-capita use constant. The blue band is population growth ±{b} points."),
    "f_nopop": ("فایل سرشماری برای این محدوده نیست؛ رشد جمعیت روی شاخص نسبی اعمال شده است.",
                "No census for this area; growth is applied to a relative index."),
    "expert": ("جزئیات بیشتر (جدول منابع و مصارف، عدم قطعیت، ضرایب) در نسخه کارشناسی: run_expert.bat",
               "More detail (sources-and-uses table, uncertainty, coefficients) in the expert version: run_expert.bat"),
    "building": ("در حال آماده‌سازی داده‌ها...", "Preparing the data..."),
}


def T(key, **kw):
    s = M[key][1 if lang == "en" else 0]
    return s.format(**kw) if kw else s


L = lambda s: term(s, lang)  # noqa: E731
N = lambda v, f="{:,.0f}": num(v, lang, f)  # noqa: E731

st.markdown(ui.css(lang) + """
<style>
.mg-status { display: flex; gap: 14px; align-items: flex-start; border: 1px solid; border-radius: 14px;
             padding: 14px 20px; margin: 2px 0 14px 0; }
.mg-status.bad { background: #fef2f2; border-color: #fecaca; color: #7f1d1d; }
.mg-status.good { background: #ecfdf5; border-color: #a7f3d0; color: #064e3b; }
.mg-status .badge { flex: 0 0 auto; color: #fff; font-weight: 800; border-radius: 999px; padding: 3px 14px;
                    font-size: .85rem; margin-top: 6px; }
.mg-status.bad .badge { background: #b91c1c; } .mg-status.good .badge { background: #047857; }
.mg-status .big { font-size: 1.28rem; font-weight: 800; line-height: 1.8; }
.mg-status .small { font-size: .95rem; line-height: 1.9; }
.mg-lead { font-size: 1.08rem; font-weight: 700; color: #0f172a; line-height: 1.9; margin: 4px 2px 10px 2px; }
.mg-tip { background: #fffbeb; border: 1px solid #fde68a; color: #78350f; border-radius: 12px; padding: 10px 16px;
          font-size: .92rem; line-height: 1.9; margin: 0 0 12px 0; }
.stTabs [data-baseweb="tab"] { font-size: 1rem; padding: 10px 18px; }
</style>""", unsafe_allow_html=True)


# ----------------------------------------------------------------------------- data (cached)
@st.cache_data(show_spinner=False)
def load(cfg_path, sig, force=False):
    return get_base(load_config(cfg_path), force=force, log=lambda *_: None)


@st.cache_data(show_spinner=False)
def engine(cfg_path, sig):
    cfg = load_config(cfg_path)
    base = load(cfg_path, sig)
    mode = cfg["county_mode_default"] if base["meta"].get("has_county_attr", True) else "geo"
    W, RET, _ = compute(base, cfg, base["meta"]["uses"], mode)
    return W, RET, mode


@st.cache_data(show_spinner=False)
def run_option(cfg_path, sig, spec_key):
    """One management option applied to the whole basin (cached once, whatever area is shown)."""
    cfg = load_config(cfg_path)
    base = load(cfg_path, sig)
    _, _, mode = engine(cfg_path, sig)
    return mgmt.run_option(base, cfg, base["meta"]["uses"], mode, thaw(spec_key))


def option_table(cfg_path, sig, presets, sbs, share):
    W0, RET0, _ = engine(cfg_path, sig)
    base = load(cfg_path, sig)
    runs = {k: run_option(cfg_path, sig, freeze(s)) for k, s in presets.items()}
    return mgmt.options_from(W0, RET0, base["indicators"], runs, base["meta"]["years"],
                             list(sbs) if sbs is not None else None, share)


@st.cache_data(show_spinner=False)
def outlook(cfg_path, sig, sbs, share, rate, horizon):
    cfg = load_config(cfg_path)
    base = load(cfg_path, sig)
    W, RET, _ = engine(cfg_path, sig)
    meta = base["meta"]
    uses = meta["uses"]
    return mgmt.outlook(W, RET, base["indicators"], meta["years"], list(sbs) if sbs is not None else None, share,
                        {u["name"]: u["return_coef"] for u in uses}, cfg, cfg["uncertainty"], [u["name"] for u in uses],
                        base, meta, rate, horizon)


def freeze(x):
    """Hashable form of a (nested) preset dict for the cache; `thaw` turns it back."""
    return tuple(sorted((k, freeze(v)) for k, v in x.items())) if isinstance(x, dict) else x


def thaw(x):
    return {k: thaw(v) for k, v in x} if isinstance(x, tuple) else x


cfgs = {str(p): load_config(p) for p in list_configs()}
if not cfgs:
    st.error("No basin configuration in configs/.")
    st.stop()


def basin_name(c):
    return c["basin"].get("name_en") if lang == "en" and c["basin"].get("name_en") else c["basin"]["name"]


# ----------------------------------------------------------------------------- header + the three controls
head = st.container()
cols = st.columns([1.4, 1, 1.4, 1] if len(cfgs) > 1 else [1, 1.4, 1])
i0 = 0
if len(cfgs) > 1:
    cfg_path = cols[0].selectbox(T("basin"), list(cfgs), format_func=lambda p: basin_name(cfgs[p]))
    i0 = 1
else:
    cfg_path = next(iter(cfgs))
cfg = cfgs[cfg_path]
sig = signature(cfg)
if not is_fresh(cfg):
    with st.spinner(T("building")):
        load(cfg_path, sig, force=True)
base = load(cfg_path, sig)
meta = base["meta"]
years = meta["years"]
W, RET, mode = engine(cfg_path, sig)
year = cols[i0].selectbox(T("year"), years, index=len(years) - 1, format_func=lambda y: fyear(y, lang))
sb_label = cfg["spatial"]["sub_basin_label"]
sb_names = {s: L(sb_label.format(id=s)) for s in meta["sub_basins"]}
area = cols[i0 + 1].selectbox(T("area"), ["all"] + meta["sub_basins"],
                              format_func=lambda a: T("area_all") if a == "all" else sb_names[a])
cols[i0 + 2].radio(T("lang"), list(LANGS), format_func=LANGS.get, horizontal=True, key="lang")
sbs = None if area == "all" else (area,)
share = mgmt.area_share(base["cells"], sbs)
with head:
    st.markdown(ui.hero(T("title"), T("subtitle", b=basin_name(cfg)),
                        [f"{T('year')} {fyear(year, lang)}", T("area_all") if area == "all" else sb_names[area]]),
                unsafe_allow_html=True)

yr = mgmt.yearly(W, RET, base["indicators"], years, list(sbs) if sbs else None, share)
row = yr.loc[year]
unit = T("unit")
tab_s, tab_a, tab_o, tab_f = st.tabs([T("tab_status"), T("tab_areas"), T("tab_options"), T("tab_future")])

# ----------------------------------------------------------------------------- status
with tab_s:
    have_d = pd.notna(row.deficit)
    loss_years, n_years = int((yr.deficit > 0).sum()), int(yr.deficit.notna().sum())
    if have_d:
        bad = row.deficit > 0
        big = T("st_bad", y=fyear(year, lang), d=N(row.deficit)) if bad else T("st_good", y=fyear(year, lang))
    else:
        bad = pd.notna(row.renewable) and row.consumption > row.renewable
        big = T("st_nodata")
    small = []
    if pd.notna(row.renewable) and row.renewable > 0:
        small.append(T("st_cons", c=N(row.consumption), p=N(100 * row.consumption / row.renewable),
                       r=N(row.renewable)))
    if n_years:
        small.append(T("st_years", n=N(loss_years, "{}"), m=N(n_years, "{}")))
    st.markdown(f"<div class='mg-status {'bad' if bad else 'good'}'><span class='badge'>"
                f"{T('badge_bad') if bad else T('badge_good')}</span><div><div class='big'>{big}</div>"
                f"<div class='small'>{' '.join(small)}</div></div></div>", unsafe_allow_html=True)
    if have_d and row.deficit > 0 and pd.notna(row.renewable) and row.consumption < row.renewable:
        st.markdown(f"<div class='mg-tip'>{T('gap')}</div>", unsafe_allow_html=True)

    by_use = mgmt.consumption_by_use(W, RET, list(sbs) if sbs else None, year)
    agri = sum(v for u, v in by_use.items() if demand.use_kind(u) == "agri")
    tot_u = float(by_use.sum()) or 1.0
    st.markdown(ui.cards([
        {"label": T("k_renew"), "value": row.renewable, "color": "#0891b2", "fmt": "{:,.0f}",
         "note": T("k_renew_n", n=N(yr.renewable.notna().sum(), "{}"), m=N(yr.renewable.mean()))},
        {"label": T("k_cons"), "value": row.consumption, "color": "#1d4ed8", "fmt": "{:,.0f}",
         "note": T("k_cons_n", p=N(100 * row.consumption / row.renewable)) if row.renewable and
         pd.notna(row.renewable) else ""},
        {"label": T("k_def"), "value": row.deficit if have_d else None, "color": "#dc2626", "fmt": "{:,.0f}",
         "tone": "neg" if have_d and row.deficit > 0 else "", "note": T("k_def_n", n=N(n_years, "{}"),
                                                                       s=N(yr.deficit.sum()))},
        {"label": T("k_agri"), "value": 100 * agri / tot_u, "color": "#d97706", "fmt": "{:.0f}", "unit": T("pct"),
         "note": T("k_agri_n", v=N(agri))},
    ], lang, unit), unsafe_allow_html=True)

    c1, c2 = st.columns([1.5, 1], gap="medium")
    trend_title = (T("trend_all", m=N(n_years, "{}")) if loss_years == n_years else
                   T("trend_some", n=N(loss_years, "{}"), m=N(n_years, "{}")))
    c1.plotly_chart(mgmt.trend_fig(yr, lang, trend_title, {"deficit": T("lbl_def"), "renewable": T("lbl_renew"),
                                                           "consumption": T("lbl_cons"), "unit": T("lbl_unit")}),
                    width="stretch", config={"displayModeBar": False})
    if len(by_use):
        top = by_use.index[0]
        c2.plotly_chart(mgmt.uses_fig(by_use, lang, T("uses_title", u=L(top), p=N(100 * by_use.iloc[0] / tot_u)), unit),
                        width="stretch", config={"displayModeBar": False})

# ----------------------------------------------------------------------------- areas
with tab_a:
    sb, ct = mgmt.hotspots(W, RET, base["cells"], year)
    if len(sb):
        top = sb.index[0]
        st.markdown(f"<div class='mg-lead'>{T('areas_lead', s=sb_names.get(top, top), c=N(sb.consumption.iloc[0]), p=N(100 * sb.consumption.iloc[0] / sb.consumption.sum()), d=N(sb.depth_mm.iloc[0]))}</div>",  # noqa: E501
                    unsafe_allow_html=True)
        c1, c2 = st.columns([1.25, 1], gap="medium")
        with c1:
            st.markdown(f"<div class='wa-note'>{T('areas_map')}</div>", unsafe_allow_html=True)
            st.plotly_chart(mgmt.map_fig(base["shapes"], sb, lang, sb_names, T("mm")), width="stretch",
                            config={"displayModeBar": False})
        with c2:
            st.plotly_chart(mgmt.rank_fig(sb.consumption, [sb_names.get(s, s) for s in sb.index], lang, T("rank_sb"),
                                          unit, h=260), width="stretch", config={"displayModeBar": False})
            cts = ct[ct.consumption > 0.005 * ct.consumption.sum()]
            st.plotly_chart(mgmt.rank_fig(cts.consumption, [L(c) for c in cts.index], lang, T("rank_ct"), unit,
                                          color="#64748b", h=300), width="stretch", config={"displayModeBar": False})
        st.caption(T("areas_note"))

# ----------------------------------------------------------------------------- management options
AGRI_USE = next((u["name"] for u in meta["uses"] if demand.use_kind(u["name"]) == "agri"), None)
PRESETS = {"agri20": {"use_pct": {AGRI_USE: -20}} if AGRI_USE else {}, "illegal": {"illegal_close": 100},
           "reuse": {"reuse_pct": 50},
           "combo": {**({"use_pct": {AGRI_USE: -15}} if AGRI_USE else {}), "illegal_close": 50, "reuse_pct": 50},
           "drought": {"climate_pct": -30}}
with tab_o:
    tab = option_table(cfg_path, sig, PRESETS, sbs, share)
    names = {k: T(f"o_{k}") for k in ["base", *PRESETS]}
    b = float(tab.loc["base", "deficit"])
    if pd.isna(b):
        st.info(T("st_nodata"))
    else:
        dec = tab.drop(index=["base", "drought"], errors="ignore").sort_values("deficit")
        best = dec.index[0]
        a = float(dec.loc[best, "deficit"])
        lead = (T("opt_stop", o=names[best], b=N(b), a=N(-a)) if a <= 0 else
                T("opt_best", o=names[best], p=N(dec.loc[best, "cut_pct"]), b=N(b), a=N(a)))
        st.markdown(f"<div class='mg-lead'>{lead}</div>", unsafe_allow_html=True)
        c1, c2 = st.columns([1.6, 1], gap="medium")
        c1.plotly_chart(mgmt.options_fig(tab, names, lang, T("opt_title"),
                                         {"deficit": T("lbl_def"), "now": T("opt_now"), "axis": T("opt_axis")}),
                        width="stretch", config={"displayModeBar": False})
        with c2.expander(T("custom"), icon=":material/build:", expanded=False):
            ca = st.slider(T("cu_agri"), 0, 50, 15, 5, key="cu_agri", format="%d%%")
            ci = st.slider(T("cu_illegal"), 0, 100, 50, 10, key="cu_illegal", format="%d%%")
            cr = st.slider(T("cu_reuse"), 0, 100, 50, 10, key="cu_reuse", format="%d%%")
            spec = {"custom": {**({"use_pct": {AGRI_USE: -ca}} if AGRI_USE and ca else {}), "illegal_close": ci,
                               "reuse_pct": cr}}
            ctab = option_table(cfg_path, sig, spec, sbs, share)
            ac = float(ctab.loc["custom", "deficit"])
            msg = (T("cu_gain", a=N(-ac), b=N(b)) if ac <= 0 else
                   T("cu_result", a=N(ac), p=N(ctab.loc["custom", "cut_pct"])))
            st.markdown(f"<div class='mg-lead'>{msg}</div>", unsafe_allow_html=True)

        def cut_text(k, v):
            if k == "base" or pd.isna(v):
                return "—"
            if v < 0:
                return T("cut_more", p=N(-v))
            return T("cut_rec", p=N(v)) if v > 100 else f"{N(v)}{T('pct')}"

        show = tab.loc[["base", *[k for k in tab.index if k != "base"]]]
        st.dataframe(pd.DataFrame({
            T("c_option"): [names[k] for k in show.index],
            T("c_def"): show.deficit.round(0),
            T("c_cut"): [cut_text(k, v) for k, v in show.cut_pct.items()],
            T("c_years"): [f"{N(v, '{}')} / {N(len(years), '{}')}" for v in show.years_loss]}),
            hide_index=True, width="stretch")
        st.caption(T("opt_note", y1=fyear(years[0], lang), y2=fyear(years[-1], lang)))

# ----------------------------------------------------------------------------- outlook
with tab_f:
    dcfg = {**demand.DEFAULTS, **{k: v for k, v in (cfg.get("demand") or {}).items() if k != "census"}}
    y0 = demand.year_start(years[-1])
    periods = demand.growth_periods(dcfg, None, y0)
    c1, c2, _ = st.columns([1.2, 1.4, 1.4])
    rate = c1.slider(T("f_rate"), 0.0, 3.0, float(periods[-1][1]), 0.1, key="f_rate")
    hz_opts = list(range(y0 + 3, y0 + 29, 1))
    horizon = c2.select_slider(T("f_h"), hz_opts, value=min(max(int(dcfg["horizon"]), hz_opts[0]), hz_opts[-1]),
                               key="f_h")
    dfp, summ = outlook(cfg_path, sig, sbs, share, rate, horizon)
    hz = fyear(summ["horizon"], lang)
    if pd.notna(summ.get("sustainable")) and pd.notna(summ.get("supply")):
        lead = (T("f_lead", h=hz, c=N(summ["cut"]), p=N(summ["cut_pct_agri"])) if summ["cut"] > 0 else
                T("f_ok", h=hz, s=N(summ["sustainable"])))
        st.markdown(f"<div class='mg-lead'>{lead}</div>", unsafe_allow_html=True)
    base_c = float(dfp.loc[summ["base_year"], "obs_consumption"])
    cards = []
    if summ["pop_absolute"]:
        cards.append({"label": T("f_pop", y=hz), "value": summ["pop_end"] / 1e6, "fmt": "{:,.2f}",
                      "unit": T("mpeople"), "color": "#7c3aed",
                      "note": T("f_pop_n", y=fyear(summ["base_year"], lang), v=N(summ["pop_base"] / 1e6, "{:,.2f}"))})
    cards += [
        {"label": T("f_cons", y=hz), "value": summ.get("supply", np.nan), "fmt": "{:,.0f}", "color": "#1d4ed8",
         "note": T("f_cons_n", v=N(base_c))},
        {"label": T("f_sust"), "value": summ["sustainable"], "fmt": "{:,.0f}", "color": "#059669",
         "note": T("f_sust_n")},
        {"label": T("f_cut", y=hz), "value": summ["cut"], "fmt": "{:,.0f}", "color": "#dc2626",
         "tone": "neg" if summ["cut"] > 0 else "pos", "note": T("f_cut_n", p=N(summ["cut_pct_agri"]))},
    ]
    st.markdown(ui.cards(cards, lang, unit), unsafe_allow_html=True)
    if not summ["pop_absolute"]:
        st.caption(T("f_nopop"))
    st.plotly_chart(mgmt.outlook_fig(dfp, summ, lang, T("f_title"),
                                     {"past": T("f_past"), "bau": T("f_bau"), "renew": T("f_renew"),
                                      "sust": T("f_sustl"), "unit": T("lbl_unit")}),
                    width="stretch", config={"displayModeBar": False})
    st.caption(T("f_note", g=N(dcfg["g_industry"], "{:g}"), b=N(demand.growth_band(dcfg), "{:g}")))

st.caption(T("expert"))
