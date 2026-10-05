"""Build step: raw files -> tidy parquet tables in dashboard/data/processed/<basin>/ (cached by signature)."""
import json
import time

import pandas as pd
from pyproj import Transformer

from . import loaders, spatial
from .config import clear_excel_cache, processed_dir, signature, to_json
from .text import natural_key

TABLES = ["W", "RES", "indicators", "cells", "wells", "dams", "dam_stats", "simaye"]


def build(cfg, log=print):
    t0 = time.time()
    report = {"warnings": [], "info": {}}
    clear_excel_cache()
    log("خواندن شیپ‌فایل‌ها ...")
    sb = spatial.load_sub_basins(cfg)
    ct = spatial.load_counties(cfg)
    cells = spatial.cell_areas(sb, ct)

    log("خواندن جدول بیلان سیمای آب (PDF) ...")
    simaye = loaders.load_simaye(cfg, report)

    log("خواندن آمار سدها ...")
    if "dams" in cfg:
        dam_W, dam_RES, dams, dam_stats = loaders.load_dams(cfg, sb, ct, report)
    else:
        dam_W = pd.DataFrame(columns=loaders.W_COLS)
        dam_RES = pd.DataFrame(columns=loaders.RES_COLS)
        dams = pd.DataFrame(columns=["dam", "sub_basin", "location_county", "county", "x", "y"])
        dam_stats = pd.DataFrame()

    log("خواندن آمار چاه‌ها (ممکن است چند ثانیه طول بکشد) ...")
    wells = loaders.load_wells(cfg, sb, ct, report) if "wells" in cfg else pd.DataFrame(
        columns=["year", "x", "y", "use", "county_attr", "county_geo", "sub_basin", "sb_method", "value"])
    gw_W = wells.groupby(["year", "use", "county_attr", "county_geo", "sub_basin"], as_index=False).value.sum()
    gw_W.insert(1, "source_group", "gw")
    gw_W.insert(2, "source_name", gw_W.sub_basin.map(lambda s: cfg["spatial"]["aquifer_label"].format(id=s)))

    log("آب انتقالی، مصارف ویژه و شاخص‌ها ...")
    tr_W, tr_RES = loaders.load_transfers(cfg, report, simaye)
    sp_W = loaders.load_special(cfg, dams, report)
    indicators = loaders.load_indicators(cfg, report, simaye)
    gw_RES = loaders.gw_resources(cfg, indicators, cells)

    W = pd.concat([dam_W, gw_W[loaders.W_COLS], tr_W, sp_W], ignore_index=True)
    W["value"] = W.value.astype(float)
    W = W[W.year.notna()]
    RES = pd.concat([dam_RES, gw_RES, tr_RES], ignore_index=True)
    RES["value"] = RES.value.astype(float)

    # geographic coordinates for the web map
    to_ll = Transformer.from_crs(cfg["basin"]["crs"], "EPSG:4326", always_xy=True)
    for df in (wells, dams):
        ok = df.x.notna() & df.y.notna() & (pd.to_numeric(df.x, errors="coerce") > 0)
        lon, lat = to_ll.transform(df.loc[ok, "x"].astype(float).values, df.loc[ok, "y"].astype(float).values)
        df["lon"], df["lat"] = None, None
        df.loc[ok, "lon"], df.loc[ok, "lat"] = lon, lat
        df["lon"] = df.lon.astype(float)
        df["lat"] = df.lat.astype(float)

    for df in (W, RES, cells, wells, dams):
        for c in df.columns:
            if c in ("sub_basin", "county_geo", "county_attr", "county", "location_county", "year"):
                df[c] = df[c].astype(object).where(df[c].notna(), None).astype("string")

    out = processed_dir(cfg)
    out.mkdir(parents=True, exist_ok=True)
    tables = {"W": W, "RES": RES, "indicators": indicators, "cells": cells, "wells": wells, "dams": dams,
              "dam_stats": dam_stats, "simaye": simaye}
    for k, df in tables.items():
        df.to_parquet(out / f"{k}.parquet", index=False)
    shapes = {"sub_basins": spatial.to_plot_shapes(sb.to_crs(4326), "sub_basin", tolerance=0.0015),
              "counties": spatial.to_plot_shapes(ct.to_crs(4326), "county", tolerance=0.0015) if ct is not None else []}
    (out / "shapes.json").write_text(json.dumps(shapes, ensure_ascii=False), encoding="utf-8")
    # water years shown = years with well statistics or a Simaye Ab table (dam-only years are incomplete)
    main_years = set(wells.year.dropna()) | set(indicators.year.dropna())
    years = sorted(main_years or set(W.year.dropna()))
    meta = {"signature": signature(cfg), "built_at": time.strftime("%Y-%m-%d %H:%M"),
            "seconds": round(time.time() - t0, 1), "years": years,
            "sub_basins": sorted(sb.sub_basin, key=natural_key), "report": report}
    (out / "meta.json").write_text(to_json(meta), encoding="utf-8")
    log(f"ساخت داده‌ها در {meta['seconds']} ثانیه تمام شد.")
    return load_processed(cfg)


def load_processed(cfg):
    out = processed_dir(cfg)
    base = {k: pd.read_parquet(out / f"{k}.parquet") for k in TABLES}
    base["shapes"] = json.loads((out / "shapes.json").read_text(encoding="utf-8"))
    base["meta"] = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    for k in ("W", "RES", "cells", "wells", "dams"):
        df = base[k]
        for c in df.columns:
            if str(df[c].dtype) == "string" or df[c].dtype == object:
                df[c] = df[c].astype(object)
    return base


def is_fresh(cfg):
    m = processed_dir(cfg) / "meta.json"
    if not m.exists():
        return False
    try:
        return json.loads(m.read_text(encoding="utf-8")).get("signature") == signature(cfg)
    except Exception:
        return False


def get_base(cfg, force=False, log=print):
    if force or not is_fresh(cfg):
        return build(cfg, log=log)
    return load_processed(cfg)
