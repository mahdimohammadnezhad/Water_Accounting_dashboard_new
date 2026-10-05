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

from .config import CONFIG_DIR, DEFAULT_USE_MAP, WELL_COLUMN_ALIASES, default_use
from .spatial import COUNTY_NAME_HINTS, SUB_BASIN_ID_HINTS, basin_crs, pick_field
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


def scan(folder, name=None, key=None, log=print):
    folder = Path(folder).resolve()
    notes, cfg = [], {}
    if not folder.exists():
        raise FileNotFoundError(folder)

    # ---- shapefiles
    polys, points = [], []
    for p in _files(folder, {".shp"}):
        try:
            info = pyogrio.read_info(p)
        except Exception:  # noqa: BLE001
            continue
        gt = (info.get("geometry_type") or "").lower()
        rec = {"path": p, "n": info.get("features", 0)}
        (polys if "polygon" in gt else points if "point" in gt else []).append(rec)
    if not polys:
        raise ValueError("هیچ شیپ‌فایل پلیگونی پیدا نشد / no polygon shapefile found (sub-basins are required).")
    ct_cands = sorted([p for p in polys if _hint(p["path"], CT_HINTS)], key=lambda p: -p["n"])
    sb_cands = [p for p in polys if p not in ct_cands]
    sb_cands.sort(key=lambda p: (-(p["n"] > 1), -_hint(p["path"], SB_HINTS), -p["path"].stat().st_mtime))
    sb_file = sb_cands[0]["path"] if sb_cands else polys[0]["path"]
    ct_file = ct_cands[0]["path"] if ct_cands else None
    rel = lambda p: p.relative_to(folder).as_posix()  # noqa: E731

    sb = gpd.read_file(sb_file)
    tmp = {"basin": {}}
    crs = basin_crs(tmp, sb)
    sb_field = pick_field(sb, SUB_BASIN_ID_HINTS)
    cfg["basin"] = {"key": key, "name": name or folder.name, "base_dir": None, "crs": crs}
    cfg["spatial"] = {"sub_basins": {"shapefile": rel(sb_file), "id_field": sb_field or "auto"},
                      "snap_distance_m": 5000}
    log(f"sub-basins: {rel(sb_file)} (id field: {sb_field}, {len(sb)} polygons, CRS {crs})")
    if ct_file:
        ct = gpd.read_file(ct_file)
        ct_field = pick_field(ct, COUNTY_NAME_HINTS, unique=False, prefer_persian=True)
        cfg["spatial"]["counties"] = {"shapefile": rel(ct_file), "name_field": ct_field, "fix_encoding": "auto"}
        log(f"counties: {rel(ct_file)} (name field: {ct_field})")
    else:
        notes.append("شیپ‌فایل شهرستان‌ها پیدا نشد / no county shapefile found")

    # ---- dam points (inside the basin, with dam names)
    basin_shape = sb.to_crs(crs).union_all().buffer(5000)
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

    # ---- excel files
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
