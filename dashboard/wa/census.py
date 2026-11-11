"""Population census (Iranian Statistical Centre household/population by village file, e.g. CN95_..._09.xlsx).

Records are hierarchical (code of record): 1 province, 2 county, 3 district (bakhsh), 4 rural district (dehestan),
5 city (zoned cities also have one record per urban zone, e.g. «مشهد1»..«مشهد 12», «مشهد ثامن»), 6/8 village.
Villages with 3 households or fewer are masked with «*» (counted as 0).
Urban population of a county = county total − sum of its villages (avoids double counting the zone records).
"""
import re

import pandas as pd

from .text import norm

COLS = {"rec": ["code of record"], "county_code": ["code of shahrestan"], "county": ["name of shahrestan"],
        "city": ["name of shahr"], "population": ["population"], "households": ["family"]}


def _fix(s):
    """Census spelling: final «ئ» stands for «ی» (e.g. «رضوئ», «مركزئ»)."""
    s = norm(s)
    return re.sub(r"ئ(?=\s|$)", "ی", s) if isinstance(s, str) else s


def read_census(path, sheet=0):
    df = pd.read_excel(path, sheet_name=sheet, dtype=str)
    df.columns = [str(c).strip().lower() for c in df.columns]
    pick = {}
    for k, aliases in COLS.items():
        col = next((c for c in df.columns if c in aliases), None)
        if col is None and k in ("rec", "county", "population"):
            raise KeyError(f"census: column {aliases[0]} not found")
        pick[k] = col
    d = pd.DataFrame({k: df[c].str.strip() if c else None for k, c in pick.items()})
    d["population"] = pd.to_numeric(d.population, errors="coerce").fillna(0)
    d["households"] = pd.to_numeric(d.households, errors="coerce").fillna(0) if pick["households"] else 0
    d["county"] = d.county.map(_fix)
    d["city"] = d.city.map(_fix)
    counties = d[d.rec == "2"].groupby(["county_code", "county"], as_index=False)[["population", "households"]].sum()
    villages = d[d.rec.isin(["6", "8"])].groupby("county_code").population.sum()
    counties["rural"] = counties.county_code.map(villages).fillna(0)
    counties["urban"] = (counties.population - counties.rural).clip(lower=0)
    cities = d[d.rec == "5"][["county_code", "city", "population"]].copy()
    # drop urban-zone records (their sum equals the parent city)
    zone = pd.Series(False, index=cities.index)
    for code, g in cities.groupby("county_code"):
        for _, parent in g.iterrows():
            kids = g[(g.city != parent.city) & g.city.str.startswith(parent.city)]
            if len(kids) and abs(kids.population.sum() - parent.population) <= 0.01 * max(parent.population, 1):
                zone[kids.index] = True
    cities = cities[~zone]
    cities["county"] = cities.county_code.map(dict(zip(counties.county_code, counties.county)))
    return counties[["county", "population", "urban", "rural", "households"]], cities[["county", "city", "population"]]


def is_census_file(path):
    """True if the first sheet looks like a census household/population file."""
    try:
        head = pd.read_excel(path, nrows=2)
    except Exception:  # noqa: BLE001
        return False
    cols = {str(c).strip().lower() for c in head.columns}
    return "code of record" in cols and "population" in cols


def census_year_from_name(name, default=1395):
    m = re.search(r"CN\s*(\d{2,4})", str(name), re.I)
    if not m:
        return default
    y = int(m.group(1))
    return y + 1300 if y < 100 else y


def county_key(name, aliases=None):
    """Matching key for county names written differently (spaces, dashes, official vs. common names)."""
    n = norm(name) or ""
    n = (aliases or {}).get(n, n)
    return re.sub(r"[\s\-‌]+", "", n)


# official census name -> name commonly used in well statistics (extend in the config: demand.census.county_aliases)
KNOWN_ALIASES = {"بینالود": "طرقبه-شاندیز"}

COUNTY_COLS = ["county", "name", "population", "urban", "rural", "households", "area_km2", "area_in_km2",
               "urban_pct", "rural_pct", "basis", "cities"]


def basin_population(counties, cities, polys, basin, data_counties, aliases=None, shares=None, layer_names=()):
    """Census counties that lie (partly) in the basin, with default shares of their population inside it.

    counties, cities: output of read_census. polys: GeoDataFrame [county, geometry] of whole county polygons
    in the basin CRS (country-wide layer preferred; may be None). basin: the basin polygon.
    data_counties: {county name in the withdrawal data: withdrawal}. aliases: {census name: name used in the
    data}. shares: {county: {urban: %, rural: %}} overrides from the config. layer_names: every county name of
    the polygon layer (also those far from the basin, which are not in `polys`).

    Defaults: rural % = share of the county's area inside the basin; urban % = 100 when at least half of the
    county lies inside (its towns are assumed to follow the county seat), else 0. A census county that has
    no polygon at all (e.g. a county created after the layer was drawn) counts fully if it holds at least 1 %
    of the basin's withdrawal.
    """
    aliases = {**KNOWN_ALIASES, **{norm(k): norm(v) for k, v in (aliases or {}).items()}}
    key = lambda n: county_key(n, aliases)  # noqa: E731
    area = {}
    if polys is not None and len(polys):
        for _, r in polys.iterrows():
            g = r.geometry
            area[key(r.county)] = (g.area / 1e6, g.intersection(basin).area / 1e6)
    known = set(area) | {key(n) for n in layer_names}
    total = sum(v for v in data_counties.values() if v == v) or 1.0
    in_data = {key(c) for c, v in data_counties.items() if isinstance(c, str) and v >= 0.01 * total} - known
    over = {key(k): v or {} for k, v in (shares or {}).items()}
    rows = []
    for _, r in counties.iterrows():
        k = key(r.county)
        tot, inside = area.get(k, (float("nan"), float("nan")))
        if k in area:
            frac = inside / tot if tot else 0.0
            basis = "area"
            if frac < 0.005 and k not in over:  # only touches the basin along its border
                continue
        elif k in in_data:
            frac, basis = 1.0, "data"
        elif k in over:
            frac, basis = 0.0, "config"
        else:
            continue
        urban, rural = (100.0 if frac >= 0.5 else 0.0), round(100 * frac, 1)
        if k in over:
            urban = float(over[k].get("urban", urban))
            rural = float(over[k].get("rural", rural))
            basis = "config"
        cs = cities[cities.county == r.county].sort_values("population", ascending=False)
        rows.append({"county": r.county, "name": aliases.get(norm(r.county), r.county),
                     "population": r.population, "urban": r.urban, "rural": r.rural, "households": r.households,
                     "area_km2": tot, "area_in_km2": inside, "urban_pct": urban, "rural_pct": rural, "basis": basis,
                     "cities": "، ".join(f"{c} ({p:,.0f})" for c, p in zip(cs.city, cs.population))})
    out = pd.DataFrame(rows, columns=COUNTY_COLS)
    return out.sort_values("population", ascending=False).reset_index(drop=True)


def load(cfg, polys, basin, data_counties, resolve, layer_names=()):
    """Census table of the basin from cfg['demand']['census'] ({file | files, year?, county_aliases?, shares?}).
    Returns (table, info)."""
    spec = cfg["demand"]["census"]
    files = spec.get("files") or spec.get("file")
    files = files if isinstance(files, list) else [files]
    parts_c, parts_t = [], []
    for f in files:
        p = resolve(cfg, f)
        if not p.exists():
            raise FileNotFoundError(f"فایل سرشماری پیدا نشد / census file not found: {p}")
        c, t = read_census(p, spec.get("sheet", 0))
        parts_c.append(c)
        parts_t.append(t)
    counties, cities = pd.concat(parts_c, ignore_index=True), pd.concat(parts_t, ignore_index=True)
    year = int(spec.get("year") or census_year_from_name(files[0]))
    table = basin_population(counties, cities, polys, basin, data_counties, spec.get("county_aliases"),
                             spec.get("shares"), layer_names)
    info = {"year": year, "files": [str(f) for f in files], "province_population": float(counties.population.sum()),
            "counties_in_file": int(len(counties))}
    return table, info
