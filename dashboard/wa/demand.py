"""Water demand: past estimate and future projections under scenarios.

Population: census population of the area (wa/census.py) carried forward / backward with a table of annual
growth rates ({from year: rate %}); the future band uses rate -/+ growth_band. Without a census the same
rates give a relative index. Population-driven uses (drinking, services) grow with the population and an
optional change of per-capita use; industry grows with its own rate; agriculture and other uses stay at the
base year unless a scenario changes them. Consumption = demand x (1 - return coef).

Scenarios
  supply  "تأمین آب شرب و صنعت": drinking, services and industry demand fully supplied; agriculture unchanged.
  balance "تعادل‌بخشی": same drinking/industry growth, agriculture cut step by step so that total consumption
          reaches target% (default 100 %) of the mean renewable water by the target year (not below a floor).
  trend   "بازنگری اقدامات اجرایی": the observed trend of the past years (effect of the measures already taken)
          continued (linear fit of past consumption, with its prediction band).
Past demand estimate: population-driven uses scaled from the base year with the population of each year.
"""
import numpy as np
import pandas as pd


def use_kind(u):
    if "شرب" in u:
        return "pop"
    if "خدمات" in u:
        return "pop"
    if "صنعت" in u:
        return "industry"
    if "کشاورزی" in u:
        return "agri"
    return "other"


def year_label(y):
    return f"{y}-{(y + 1) % 100:02d}"


def year_start(label):
    return int(str(label)[:4])


DEFAULT_RATE = 1.3
DEFAULTS = {"horizon": 1420, "growth": None, "growth_band": 0.5, "g_industry": 2.0, "percap_change": 0.0,
            "target_pct": 100.0, "target_year": 1415, "agri_floor": 40.0}


def growth_periods(p, census_year=None, base_year=None):
    """[(from_year, rate %)] sorted by year. `p['growth']` may be a list of {from, rate} dicts or (from, rate)
    pairs; older configs with g_low / g_mid / g_high still work (g_mid for every year)."""
    out = []
    for r in p.get("growth") or []:
        f, v = (r.get("from"), r.get("rate")) if isinstance(r, dict) else tuple(r)[:2]
        try:
            f, v = int(float(f)), float(v)
        except (TypeError, ValueError):
            continue
        if v == v:
            out.append((f, v))
    if out:
        return sorted(dict(out).items())
    mid = float(p.get("g_mid", DEFAULT_RATE))
    start = int(census_year or (base_year or 1400) - 5)
    return [(start, mid)] + ([(int(base_year) + 1, mid)] if base_year and base_year + 1 > start else [])


def growth_band(p):
    if p.get("growth_band") is not None:
        return float(p["growth_band"])
    if p.get("g_low") is not None and p.get("g_high") is not None:
        return (float(p["g_high"]) - float(p["g_low"])) / 2
    return 0.5


def rate_at(periods, y):
    """Growth rate (%) in force in year y: the last period starting at or before y (the first one before it)."""
    r = periods[0][1]
    for f, v in periods:
        if y >= f:
            r = v
    return r


def population_series(p0, y_ref, periods, y_from, y_to, y_base, band=0.0):
    """Population by year (start year of the water year) from p0 in y_ref. P(y) = P(y-1) x (1 + rate(y)).
    After y_base the low / high series grow with rate -/+ band (the band opens from the base year)."""
    lo_y, hi_y = min(y_from, y_ref), max(y_to, y_ref, y_base)
    mid = {y_ref: float(p0)}
    for y in range(y_ref + 1, hi_y + 1):
        mid[y] = mid[y - 1] * (1 + rate_at(periods, y) / 100)
    for y in range(y_ref - 1, lo_y - 1, -1):
        mid[y] = mid[y + 1] / (1 + rate_at(periods, y + 1) / 100)
    lo, hi = dict(mid), dict(mid)
    for y in range(max(y_base, y_ref) + 1, hi_y + 1):
        r = rate_at(periods, y)
        lo[y] = lo[y - 1] * (1 + (r - band) / 100)
        hi[y] = hi[y - 1] * (1 + (r + band) / 100)
    return pd.DataFrame({"pop": mid, "pop_lo": lo, "pop_hi": hi}).sort_index()


def project(hist_w, coef, renew, renew_sd_pct, p, pop0=None, census_year=None):
    """hist_w: DataFrame index=year label, columns=use, withdrawal (MCM) of the selection.
    coef: {use: return coef}. renew: Series year label -> renewable water of the selection (may be empty).
    pop0: census population of the selection in census_year (None -> growth rates act on a relative index).
    Returns (frame indexed by year label, summary dict)."""
    p = {**DEFAULTS, **(p or {})}
    hist_w = hist_w.fillna(0)
    years = sorted(hist_w.index, key=year_start)
    y0 = year_start(years[-1])
    base = hist_w.loc[years[-1]]
    uses = list(hist_w.columns)
    kinds = {u: use_kind(u) for u in uses}
    c = np.array([1 - coef.get(u, 0) for u in uses])
    future = list(range(y0 + 1, int(p["horizon"]) + 1))
    T = max(len(future), 1)
    absolute = bool(pop0) and pop0 > 0 and census_year is not None
    periods = growth_periods(p, census_year if absolute else None, y0)
    band = growth_band(p)
    y_ref = int(census_year) if absolute else y0
    pop = population_series(pop0 if absolute else 1.0, y_ref, periods, year_start(years[0]), int(p["horizon"]), y0,
                            band)
    p_base = float(pop.loc[y0, "pop"])

    def withdrawals(t, col="pop"):
        """Withdrawal by use t years after the base year (t may be negative); col = pop / pop_lo / pop_hi."""
        pc = 1 + p["percap_change"] / 100 * min(max(t, 0), T) / T
        f = {"pop": float(pop.loc[y0 + t, col]) / p_base * pc, "industry": (1 + p["g_industry"] / 100) ** t,
             "agri": 1.0, "other": 1.0}
        return np.array([base[u] * f[kinds[u]] for u in uses])

    ip = [i for i, u in enumerate(uses) if kinds[u] == "pop"]
    rows = {}
    # observed
    for y in years:
        w = hist_w.loc[y].values
        ys = year_start(y)
        rows[y] = {"obs_withdrawal": w.sum(), "obs_consumption": float((w * c).sum())}
        rows[y].update(pop.loc[ys].to_dict())
        if absolute and ip:
            rows[y]["percap"] = float(w[ip].sum()) * 1e9 / (float(pop.loc[ys, "pop"]) * 365)
        # past demand estimate: population-driven uses scaled with the population, the others as observed
        t = ys - y0
        wp = withdrawals(t)
        est = np.array([wp[i] if kinds[u] in ("pop", "industry") else w[i] for i, u in enumerate(uses)])
        rows[y]["demand_est"] = float((est * c).sum())
    # renewable water: history and a constant future level (mean) with its uncertainty band
    rmean = float(renew.mean()) if len(renew) else np.nan
    if len(renew):
        rng = np.random.default_rng(3)
        samp = rng.choice(renew.values, 4000) * rng.normal(1, renew_sd_pct / 100, 4000)
        r_lo, r_hi = np.percentile(samp, [5, 95])
        for y in years:
            if y in renew.index:
                rows[y]["renew"] = renew[y]
                rows[y]["renew_lo"] = renew[y] * (1 - 1.645 * renew_sd_pct / 100)
                rows[y]["renew_hi"] = renew[y] * (1 + 1.645 * renew_sd_pct / 100)
    # trend scenario: linear fit of past consumption
    x = np.array([year_start(y) for y in years], dtype=float)
    yv = np.array([rows[y]["obs_consumption"] for y in years])
    n = len(x)
    if n >= 3:
        b, a = np.polyfit(x, yv, 1)
        resid = yv - (a + b * x)
        s = np.sqrt((resid ** 2).sum() / (n - 2))
        sxx = ((x - x.mean()) ** 2).sum()
    target = p["target_pct"] / 100 * rmean if len(renew) else np.nan
    ia = [i for i, u in enumerate(uses) if kinds[u] == "agri"]
    reached_year = None
    for yy in future:
        t = yy - y0
        lab = year_label(yy)
        r = rows.setdefault(lab, {})
        r.update(pop.loc[yy].to_dict())
        w_mid, w_lo, w_hi = withdrawals(t), withdrawals(t, "pop_lo"), withdrawals(t, "pop_hi")
        r["supply"], r["supply_lo"], r["supply_hi"] = (float((w * c).sum()) for w in (w_mid, w_lo, w_hi))
        r["supply_withdrawal"] = float(w_mid.sum())
        # balancing: agriculture consumption ramps to what the target leaves (not below the floor)
        if len(renew) and ia:
            agri_base = float((w_mid[ia] * c[ia]).sum())
            non_agri = r["supply"] - agri_base
            need = max(p["agri_floor"] / 100 * agri_base, target - non_agri)
            ramp = min(t / max(p["target_year"] - y0, 1), 1.0)
            agri = agri_base + (min(need, agri_base) - agri_base) * ramp
            r["balance"] = non_agri + agri
            if reached_year is None and r["balance"] <= target + 1e-6:
                reached_year = lab
        if n >= 3:
            pred = a + b * yy
            half = 1.645 * s * np.sqrt(1 + 1 / n + (yy - x.mean()) ** 2 / sxx)
            r["trend"], r["trend_lo"], r["trend_hi"] = max(pred, 0), max(pred - half, 0), max(pred + half, 0)
        if len(renew):
            r["renew"], r["renew_lo"], r["renew_hi"] = rmean, r_lo, r_hi
    df = pd.DataFrame(rows).T
    df = df.loc[sorted(df.index, key=year_start)]
    if len(renew):
        df["target"] = target
    end = year_label(int(p["horizon"]))
    summary = {"base_year": years[-1], "horizon": end, "renew_mean": rmean, "target": target,
               "reached_year": reached_year, "trend_slope": float(b) if n >= 3 else np.nan,
               "pop_base_consumption": float(sum(base[u] * c[i] for i, u in enumerate(uses) if kinds[u] == "pop")),
               "pop_absolute": absolute, "census_year": int(census_year) if absolute else None,
               "pop_census": float(pop0) if absolute else None, "pop_base": p_base,
               "periods": periods, "growth_band": band}
    end_y = int(p["horizon"])
    summary["pop_end"], summary["pop_end_lo"], summary["pop_end_hi"] = (float(pop.loc[end_y, k]) for k in
                                                                        ("pop", "pop_lo", "pop_hi"))
    if absolute and ip:
        summary["percap"] = float(base.iloc[ip].sum()) * 1e9 / (p_base * 365)
    for k in ("supply", "balance", "trend"):
        if k in df and end in df.index and pd.notna(df.loc[end, k]):
            summary[k] = float(df.loc[end, k])
    return df, summary
