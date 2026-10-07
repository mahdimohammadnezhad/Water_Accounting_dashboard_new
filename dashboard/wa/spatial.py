"""Sub-basin / county polygons, point assignment and county x sub-basin cell areas."""
import math
import warnings

import geopandas as gpd
import numpy as np
import pandas as pd

from .config import resolve
from .text import auto_fix_names, has_persian, natural_key, norm

UNKNOWN = "نامشخص"
SUB_BASIN_ID_HINTS = ["layer", "id", "sub_basin", "subbasin", "code", "name", "zir", "zone"]
COUNTY_NAME_HINTS = ["per_nam", "shahrestan", "county", "name", "nam", "شهرستان"]


def utm_crs(gdf):
    """UTM zone of a layer's centroid (for layers stored in lon/lat)."""
    c = gdf.to_crs(4326).union_all().centroid
    zone = int((c.x + 180) // 6) + 1
    return f"EPSG:{32600 + zone if c.y >= 0 else 32700 + zone}"


def basin_crs(cfg, sub_basins_raw):
    """Working (metric) CRS: config -> sub-basin shapefile if projected -> UTM zone of its centroid."""
    if cfg["basin"].get("crs"):
        return cfg["basin"]["crs"]
    crs = sub_basins_raw.crs
    if crs is not None and crs.is_projected:
        return crs.to_string()
    if crs is None:
        return "EPSG:32640"
    return utm_crs(sub_basins_raw)


def _read(cfg, spec):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        g = gpd.read_file(resolve(cfg, spec["shapefile"]), encoding=spec.get("encoding"))
    if g.crs is None:
        g = g.set_crs(cfg["basin"].get("crs") or "EPSG:32640")
    return g


def _prepare(cfg, g):
    g = g.to_crs(cfg["basin"]["crs"])
    g["geometry"] = g.geometry.make_valid()
    return g[g.geometry.notna() & ~g.geometry.is_empty]


def pick_field(g, hints, unique=True, prefer_persian=False):
    cols = [c for c in g.columns if c != "geometry"]
    good = []
    for c in cols:
        s = g[c]
        if s.isna().all():
            continue
        if unique and s.nunique() < len(g):
            continue
        good.append(c)
    if not good:
        return None
    if prefer_persian:
        fixed = {c: auto_fix_names(list(g[c].astype(str))) for c in good if g[c].dtype == object}
        pers = [c for c, v in fixed.items() if sum(has_persian(x) for x in v) >= 0.6 * len(v)]
        if pers:
            good = pers + [c for c in good if c not in pers]
    for h in hints:
        for c in good:
            if c.lower() == h:
                return c
    for h in hints:
        for c in good:
            if h in c.lower():
                return c
    return good[0]


def load_sub_basins(cfg):
    spec = cfg["spatial"]["sub_basins"]
    g = _read(cfg, spec)
    cfg["basin"]["crs"] = basin_crs(cfg, g)
    g = _prepare(cfg, g)
    field = spec.get("id_field")
    if not field or field == "auto" or field not in g:
        field = pick_field(g, SUB_BASIN_ID_HINTS)
    ids = auto_fix_names(list(g[field]), spec.get("fix_encoding", "auto")) if field else list(range(1, len(g) + 1))
    g["sub_basin"] = [norm(v) for v in ids]
    g = g.dissolve("sub_basin", as_index=False)[["sub_basin", "geometry"]]
    spec["_id_field_used"] = field
    return g.sort_values("sub_basin", key=lambda s: s.map(natural_key)).reset_index(drop=True)


def load_counties(cfg, sub_basins=None):
    spec = cfg["spatial"].get("counties")
    if not spec:
        return None
    g = _prepare(cfg, _read(cfg, spec))
    field = spec.get("name_field")
    if not field or field == "auto" or field not in g:
        field = pick_field(g, COUNTY_NAME_HINTS, unique=False, prefer_persian=True)
    names = auto_fix_names(list(g[field].astype(str)), spec.get("fix_encoding", "auto"))
    g["county"] = [norm(v) for v in names]
    g = g.dissolve("county", as_index=False)[["county", "geometry"]]
    if sub_basins is not None and len(g) > 1:  # keep counties that really overlap the basin (> 0.5 km2)
        basin = sub_basins.union_all()
        g = g[g.geometry.intersection(basin).area > 5e5].reset_index(drop=True)
    return g


def assign(points, polys, key, snap_m):
    """Polygon key for each point: inside -> that polygon; else nearest within snap_m; else NaN.
    Returns (values, method) aligned with points.index."""
    out = pd.Series(np.nan, index=points.index, dtype=object)
    how = pd.Series("outside", index=points.index, dtype=object)
    if polys is None or polys.empty:
        return out, how
    j = gpd.sjoin(points[["geometry"]], polys[[key, "geometry"]], how="left", predicate="within")
    j = j[~j.index.duplicated()]
    idx = j.index[j[key].notna()]
    out.loc[idx] = j.loc[idx, key].values
    how.loc[idx] = "inside"
    rest = points.loc[out.isna()]
    if len(rest) and snap_m:
        n = gpd.sjoin_nearest(rest[["geometry"]], polys[[key, "geometry"]], how="left",
                              max_distance=snap_m, distance_col="_d")
        n = n[~n.index.duplicated()]
        idx = n.index[n[key].notna()]
        out.loc[idx] = n.loc[idx, key].values
        how.loc[idx] = "nearest"
    return out, how


def cell_areas(sub_basins, counties):
    """Area of every (sub_basin, county) piece. Pieces are rescaled so each sub-basin's
    pieces add up to the full sub-basin area (slivers not covered by any county are spread
    proportionally); `share` is the fraction of the whole basin."""
    sb_area = sub_basins.set_index("sub_basin").area
    if counties is None or counties.empty:
        cells = pd.DataFrame({"sub_basin": sb_area.index, "county": UNKNOWN, "area_km2": sb_area.values / 1e6})
    else:
        inter = gpd.overlay(sub_basins, counties, how="intersection", keep_geom_type=True)
        inter["a"] = inter.area
        cells = inter.groupby(["sub_basin", "county"], as_index=False)["a"].sum()
        cells = cells[cells.a > 1e3]  # drop < 0.001 km2 slivers
        tot = cells.groupby("sub_basin").a.transform("sum")
        cells["area_km2"] = cells.a / tot * cells.sub_basin.map(sb_area) / 1e6
        missing = set(sb_area.index) - set(cells.sub_basin)
        extra = pd.DataFrame({"sub_basin": list(missing), "county": UNKNOWN,
                              "area_km2": [sb_area[m] / 1e6 for m in missing]})
        cells = pd.concat([cells[["sub_basin", "county", "area_km2"]], extra], ignore_index=True)
    cells["share"] = cells.area_km2 / cells.area_km2.sum()
    return cells.reset_index(drop=True)


# ----------------------------------------------------------------------------- country-wide layers
STUDY_AREA_NAME_HINTS = ["mah_name", "mahdoude", "name", "nam"]
STUDY_AREA_CODE_HINTS = ["mah_code", "code", "id"]


def read_regional(spec, around=None):
    """Country-wide layers in their own CRS: {'study_areas': [name, code, province, geometry],
    'counties': [county, geometry]} (keys only for layers that exist).
    `around` (a GeoSeries) limits reading to features near the basin, which is much faster."""
    out = {}
    if not spec:
        return out
    kw = {"bbox": around} if around is not None else {}
    if "study_areas" in spec:
        s = spec["study_areas"]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            g = gpd.read_file(s["shapefile"], **kw)
        if g.crs is None:
            g = g.set_crs(4326)
        nf = s.get("name_field") if s.get("name_field") in g else pick_field(g, STUDY_AREA_NAME_HINTS, False, True)
        cf = s.get("code_field") if s.get("code_field") in g else pick_field(g, STUDY_AREA_CODE_HINTS)
        pf = s.get("province_field") if s.get("province_field") in g else None
        enc = s.get("fix_encoding", "auto")
        g["name"] = [norm(v) for v in auto_fix_names(list(g[nf].astype(str)), enc)]
        g["code"] = g[cf].map(norm) if cf else g.index.astype(str)
        g["province"] = [norm(v) for v in auto_fix_names(list(g[pf].astype(str)), enc)] if pf else None
        g["geometry"] = g.geometry.make_valid()
        out["study_areas"] = g[["name", "code", "province", "geometry"]]
    if "counties" in spec:
        s = spec["counties"]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            g = gpd.read_file(s["shapefile"], **kw)
        if g.crs is None:
            g = g.set_crs(4326)
        nf = s.get("name_field") if s.get("name_field") in g else pick_field(g, COUNTY_NAME_HINTS, False, True)
        g["county"] = [norm(v) for v in auto_fix_names(list(g[nf].astype(str)), s.get("fix_encoding", "auto"))]
        g["geometry"] = g.geometry.make_valid()
        out["counties"] = g.dissolve("county", as_index=False)[["county", "geometry"]]
    return out


def find_study_area(study_areas, key=None, sub_basins=None):
    """The basin's own study area: by code or name (`key`), else the one overlapping the sub-basins most."""
    if study_areas is None or study_areas.empty:
        return None
    if key:
        k = norm(key)
        hit = study_areas[(study_areas.code == k) | (study_areas.name == k)]
        if hit.empty:  # partial name, e.g. 'مشهد - چناران' -> 'مشهد'
            hit = study_areas[study_areas.name.map(lambda n: bool(n) and (n in k or k in n))]
        if len(hit) > 1 and sub_basins is not None:
            ov = hit.to_crs(sub_basins.crs).intersection(sub_basins.union_all()).area
            hit = hit.loc[[ov.idxmax()]]
        return hit.iloc[[0]] if len(hit) else None
    if sub_basins is not None:
        sa = study_areas.to_crs(sub_basins.crs)
        ov = sa.intersection(sub_basins.union_all()).area
        return study_areas.loc[[ov.idxmax()]] if ov.max() > 0 else None
    return None


def sub_basins_from_study_area(cfg, sa_row):
    """A basin without a sub-basin shapefile: the study area itself is the single sub-basin."""
    g = sa_row[["name", "geometry"]].rename(columns={"name": "sub_basin"}).reset_index(drop=True)
    cfg["basin"]["crs"] = basin_crs(cfg, g)
    return _prepare(cfg, g)[["sub_basin", "geometry"]]


def counties_from_regional(regional_counties, sub_basins):
    g = regional_counties.to_crs(sub_basins.crs)
    g = g[g.geometry.intersection(sub_basins.union_all()).area > 5e5]
    return g.reset_index(drop=True)


def context_layers(regional, sub_basins, own_sa, basin_counties, buffer_km):
    """Neighbouring study areas / counties (lon-lat plot shapes) within buffer_km of the basin."""
    out = {"study_area": [], "context_study_areas": [], "context_counties": []}
    area = sub_basins.union_all().buffer(buffer_km * 1000)
    if own_sa is not None:
        out["study_area"] = to_plot_shapes(own_sa.to_crs(4326), "name", tolerance=0.0015)
    if "study_areas" in regional:
        sa = regional["study_areas"]
        sa = sa[sa.to_crs(sub_basins.crs).intersects(area)]
        if own_sa is not None:
            sa = sa[sa.code != own_sa.code.iloc[0]]
        out["context_study_areas"] = to_plot_shapes(sa.to_crs(4326), "name", tolerance=0.004)
    if "counties" in regional:
        ct = regional["counties"]
        ct = ct[ct.to_crs(sub_basins.crs).intersects(area)]
        if basin_counties is not None:
            ct = ct[~ct.county.isin(set(basin_counties.county))]
        out["context_counties"] = to_plot_shapes(ct.to_crs(4326), "county", tolerance=0.004)
    return out


def to_plot_shapes(gdf, key, tolerance=150):
    """Simplified outline coordinates for plotting."""
    shapes = []
    for _, r in gdf.iterrows():
        geom = r.geometry.simplify(tolerance)
        polys = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
        rings = []
        for p in polys:
            if p.geom_type != "Polygon" or p.is_empty:
                continue
            rings.append([list(map(float, c[:2])) for c in p.exterior.coords])
        lp = r.geometry.representative_point()
        if not math.isnan(lp.x):
            shp = {"id": str(r[key]), "rings": rings, "label_xy": [lp.x, lp.y]}
            if "province" in r and isinstance(r["province"], str):
                shp["province"] = r["province"]
            shapes.append(shp)
    return shapes
