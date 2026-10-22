"""Uncertainty bands by Monte Carlo propagation of input errors.

Every input gets a multiplicative error factor ~ N(1, sd) (sd = relative 1-sigma error from
config `uncertainty.relative_sd`, truncated at 0):
  * withdrawals by class: metered wells, unmetered wells, illegal wells, dams, transfer, treatment, ...
  * Simaye Ab terms: renewable surface, renewable groundwater, aquifer storage change (ΔS)
  * return-flow coefficients (one factor per use, result clipped to [0, 1])
The same samples feed every derived number, so withdrawal, return, consumption, resources and the
balance check stay mutually consistent. The band is the central `level` % of the samples (default 5-95 %).
The deterministic value shown in the dashboard is the best estimate; the band only adds the range.
"""
import numpy as np
import pandas as pd


def _factor(rng, n, sd_pct):
    return np.clip(rng.normal(1.0, sd_pct / 100.0, n), 0, None)


def _q(a, level):
    lo = (100 - level) / 2
    return float(np.percentile(a, lo)), float(np.percentile(a, 100 - lo))


def simulate(Wf, coef, res, ind, unc, seed=7):
    """Wf: selected withdrawals (columns use, cls, value). coef: {use: return coef}.
    res: {"dam": x, "gw": x, "transfer": x} available volumes counted in the balance.
    ind: selection-scaled Simaye Ab terms {"renew_surface", "renew_ground", "nonrenewable"} or None.
    Returns a dict of sample arrays."""
    sd, n = unc["relative_sd"], int(unc.get("samples", 400))
    rng = np.random.default_rng(seed)
    fac = {}

    def f(key, default="gw"):
        if key not in fac:
            fac[key] = _factor(rng, n, sd.get(key, sd.get(default, 15)))
        return fac[key]

    agg = Wf.groupby(["cls", "use"]).value.sum() if len(Wf) else pd.Series(dtype=float)
    uses = sorted(set(agg.index.get_level_values(1))) if len(agg) else []
    w_use = np.zeros((n, len(uses)))
    for (cls, u), v in agg.items():
        w_use[:, uses.index(u)] += v * f(cls)
    c0 = np.array([coef.get(u, 0.0) for u in uses])
    c = np.clip(c0 * rng.normal(1.0, sd.get("return_coef", 20) / 100.0, (n, len(uses))), 0, 1)
    w = w_use.sum(axis=1)
    r = (w_use * c).sum(axis=1)

    f_rg, f_ds, f_rs = f("renew_ground"), f("storage_change"), f("renew_surface")
    rg = nr = 0.0
    if ind is not None:
        rg = float(np.nan_to_num(ind.get("renew_ground", 0.0)))
        nr = float(np.nan_to_num(ind.get("nonrenewable", 0.0)))
    gw = float(res.get("gw", 0.0))
    # the groundwater available volume = renewable GW + non-renewable, each with its own error
    gw_s = gw * (rg * f_rg + nr * f_ds) / (rg + nr) if (rg + nr) > 0 else gw * f_rg
    res_s = float(res.get("dam", 0.0)) * f("dam") + gw_s + float(res.get("transfer", 0.0)) * f("transfer")
    out = {"withdrawal": w, "return": r, "consumption": w - r, "resources": res_s, "balance": res_s - (w - r),
           "use_withdrawal": {u: w_use[:, i] for i, u in enumerate(uses)},
           "use_consumption": {u: w_use[:, i] * (1 - c[:, i]) for i, u in enumerate(uses)}}
    if ind is not None:
        rs = float(np.nan_to_num(ind.get("renew_surface", 0.0)))
        out.update(renew_surface=rs * f_rs, renew_ground=rg * f_rg, renew_total=rs * f_rs + rg * f_rg,
                   nonrenewable=nr * f_ds)
    return out


def bands(samples, level=90):
    """Sample arrays -> (low, high) tuples (nested for per-use dicts)."""
    out = {}
    for k, v in samples.items():
        out[k] = {u: _q(a, level) for u, a in v.items()} if isinstance(v, dict) else _q(v, level)
    return out


def selection_inputs(W, RES, filt_fn, year, sbs, counties, uses_sel, groups, restrict_fn, balance_groups):
    """Inputs for `simulate` consistent with the balance table of the same selection."""
    Wf = restrict_fn(filt_fn(W, year, sbs, counties, uses_sel))
    Wf = Wf[Wf.source_group.isin(groups)]
    Rf = filt_fn(RES, year, sbs, counties)
    Rf = Rf[Rf.source_group.isin([g for g in groups if g in balance_groups])]
    res = Rf.groupby("source_group").value.sum().to_dict()
    return Wf, res
