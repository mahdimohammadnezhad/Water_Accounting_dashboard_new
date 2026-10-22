"""Management scenarios: modify the processed data, then run the normal engine on it.

Levers (all relative to the observed year):
  use_pct         {use: %}  change of each use's withdrawal (all sources)
  gw_pct          %         change of all groundwater withdrawals (e.g. pumping quota)
  illegal_close   %         share of the illegal wells' withdrawal that is stopped
  reuse_pct       %         share of treatment-plant output reused for agriculture, replacing groundwater
  transfer_delta  MCM/yr    change of the inter-basin transfer withdrawal
  climate_pct     %         change of renewable water (Simaye Ab) and of dam inflows (wet/dry year)
  scope           "all" | "selection"  apply to the whole basin or only to the selected sub-basins/counties

Aquifer effect: the aquifer deficit (-ΔS) of the scenario is the observed deficit plus the change in
groundwater withdrawal, minus the change in return flow reaching the aquifers, minus the change in recharge.
"""
import pandas as pd

from .engine import compute

DEFAULT = {"use_pct": {}, "gw_pct": 0.0, "illegal_close": 0.0, "reuse_pct": 0.0, "transfer_delta": 0.0,
           "climate_pct": 0.0, "scope": "all"}


def is_active(s):
    return bool(s) and (any(abs(v) > 1e-9 for v in (s.get("use_pct") or {}).values()) or any(
        abs(float(s.get(k, 0))) > 1e-9 for k in ("gw_pct", "illegal_close", "reuse_pct", "transfer_delta",
                                                 "climate_pct")))


def _agri_use(uses):
    return next((u["name"] for u in uses if "کشاورزی" in u["name"]), None)


def apply(base, cfg, uses, mode, s, sbs=None, counties=None):
    """Scenario copy of `base` (W, RES, indicators changed). sbs/counties: selection for scope='selection'."""
    W = base["W"].copy()
    RES = base["RES"].copy()
    ind = base["indicators"].copy()
    ccol = "county_attr" if mode == "attribute" else "county_geo"
    if s.get("scope") == "selection" and sbs is not None and counties is not None:
        scope = W.sub_basin.isin(sbs) & W[ccol].isin(counties)
    else:
        scope = pd.Series(True, index=W.index)

    for u, pct in (s.get("use_pct") or {}).items():
        W.loc[scope & (W.use == u), "value"] *= 1 + pct / 100.0
    gw = scope & (W.source_group == "gw")
    W.loc[gw, "value"] *= 1 + s.get("gw_pct", 0) / 100.0
    W.loc[gw & (W.cls == "gw_i"), "value"] *= 1 - s.get("illegal_close", 0) / 100.0

    if s.get("transfer_delta"):
        tr = W.source_group == "transfer"
        tot = W[tr].groupby("year").value.transform("sum")
        k = ((tot + float(s["transfer_delta"])).clip(lower=0) / tot).where(tot > 0, 1.0)
        W.loc[tr, "value"] *= k

    if s.get("reuse_pct") and _agri_use(uses):
        ag = _agri_use(uses)
        tmp = dict(base, W=W)
        _, RET, _ = compute(tmp, cfg, uses, mode)
        trt = RET[RET.source_group == "treatment"]
        add = []
        for yr, g in trt.groupby("year"):
            V = g.value.sum() * s["reuse_pct"] / 100.0
            m = scope & (W.year == yr) & (W.use == ag) & (W.source_group == "gw")
            A = W.loc[m, "value"].sum()
            used = min(V, A)
            if used <= 0:
                continue
            W.loc[m, "value"] *= (A - used) / A
            top = g.loc[g.value.idxmax()]
            add.append({"year": yr, "source_group": "treatment", "source_name": cfg["treatment_label"], "use": ag,
                        "county_attr": top.county, "county_geo": top.county, "sub_basin": top.sub_basin,
                        "value": used, "cls": "treatment"})
        if add:
            W = pd.concat([W, pd.DataFrame(add)], ignore_index=True)

    c = s.get("climate_pct", 0) / 100.0
    if c and len(ind):
        rg, nr = ind.set_index("year").renew_ground.fillna(0), ind.set_index("year").nonrenewable.fillna(0)
        k = ((rg * (1 + c) + nr) / (rg + nr)).where((rg + nr) > 0, 1.0)
        g = RES.source_group == "gw"
        RES.loc[g, "value"] *= RES.loc[g, "year"].map(k).fillna(1.0)
        for col in ("renew_surface", "renew_ground"):
            ind[col] = ind[col] * (1 + c)
        ind["renew_total"] = ind.renew_surface.fillna(0) + ind.renew_ground.fillna(0)
        ind["gw_available"] = ind.renew_ground.fillna(0) + ind.nonrenewable.fillna(0)
        ds = base.get("dam_stats")
        if ds is not None and len(ds) and "inflow" in ds:
            extra = ds.groupby(["year", "dam"]).inflow.first().fillna(0) * c
            d = RES.source_group == "dam"
            RES.loc[d, "value"] += [extra.get((y, n), 0.0) for y, n in zip(RES.loc[d, "year"], RES.loc[d, "source_name"])]
    return dict(base, W=W, RES=RES, indicators=ind)


def aquifer_deficit(obs_deficit, W_b, RET_b, W_s, RET_s, rg_b, rg_s):
    """Scenario aquifer deficit (-ΔS) from the observed one and the changes in GW withdrawal, GW return and recharge."""
    dW = W_s[W_s.source_group == "gw"].value.sum() - W_b[W_b.source_group == "gw"].value.sum()
    dR = RET_s[RET_s.source_group == "gw"].value.sum() - RET_b[RET_b.source_group == "gw"].value.sum()
    return obs_deficit + dW - dR - (rg_s - rg_b)
