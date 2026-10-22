"""Build step: raw files -> tidy parquet tables in dashboard/data/processed/<basin>/ (cached by signature).

Only the sub-basin shapefile is mandatory. Each other source (wells, dams, Simaye Ab PDFs, transfers,
special uses) is optional; if one fails to load, the build continues and the error is reported in the
dashboard's data-quality tab.
"""
import json
import time
import traceback

import geopandas as gpd
import pandas as pd
from pyproj import Transformer

from . import loaders, spatial
from .config import clear_excel_cache, processed_dir, regional_spec, resolve_uses, signature, to_json
from .text import natural_key

TABLES = ["W", "RES", "indicators", "cells", "wells", "dams", "dam_stats", "simaye"]
WELL_COLS = ["year", "x", "y", "use", "county_attr", "county_geo", "sub_basin", "sb_method", "cls", "value"]
DAM_META_COLS = ["dam", "sub_basin", "location_county", "county", "x", "y"]


def _step(report, name_fa, name_en, fn, fallback):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001 - keep building with what is available
        loaders.warn(report, f"خطا در خواندن {name_fa}: {e}", f"Error while reading {name_en}: {e}")
        report.setdefault("errors", []).append(traceback.format_exc())
        return fallback()


def build(cfg, log=print):
    t0 = time.time()
    report = {"warnings": [], "info": {}}
    clear_excel_cache()
    log("shapefiles ...")
    reg_spec = regional_spec(cfg)
    reg_name = ("لایه‌های سراسری (محدوده‌ها و شهرستان‌های کشور)", "country-wide layers")
    if cfg["spatial"].get("sub_basins"):
        sb = spatial.load_sub_basins(cfg)
        report["info"]["sub-basin id field"] = cfg["spatial"]["sub_basins"].get("_id_field_used")
        around = None
        if reg_spec:  # read only the neighbourhood of the basin (fast)
            around = gpd.GeoSeries([sb.union_all().buffer(reg_spec["context_buffer_km"] * 1500)], crs=sb.crs)
        regional = _step(report, *reg_name, lambda: spatial.read_regional(reg_spec, around), dict)
    else:  # no sub-basin shapefile: the study area found by name/code is the single sub-basin
        regional = _step(report, *reg_name, lambda: spatial.read_regional(reg_spec), dict)
        sa = spatial.find_study_area(regional.get("study_areas"), cfg.get("study_area"))
        if sa is None:
            raise ValueError(f"محدوده مطالعاتی «{cfg.get('study_area')}» در لایه سراسری پیدا نشد / "
                             f"study area '{cfg.get('study_area')}' not found in the country-wide layer.")
        sb = spatial.sub_basins_from_study_area(cfg, sa)
        loaders.warn(report, "شیپ‌فایل زیرحوضه تعریف نشده؛ کل محدوده مطالعاتی یک زیرحوضه در نظر گرفته شد.",
                     "No sub-basin shapefile: the whole study area is used as a single sub-basin.")
    own_sa = _step(report, "محدوده مطالعاتی", "study area",
                   lambda: spatial.find_study_area(regional.get("study_areas"), cfg.get("study_area"), sb), lambda: None)
    if own_sa is not None:
        r = own_sa.iloc[0]
        report["info"]["study area"] = f"{r['name']} ({r['code']}{', ' + r['province'] if r['province'] else ''})"
    if cfg["spatial"].get("counties"):
        ct = _step(report, "شیپ‌فایل شهرستان‌ها", "county shapefile", lambda: spatial.load_counties(cfg, sb),
                   lambda: None)
    elif "counties" in regional:
        ct = spatial.counties_from_regional(regional["counties"], sb)
        report["info"]["counties"] = "country-wide layer"
    else:
        ct = None
    cells = spatial.cell_areas(sb, ct)
    report["info"]["crs"] = cfg["basin"]["crs"]
    context = _step(report, "لایه‌های اطراف", "context layers",
                    lambda: spatial.context_layers(regional, sb, own_sa, ct, reg_spec["context_buffer_km"]),
                    dict) if reg_spec else {}

    log("simaye ab pdf ...")
    simaye = _step(report, "PDFهای سیمای آب", "Simaye Ab PDFs", lambda: loaders.load_simaye(cfg, report),
                   pd.DataFrame)

    log("dams ...")
    empty_dams = lambda: (pd.DataFrame(columns=loaders.W_COLS), pd.DataFrame(columns=loaders.RES_COLS),  # noqa: E731
                          pd.DataFrame(columns=DAM_META_COLS), pd.DataFrame())
    dam_W, dam_RES, dams, dam_stats = _step(report, "آمار سدها", "dam statistics",
                                            lambda: loaders.load_dams(cfg, sb, ct, report), empty_dams) \
        if cfg.get("dams") else empty_dams()

    log("wells ...")
    wells = _step(report, "آمار چاه‌ها", "well statistics", lambda: loaders.load_wells(cfg, sb, ct, report),
                  lambda: pd.DataFrame(columns=WELL_COLS)) if cfg.get("wells") else pd.DataFrame(columns=WELL_COLS)
    gw_W = wells.groupby(["year", "use", "county_attr", "county_geo", "sub_basin", "cls"], as_index=False).value.sum()
    gw_W.insert(1, "source_group", "gw")
    gw_W.insert(2, "source_name", gw_W.sub_basin.map(lambda s: cfg["spatial"]["aquifer_label"].format(id=s)))
    W_main = pd.concat([dam_W, gw_W[loaders.W_COLS + ["cls"]]], ignore_index=True)

    log("transfers, special uses, indicators ...")
    empty_pair = lambda: (pd.DataFrame(columns=loaders.W_COLS), pd.DataFrame(columns=loaders.RES_COLS))  # noqa: E731
    tr_W, tr_RES = _step(report, "آب انتقالی", "transfers", lambda: loaders.load_transfers(cfg, report, simaye, W_main),
                         empty_pair)
    sp_W = _step(report, "مصارف ویژه", "special uses", lambda: loaders.load_special(cfg, dams, report),
                 lambda: pd.DataFrame(columns=loaders.W_COLS))
    indicators = _step(report, "شاخص‌های سیمای آب", "Simaye Ab indicators",
                       lambda: loaders.load_indicators(cfg, report, simaye),
                       lambda: pd.DataFrame(columns=loaders.IND_COLS))
    gw_RES = loaders.gw_resources(cfg, indicators, cells)

    W = pd.concat([W_main, tr_W, sp_W], ignore_index=True)
    W["value"] = pd.to_numeric(W.value, errors="coerce").fillna(0.0)
    W = W[W.year.notna()]
    # uncertainty/scenario class of every withdrawal (wells: gw_m/gw_u/gw_i/gw; else the source group)
    W["cls"] = (W["cls"] if "cls" in W else pd.Series(None, index=W.index)).fillna(W.source_group)
    RES = pd.concat([dam_RES, gw_RES, tr_RES], ignore_index=True)
    RES["value"] = pd.to_numeric(RES.value, errors="coerce").fillna(0.0)
    if W.empty:
        loaders.warn(report, "هیچ برداشتی خوانده نشد؛ مسیر فایل‌های چاه و سد را در پیکربندی بررسی کنید.",
                     "No withdrawals were read; check the well and dam file paths in the config.")

    # geographic coordinates for the web map
    to_ll = Transformer.from_crs(cfg["basin"]["crs"], "EPSG:4326", always_xy=True)
    for df in (wells, dams):
        x, y = pd.to_numeric(df.x, errors="coerce"), pd.to_numeric(df.y, errors="coerce")
        ok = x.notna() & y.notna() & (x != 0)
        df["lon"], df["lat"] = float("nan"), float("nan")
        if ok.any():
            lon, lat = to_ll.transform(x[ok].values, y[ok].values)
            df.loc[ok, "lon"], df.loc[ok, "lat"] = lon, lat

    for df in (W, RES, cells, wells, dams):
        for c in df.columns:
            if c in ("sub_basin", "county_geo", "county_attr", "county", "location_county", "year", "use",
                     "source_name", "source_group", "dam"):
                df[c] = df[c].astype(object).where(df[c].notna(), None).astype("string")

    out = processed_dir(cfg)
    out.mkdir(parents=True, exist_ok=True)
    tables = {"W": W, "RES": RES, "indicators": indicators, "cells": cells, "wells": wells, "dams": dams,
              "dam_stats": dam_stats, "simaye": simaye}
    for k, df in tables.items():
        df.reset_index(drop=True).to_parquet(out / f"{k}.parquet", index=False)
    shapes = {"sub_basins": spatial.to_plot_shapes(sb.to_crs(4326), "sub_basin", tolerance=0.0015),
              "counties": spatial.to_plot_shapes(ct.to_crs(4326), "county", tolerance=0.0015) if ct is not None else [],
              "study_area": [], "context_study_areas": [], "context_counties": [], **context}
    (out / "shapes.json").write_text(json.dumps(shapes, ensure_ascii=False), encoding="utf-8")
    # water years shown = years with well statistics or a Simaye Ab table (dam-only years are incomplete)
    no_simaye = sorted(set(wells.year.dropna()) - set(indicators.year.dropna()))
    if cfg.get("indicators") and no_simaye:
        loaders.warn(report, f"برای این سال‌ها جدول سیمای آب نیست؛ آب زیرزمینی در دسترس (G) و کنترل بیلان آنها ناقص است: "
                             f"{no_simaye}",
                     f"No Simaye Ab table for these years; their groundwater availability (G) and balance check are "
                     f"incomplete: {no_simaye}")
    main_years = set(wells.year.dropna()) | set(indicators.year.dropna())
    years = sorted(main_years or set(W.year.dropna()))
    use_totals = W.groupby("use").value.sum().sort_values(ascending=False)
    meta = {"signature": signature(cfg), "built_at": time.strftime("%Y-%m-%d %H:%M"),
            "seconds": round(time.time() - t0, 1), "years": years,
            "sub_basins": sorted(sb.sub_basin, key=natural_key),
            "uses": resolve_uses(cfg, list(use_totals.index)),
            "has_county_attr": bool(len(wells)) and bool((wells.county_attr != spatial.UNKNOWN).any()),
            "has_county_geo": ct is not None and not ct.empty,
            "report": report}
    (out / "meta.json").write_text(to_json(meta), encoding="utf-8")
    log(f"done in {meta['seconds']} s")
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
    except Exception:  # noqa: BLE001
        return False


def get_base(cfg, force=False, log=print):
    if force or not is_fresh(cfg):
        return build(cfg, log=log)
    return load_processed(cfg)
