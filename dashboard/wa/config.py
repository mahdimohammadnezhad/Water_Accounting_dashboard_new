"""Basin configuration: one YAML file per basin under dashboard/configs/."""
import hashlib
import json
import os
from pathlib import Path

import pandas as pd
import yaml

from .text import norm

DASHBOARD_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = DASHBOARD_DIR / "configs"
PROCESSED_DIR = DASHBOARD_DIR / "data" / "processed"

# Internal keys for source groups; Persian labels are what users see.
GROUP_LABELS = {
    "dam": "سد",
    "river": "بازه رودخانه",
    "gw": "آب زیرزمینی",
    "transfer": "انتقالی",
    "treatment": "تصفیه خانه",
}
GROUP_ORDER = ["dam", "river", "gw", "transfer", "treatment"]


def list_configs():
    return sorted(CONFIG_DIR.glob("*.yaml"))


def load_config(path):
    path = Path(path)
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    basin = cfg.setdefault("basin", {})
    basin.setdefault("key", path.stem)
    basin.setdefault("name", path.stem)
    basin["base_dir"] = str((path.parent / basin.get("base_dir", ".")).resolve())
    cfg["_path"] = str(path)

    sp = cfg.setdefault("spatial", {})
    sp.setdefault("sub_basin_label", "زیرحوضه {id}")
    sp.setdefault("river_reach_label", "بازه رودخانه {id}")
    sp.setdefault("aquifer_label", "آبخوان زیرحوضه {id}")
    sp.setdefault("snap_distance_m", 5000)

    for u in cfg.get("uses", []):
        u["name"] = norm(u["name"])
        u.setdefault("return_coef", 0.0)
        u.setdefault("river_fraction", 0.0)
        u.setdefault("return_group", "sub_basin")
        u.setdefault("breakdown", u["return_group"])
        u["members"] = [norm(m) for m in u.get("members", [])] or None
        u["treatment_fraction"] = {norm(k): v for k, v in (u.get("treatment_fraction") or {}).items()}
    cfg["county_outlet_reach"] = {norm(k): str(v) for k, v in (cfg.get("county_outlet_reach") or {}).items()}
    cfg.setdefault("balance_source_groups", ["dam", "gw", "transfer"])
    cfg.setdefault("treatment_label", "تصفیه خانه")
    cfg.setdefault("county_mode_default", "attribute")
    return cfg


def resolve(cfg, rel):
    p = Path(rel)
    return p if p.is_absolute() else Path(cfg["basin"]["base_dir"]) / p


def input_files(cfg):
    """Every file the build reads — used to detect when the processed cache is stale."""
    files = []
    sp = cfg["spatial"]
    for key in ("sub_basins", "counties"):
        if key in sp:
            files.append(sp[key]["shapefile"])
    if "wells" in cfg:
        files.append(cfg["wells"]["file"])
        if cfg["wells"].get("location_overrides"):
            files.append(cfg["wells"]["location_overrides"])
    if "dams" in cfg:
        files.append(cfg["dams"]["file"])
        if cfg["dams"].get("points"):
            files.append(cfg["dams"]["points"]["shapefile"])
    for t in cfg.get("transfers") or []:
        if "table" in t:
            files.append(t["table"]["file"])
    for s in cfg.get("special_withdrawals") or []:
        files.append(s["table"]["file"])
    ind = cfg.get("indicators") or {}
    if isinstance(ind, dict):
        files += [t["file"] for t in ind.values()]
    if cfg.get("simaye_ab"):
        folder = resolve(cfg, cfg["simaye_ab"]["folder"])
        files += sorted(folder.glob(cfg["simaye_ab"].get("pattern", "*.pdf")))
    out = []
    for f in dict.fromkeys(files):
        p = resolve(cfg, f)
        out.append(p)
        if p.suffix.lower() == ".shp":
            out.append(p.with_suffix(".dbf"))
    return out


def signature(cfg):
    """Hash of config contents + input file mtimes/sizes."""
    h = hashlib.sha1()
    h.update(Path(cfg["_path"]).read_bytes())
    for mod in ("loaders.py", "spatial.py", "build.py", "text.py", "simaye_ab.py"):  # code changes invalidate cache
        h.update((Path(__file__).parent / mod).read_bytes())
    for p in input_files(cfg):
        st = os.stat(p) if p.exists() else None
        h.update(f"{p}|{st.st_mtime if st else 0}|{st.st_size if st else 0}".encode())
    return h.hexdigest()[:16]


def processed_dir(cfg):
    return PROCESSED_DIR / cfg["basin"]["key"]


_EXCEL_CACHE = {}


def read_table(cfg, spec, columns=None):
    """Read a sheet/CSV described by {file, sheet?, filter?}; rename columns via `columns` {canonical: header}."""
    path = resolve(cfg, spec["file"])
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path)
    else:
        key = str(path)
        if key not in _EXCEL_CACHE:
            _EXCEL_CACHE[key] = pd.ExcelFile(path)
        df = _EXCEL_CACHE[key].parse(spec.get("sheet", 0))
    # match headers by normalized spelling so 'سال آبي' == 'سال آبی'
    by_norm = {norm(c): c for c in df.columns}
    for col, val in (spec.get("filter") or {}).items():
        c = by_norm[norm(col)]
        vals = val if isinstance(val, list) else [val]
        df = df[df[c].map(norm).isin([norm(v) for v in vals])]
    if columns:
        missing = [h for h in columns.values() if norm(h) not in by_norm]
        if missing:
            raise KeyError(f"{path.name}: ستون(های) {missing} پیدا نشد. ستون‌های موجود: {list(df.columns)}")
        df = df[[by_norm[norm(h)] for h in columns.values()]].copy()
        df.columns = list(columns.keys())
    return df


def clear_excel_cache():
    _EXCEL_CACHE.clear()


def to_json(obj):
    return json.dumps(obj, ensure_ascii=False, indent=1, default=str)
