"""Balance engine: return flows, treatment output and the resource list, for a chosen county basis.

Return-flow rule (same as the DYNMIC sheet, generalized):
  * Uses are grouped per year by `return_group` (county or sub_basin).
  * Group return R = return_coef x total withdrawal of the group (all sources).
  * R x river_fraction goes to a river reach: for county groups the reach in `county_outlet_reach`
    (e.g. Mashhad -> reach 4), for sub-basin groups the reach of that sub-basin.
  * The rest goes to aquifers, split over the group's cells in proportion to their groundwater
    withdrawals (total withdrawals when the group has no groundwater).
  * treatment_fraction[county] x R is reported as treatment-plant output (an "of which" figure).
"""
import pandas as pd

from .text import natural_key

KEY = ["year", "source_group", "source_name", "use", "county", "sub_basin"]


def select_county(df, mode):
    df = df.copy()
    if "county_attr" in df:
        df["county"] = df["county_attr"] if mode == "attribute" else df["county_geo"]
        df = df.drop(columns=["county_attr", "county_geo"])
    else:
        df = df.rename(columns={"county_geo": "county"})
    return df


def compute(base, cfg, uses, mode):
    """uses: list of use dicts (possibly with user-edited coefficients). Returns W, RET, RES."""
    W = select_county(base["W"], mode)
    W = W.groupby(KEY, as_index=False).value.sum()
    RET = _returns(W, uses, cfg["county_outlet_reach"])
    sp = cfg["spatial"]
    labels = {"river": sp["river_reach_label"], "gw": sp["aquifer_label"]}
    RET["source_name"] = [cfg["treatment_label"] if g == "treatment" else labels[g].format(id=sb)
                          for g, sb in zip(RET.source_group, RET.sub_basin)]
    RES = select_county(base["RES"], mode)
    trt = RET[RET.source_group == "treatment"].groupby(["year", "source_group", "source_name", "county", "sub_basin"],
                                                       as_index=False).value.sum()
    RES = pd.concat([RES, trt], ignore_index=True)
    return W, RET, RES


def _returns(W, uses, outlet):
    out = []
    for u in uses:
        Wu = W[W.use == u["name"]]
        coef, f = float(u["return_coef"]), float(u["river_fraction"])
        if Wu.empty or coef == 0:
            continue
        g = u["return_group"]
        o = "sub_basin" if g == "county" else "county"
        tot = Wu.groupby(["year", g, o]).value.sum()
        gw = Wu[Wu.source_group == "gw"].groupby(["year", g, o]).value.sum()
        tf = u.get("treatment_fraction") or {}
        for (yr, key), s in tot.groupby(level=[0, 1]):
            s = s.droplevel([0, 1])
            T = s.sum()
            if T <= 0:
                continue
            R = coef * T

            def rec(other, kind, v):
                county, sb = (key, other) if g == "county" else (other, key)
                out.append((yr, u["name"], county, sb, kind, v))

            if g == "county":
                reach = outlet.get(key) or s.idxmax()
            if f > 0:
                if g == "county":
                    rec(reach, "river", R * f)
                else:
                    for other, w in (s / T).items():
                        rec(other, "river", R * f * w)
            if f < 1:
                try:
                    wts = gw.loc[(yr, key)]
                except KeyError:
                    wts = None
                if wts is None or wts.sum() <= 0:
                    wts = s
                for other, w in (wts / wts.sum()).items():
                    rec(other, "gw", R * (1 - f) * w)
            if tf:
                if g == "county":
                    if key in tf:
                        rec(reach, "treatment", R * tf[key])
                else:
                    for other, w in (s / T).items():
                        if other in tf:
                            rec(other, "treatment", R * w * tf[other])
    return pd.DataFrame(out, columns=["year", "use", "county", "sub_basin", "source_group", "value"])


def restrict_members(df, uses, enabled):
    """Excel-template mode: keep only the members listed for each use (e.g. 5 counties for drinking)."""
    if not enabled or df.empty:
        return df
    keep = pd.Series(True, index=df.index)
    for u in uses:
        if u.get("members") and u["breakdown"] in ("county", "sub_basin"):
            m = df.use == u["name"]
            keep &= ~m | df[u["breakdown"]].isin(u["members"])
    return df[keep]


def row_catalog(base, cfg, W, RES):
    """Ordered source rows: dams, river reaches, aquifers, transfers, treatment."""
    sp = cfg["spatial"]
    sbs = [s for s in base["meta"]["sub_basins"]]
    rows = []
    dams = list(base["dams"].dam) if len(base["dams"]) else []
    extra = sorted(set(W.loc[W.source_group == "dam", "source_name"]) - set(dams))
    dam_sb = dict(zip(base["dams"].dam, base["dams"].sub_basin)) if len(base["dams"]) else {}
    for d in dams + extra:
        rows.append(("dam", d, dam_sb.get(d)))
    for s in sbs:
        rows.append(("river", sp["river_reach_label"].format(id=s), s))
    for s in sbs + sorted(set(W.loc[W.source_group == "gw", "sub_basin"]) - set(sbs), key=natural_key):
        rows.append(("gw", sp["aquifer_label"].format(id=s), s))
    for t in dict.fromkeys(list(RES.loc[RES.source_group == "transfer", "source_name"]) +
                           list(W.loc[W.source_group == "transfer", "source_name"])):
        rows.append(("transfer", t, None))
    rows.append(("treatment", cfg["treatment_label"], None))
    return rows
