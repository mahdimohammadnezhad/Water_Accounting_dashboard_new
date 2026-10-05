"""Read raw inputs (wells, dam statistics, transfers, special uses, indicators) into tidy tables.

Every withdrawal ends up as one row of:
    year, source_group, source_name, use, county_attr, county_geo, sub_basin, value   (million m3)
county_attr = county written in the source data, county_geo = county polygon from the shapefile.
"""
import geopandas as gpd
import numpy as np
import pandas as pd

from .config import read_table, resolve
from .simaye_ab import read_folder
from .spatial import UNKNOWN, assign
from .text import norm, norm_year

W_COLS = ["year", "source_group", "source_name", "use", "county_attr", "county_geo", "sub_basin", "value"]
RES_COLS = ["year", "source_group", "source_name", "county_geo", "sub_basin", "value"]


def _label(cfg, kind, sb):
    return cfg["spatial"][kind].format(id=sb)


def _strip_sad(s):
    s = norm(s) or ""
    return s[3:].strip() if s.startswith("سد ") else s


# --------------------------------------------------------------------------- wells
def load_wells(cfg, sub_basins, counties, report):
    w = cfg["wells"]
    df = read_table(cfg, {"file": w["file"], "sheet": w.get("sheet", 0), "filter": w.get("filter")},
                    columns=w["columns"])
    df["year"] = df.year.map(norm_year)
    df["county_attr"] = df.county.map(norm).fillna(UNKNOWN)
    raw_use = df.use.map(norm)
    use_map = {norm(k): norm(v) for k, v in (w.get("use_map") or {}).items()}
    unmapped = sorted(set(raw_use.dropna()) - set(use_map))
    if use_map and unmapped:
        report["warnings"].append(f"کاربری‌های چاه بدون نگاشت (با همان نام آمده‌اند): {unmapped}")
    df["use"] = raw_use.map(lambda u: use_map.get(u, u))
    for o in w.get("use_overrides") or []:
        m = (df.county_attr == norm(o["county"])) & (df.use == norm(o["from"]))
        df.loc[m, "use"] = norm(o["to"])
        report["info"][f"تغییر کاربری {o['from']}→{o['to']} در {o['county']}"] = int(m.sum())
    for c in ("x", "y", "value"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["value"] = df.value.fillna(0) * float(w.get("value_factor", 1))

    # spatial assignment once per unique location
    loc = df[["x", "y"]].drop_duplicates().reset_index(drop=True)
    pts = gpd.GeoDataFrame(loc, geometry=gpd.points_from_xy(loc.x.fillna(0), loc.y.fillna(0)),
                           crs=w.get("crs", cfg["basin"]["crs"])).to_crs(cfg["basin"]["crs"])
    snap = cfg["spatial"]["snap_distance_m"]
    loc["sub_basin"], loc["sb_method"] = assign(pts, sub_basins, "sub_basin", snap)
    if counties is not None:
        loc["county_geo"], _ = assign(pts, counties, "county", snap)
    else:
        loc["county_geo"] = np.nan

    ov_path = w.get("location_overrides")
    if ov_path and resolve(cfg, ov_path).exists():
        ov = pd.read_csv(resolve(cfg, ov_path))
        ov["sub_basin"] = ov.sub_basin.map(norm)
        n = 0
        for _, r in ov.iterrows():
            m = (loc.x.round() == round(r.x)) & (loc.y.round() == round(r.y))
            loc.loc[m, "sub_basin"] = r.sub_basin
            loc.loc[m, "sb_method"] = "اصلاح دستی"
            if "county_geo" in ov.columns and pd.notna(r.get("county_geo")):
                loc.loc[m, "county_geo"] = norm(r.county_geo)
            n += int(m.sum())
        report["info"]["موقعیت چاه اصلاح‌شده با فایل overrides"] = n

    df = df.merge(loc[["x", "y", "sub_basin", "sb_method", "county_geo"]], on=["x", "y"], how="left")
    df = df[~(df.sub_basin.isna() & (df.value == 0))]  # unlocatable records with zero withdrawal
    geo_names = set(counties.county) if counties is not None else set()
    fallback = df.county_attr.where(df.county_attr.isin(geo_names), UNKNOWN)
    df["county_geo"] = df.county_geo.fillna(fallback)
    unk = df.sub_basin.isna()
    if unk.any() and w.get("unlocated", "county_majority") == "county_majority":
        # wells with missing/invalid coordinates -> the sub-basin holding most wells of the same county
        major = df[~unk].groupby("county_attr").sub_basin.agg(lambda s: s.value_counts().idxmax())
        df.loc[unk, "sub_basin"] = df.loc[unk, "county_attr"].map(major)
        df.loc[unk & df.sub_basin.notna(), "sb_method"] = "مختصات نامعتبر: زیرحوضه اصلی همان شهرستان"
        report["warnings"].append(
            f"{int(unk.sum())} رکورد چاه ({df.loc[unk, 'value'].sum():.3f} م.م.م در همه سال‌ها) مختصات نامعتبر یا "
            f"بیش از {cfg['spatial']['snap_distance_m'] / 1000:g} کیلومتر بیرون از مرز داشتند و به زیرحوضه اصلی "
            f"شهرستانشان نسبت داده شدند.")
    unk = df.sub_basin.isna()
    if unk.any():
        report["warnings"].append(
            f"{int(unk.sum())} رکورد چاه ({df.loc[unk, 'value'].sum():.3f} م.م.م) زیرحوضه نامشخص دارند.")
    df["sub_basin"] = df.sub_basin.fillna(UNKNOWN)
    report["info"]["رکوردهای چاه"] = len(df)
    report["info"]["نحوه تعیین زیرحوضه چاه‌ها"] = df.sb_method.value_counts().to_dict()
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
    begin_col = h2[h2 == "حجم ابتدای سال آبی"].index[0]
    end_col = h2[h2 == "حجم انتهای سال آبی"].index
    inflow_col = h1_raw[h1_raw == "ورودی"].index[0]
    use_cols = [(c, use_map[h2[c]]) for c in raw.columns if h1[c] == "مصارف" and h2[c] in use_map]
    rows = []
    for _, r in raw.iloc[r0 + 2:].iterrows():
        name = norm(r[name_col])
        if not name or name in ("مجموع", "جمع", "جمع کل"):
            continue
        rec = {"raw_name": name, "location": norm(r[loc_col[0]]) if len(loc_col) else None,
               "begin": pd.to_numeric(r[begin_col], errors="coerce"),
               "inflow": pd.to_numeric(r[inflow_col], errors="coerce"),
               "end": pd.to_numeric(r[end_col[0]], errors="coerce") if len(end_col) else np.nan}
        for c, u in use_cols:
            rec[u] = pd.to_numeric(r[c], errors="coerce")
        rows.append(rec)
    return pd.DataFrame(rows), [u for _, u in use_cols]


def load_dams(cfg, sub_basins, counties, report):
    d = cfg["dams"]
    path = resolve(cfg, d["file"])
    xl = pd.ExcelFile(path)
    use_map = {norm(k): norm(v) for k, v in d["use_map"].items()}
    dam_list = d.get("list") or []
    candidates = {}
    for dm in dam_list:
        dm["name"] = norm(dm["name"])
        for a in [dm["name"]] + list(dm.get("aliases") or []):
            candidates[_strip_sad(a)] = dm["name"]

    # dam locations (optional point shapefile) -> sub-basin & location county
    loc = {}
    if d.get("points"):
        g = gpd.read_file(resolve(cfg, d["points"]["shapefile"])).to_crs(cfg["basin"]["crs"])
        g["pname"] = g[d["points"]["name_field"]].map(_strip_sad)
        g["sb"], _ = assign(g, sub_basins, "sub_basin", cfg["spatial"]["snap_distance_m"])
        if counties is not None:
            g["ct"], _ = assign(g, counties, "county", cfg["spatial"]["snap_distance_m"])
        for _, r in g.iterrows():
            for cand, canon in candidates.items():
                if r.pname == cand or r.pname.startswith(cand + " "):
                    loc[canon] = {"sub_basin": r.sb, "location_county": r.get("ct"),
                                  "x": r.geometry.x, "y": r.geometry.y}

    frames = []
    for sh in xl.sheet_names:
        year = norm_year(sh)
        if not year:
            continue
        df, _ = _parse_dam_sheet(xl.parse(sh, header=None), use_map)
        df["year"] = year
        frames.append(df)
    allf = pd.concat(frames, ignore_index=True)
    allf["dam"] = allf.raw_name.map(lambda n: candidates.get(_strip_sad(n)))
    unknown = sorted(set(allf.loc[allf.dam.isna(), "raw_name"]))
    if unknown:
        report["warnings"].append(f"سدهای بدون تعریف در پیکربندی (با نام خودشان آمدند): {unknown}")
        allf["dam"] = allf.dam.fillna("سد " + allf.raw_name)

    # county of each dam: config override -> «موقعیت» column of the dam statistics -> dam point location
    stat_loc = allf.dropna(subset=["location"]).groupby("dam").location.agg(lambda s: s.value_counts().idxmax()) \
        if allf.location.notna().any() else pd.Series(dtype=object)
    meta = []
    cfg_by_name = {dm["name"]: dm for dm in dam_list}
    for name in dict.fromkeys(list(cfg_by_name) + list(allf.dam.unique())):
        dm, lc = cfg_by_name.get(name, {}), loc.get(name, {})
        sb = norm(dm.get("sub_basin")) if dm.get("sub_basin") not in (None, "auto") else lc.get("sub_basin")
        meta.append({"dam": name, "sub_basin": sb if isinstance(sb, str) else UNKNOWN,
                     "location_county": lc.get("location_county"),
                     "county": norm(dm.get("county")) or stat_loc.get(name) or lc.get("location_county") or UNKNOWN,
                     "x": lc.get("x"), "y": lc.get("y")})
    meta = pd.DataFrame(meta)
    allf = allf.merge(meta[["dam", "sub_basin", "county"]], on="dam", how="left")

    uses = list(dict.fromkeys(use_map.values()))
    wd = allf.melt(id_vars=["year", "dam", "sub_basin", "county"], value_vars=[u for u in uses if u in allf],
                   var_name="use", value_name="value")
    wd = wd[wd.value.fillna(0) != 0]
    W = pd.DataFrame({"year": wd.year, "source_group": "dam", "source_name": wd.dam, "use": wd.use,
                      "county_attr": wd.county, "county_geo": wd.county, "sub_basin": wd.sub_basin,
                      "value": wd.value})
    RES = pd.DataFrame({"year": allf.year, "source_group": "dam", "source_name": allf.dam,
                        "county_geo": allf.county, "sub_basin": allf.sub_basin,
                        "value": allf.begin.fillna(0) + allf.inflow.fillna(0)})
    report["info"]["سدها"] = meta.dam.tolist()
    return W, RES, meta, allf


# --------------------------------------------------------------------------- transfers
def load_transfers(cfg, report, simaye=None):
    """Inter-basin transfers. Either from the Simaye Ab table (source: simaye_ab, field: ...) or from a
    table with year/use/value (+ begin_storage/inflow or available) columns."""
    Ws, Rs = [], []
    for t in cfg.get("transfers") or []:
        name = norm(t["name"])
        if t.get("source") == "simaye_ab":
            if simaye is None or simaye.empty or t["field"] not in simaye:
                report["warnings"].append(f"آب انتقالی «{name}» در جدول سیمای آب پیدا نشد.")
                continue
            df = pd.DataFrame({"year": simaye.year, "use": norm(t["use"]), "value": simaye[t["field"]]})
        else:
            df = read_table(cfg, t["table"], columns=t["columns"])
            df["year"] = df.year.map(norm_year)
        um = {norm(k): norm(v) for k, v in (t.get("use_map") or {}).items()}
        df["use"] = df.use.map(norm).map(lambda u: um.get(u, u))
        df["value"] = pd.to_numeric(df.value, errors="coerce").fillna(0)
        sb, county = norm(t["sub_basin"]), norm(t["county"])
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
    rows, notes = read_folder(resolve(cfg, s["folder"]), s.get("pattern", "*.pdf"), s.get("assume_deficit", True))
    report["warnings"] += notes
    df = pd.DataFrame(rows)
    if df.empty:
        report["warnings"].append("هیچ جدول بیلانی از PDFهای سیمای آب خوانده نشد.")
        return df
    df["year"] = df.year.map(norm_year)
    dup = df[df.year.duplicated(keep=False)]
    if len(dup):
        report["warnings"].append(f"چند PDF برای یک سال: {sorted(set(dup.file))}؛ آخرین فایل استفاده شد.")
    df = df.drop_duplicates("year", keep="last").sort_values("year").reset_index(drop=True)
    report["info"]["سیمای آب (PDF)"] = {r.year: r.file for r in df.itertuples()}
    return df


# --------------------------------------------------------------------------- indicators
def load_indicators(cfg, report, simaye=None):
    ind = cfg.get("indicators") or {}
    if ind == "simaye_ab":
        if simaye is None or simaye.empty:
            return pd.DataFrame(columns=["year", "renew_surface", "renew_ground", "renew_total", "nonrenewable",
                                         "gw_available", "source"])
        out = pd.DataFrame({"year": simaye.year, "renew_surface": simaye.renew_surface,
                            "renew_ground": simaye.renew_ground, "renew_total": simaye.renew_total,
                            "nonrenewable": -simaye.delta_s, "source": simaye.file})
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
        return pd.DataFrame(columns=["year", "renew_surface", "renew_ground", "renew_total", "nonrenewable",
                                     "gw_available"])
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
    rows = []
    for _, r in indicators.iterrows():
        if pd.isna(r.gw_available):
            continue
        for _, c in cells.iterrows():
            rows.append({"year": r.year, "source_group": "gw",
                         "source_name": _label(cfg, "aquifer_label", c.sub_basin),
                         "county_geo": c.county, "sub_basin": c.sub_basin, "value": r.gw_available * c.share})
    return pd.DataFrame(rows, columns=RES_COLS)
