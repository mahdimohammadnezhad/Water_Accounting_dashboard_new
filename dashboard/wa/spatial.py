"""Sub-basin / county polygons, point assignment and county x sub-basin cell areas."""
import warnings

import geopandas as gpd
import numpy as np
import pandas as pd

from .config import resolve
from .text import fix_mojibake, norm, natural_key

UNKNOWN = "نامشخص"


def _read(cfg, spec):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        g = gpd.read_file(resolve(cfg, spec["shapefile"]))
    crs = cfg["basin"]["crs"]
    if g.crs is None:
        g = g.set_crs(crs)
    g = g.to_crs(crs)
    g["geometry"] = g.geometry.make_valid()
    return g


def load_sub_basins(cfg):
    spec = cfg["spatial"]["sub_basins"]
    g = _read(cfg, spec)
    g["sub_basin"] = g[spec["id_field"]].map(lambda v: norm(v))
    g = g.dissolve("sub_basin", as_index=False)[["sub_basin", "geometry"]]
    return g.sort_values("sub_basin", key=lambda s: s.map(natural_key)).reset_index(drop=True)


def load_counties(cfg):
    spec = cfg["spatial"].get("counties")
    if not spec:
        return None
    g = _read(cfg, spec)
    names = g[spec["name_field"]]
    if spec.get("fix_encoding"):
        names = names.map(lambda s: fix_mojibake(s, spec["fix_encoding"]))
    g["county"] = names.map(norm)
    return g.dissolve("county", as_index=False)[["county", "geometry"]]


def assign(points, polys, key, snap_m):
    """Polygon key for each point: inside -> that polygon; else nearest within snap_m; else NaN.
    Returns (values, method) aligned with points.index."""
    out = pd.Series(np.nan, index=points.index, dtype=object)
    how = pd.Series("بیرون از محدوده", index=points.index, dtype=object)
    j = gpd.sjoin(points[["geometry"]], polys[[key, "geometry"]], how="left", predicate="within")
    j = j[~j.index.duplicated()]
    idx = j.index[j[key].notna()]
    out.loc[idx] = j.loc[idx, key].values
    how.loc[idx] = "داخل پلیگون"
    rest = points.loc[out.isna()]
    if len(rest) and snap_m:
        n = gpd.sjoin_nearest(rest[["geometry"]], polys[[key, "geometry"]], how="left",
                              max_distance=snap_m, distance_col="_d")
        n = n[~n.index.duplicated()]
        idx = n.index[n[key].notna()]
        out.loc[idx] = n.loc[idx, key].values
        how.loc[idx] = "نزدیک‌ترین پلیگون"
    return out, how


def cell_areas(sub_basins, counties):
    """Area of every (sub_basin, county) piece. Pieces are rescaled so each sub-basin's
    pieces add up to the full sub-basin area (slivers not covered by any county are spread
    proportionally); `share` is the fraction of the whole basin."""
    sb_area = sub_basins.set_index("sub_basin").area
    if counties is None:
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


def to_plot_shapes(gdf, key, tolerance=150):
    """Simplified outline coordinates (in the work CRS) for offline plotting."""
    shapes = []
    for _, r in gdf.iterrows():
        geom = r.geometry.simplify(tolerance)
        polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
        rings = []
        for p in polys:
            if p.geom_type != "Polygon" or p.is_empty:
                continue
            rings.append([list(map(float, c[:2])) for c in p.exterior.coords])
        lp = r.geometry.representative_point()
        shapes.append({"id": str(r[key]), "rings": rings, "label_xy": [lp.x, lp.y]})
    return shapes
