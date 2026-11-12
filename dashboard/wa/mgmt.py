"""Management (decision) view: a few numbers, plain sentences and charts whose titles state the finding.

Everything is computed with the same engine as the expert dashboard (wa.engine, wa.scenario, wa.demand).
Area = the whole study area or a set of sub-basins (hydrological units, so that Simaye Ab terms can be scaled
by area). Volumes in million m3 (MCM).

    consumption = withdrawal - return flow (return to rivers and aquifers; treatment output is part of it)
    deficit     = aquifer storage loss reported by Simaye Ab (-dS), scaled by area
    sustainable consumption = mean consumption - mean deficit (the consumption that, over the record, would
                              have left the aquifers unchanged; first-order estimate)
"""
import numpy as np
import pandas as pd
import plotly.colors as pc
import plotly.graph_objects as go

from . import demand, scenario
from .charts import FONT, _lines, _layout, _rgba
from .engine import compute
from .i18n import num, term
from .i18n import year as fyear

RENEW, CONS, DEF, AGRI, OTHER, GOOD = "#0891b2", "#1d4ed8", "#dc2626", "#d97706", "#94a3b8", "#059669"


def _sel(df, sbs, year=None):
    m = pd.Series(True, index=df.index)
    if sbs is not None:
        m &= df.sub_basin.isin(sbs)
    if year is not None:
        m &= df.year == year
    return df[m]


def area_share(cells, sbs):
    return 1.0 if sbs is None else float(cells[cells.sub_basin.isin(sbs)].share.sum())


def yearly(W, RET, ind, years, sbs, share):
    """One row per water year: withdrawal, return, consumption, groundwater withdrawal, renewable, deficit."""
    w = _sel(W, sbs).groupby("year").value.sum()
    r = _sel(RET[RET.source_group != "treatment"], sbs).groupby("year").value.sum()
    gw = _sel(W[W.source_group == "gw"], sbs).groupby("year").value.sum()
    df = pd.DataFrame(index=list(years))
    df["withdrawal"] = w.reindex(years).fillna(0.0)
    df["return"] = r.reindex(years).fillna(0.0)
    df["consumption"] = df.withdrawal - df["return"]
    df["gw"] = gw.reindex(years).fillna(0.0)
    i = ind.set_index("year") if len(ind) else pd.DataFrame(columns=["renew_total", "nonrenewable", "renew_ground"])
    for col, name in (("renew_total", "renewable"), ("nonrenewable", "deficit"), ("renew_ground", "recharge")):
        df[name] = pd.to_numeric(i[col], errors="coerce").reindex(years) * share if col in i else np.nan
    return df


def consumption_by_use(W, RET, sbs, year):
    w = _sel(W, sbs, year).groupby("use").value.sum()
    r = _sel(RET[RET.source_group != "treatment"], sbs, year).groupby("use").value.sum()
    return (w - r.reindex(w.index).fillna(0.0)).clip(lower=0).sort_values(ascending=False)


def hotspots(W, RET, cells, year):
    """Consumption by sub-basin (with depth over its area, mm/yr) and by county (as written in the statistics)."""
    w = _sel(W, None, year)
    r = _sel(RET[RET.source_group != "treatment"], None, year)
    sb = pd.DataFrame({"withdrawal": w.groupby("sub_basin").value.sum()})
    sb["consumption"] = sb.withdrawal - r.groupby("sub_basin").value.sum().reindex(sb.index).fillna(0.0)
    sb["area_km2"] = cells.groupby("sub_basin").area_km2.sum().reindex(sb.index)
    sb["depth_mm"] = sb.consumption / sb.area_km2 * 1000.0
    ct = pd.DataFrame({"withdrawal": w.groupby("county").value.sum()})
    ct["consumption"] = ct.withdrawal - r.groupby("county").value.sum().reindex(ct.index).fillna(0.0)
    return sb.sort_values("consumption", ascending=False), ct.sort_values("consumption", ascending=False)


# ----------------------------------------------------------------------------- management options
def run_option(base, cfg, uses, mode, spec):
    """Engine output of one option for the whole basin: (W, RET, indicators). Independent of the area shown."""
    bs = scenario.apply(base, cfg, uses, mode, {**scenario.DEFAULT, **spec})
    W1, RET1, _ = compute(bs, cfg, uses, mode)
    return W1, RET1, bs["indicators"]


def options_from(W0, RET0, ind0, runs, years, sbs, share):
    """Mean effect of every option over the record for the area: consumption, groundwater pumping, aquifer deficit.
    runs: {key: (W, RET, indicators)} from run_option."""
    y0 = yearly(W0, RET0, ind0, years, sbs, share)
    rows = [{"key": "base", "consumption": y0.consumption.mean(), "gw": y0.gw.mean(),
             "deficit": y0.deficit.mean(), "years_loss": int((y0.deficit > 0).sum())}]
    for key, (W1, RET1, ind1) in runs.items():
        y1 = yearly(W1, RET1, ind1, years, sbs, share)
        d = []
        for y in years:
            obs = y0.deficit.get(y)
            if obs is None or pd.isna(obs):
                continue
            d.append(scenario.aquifer_deficit(float(obs), _sel(W0, sbs, y), _sel(RET0, sbs, y), _sel(W1, sbs, y),
                                              _sel(RET1, sbs, y), float(np.nan_to_num(y0.recharge.get(y))),
                                              float(np.nan_to_num(y1.recharge.get(y)))))
        d = np.array(d, dtype=float)
        rows.append({"key": key, "consumption": y1.consumption.mean(), "gw": y1.gw.mean(),
                     "deficit": float(d.mean()) if len(d) else np.nan, "years_loss": int((d > 0).sum())})
    out = pd.DataFrame(rows).set_index("key")
    b = out.loc["base", "deficit"]
    out["cut_pct"] = (b - out.deficit) / b * 100 if b and b > 0 else np.nan
    return out


def options(base, cfg, uses, mode, presets, years, sbs, share):
    W0, RET0, _ = compute(base, cfg, uses, mode)
    runs = {k: run_option(base, cfg, uses, mode, s) for k, s in presets.items()}
    return options_from(W0, RET0, base["indicators"], runs, years, sbs, share)


# ----------------------------------------------------------------------------- future
def population0(base, meta, W, sbs, uses_all, years):
    """Census population of the area (default county shares); None when the basin has no census."""
    cen, info = base.get("census"), meta.get("census") or {}
    if cen is None or not len(cen) or not info:
        return None, None
    pop = float((cen.urban.astype(float) * cen.urban_pct.astype(float) / 100
                 + cen.rural.astype(float) * cen.rural_pct.astype(float) / 100).sum())
    if sbs is not None:  # part of the basin: share of drinking and services withdrawal of the last year
        pu = [u for u in uses_all if demand.use_kind(u) == "pop"]
        Wp = W[(W.year == years[-1]) & W.use.isin(pu)]
        tot = float(Wp.value.sum())
        pop *= float(Wp[Wp.sub_basin.isin(sbs)].value.sum()) / tot if tot > 0 else 0.0
    return (pop if pop > 0 else None), int(info["year"])


def outlook(W, RET, ind, years, sbs, share, coef, cfg, unc, uses_all, base, meta, rate, horizon):
    yr = yearly(W, RET, ind, years, sbs, share)
    hist = _sel(W, sbs).pivot_table(index="year", columns="use", values="value", aggfunc="sum").reindex(years).fillna(0)
    renew = yr.renewable.dropna()
    sdv = unc["relative_sd"]
    i = ind.set_index("year") if len(ind) else pd.DataFrame()
    sd_r = float(((sdv["renew_surface"] * i.renew_surface.mean()) ** 2 + (sdv["renew_ground"] * i.renew_ground.mean())
                  ** 2) ** 0.5 / i.renew_total.mean()) if len(i) else 0.0
    pop0, cen_year = population0(base, meta, W, sbs, uses_all, years)
    y0 = demand.year_start(years[-1])
    p = {**demand.DEFAULTS, **{k: v for k, v in (cfg.get("demand") or {}).items() if k != "census"}}
    past = [(f, r) for f, r in demand.growth_periods(p, cen_year, y0) if f <= y0]
    p.update(horizon=int(horizon), growth=past + [(y0 + 1, float(rate))])
    dfp, summ = demand.project(hist, coef, renew, sd_r, p, pop0, cen_year)
    ok = yr.dropna(subset=["deficit"])
    summ["sustainable"] = float(ok.consumption.mean() - ok.deficit.mean()) if len(ok) else np.nan
    agri = [u for u in uses_all if demand.use_kind(u) == "agri"]
    summ["agri_base"] = float(sum(hist.loc[years[-1], u] * (1 - coef.get(u, 0)) for u in agri if u in hist))
    summ["cut"] = max(summ.get("supply", np.nan) - summ["sustainable"], 0.0)
    summ["cut_pct_agri"] = 100 * summ["cut"] / summ["agri_base"] if summ["agri_base"] > 0 else np.nan
    return dfp, summ


# ----------------------------------------------------------------------------- figures
def _rtl(fig, lang, horizontal=False):
    if lang == "fa" and horizontal:
        fig.update_xaxes(autorange="reversed")
        fig.update_yaxes(side="right")
    return fig


def trend_fig(yr, lang, title, labels):
    x = [fyear(y, lang) for y in yr.index]
    fig = go.Figure()
    fig.add_bar(x=x, y=-yr.deficit, name=labels["deficit"], marker_color=_rgba(DEF, 0.55),
                hovertemplate="%{x}<br>" + labels["deficit"] + ": %{customdata:,.0f}<extra></extra>",
                customdata=yr.deficit)
    fig.add_scatter(x=x, y=yr.renewable, name=labels["renewable"], mode="lines+markers",
                    line=dict(color=RENEW, width=3), marker=dict(size=7),
                    hovertemplate="%{x}<br>" + labels["renewable"] + ": %{y:,.0f}<extra></extra>")
    fig.add_scatter(x=x, y=yr.consumption, name=labels["consumption"], mode="lines+markers",
                    line=dict(color=CONS, width=3), marker=dict(size=7),
                    hovertemplate="%{x}<br>" + labels["consumption"] + ": %{y:,.0f}<extra></extra>")
    fig.add_hline(y=0, line_color="#64748b", line_width=1)
    _layout(fig, lang, h=400, title=title, barmode="relative")
    fig.update_yaxes(title=labels["unit"])
    fig.update_xaxes(type="category")  # "1400-01" would otherwise be read as a date
    return fig


def uses_fig(by_use, lang, title, unit):
    """Consumption by use, largest first; agriculture highlighted."""
    tot = float(by_use.sum()) or 1.0
    names = [term(u, lang) for u in by_use.index]
    colors = [AGRI if demand.use_kind(u) == "agri" else OTHER for u in by_use.index]
    pct = "٪" if lang == "fa" else "%"
    fig = rank_fig(by_use.values, names, lang, title, unit, color=colors, h=400)
    fig.update_traces(text=[f"{num(v, lang, '{:,.0f}')} ({num(100 * v / tot, lang, '{:.0f}')}{pct})"
                            for v in by_use.values])
    return fig


def rank_fig(values, labels, lang, title, unit, color=CONS, fmt="{:,.0f}", h=320):
    text = [num(v, lang, fmt) for v in values]
    fig = go.Figure(go.Bar(x=list(values), y=list(labels), orientation="h", marker_color=color, text=text,
                           textposition="outside", cliponaxis=False,
                           hovertemplate="%{y}: %{x:,.1f} " + unit + "<extra></extra>"))
    _layout(fig, lang, h=h, title=title, showlegend=False)
    vmax = max(list(values) + [1e-9]) * 1.3
    fig.update_xaxes(showticklabels=False, showgrid=False, range=[vmax, 0] if lang == "fa" else [0, vmax])
    fig.update_yaxes(autorange="reversed", side="right" if lang == "fa" else "left")
    return fig


def map_fig(shapes, sb, lang, names, unit):
    """Sub-basins coloured by consumption per area (mm of water per year). Drawn as a plain (non-tile) figure so
    that Persian labels are shaped correctly; x = longitude, y = latitude with the true aspect ratio."""
    vals = sb.depth_mm.dropna()
    lo, hi = (float(vals.min()), float(vals.max())) if len(vals) else (0.0, 1.0)
    scale = pc.sequential.YlOrRd
    fig = go.Figure()
    pts = []
    for s in shapes.get("sub_basins") or []:
        v = sb.depth_mm.get(s["id"], np.nan)
        f = 0.0 if hi <= lo or pd.isna(v) else (v - lo) / (hi - lo)
        col = pc.sample_colorscale(scale, [0.12 + 0.8 * f])[0]
        lon, lat = _lines(s["rings"])
        pts += [p for r in s["rings"] for p in r]
        c = sb.consumption.get(s["id"], np.nan)
        fig.add_scatter(x=lon, y=lat, mode="lines", fill="toself", fillcolor=col, line=dict(color="#ffffff", width=2),
                        showlegend=False, hoveron="fills", name=names.get(s["id"], s["id"]),
                        hovertemplate=f"{names.get(s['id'], s['id'])}<br>{num(c, lang, '{:,.0f}')} MCM · "
                                      f"{num(v, lang, '{:,.0f}')} {unit}<extra></extra>")
    for s in shapes.get("study_area") or []:
        lon, lat = _lines(s["rings"])
        fig.add_scatter(x=lon, y=lat, mode="lines", line=dict(color="#0b3a5b", width=2.5), hoverinfo="skip",
                        showlegend=False)
    for s in shapes.get("sub_basins") or []:
        v = sb.depth_mm.get(s["id"], np.nan)
        fig.add_annotation(x=s["label_xy"][0], y=s["label_xy"][1], showarrow=False,
                           text=f"<b>{names.get(s['id'], s['id'])}</b><br>{num(v, lang, '{:,.0f}')} {unit}",
                           font=dict(size=13, color="#0f172a", family=FONT), bgcolor="rgba(255,255,255,.75)",
                           borderpad=3)
    lat0 = float(np.mean([p[1] for p in pts])) if pts else 36.5
    fig.update_xaxes(visible=False, scaleanchor="y", scaleratio=float(np.cos(np.radians(lat0))))
    fig.update_yaxes(visible=False)
    fig.update_layout(height=520, margin=dict(l=0, r=0, t=0, b=0), font=dict(family=FONT), paper_bgcolor="#ffffff",
                      plot_bgcolor="#ffffff", hoverlabel=dict(font_family=FONT))
    return fig


def options_fig(tab, names, lang, title, labels, risk_key="drought", metric="deficit"):
    """Mean value of `metric` after each option (bars) against the present situation (line). metric = "deficit"
    (aquifer storage loss; green when it turns into a gain) or "consumption" (basins without Simaye Ab)."""
    t = tab.drop(index="base").sort_values(metric)
    base = float(tab.loc["base", metric])
    ys = [names[k] for k in t.index]
    if metric == "deficit":
        colors = ["#94a3b8" if k == risk_key else (GOOD if v <= 0 else _rgba(DEF, 0.75)) for k, v in t[metric].items()]
    else:
        colors = ["#94a3b8" if k == risk_key else CONS for k in t.index]
    text = [num(v, lang, "{:+,.0f}" if v < 0 else "{:,.0f}") for v in t[metric]]
    fig = go.Figure(go.Bar(x=t[metric], y=ys, orientation="h", marker_color=colors, text=text, textposition="outside",
                           cliponaxis=False, hovertemplate="%{y}<br>" + labels["deficit"] + ": %{x:,.1f}<extra></extra>"))
    fig.add_vline(x=base, line_dash="dash", line_color="#334155", line_width=1.5)
    fig.add_vline(x=0, line_color="#64748b", line_width=1)
    fig.add_annotation(x=base, y=1.02, yref="paper", text=labels["now"], showarrow=False, yanchor="bottom",
                       font=dict(size=12, color="#334155"))
    _layout(fig, lang, h=360, title=title, showlegend=False)
    lo = min(0.0, float(t[metric].min())) * 1.3 - 5
    hi = max(base, float(t[metric].max())) * 1.25
    fig.update_xaxes(title=labels["axis"], range=[hi, lo] if lang == "fa" else [lo, hi])
    fig.update_yaxes(autorange="reversed", side="right" if lang == "fa" else "left")
    return fig


def outlook_fig(dfp, summ, lang, title, labels):
    x = [fyear(y, lang) for y in dfp.index]
    past = dfp.obs_consumption.notna()
    fut = dfp.supply.notna() if "supply" in dfp else pd.Series(False, index=dfp.index)
    fig = go.Figure()
    if fut.any():
        xf = [x[i] for i in range(len(x)) if fut.iloc[i]]
        lo, hi = dfp.loc[fut, "supply_lo"], dfp.loc[fut, "supply_hi"]
        fig.add_scatter(x=xf + xf[::-1], y=list(hi) + list(lo)[::-1], fill="toself", mode="lines", line=dict(width=0),
                        fillcolor=_rgba(CONS, 0.12), hoverinfo="skip", showlegend=False)
        fig.add_scatter(x=xf, y=dfp.loc[fut, "supply"], name=labels["bau"], mode="lines",
                        line=dict(color=CONS, width=3, dash="dash"),
                        hovertemplate="%{x}<br>" + labels["bau"] + ": %{y:,.0f}<extra></extra>")
    fig.add_scatter(x=[x[i] for i in range(len(x)) if past.iloc[i]], y=dfp.loc[past, "obs_consumption"],
                    name=labels["past"], mode="lines+markers", line=dict(color="#0f172a", width=3), marker=dict(size=7),
                    hovertemplate="%{x}<br>" + labels["past"] + ": %{y:,.0f}<extra></extra>")
    if pd.notna(summ.get("renew_mean")):
        fig.add_hline(y=summ["renew_mean"], line_dash="dot", line_color=RENEW, line_width=2,
                      annotation_text=labels["renew"], annotation_position="top left" if lang == "fa" else "top right",
                      annotation_font=dict(color=RENEW, size=12))
    if pd.notna(summ.get("sustainable")):
        fig.add_hline(y=summ["sustainable"], line_dash="dash", line_color=GOOD, line_width=2.5,
                      annotation_text=labels["sust"], annotation_position="bottom left" if lang == "fa" else "bottom right",
                      annotation_font=dict(color=GOOD, size=12))
    _layout(fig, lang, h=460, title=title)
    fig.update_layout(legend=dict(y=-0.3))  # below the rotated year labels
    fig.update_yaxes(title=labels["unit"])
    fig.update_xaxes(type="category", tickangle=-60, tickfont=dict(size=10), categoryorder="array", categoryarray=x)
    return fig
