"""Scan a data folder and write a basin config automatically.

Expected (any names, any sub-folders): one well-statistics Excel, one dam-statistics Excel (one sheet per
water year), the Simaye Ab PDFs, and shapefiles for sub-basins, counties and (optionally) dam points.
"""
import os
import re
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio
import yaml

from .config import CONFIG_DIR, DEFAULT_USE_MAP, WELL_COLUMN_ALIASES, default_use, regional_spec
from .spatial import COUNTY_NAME_HINTS, SUB_BASIN_ID_HINTS, basin_crs, find_study_area, pick_field, read_regional
from .text import match_column, norm, sheet_year

SKIP_DIRS = {".venv", "venv", "dashboard", ".git", "__pycache__", "data"}
SB_HINTS = ["fixed", "final", "sub", "zir", "basin", "boundary", "hoze", "حوضه", "محدوده"]
CT_HINTS = ["shahrestan", "county", "counties", "شهرستان", "shahr"]
DAM_HINTS = ["dam", "sad", "سد"]


def _files(folder, exts):
    out = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for f in files:
            if Path(f).suffix.lower() in exts and not f.startswith("~$"):
                out.append(Path(root) / f)
    return sorted(out)


def _well_score(path):
    """How well the first sheet's header matches the well-statistics columns."""
    try:
        head = pd.read_excel(path, nrows=3)
    except Exception:  # noqa: BLE001
        return 0, {}
    score, cols = 0, {}
    for key, aliases in WELL_COLUMN_ALIASES.items():
        c = match_column(head.columns, aliases)
        if c is not None:
            rank = next((i for i, a in enumerate(aliases) if norm(a).lower() in norm(c).lower()), len(aliases))
            score += 10 + (len(aliases) - rank)
            cols[key] = str(c)
    return score, cols


def _is_dam_file(path):
    try:
        xl = pd.ExcelFile(path)
    except Exception:  # noqa: BLE001
        return 0
    years = [s for s in xl.sheet_names if sheet_year(s)]
    if not years:
        return 0
    raw = xl.parse(years[0], header=None, nrows=15)
    return len(years) if any(norm(v) == "نام سد" for v in raw.values.ravel()) else 0


def _hint(path, hints):
    s = path.stem.lower()
    return sum(1 for i, h in enumerate(hints) if h in s)


def _excel_roles(folder):
    xls = _files(folder, {".xls", ".xlsx", ".xlsm"})
    wells, dams = None, None
    for p in xls:
        n = _is_dam_file(p)
        if n and (dams is None or n > dams[1]):
            dams = (p, n)
    for p in xls:
        if dams and p == dams[0]:
            continue
        s, cols = _well_score(p)
        if s >= 50 and (wells is None or s > wells[1]):
            wells = (p, s, cols)
    return wells, dams


def _study_area_from_wells(sa_all, ct_all, wells):
    """Study area holding most wells. UTM coordinates fall inside Iran in every zone that covers it (38-41),
    so the zone is chosen by name agreement: the county (or study-area) written in the well statistics must
    match the polygon the well falls in. Returns (study-area rows, zone)."""
    cols = wells[2]
    head = pd.read_excel(wells[0], nrows=2)
    sa_col = match_column(head.columns, ["محدوده مطالعاتی", "محدوده", "study area", "mahdoude"])
    use = [cols["x"], cols["y"]] + [c for c in (cols.get("county"), sa_col) if c]
    df = pd.read_excel(wells[0], usecols=use)
    df["_x"], df["_y"] = pd.to_numeric(df[cols["x"]], errors="coerce"), pd.to_numeric(df[cols["y"]], errors="coerce")
    df = df[(df._x > 0) & (df._y > 0)]
    df = df.sample(min(len(df), 3000), random_state=0).reset_index(drop=True)
    best = None
    for zone in (38, 39, 40, 41):
        pts = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df._x, df._y), crs=f"EPSG:326{zone}").to_crs(sa_all.crs)
        j = gpd.sjoin(pts, sa_all[["name", "code", "geometry"]], predicate="within")
        if j.empty:
            continue
        score = len(j) / 1e6  # tie-breaker only
        if cols.get("county") and ct_all is not None:
            jc = gpd.sjoin(pts, ct_all[["county", "geometry"]].to_crs(sa_all.crs), predicate="within")
            score += (jc[cols["county"]].map(norm) == jc.county).sum()
        elif sa_col:
            score += sum(1 for a, n in zip(j[sa_col].map(norm), j.name) if isinstance(a, str) and n and n in a)
        if best is None or score > best[0]:
            best = (score, j.code.value_counts().idxmax(), zone)
    return (sa_all[sa_all.code == best[1]], best[2]) if best else (None, None)


def scan(folder, name=None, key=None, log=print):
    folder = Path(folder).resolve()
    notes, cfg = [], {}
    if not folder.exists():
        raise FileNotFoundError(folder)
    rel = lambda p: p.relative_to(folder).as_posix()  # noqa: E731
    wells, dams = _excel_roles(folder)

    # ---- country-wide layers (configs/_regional.yaml): never taken as this basin's own layers
    reg = regional_spec({"basin": {"base_dir": str(folder)}})
    reg_files = {Path(reg[k]["shapefile"]).resolve() for k in ("study_areas", "counties") if reg and k in reg}

    # ---- shapefiles of the basin itself (layers with many features are country/province-wide)
    polys, points = [], []
    for p in _files(folder, {".shp"}):
        if p.resolve() in reg_files:
            continue
        try:
            info = pyogrio.read_info(p)
        except Exception:  # noqa: BLE001
            continue
        gt = (info.get("geometry_type") or "").lower()
        rec = {"path": p, "n": info.get("features", 0)}
        if "polygon" in gt and rec["n"] <= 60:
            polys.append(rec)
        elif "point" in gt:
            points.append(rec)
    ct_cands = sorted([p for p in polys if _hint(p["path"], CT_HINTS)], key=lambda p: -p["n"])
    sb_cands = [p for p in polys if p not in ct_cands]
    sb_cands.sort(key=lambda p: (-(p["n"] > 1), -_hint(p["path"], SB_HINTS), -p["path"].stat().st_mtime))
    sb_file = sb_cands[0]["path"] if sb_cands else None
    ct_file = ct_cands[0]["path"] if ct_cands else None
    cfg["basin"] = {"key": key, "name": name or folder.name, "base_dir": None}
    cfg["spatial"] = {"snap_distance_m": 5000}

    regional = read_regional(reg) if reg else {}
    sa_all = regional.get("study_areas")
    if sb_file:
        sb = gpd.read_file(sb_file)
        crs = basin_crs({"basin": {}}, sb)
        sb_field = pick_field(sb, SUB_BASIN_ID_HINTS)
        cfg["spatial"]["sub_basins"] = {"shapefile": rel(sb_file), "id_field": sb_field or "auto"}
        log(f"sub-basins: {rel(sb_file)} (id field: {sb_field}, {len(sb)} polygons, CRS {crs})")
        sb = sb.to_crs(crs)
        own = find_study_area(sa_all, None, sb) if sa_all is not None else None
    elif sa_all is not None and wells:
        own, zone = _study_area_from_wells(sa_all, regional.get("counties"), wells)
        if own is None:
            raise ValueError("نه شیپ‌فایل زیرحوضه پیدا شد و نه محدوده مطالعاتی از روی چاه‌ها / no sub-basin "
                             "shapefile and the study area could not be found from the wells.")
        sb = own[["geometry"]].copy()
        crs = f"EPSG:326{zone}"  # the zone the well coordinates are in
        sb = sb.to_crs(crs)
        notes.append("شیپ‌فایل زیرحوضه پیدا نشد؛ کل محدوده مطالعاتی یک زیرحوضه است / no sub-basin shapefile: "
                     "the study area is used as a single sub-basin")
    else:
        raise ValueError("هیچ شیپ‌فایل زیرحوضه‌ای پیدا نشد / no sub-basin shapefile found (and no country-wide "
                         "study-area layer in configs/_regional.yaml).")
    cfg["basin"]["crs"] = crs
    if own is not None:
        r = own.iloc[0]
        unique = (sa_all.name == r["name"]).sum() == 1
        cfg["study_area"] = r["name"] if unique else r["code"]
        log(f"study area: {r['name']} ({r['code']})")
    if ct_file:
        ct = gpd.read_file(ct_file)
        ct_field = pick_field(ct, COUNTY_NAME_HINTS, unique=False, prefer_persian=True)
        cfg["spatial"]["counties"] = {"shapefile": rel(ct_file), "name_field": ct_field, "fix_encoding": "auto"}
        log(f"counties: {rel(ct_file)} (name field: {ct_field})")
    elif reg and "counties" in reg:
        log("counties: country-wide layer (configs/_regional.yaml)")
    else:
        notes.append("شیپ‌فایل شهرستان‌ها پیدا نشد / no county shapefile found")

    # ---- dam points (inside the basin, with dam names)
    basin_shape = sb.union_all().buffer(5000)
    best = None
    for p in points:
        if not _hint(p["path"], DAM_HINTS):
            continue
        try:
            g = gpd.read_file(p["path"])
            g = (g.set_crs(crs) if g.crs is None else g).to_crs(crs)
            inside = int(g.within(basin_shape).sum())
            field = pick_field(g, ["name", "nam", "dam"], unique=False, prefer_persian=True)
        except Exception:  # noqa: BLE001
            continue
        if inside and (best is None or inside > best[1]):
            best = (p["path"], inside, field)

    # ---- excel files (detected above)
    if wells:
        cfg["wells"] = {"file": rel(wells[0]), "sheet": 0, "columns": wells[2], "unlocated": "county_majority"}
        log(f"wells: {rel(wells[0])} columns={wells[2]}")
        cfg["county_mode_default"] = "attribute" if "county" in wells[2] else "geo"
    else:
        notes.append("فایل آمار چاه‌ها پیدا نشد / no well-statistics Excel found")
        cfg["county_mode_default"] = "geo"
    if dams:
        cfg["dams"] = {"file": rel(dams[0]), "list": []}
        if best:
            cfg["dams"]["points"] = {"shapefile": rel(best[0]), "name_field": best[2]}
        log(f"dams: {rel(dams[0])} ({dams[1]} yearly sheets); points: {rel(best[0]) if best else '-'}")
    else:
        notes.append("فایل آمار سدها پیدا نشد / no dam-statistics Excel found")

    # ---- Simaye Ab PDFs: the folder holding most PDFs
    pdfs = _files(folder, {".pdf"})
    transfer = False
    if pdfs:
        by_dir = pd.Series([p.parent for p in pdfs]).value_counts()
        pdir = by_dir.index[0]
        cfg["simaye_ab"] = {"folder": rel(pdir) if pdir != folder else ".", "pattern": "*.pdf", "assume_deficit": True}
        cfg["indicators"] = "simaye_ab"
        from .simaye_ab import read_folder
        rows, _ = read_folder(pdir)
        log(f"simaye ab: {rel(pdir) if pdir != folder else '.'} -> {len(rows)} of {by_dir.iloc[0]} PDFs read")
        if not rows:
            notes.append("جدول بیلان در PDFها خوانده نشد / no balance table could be read from the PDFs")
        transfer = any(r.get("transfer_in") for r in rows)
    else:
        notes.append("PDF سیمای آب پیدا نشد / no Simaye Ab PDF found")
    if transfer:
        cfg["transfers"] = [{"name": "آب انتقالی", "source": "simaye_ab", "field": "transfer_in", "use": "شرب",
                             "county": "auto", "sub_basin": "auto"}]

    # ---- uses found in the data (default return-flow parameters, editable)
    names = []
    if wells:
        col = wells[2].get("use")
        if col:
            raw = pd.read_excel(wells[0], usecols=[col])[col].map(norm).dropna().unique()
            names += [DEFAULT_USE_MAP.get(u, u) for u in raw]
    if dams:
        names += ["شرب", "کشاورزی", "صنعتی", "خدمات"]
    order = ["شرب", "شرب روستایی", "کشاورزی", "صنعتی", "خدمات"]
    names = sorted(dict.fromkeys(names), key=lambda n: order.index(n) if n in order else 99)
    cfg["uses"] = [{k: v for k, v in default_use(n).items() if k in ("name", "return_coef", "river_fraction",
                                                                      "return_group")} for n in names]
    return cfg, notes


def slug(text):
    s = re.sub(r"[^A-Za-z0-9_]+", "_", str(text)).strip("_").lower()
    return s or "basin"


def write_config(cfg, folder, key=None):
    folder = Path(folder).resolve()
    key = key or cfg["basin"].get("key") or slug(folder.name)
    if key in ("basin",) or not re.match(r"^[a-z0-9_]+$", key):
        key = slug(key)
    n, base = 2, key
    while (CONFIG_DIR / f"{key}.yaml").exists():
        key, n = f"{base}_{n}", n + 1
    cfg["basin"]["key"] = key
    try:
        cfg["basin"]["base_dir"] = os.path.relpath(folder, CONFIG_DIR).replace("\\", "/")
    except ValueError:  # different drive on Windows
        cfg["basin"]["base_dir"] = str(folder).replace("\\", "/")
    header = ("# Generated automatically by new_basin.py / the dashboard's 'add basin' panel.\n"
              "# Review and edit freely: return coefficients (uses), county_outlet_reach, dam names (dams.list),\n"
              "# transfers. See configs/mashhad.yaml for a fully documented example.\n")
    path = CONFIG_DIR / f"{key}.yaml"
    path.write_text(header + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path
