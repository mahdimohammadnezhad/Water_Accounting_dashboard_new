"""Plotly figures for the dashboard."""
import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from .config import GROUP_LABELS, GROUP_ORDER
from .text import natural_key

FONT = "Vazirmatn, Tahoma, sans-serif"
USE_COLORS = ["#2563eb", "#0d9488", "#d97706", "#7c3aed", "#db2777", "#0284c7", "#65a30d", "#475569"]
GROUP_COLORS = {"dam": "#1d4ed8", "river": "#06b6d4", "gw": "#b45309", "transfer": "#059669", "treatment": "#64748b"}
SB_COLORS = ["#38bdf8", "#4ade80", "#facc15", "#f472b6", "#a78bfa", "#fb923c", "#2dd4bf", "#94a3b8"]
COUNTY_COLORS = ["#ef4444", "#f97316", "#eab308", "#a855f7", "#ec4899", "#14b8a6", "#e11d48", "#8b5cf6", "#f59e0b"]
UNIT = "میلیون مترمکعب"

BASEMAPS = {
    "osm": "OpenStreetMap",
    "satellite": "تصویر ماهواره‌ای",
    "plain": "ساده (بدون اینترنت)",
}
ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"


def use_colors(uses):
    return {u: USE_COLORS[i % len(USE_COLORS)] for i, u in enumerate(uses)}


def _layout(fig, h=420, title=None, **kw):
    fig.update_layout(
        font=dict(family=FONT, size=13, color="#1e293b"), height=h,
        margin=dict(l=10, r=10, t=56 if title else 16, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#ffffff", hoverlabel=dict(font_family=FONT),
        legend=dict(orientation="h", yanchor="top", y=-0.12, xanchor="right", x=1, font=dict(size=12)),
        title=dict(text=f"<b>{title}</b>" if title else None, x=0.99, xanchor="right", font=dict(size=15)), **kw)
    fig.update_xaxes(gridcolor="#eef2f7", zeroline=False)
    fig.update_yaxes(gridcolor="#eef2f7", zeroline=False)
    return fig


def sankey(Wf, uses_order):
    if Wf.empty:
        return None
    d = Wf.groupby(["source_group", "source_name", "use"], as_index=False).value.sum()
    d = d[d.value > 1e-6]
    srcs = []
    for g in GROUP_ORDER:
        srcs += sorted(d.loc[d.source_group == g, "source_name"].unique(), key=natural_key)
    uses = [u for u in uses_order if u in set(d.use)]
    nodes = srcs + uses
    gmap = dict(zip(d.source_name, d.source_group))
    ucol = use_colors(uses_order)
    ix = {n: i for i, n in enumerate(nodes)}
    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(label=nodes, color=[GROUP_COLORS[gmap[s]] for s in srcs] + [ucol[u] for u in uses],
                  pad=16, thickness=18, line=dict(color="white", width=1),
                  hovertemplate="%{label}<br>%{value:,.2f} " + UNIT + "<extra></extra>"),
        link=dict(source=[ix[s] for s in d.source_name], target=[ix[u] for u in d.use], value=d.value,
                  color=[_rgba(ucol[u], 0.32) for u in d.use],
                  hovertemplate="%{source.label} ← %{target.label}<br>%{value:,.2f}<extra></extra>")))
    return _layout(fig, 540, "جریان برداشت: از منبع تا کاربری")


def bar_use_by_group(Wf, uses_order):
    d = Wf.groupby(["use", "source_group"], as_index=False).value.sum()
    fig = go.Figure()
    for g in GROUP_ORDER:
        s = d[d.source_group == g].set_index("use").value.reindex(uses_order).fillna(0)
        if s.sum() > 0:
            fig.add_bar(name=GROUP_LABELS[g], x=s.index, y=s.values, marker_color=GROUP_COLORS[g],
                        hovertemplate="%{x}<br>" + GROUP_LABELS[g] + ": %{y:,.2f}<extra></extra>")
    fig.update_layout(barmode="stack", yaxis_title=UNIT, bargap=0.35)
    return _layout(fig, 430, "برداشت هر کاربری به تفکیک نوع منبع")


def consumption_donut(by_use, uses_order):
    s = pd.Series(by_use)
    s = s[s > 1e-6]
    if s.empty:
        return None
    col = use_colors(uses_order)
    fig = go.Figure(go.Pie(labels=s.index, values=s.values, hole=0.6, sort=False,
                           marker=dict(colors=[col[u] for u in s.index], line=dict(color="white", width=2)),
                           textinfo="percent", hovertemplate="%{label}<br>%{value:,.2f} " + UNIT + "<extra></extra>"))
    fig.add_annotation(text=f"<b>{s.sum():,.1f}</b><br>مصرف کل", showarrow=False, font=dict(size=15))
    return _layout(fig, 430, "سهم کاربری‌ها از مصرف (C)")


def trend_withdrawals(by_year_use, uses_order):
    fig = go.Figure()
    col = use_colors(uses_order)
    for u in uses_order:
        if u in by_year_use.columns and by_year_use[u].sum() > 0:
            fig.add_bar(name=u, x=by_year_use.index, y=by_year_use[u], marker_color=col[u])
    fig.update_layout(barmode="stack", yaxis_title=UNIT, xaxis_type="category", bargap=0.3)
    return _layout(fig, 430, "روند برداشت سالانه به تفکیک کاربری")


def trend_balance(tot):
    fig = go.Figure()
    spec = [("resources", "منابع در دسترس (سد + زیرزمینی + انتقالی)", "#1d4ed8", "solid"),
            ("withdrawal", "برداشت", "#b45309", "solid"),
            ("consumption", "مصرف (C)", "#dc2626", "solid"),
            ("balance", "کنترل بیلان (B)", "#059669", "dot")]
    for k, name, c, dash in spec:
        fig.add_scatter(x=tot.index, y=tot[k], name=name, mode="lines+markers",
                        line=dict(color=c, dash=dash, width=3), marker=dict(size=8))
    fig.add_hline(y=0, line_color="#94a3b8", line_width=1)
    fig.update_layout(yaxis_title=UNIT, xaxis_type="category")
    return _layout(fig, 430, "روند منابع، مصارف و کنترل بیلان")


def trend_indicators(ind):
    fig = go.Figure()
    spec = [("renew_surface", "تجدیدپذیر سطحی (رواناب)", "#0ea5e9"),
            ("renew_ground", "تجدیدپذیر زیرزمینی (نفوذ)", "#b45309"),
            ("nonrenewable", "غیرتجدیدپذیر (کسری مخزن)", "#dc2626")]
    for k, name, c in spec:
        fig.add_bar(x=ind.year, y=ind[k], name=name, marker_color=c)
    fig.update_layout(barmode="group", yaxis_title=UNIT, xaxis_type="category", bargap=0.25)
    return _layout(fig, 410, "آب تجدیدپذیر و غیرتجدیدپذیر (سیمای آب)")


def heatmap(mat, title, fmt=",.2f", scale="Blues"):
    if mat.empty:
        return None
    fig = go.Figure(go.Heatmap(z=mat.values, x=list(mat.columns), y=list(mat.index), colorscale=scale,
                               text=[[("" if v == 0 or np.isnan(v) else format(v, fmt)) for v in r] for r in mat.values],
                               texttemplate="%{text}", hovertemplate="%{y} / %{x}<br>%{z:,.2f}<extra></extra>",
                               showscale=False, xgap=2, ygap=2))
    fig.update_yaxes(autorange="reversed")
    fig = _layout(fig, 170 + 52 * len(mat), title)
    fig.update_layout(margin=dict(t=60, b=40))
    return fig


# ----------------------------------------------------------------------------- map
def _lines(rings):
    lon, lat = [], []
    for ring in rings:
        lon += [p[0] for p in ring] + [None]
        lat += [p[1] for p in ring] + [None]
    return lon, lat


def basin_map(shapes, sbs_sel, wells, dams, uses_order, sb_label, basemap="osm",
              show_sb=True, show_ct=True, show_wells=True, show_dams=True):
    fig = go.Figure()
    sat = basemap == "satellite"
    all_pts = []
    if show_sb:
        for i, s in enumerate(sorted(shapes["sub_basins"], key=lambda s: natural_key(s["id"]))):
            on = s["id"] in sbs_sel
            lon, lat = _lines(s["rings"])
            all_pts += [p for r in s["rings"] for p in r]
            c = SB_COLORS[i % len(SB_COLORS)]
            fig.add_scattermap(lon=lon, lat=lat, mode="lines", fill="toself",
                               fillcolor=_rgba(c, 0.28 if on else 0.06), line=dict(color=c if on else "#94a3b8",
                                                                                   width=3 if on else 1.5),
                               name=sb_label.format(id=s["id"]), legendgroup="sb", legendgrouptitle_text="زیرحوضه‌ها",
                               hoverinfo="name")
    if show_ct:
        for i, s in enumerate(sorted(shapes["counties"], key=lambda s: s["id"])):
            lon, lat = _lines(s["rings"])
            c = COUNTY_COLORS[i % len(COUNTY_COLORS)]
            fig.add_scattermap(lon=lon, lat=lat, mode="lines", line=dict(color=c, width=3 if sat else 2.2),
                               name=s["id"], legendgroup="ct", legendgrouptitle_text="مرز شهرستان‌ها",
                               hoverinfo="name")
            fig.add_scattermap(lon=[s["label_xy"][0]], lat=[s["label_xy"][1]], mode="markers",
                               marker=dict(size=11, color=c, opacity=0.95), name=s["id"], legendgroup="ct",
                               showlegend=False, hovertemplate=f"شهرستان {s['id']}<extra></extra>")
    col = use_colors(uses_order)
    if show_wells and len(wells):
        agg = wells.dropna(subset=["lon"]).groupby(["lon", "lat", "use", "county", "sub_basin"],
                                                  as_index=False).value.sum()
        for u in uses_order:
            d = agg[agg.use == u]
            if d.empty:
                continue
            fig.add_scattermap(lon=d.lon, lat=d.lat, mode="markers", name=u, legendgroup="w",
                               legendgrouptitle_text="چاه‌ها (اندازه = برداشت)",
                               marker=dict(color=col[u], size=np.clip(np.sqrt(d.value) * 14, 3, 11), opacity=0.6),
                               customdata=np.stack([d.county, d.sub_basin, d.value], axis=1),
                               hovertemplate=f"چاه {u}<br>شهرستان: %{{customdata[0]}}<br>زیرحوضه: %{{customdata[1]}}"
                                             "<br>برداشت: %{customdata[2]:.3f} م.م.م<extra></extra>")
    if show_dams:
        d = dams.dropna(subset=["lon"])
        if len(d):
            fig.add_scattermap(lon=d.lon, lat=d.lat, mode="markers", name="سد",
                               marker=dict(size=17, color="#1d4ed8", symbol="circle"),
                               text=d.dam, hovertemplate="%{text}<extra></extra>", legendgroup="d",
                               legendgrouptitle_text="سدها")
    if all_pts:
        lons, lats = [p[0] for p in all_pts], [p[1] for p in all_pts]
        center = dict(lon=(min(lons) + max(lons)) / 2, lat=(min(lats) + max(lats)) / 2)
        span = max(max(lons) - min(lons), (max(lats) - min(lats)) * 1.3)
        zoom = max(1, math.log2(360 / span) + 0.2)
    else:
        center, zoom = dict(lon=59.4, lat=36.4), 7.5
    map_kw = dict(center=center, zoom=zoom)
    if basemap == "osm":
        map_kw["style"] = "open-street-map"
    elif sat:
        map_kw.update(style="white-bg", layers=[dict(below="traces", sourcetype="raster", source=[ESRI],
                                                     sourceattribution="Esri World Imagery")])
    else:
        map_kw["style"] = "white-bg"
    fig.update_layout(map=map_kw, height=720, margin=dict(l=0, r=0, t=0, b=0), font=dict(family=FONT),
                      legend=dict(x=0.995, xanchor="right", y=0.99, bgcolor="rgba(255,255,255,0.88)",
                                  bordercolor="#cbd5e1", borderwidth=1, font=dict(size=12), groupclick="toggleitem"),
                      hoverlabel=dict(font_family=FONT))
    return fig


def _rgba(hex_color, a):
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{a})"
