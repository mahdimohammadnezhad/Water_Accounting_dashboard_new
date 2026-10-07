"""Basin configuration: one YAML file per basin under dashboard/configs/.

Only `basin` and `spatial.sub_basins` are required; every other section is optional and anything not
given is filled with the defaults below (column aliases, use mapping, return-flow coefficients), so the
same code runs for any study area whose files follow the usual formats.
"""
import copy
import hashlib
import json
import os
from pathlib import Path

import pandas as pd
import yaml

from .text import match_column, norm

DASHBOARD_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = DASHBOARD_DIR / "configs"
PROCESSED_DIR = DASHBOARD_DIR / "data" / "processed"

# Internal keys for source groups; labels are translated in the UI (wa/i18n.py).
GROUP_LABELS = {
    "dam": "سد",
    "river": "بازه رودخانه",
    "gw": "آب زیرزمینی",
    "transfer": "انتقالی",
    "treatment": "تصفیه خانه",
}
GROUP_ORDER = ["dam", "river", "gw", "transfer", "treatment"]

# ----------------------------------------------------------------------------- defaults
WELL_COLUMN_ALIASES = {
    "year": ["سال آبی", "سال", "year", "water_year", "water year"],
    "county": ["شهرستان", "county", "shahrestan"],
    "x": ["MA_XUTM", "XUTM", "X_UTM", "UTM_X", "Easting", "X", "طول"],
    "y": ["MA_YUTM", "YUTM", "Y_UTM", "UTM_Y", "Northing", "Y", "عرض"],
    "use": ["نوع مصرف", "مصرف", "use", "type of use", "kind of use"],
    "value": ["برداشت واقعی", "برداشت", "تخلیه مترمکعب", "تخلیه", "withdrawal", "value", "volume"],
}
DEFAULT_USE_MAP = {
    "کشاورزی": "کشاورزی", "دام و طیور": "کشاورزی", "دامداری": "کشاورزی", "آبزی پروری": "کشاورزی",
    "شرب": "شرب", "شرب شهری": "شرب",
    "شرب روستا": "شرب روستایی", "شرب روستایی": "شرب روستایی", "شرب اشخاص": "شرب روستایی",
    "صنعت": "صنعتی", "صنعتی": "صنعتی",
    "خدمات": "خدمات", "سایر": "خدمات", "فضای سبز": "فضای سبز",
}
DEFAULT_DAM_USE_MAP = {"کشاورزی": "کشاورزی", "شرب": "شرب", "صنعت": "صنعتی", "صنعتی": "صنعتی",
                       "سایر": "خدمات", "خدمات": "خدمات", "محیط زیست": "محیط زیست"}
# return-flow defaults (Simaye Ab: 70% for drinking & industry, 15% for agriculture & services)
_USE_DEFAULTS = [
    ("شرب روستایی", dict(return_coef=0.15, river_fraction=0.5, return_group="sub_basin")),
    ("شرب", dict(return_coef=0.7, river_fraction=0.5, return_group="county")),
    ("صنعت", dict(return_coef=0.7, river_fraction=0.5, return_group="county")),
    ("کشاورزی", dict(return_coef=0.15, river_fraction=0.0, return_group="sub_basin")),
    ("خدمات", dict(return_coef=0.15, river_fraction=0.5, return_group="sub_basin")),
    ("محیط زیست", dict(return_coef=0.0, river_fraction=0.0, return_group="sub_basin")),
]
USE_ORDER = ["شرب", "شرب روستایی", "کشاورزی", "صنعتی", "خدمات"]


def default_use(name):
    name = norm(name)
    params = dict(return_coef=0.15, river_fraction=0.0, return_group="sub_basin")
    for key, p in _USE_DEFAULTS:
        if key in name:
            params = dict(p)
            break
    return _complete_use({"name": name, **params, "auto": True})


def _complete_use(u):
    u["name"] = norm(u["name"])
    u.setdefault("return_coef", 0.0)
    u.setdefault("river_fraction", 0.0)
    u.setdefault("return_group", "sub_basin")
    u.setdefault("breakdown", u["return_group"])
    u["members"] = [norm(m) for m in (u.get("members") or [])] or None
    u["treatment_fraction"] = {norm(k): v for k, v in (u.get("treatment_fraction") or {}).items()}
    return u


def resolve_uses(cfg, names_in_data):
    """Configured uses first, then every other use found in the data with default coefficients."""
    uses = [copy.deepcopy(u) for u in cfg.get("uses") or []]
    known = {u["name"] for u in uses}
    extra = [n for n in dict.fromkeys(names_in_data) if n and n not in known]
    extra.sort(key=lambda n: USE_ORDER.index(n) if n in USE_ORDER else len(USE_ORDER))
    return uses + [default_use(n) for n in extra]


# ----------------------------------------------------------------------------- loading
def list_configs():
    return sorted(p for p in CONFIG_DIR.glob("*.yaml") if not p.name.startswith("_"))


def load_config(path):
    path = Path(path)
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
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
    if "sub_basins" not in sp and not cfg.get("study_area"):
        raise ValueError(f"{path.name}: spatial.sub_basins (شیپ‌فایل زیرحوضه‌ها) یا study_area (نام/کد محدوده مطالعاتی) "
                         f"لازم است / define spatial.sub_basins or study_area.")
    if cfg.get("study_area") is not None:
        cfg["study_area"] = norm(cfg["study_area"])

    cfg["uses"] = [_complete_use(u) for u in cfg.get("uses") or []]
    cfg["county_outlet_reach"] = {norm(k): str(v) for k, v in (cfg.get("county_outlet_reach") or {}).items()}
    cfg.setdefault("balance_source_groups", ["dam", "gw", "transfer"])
    cfg.setdefault("treatment_label", "تصفیه خانه")
    cfg.setdefault("county_mode_default", "attribute")
    return cfg


def resolve(cfg, rel):
    p = Path(rel)
    return p if p.is_absolute() else Path(cfg["basin"]["base_dir"]) / p


REGIONAL_FILE = CONFIG_DIR / "_regional.yaml"


def regional_spec(cfg):
    """Country-wide study-area / county layers: basin config `regional:` or configs/_regional.yaml.
    Returns the spec with absolute shapefile paths (missing files dropped), or None."""
    if cfg.get("regional") is not None:
        spec, base = dict(cfg["regional"] or {}), Path(cfg["basin"]["base_dir"])
    elif REGIONAL_FILE.exists():
        spec = yaml.safe_load(REGIONAL_FILE.read_text(encoding="utf-8")) or {}
        base = (REGIONAL_FILE.parent / spec.get("base_dir", ".")).resolve()
    else:
        return None
    out = {"context_buffer_km": float(spec.get("context_buffer_km", 150))}
    for key in ("study_areas", "counties"):
        layer = spec.get(key)
        if layer and layer.get("shapefile"):
            p = Path(layer["shapefile"])
            p = p if p.is_absolute() else base / p
            if p.exists():
                out[key] = {**layer, "shapefile": str(p)}
    return out if ("study_areas" in out or "counties" in out) else None


def input_files(cfg):
    """Every file the build reads — used to detect when the processed cache is stale."""
    files = []
    sp = cfg["spatial"]
    for key in ("sub_basins", "counties"):
        if sp.get(key):
            files.append(sp[key]["shapefile"])
    if cfg.get("wells"):
        files.append(cfg["wells"]["file"])
        if cfg["wells"].get("location_overrides"):
            files.append(cfg["wells"]["location_overrides"])
    if cfg.get("dams"):
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
        if folder.exists():
            files += sorted(folder.glob(cfg["simaye_ab"].get("pattern", "*.pdf")))
    reg = regional_spec(cfg)
    if reg:
        files += [reg[k]["shapefile"] for k in ("study_areas", "counties") if k in reg]
        if cfg.get("regional") is None:
            files.append(REGIONAL_FILE)
    out = []
    for f in dict.fromkeys(files):
        p = resolve(cfg, f)
        out.append(p)
        if p.suffix.lower() == ".shp":
            out.append(p.with_suffix(".dbf"))
    return out


def signature(cfg):
    """Hash of config contents + build code + input file mtimes/sizes."""
    h = hashlib.sha1()
    h.update(Path(cfg["_path"]).read_bytes())
    for mod in ("loaders.py", "spatial.py", "build.py", "text.py", "simaye_ab.py", "config.py"):
        h.update((Path(__file__).parent / mod).read_bytes())
    for p in input_files(cfg):
        st = os.stat(p) if p.exists() else None
        h.update(f"{p}|{st.st_mtime if st else 0}|{st.st_size if st else 0}".encode())
    return h.hexdigest()[:16]


def processed_dir(cfg):
    return PROCESSED_DIR / cfg["basin"]["key"]


_EXCEL_CACHE = {}


def excel_file(path):
    key = str(path)
    if key not in _EXCEL_CACHE:
        _EXCEL_CACHE[key] = pd.ExcelFile(path)
    return _EXCEL_CACHE[key]


def read_table(cfg, spec, columns=None, aliases=None):
    """Read a sheet/CSV described by {file, sheet?, filter?}.
    `columns` {canonical: header} renames columns; a canonical name missing from `columns` (or whose header
    is not found) is looked up in `aliases` {canonical: [possible headers]}."""
    path = resolve(cfg, spec["file"])
    if not path.exists():
        raise FileNotFoundError(f"فایل پیدا نشد / file not found: {path}")
    df = pd.read_csv(path) if path.suffix.lower() == ".csv" else excel_file(path).parse(spec.get("sheet", 0))
    by_norm = {norm(c): c for c in df.columns}
    for col, val in (spec.get("filter") or {}).items():
        c = by_norm.get(norm(col))
        if c is None:
            continue
        vals = val if isinstance(val, list) else [val]
        df = df[df[c].map(norm).isin([norm(v) for v in vals])]
    if columns or aliases:
        wanted = dict(columns or {})
        for k in (aliases or {}):
            wanted.setdefault(k, None)
        picked = {}
        for canon, header in wanted.items():
            col = by_norm.get(norm(header)) if header else None
            if col is None and aliases and canon in aliases:
                col = match_column(df.columns, aliases[canon])
            if col is not None:
                picked[canon] = col
        lost = [columns[c] for c in (columns or {}) if c not in picked]  # explicitly configured -> required
        if lost:
            raise KeyError(f"{path.name}: ستون(های) {lost} پیدا نشد / columns not found. "
                           f"ستون‌های موجود / available: {list(df.columns)}")
        df = df[list(picked.values())].copy()
        df.columns = list(picked.keys())
    return df


def clear_excel_cache():
    _EXCEL_CACHE.clear()


def to_json(obj):
    return json.dumps(obj, ensure_ascii=False, indent=1, default=str)
