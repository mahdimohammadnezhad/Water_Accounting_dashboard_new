"""Read raw inputs (wells, dam statistics, transfers, special uses, indicators) into tidy tables.

Every withdrawal ends up as one row of:
    year, source_group, source_name, use, county_attr, county_geo, sub_basin, value   (million m3)
county_attr = county written in the source data, county_geo = county polygon from the shapefile.

All sections are optional and tolerant: missing columns are looked up by alias, unreadable sheets/PDFs are
skipped with a warning (report["warnings"] holds {"fa": ..., "en": ...} messages).
"""
import geopandas as gpd
import numpy as np
import pandas as pd

from .config import (DEFAULT_DAM_USE_MAP, DEFAULT_USE_MAP, WELL_COLUMN_ALIASES, excel_file, read_table,
                     resolve)
from .simaye_ab import read_folder
from .spatial import UNKNOWN, assign
from .text import auto_fix_names, norm, norm_year, sheet_year

W_COLS = ["year", "source_group", "source_name", "use", "county_attr", "county_geo", "sub_basin", "value"]
RES_COLS = ["year", "source_group", "source_name", "county_geo", "sub_basin", "value"]
TOTAL_WORDS = {"کل", "جمع", "مجموع", "جمع کل"}


def warn(report, fa, en):
    report["warnings"].append({"fa": fa, "en": en})


def _label(cfg, kind, sb):
    return cfg["spatial"][kind].format(id=sb)


def _strip_sad(s):
    s = norm(s) or ""
    return s[3:].strip() if s.startswith("سد ") else s


def _use_map(defaults, custom):
    m = {norm(k): norm(v) for k, v in defaults.items()}
    m.update({norm(k): norm(v) for k, v in (custom or {}).items()})
    return m


# --------------------------------------------------------------------------- wells
def load_wells(cfg, sub_basins, counties, report):
    w = cfg["wells"]
    df = read_table(cfg, {"file": w["file"], "sheet": w.get("sheet", 0), "filter": w.get("filter")},
                    columns=w.get("columns"), aliases=WELL_COLUMN_ALIASES)
    need = [c for c in ("year", "x", "y", "use", "value") if c not in df]
    if need:
        raise KeyError(f"{w['file']}: ستون‌های لازم پیدا نشد / required columns not found: {need}. "
                       f"در پیکربندی wells.columns را تنظیم کنید / set wells.columns in the config.")
    report["info"]["wells: columns used"] = list(df.columns)
    df["year"] = df.year.map(norm_year)
    df = df[df.year.notna()]
    df["county_attr"] = (df.county.map(norm) if "county" in df else pd.Series(None, index=df.index)).fillna(UNKNOWN)
    raw_use = df.use.map(norm).fillna(UNKNOWN)
    use_map = _use_map(DEFAULT_USE_MAP, w.get("use_map"))
    unmapped = sorted(set(raw_use) - set(use_map))
    if unmapped:
        warn(report, f"کاربری‌های چاه بدون نگاشت (با همان نام آمده‌اند): {unmapped}",
             f"Well uses without a mapping (kept as is): {unmapped}")
    df["use"] = raw_use.map(lambda u: use_map.get(u, u))
    for o in w.get("use_overrides") or []:
        m = (df.county_attr == norm(o["county"])) & (df.use == norm(o["from"]))
        df.loc[m, "use"] = norm(o["to"])
        report["info"][f"use override {o['from']}->{o['to']} ({o['county']})"] = int(m.sum())
    for c in ("x", "y", "value"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    factor = w.get("value_factor")
    if factor is None:  # auto: volumes in m3 -> million m3
        nz = df.value[df.value > 0]
        factor = 1e-6 if len(nz) and nz.median() > 100 else 1.0
        report["info"]["wells: value factor (auto)"] = factor
    df["value"] = df.value.fillna(0) * float(factor)

    # spatial assignment once per unique location
    crs = w.get("crs") or cfg["basin"]["crs"]
    if not w.get("crs") and df.x.abs().max() <= 180 and df.y.abs().max() <= 90:
        crs = "EPSG:4326"  # coordinates are longitude/latitude
    loc = df[["x", "y"]].drop_duplicates().reset_index(drop=True)
    pts = gpd.GeoDataFrame(loc, geometry=gpd.points_from_xy(loc.x.fillna(0), loc.y.fillna(0)),
                           crs=crs).to_crs(cfg["basin"]["crs"])
    snap = cfg["spatial"]["snap_distance_m"]
    loc["sub_basin"], loc["sb_method"] = assign(pts, sub_basins, "sub_basin", snap)
    loc["county_geo"] = assign(pts, counties, "county", snap)[0] if counties is not None else np.nan

    ov_path = w.get("location_overrides")
    if ov_path and resolve(cfg, ov_path).exists():
        ov = pd.read_csv(resolve(cfg, ov_path))
        ov["sub_basin"] = ov.sub_basin.map(norm)
        n = 0
        for _, r in ov.iterrows():
            m = (loc.x.round() == round(r.x)) & (loc.y.round() == round(r.y))
            loc.loc[m, "sub_basin"] = r.sub_basin
            loc.loc[m, "sb_method"] = "override"
            if "county_geo" in ov.columns and pd.notna(r.get("county_geo")):
                loc.loc[m, "county_geo"] = norm(r.county_geo)
            n += int(m.sum())
        report["info"]["wells: locations overridden"] = n

    df = df.merge(loc[["x", "y", "sub_basin", "sb_method", "county_geo"]], on=["x", "y"], how="left")
    df = df[~(df.sub_basin.isna() & (df.value == 0))]  # unlocatable records with zero withdrawal
    geo_names = set(counties.county) if counties is not None else set()
    fallback = df.county_attr.where(df.county_attr.isin(geo_names), UNKNOWN)
    df["county_geo"] = df.county_geo.fillna(fallback)
    unk = df.sub_basin.isna()
    if unk.any() and w.get("unlocated", "county_majority") == "county_majority" and (~unk).any():
        # wells with missing/invalid coordinates -> the sub-basin holding most wells of the same county
        major = df[~unk].groupby("county_attr").sub_basin.agg(lambda s: s.value_counts().idxmax())
        df.loc[unk, "sub_basin"] = df.loc[unk, "county_attr"].map(major)
        df.loc[unk & df.sub_basin.notna(), "sb_method"] = "county majority"
        km = cfg["spatial"]["snap_distance_m"] / 1000
        v = df.loc[unk, "value"].sum()
        warn(report, f"{int(unk.sum())} رکورد چاه ({v:.3f} م.م.م در همه سال‌ها) مختصات نامعتبر یا بیش از {km:g} "
                     f"کیلومتر بیرون از مرز داشتند و به زیرحوضه اصلی شهرستانشان نسبت داده شدند.",
             f"{int(unk.sum())} well records ({v:.3f} MCM over all years) had invalid coordinates or lay more than "
             f"{km:g} km outside the boundary; they were assigned to the main sub-basin of their county.")
    unk = df.sub_basin.isna()
    if unk.any():
        v = df.loc[unk, "value"].sum()
        warn(report, f"{int(unk.sum())} رکورد چاه ({v:.3f} م.م.م) زیرحوضه نامشخص دارند.",
             f"{int(unk.sum())} well records ({v:.3f} MCM) have an unknown sub-basin.")
    if len(df) and (df.sub_basin.isna().mean() > 0.5):
        warn(report, "بیشتر چاه‌ها بیرون از زیرحوضه‌ها افتاده‌اند؛ سیستم مختصات (basin.crs / wells.crs) را بررسی کنید.",
             "Most wells fall outside the sub-basins; check the coordinate system (basin.crs / wells.crs).")
    df["sub_basin"] = df.sub_basin.fillna(UNKNOWN)
    report["info"]["wells: records"] = len(df)
    report["info"]["wells: sub-basin assignment"] = df.sb_method.value_counts().to_dict()
    return df[["year", "x", "y", "use", "county_attr", "county_geo", "sub_basin", "sb_method", "value"]]


# --------------------------------------------------------------------------- dams
def _parse_dam_sheet(raw, use_map):
    r0 = next(i for i in range(min(15, len(raw))) if any(norm(v) == "نام سد" for v in raw.iloc[i]))
    h1_raw = raw.iloc[r0].map(norm)
    h1 = h1_raw.ffill()
    h2 = raw.iloc[r0 + 1].map(norm)
    name_col = h1_raw[h1_raw == "نام سد"].index[0]
    # location/county column: labelled «موقعیت», or an unlabelled text column right after the name
    loc_col = h1_raw[h1_raw == "موقعیت"].index
    if not len(loc_col):
        nxt = name_col + 1
        if nxt in raw.columns and pd.isna(h1_raw.get(nxt)) and pd.isna(h2.get(nxt)) and \
                raw.iloc[r0 + 2:][nxt].dropna().map(lambda v: isinstance(v, str)).all():
            loc_col = [nxt]

    def find(series, label):
        hit = series[series == label].index
        return hit[0] if len(hit) else None

    begin_col = find(h2, "حجم ابتدای سال آبی")
    end_col = find(h2, "حجم انتهای سال آبی")
    inflow_col = find(h1_raw, "ورودی")
    use_cols = [(c, use_map.get(h2[c], h2[c])) for c in raw.columns
                if h1[c] == "مصارف" and isinstance(h2[c], str) and h2[c] not in TOTAL_WORDS]
    rows = []
    for _, r in raw.iloc[r0 + 2:].iterrows():
        name = norm(r[name_col])
        if not name or name in TOTAL_WORDS:
            continue
        num = lambda c: pd.to_numeric(r[c], errors="coerce") if c is not None else np.nan  # noqa: E731
        rec = {"raw_name": name, "location": norm(r[loc_col[0]]) if len(loc_col) else None,
               "begin": num(begin_col), "inflow": num(inflow_col), "end": num(end_col)}
        for c, u in use_cols:
            rec[u] = pd.to_numeric(r[c], errors="coerce")
        rows.append(rec)
    return pd.DataFrame(rows), [u for _, u in use_cols]


def load_dams(cfg, sub_basins, counties, report):
    d = cfg["dams"]
    xl = excel_file(resolve(cfg, d["file"]))
    use_map = _use_map(DEFAULT_DAM_USE_MAP, d.get("use_map"))
    dam_list = d.get("list") or []
    candidates = {}
    for dm in dam_list:
        dm["name"] = norm(dm["name"])
        for a in [dm["name"]] + list(dm.get("aliases") or []):
            candidates[_strip_sad(a)] = dm["name"]

    frames, uses = [], []
    for sh in xl.sheet_names:
        year = sheet_year(sh)
        if not year:
            continue
        try:
            df, u = _parse_dam_sheet(xl.parse(sh, header=None), use_map)
        except Exception as e:  # noqa: BLE001
            warn(report, f"شیت «{sh}» فایل سدها خوانده نشد ({e}).", f"Dam sheet '{sh}' could not be read ({e}).")
            continue
        df["year"] = year
        frames.append(df)
        uses += u
    if not frames:
        warn(report, "هیچ شیت سال آبی در فایل آمار سدها خوانده نشد.", "No water-year sheet could be read from the dam file.")
        return (pd.DataFrame(columns=W_COLS), pd.DataFrame(columns=RES_COLS),
                pd.DataFrame(columns=["dam", "sub_basin", "location_county", "county", "x", "y"]), pd.DataFrame())
    allf = pd.concat(frames, ignore_index=True)
    allf["dam"] = allf.raw_name.map(lambda n: candidates.get(_strip_sad(n)))
    unknown = sorted(set(allf.loc[allf.dam.isna(), "raw_name"]))
    if unknown and dam_list:
        warn(report, f"سدهای بدون تعریف در پیکربندی (با نام خودشان آمدند): {unknown}",
             f"Dams not listed in the config (kept under their own names): {unknown}")
    allf["dam"] = allf.dam.fillna("سد " + allf.raw_name.map(_strip_sad))
    for raw, canon in zip(allf.raw_name, allf.dam):
        candidates.setdefault(_strip_sad(raw), canon)

    # dam locations (optional point shapefile) -> sub-basin & location county
    loc = {}
    if d.get("points"):
        try:
            g = gpd.read_file(resolve(cfg, d["points"]["shapefile"]))
            g = (g.set_crs(cfg["basin"]["crs"]) if g.crs is None else g).to_crs(cfg["basin"]["crs"])
            field = d["points"].get("name_field") or next(c for c in g.columns if c != "geometry")
            g["pname"] = [_strip_sad(v) for v in auto_fix_names(list(g[field]), d["points"].get("fix_encoding", "auto"))]
            g["sb"], _ = assign(g, sub_basins, "sub_basin", cfg["spatial"]["snap_distance_m"])
            g["ct"] = assign(g, counties, "county", cfg["spatial"]["snap_distance_m"])[0] if counties is not None else None
            for _, r in g.iterrows():
                for cand, canon in candidates.items():
                    if cand and (r.pname == cand or r.pname.startswith(cand + " ")) and canon not in loc:
                        loc[canon] = {"sub_basin": r.sb, "location_county": r.ct, "x": r.geometry.x, "y": r.geometry.y}
        except Exception as e:  # noqa: BLE001
            warn(report, f"شیپ‌فایل نقاط سد خوانده نشد ({e}).", f"Dam point shapefile could not be read ({e}).")

    # county of each dam: config override -> «موقعیت» column of the dam statistics -> dam point location
    stat_loc = allf.dropna(subset=["location"]).groupby("dam").location.agg(lambda s: s.value_counts().idxmax()) \
        if allf.location.notna().any() else pd.Series(dtype=object)
    meta = []
    cfg_by_name = {dm["name"]: dm for dm in dam_list}
    for name in dict.fromkeys(list(cfg_by_name) + list(allf.dam.unique())):
        dm, lc = cfg_by_name.get(name, {}), loc.get(name, {})
        sb = norm(dm.get("sub_basin")) if dm.get("sub_basin") not in (None, "auto") else lc.get("sub_basin")
        ct = lc.get("location_county")
        meta.append({"dam": name, "sub_basin": sb if isinstance(sb, str) else UNKNOWN,
                     "location_county": ct if isinstance(ct, str) else None,
                     "county": norm(dm.get("county")) or stat_loc.get(name) or (ct if isinstance(ct, str) else None)
                     or UNKNOWN, "x": lc.get("x"), "y": lc.get("y")})
    meta = pd.DataFrame(meta)
    unloc = meta[meta.sub_basin == UNKNOWN].dam.tolist()
    if unloc:
        warn(report, f"زیرحوضه این سدها معلوم نشد (نقطه سد پیدا نشد): {unloc}",
             f"Sub-basin unknown for these dams (no matching dam point): {unloc}")
    allf = allf.merge(meta[["dam", "sub_basin", "county"]], on="dam", how="left")

    uses = [u for u in dict.fromkeys(uses) if u in allf]
    wd = allf.melt(id_vars=["year", "dam", "sub_basin", "county"], value_vars=uses, var_name="use", value_name="value")
    wd = wd[wd.value.fillna(0) != 0]
    W = pd.DataFrame({"year": wd.year, "source_group": "dam", "source_name": wd.dam, "use": wd.use,
                      "county_attr": wd.county, "county_geo": wd.county, "sub_basin": wd.sub_basin,
                      "value": wd.value})
    RES = pd.DataFrame({"year": allf.year, "source_group": "dam", "source_name": allf.dam,
                        "county_geo": allf.county, "sub_basin": allf.sub_basin,
                        "value": allf.begin.fillna(0) + allf.inflow.fillna(0)})
    report["info"]["dams"] = meta.dam.tolist()
    return W, RES, meta, allf


# --------------------------------------------------------------------------- transfers
def _auto_place(W, use):
    """County / sub-basin where a use is largest (to place a transfer whose location is not configured)."""
    d = W[W.use == use]
    if d.empty:
        d = W
    if d.empty:
        return UNKNOWN, UNKNOWN
    county = d.groupby("county_attr").value.sum().idxmax()
    sb = d[d.county_attr == county].groupby("sub_basin").value.sum().idxmax()
    return county, sb


def load_transfers(cfg, report, simaye=None, W_main=None):
    """Inter-basin transfers. Either from the Simaye Ab table (source: simaye_ab, field: ...) or from a
    table with year/use/value (+ begin_storage/inflow or available) columns."""
    Ws, Rs = [], []
    for t in cfg.get("transfers") or []:
        name = norm(t.get("name") or "آب انتقالی")
        if t.get("source") == "simaye_ab":
            field = {"doosti_transfer": "transfer_in"}.get(t.get("field", "transfer_in"), t.get("field", "transfer_in"))
            if simaye is None or simaye.empty or field not in simaye or simaye[field].isna().all():
                warn(report, f"آب انتقالی «{name}» در جدول سیمای آب پیدا نشد.",
                     f"Transfer '{name}' was not found in the Simaye Ab tables.")
                continue
            df = pd.DataFrame({"year": simaye.year, "use": norm(t.get("use", "شرب")), "value": simaye[field]})
        else:
            df = read_table(cfg, t["table"], columns=t["columns"])
            df["year"] = df.year.map(norm_year)
        um = {norm(k): norm(v) for k, v in (t.get("use_map") or {}).items()}
        df["use"] = df.use.map(norm).map(lambda u: um.get(u, u))
        df["value"] = pd.to_numeric(df.value, errors="coerce").fillna(0)
        county, sb = norm(t.get("county", "auto")), norm(t.get("sub_basin", "auto"))
        if "auto" in (county, sb):
            ac, asb = _auto_place(W_main if W_main is not None else pd.DataFrame(columns=W_COLS), df.use.iloc[0])
            county = ac if county == "auto" else county
            sb = asb if sb == "auto" else sb
            report["info"][f"transfer '{name}' placed in"] = f"{county} / {sb}"
        w = df.groupby(["year", "use"], as_index=False).value.sum()
        w = w[w.value != 0]
        Ws.append(pd.DataFrame({"year": w.year, "source_group": "transfer", "source_name": name, "use": w.use,
                                "county_attr": county, "county_geo": county, "sub_basin": sb, "value": w.value}))
        per_year = df.groupby("year").first()
        if t.get("available") is not None:  # fixed allocation (e.g. Mashhad's share of Doosti dam)
            avail = pd.Series(float(t["available"]), index=per_year.index)
        elif "available" in per_year:
            avail = pd.to_numeric(per_year.available, errors="coerce")
        elif "begin_storage" in per_year:
            avail = pd.to_numeric(per_year.begin_storage, errors="coerce").fillna(0) + \
                    pd.to_numeric(per_year.inflow, errors="coerce").fillna(0)
        else:
            avail = df.groupby("year").value.sum()
        if t.get("cap") is not None:
            avail = avail.clip(upper=float(t["cap"]))
        Rs.append(pd.DataFrame({"year": avail.index, "source_group": "transfer", "source_name": name,
                                "county_geo": county, "sub_basin": sb, "value": avail.values}))
    W = pd.concat(Ws, ignore_index=True) if Ws else pd.DataFrame(columns=W_COLS)
    R = pd.concat(Rs, ignore_index=True) if Rs else pd.DataFrame(columns=RES_COLS)
    return W, R


# --------------------------------------------------------------------------- special uses
def load_special(cfg, dam_meta, report):
    out = []
    transfers = {norm(t["name"]): t for t in cfg.get("transfers") or []}
    dam_sb = dict(zip(dam_meta.dam, dam_meta.sub_basin))
    for s in cfg.get("special_withdrawals") or []:
        df = read_table(cfg, s["table"])
        by_norm = {norm(c): c for c in df.columns}
        years = df[by_norm[norm(s.get("year_column", "Year"))]].map(norm_year)
        use, county = norm(s["use"]), norm(s["county"])
        for src in s["sources"]:
            col = by_norm[norm(src["column"])]
            val = pd.to_numeric(df[col], errors="coerce").fillna(0) * float(src.get("factor", 1))
            grp = src["source_group"]
            sb = norm(src.get("sub_basin")) if src.get("sub_basin") is not None else None
            if grp == "dam":
                name = norm(src["source_name"])
                sb = sb or dam_sb.get(name)
            elif grp == "transfer":
                name = norm(src["source_name"])
                sb = sb or norm(transfers[name]["sub_basin"])
            sb = sb or norm(s["sub_basin"])
            if grp == "gw":
                name = _label(cfg, "aquifer_label", sb)
            elif grp == "treatment":
                name = cfg["treatment_label"]
            c = norm(src.get("county", county))
            out.append(pd.DataFrame({"year": years, "source_group": grp, "source_name": name, "use": use,
                                     "county_attr": c, "county_geo": c, "sub_basin": sb, "value": val}))
    W = pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=W_COLS)
    return W[W.value != 0]


# --------------------------------------------------------------------------- Simaye Ab PDFs
def load_simaye(cfg, report):
    s = cfg.get("simaye_ab")
    if not s:
        return pd.DataFrame()
    folder = resolve(cfg, s["folder"])
    if not folder.exists():
        warn(report, f"پوشه سیمای آب پیدا نشد: {folder}", f"Simaye Ab folder not found: {folder}")
        return pd.DataFrame()
    rows, notes = read_folder(folder, s.get("pattern", "*.pdf"), s.get("assume_deficit", True))
    report["warnings"] += notes
    df = pd.DataFrame(rows)
    if df.empty:
        warn(report, "هیچ جدول بیلانی از PDFهای سیمای آب خوانده نشد.", "No balance table could be read from the Simaye Ab PDFs.")
        return df
    df["year"] = df.year.map(norm_year)
    df = df[df.year.notna()]
    dup = df[df.year.duplicated(keep=False)]
    if len(dup):
        warn(report, f"چند PDF برای یک سال: {sorted(set(dup.file))}؛ آخرین فایل استفاده شد.",
             f"Several PDFs for the same year: {sorted(set(dup.file))}; the last one was used.")
    df = df.drop_duplicates("year", keep="last").sort_values("year").reset_index(drop=True)
    report["info"]["simaye ab (pdf)"] = {r.year: r.file for r in df.itertuples()}
    return df


# --------------------------------------------------------------------------- indicators
IND_COLS = ["year", "renew_surface", "renew_ground", "renew_total", "nonrenewable", "gw_available"]


def load_indicators(cfg, report, simaye=None):
    ind = cfg.get("indicators") or {}
    if ind == "simaye_ab":
        if simaye is None or simaye.empty:
            return pd.DataFrame(columns=IND_COLS)
        get = lambda c: simaye[c] if c in simaye else pd.Series(np.nan, index=simaye.index)  # noqa: E731
        out = pd.DataFrame({"year": simaye.year, "renew_surface": get("renew_surface"),
                            "renew_ground": get("renew_ground"), "renew_total": get("renew_total"),
                            "nonrenewable": -get("delta_s"), "source": get("file")})
        out["gw_available"] = out.renew_ground.fillna(0) + out.nonrenewable.fillna(0)
        return out
    frames = []
    if "renewable" in ind:
        r = ind["renewable"]
        df = read_table(cfg, r, columns=r["columns"])
        df["year"] = df.year.map(norm_year)
        df["type"] = df.type.map(norm)
        df["value"] = pd.to_numeric(df.value, errors="coerce")
        p = df.pivot_table(index="year", columns="type", values="value", aggfunc="sum")
        frames.append(pd.DataFrame({"renew_surface": p.get(norm(r.get("surface", "سطحی"))),
                                    "renew_ground": p.get(norm(r.get("ground", "زیرزمینی")))}))
    if "storage_change" in ind:
        r = ind["storage_change"]
        df = read_table(cfg, r, columns=r["columns"])
        df["year"] = df.year.map(norm_year)
        frames.append(pd.DataFrame({"nonrenewable": -pd.to_numeric(df.value, errors="coerce").values},
                                   index=df.year.values))
    if not frames:
        return pd.DataFrame(columns=IND_COLS)
    out = pd.concat(frames, axis=1)
    for c in ("renew_surface", "renew_ground", "nonrenewable"):
        if c not in out:
            out[c] = np.nan
    out["renew_total"] = out.renew_surface.fillna(0) + out.renew_ground.fillna(0)
    out["gw_available"] = out.renew_ground.fillna(0) + out.nonrenewable.fillna(0)
    out.index.name = "year"
    return out.reset_index()


def gw_resources(cfg, indicators, cells):
    """GW available volume (renewable GW + non-renewable) split over county x sub-basin cells by area."""
    ind = indicators.dropna(subset=["gw_available"])
    if ind.empty or cells.empty:
        return pd.DataFrame(columns=RES_COLS)
    x = ind[["year", "gw_available"]].merge(cells[["sub_basin", "county", "share"]], how="cross")
    return pd.DataFrame({"year": x.year, "source_group": "gw",
                         "source_name": x.sub_basin.map(lambda s: _label(cfg, "aquifer_label", s)),
                         "county_geo": x.county, "sub_basin": x.sub_basin,
                         "value": x.gw_available * x.share})[RES_COLS]
