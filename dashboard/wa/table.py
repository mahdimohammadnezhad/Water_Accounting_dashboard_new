"""DYNMIC-style balance table: source rows x (use, breakdown member, withdrawal/return) columns."""
import io

import numpy as np
import pandas as pd

from .config import GROUP_LABELS
from .engine import restrict_members, row_catalog
from .text import natural_key

KW, KR = "برداشت", "برگشت"
G_COL = ("حجم در دسترس (G)", "", "")
CTRL_COL = ("کنترل (G − برداشت)", "", "")
SUMMARY = "جمع‌بندی"
ROW_TOTAL, ROW_CONS, ROW_BAL = "مجموع", "مصارف (C)", "کنترل بیلان (B)"
ALL = "کل"

LAYOUTS = {
    "excel": "قالب اکسل (DYNMIC)",
    "county": "همه کاربری‌ها به تفکیک شهرستان",
    "sub_basin": "همه کاربری‌ها به تفکیک زیرحوضه",
    "none": "فقط به تفکیک کاربری",
}


def filt(df, year=None, sbs=None, counties=None, uses=None):
    m = pd.Series(True, index=df.index)
    if year is not None:
        m &= df.year == year
    if sbs is not None:
        m &= df.sub_basin.isin(sbs)
    if counties is not None:
        m &= df.county.isin(counties)
    if uses is not None and "use" in df:
        m &= df.use.isin(uses)
    return df[m]


def breakdown_of(u, layout):
    return u["breakdown"] if layout == "excel" else layout


def use_header(u):
    return f"{u['name']} (ضریب برگشت {float(u['return_coef']):g})"


def _with_member(df, sel_uses, layout, sb_label):
    parts = []
    for u in sel_uses:
        d = df[df.use == u["name"]].copy()
        b = breakdown_of(u, layout)
        if b == "county":
            d["member"] = d.county
        elif b == "sub_basin":
            d["member"] = d.sub_basin.map(lambda s: sb_label.format(id=s))
        else:
            d["member"] = ALL
        parts.append(d)
    return pd.concat(parts, ignore_index=True) if parts else df.assign(member=pd.Series(dtype=object))


def build_table(base, cfg, uses, W, RET, RES, year, sbs, counties, uses_sel, layout, groups_sel, restrict):
    sb_label = cfg["spatial"]["sub_basin_label"]
    sel_uses = [u for u in uses if u["name"] in uses_sel]
    coef = {u["name"]: float(u["return_coef"]) for u in uses}

    Wf = restrict_members(filt(W, year, sbs, counties, uses_sel), uses, restrict)
    Rf = restrict_members(filt(RET, year, sbs, counties, uses_sel), uses, restrict)
    Sf = filt(RES, year, sbs, counties)
    Wm, Rm = _with_member(Wf, sel_uses, layout, sb_label), _with_member(Rf, sel_uses, layout, sb_label)

    # ---- columns
    cols = []
    for u in sel_uses:
        b = breakdown_of(u, layout)
        present = set(Wm.loc[Wm.use == u["name"], "member"]) | set(Rm.loc[Rm.use == u["name"], "member"])
        if b == "county":
            listed = [m for m in (u["members"] or []) if m in counties] if layout == "excel" else []
            members = listed + sorted(present - set(listed))
        elif b == "sub_basin":
            members = [sb_label.format(id=s) for s in sorted(sbs, key=natural_key)]
            members += sorted(present - set(members))
        else:
            members = [ALL]
        if not members:
            members = [ALL]
        h = use_header(u)
        for m in members:
            cols += [(h, m, KW), (h, m, KR)]
    use_of_header = {use_header(u): u["name"] for u in sel_uses}

    # ---- rows
    wp = Wm.groupby(["source_group", "source_name", "use", "member"]).value.sum()
    rp = Rm.groupby(["source_group", "source_name", "use", "member"]).value.sum()
    gp = Sf.groupby(["source_group", "source_name"]).value.sum()
    rows = []
    for grp, name, sb in row_catalog(base, cfg, W, RES):
        if grp not in groups_sel:
            continue
        if sb is not None and sb not in sbs:
            continue
        has = (grp, name) in gp.index or \
            any(k[:2] == (grp, name) for k in wp.index) or any(k[:2] == (grp, name) for k in rp.index)
        if grp in ("transfer", "treatment") and not has:
            continue
        rows.append((grp, name))

    data = []
    for grp, name in rows:
        rec = {G_COL: gp.get((grp, name), 0.0) if grp != "river" else np.nan}
        for c in cols:
            u = use_of_header[c[0]]
            src = wp if c[2] == KW else rp
            rec[c] = src.get((grp, name, u, c[1]), 0.0)
        data.append(rec)
    idx = pd.MultiIndex.from_tuples([(GROUP_LABELS[g], n) for g, n in rows], names=["گروه منبع", "منبع"])
    t = pd.DataFrame(data, index=idx, columns=[G_COL] + cols)
    t[CTRL_COL] = 0.0
    t.columns = pd.MultiIndex.from_tuples(t.columns, names=["کاربری", "تفکیک", ""])
    wcols = [c for c in cols if c[2] == KW]
    rcols = [c for c in cols if c[2] == KR]
    t[CTRL_COL] = t[G_COL].fillna(0) - t[wcols].sum(axis=1)

    # ---- summary rows (as in DYNMIC rows 22-24)
    bal_groups = {GROUP_LABELS[g] for g in cfg["balance_source_groups"]}
    in_bal = t.index.get_level_values(0).isin(list(bal_groups))
    resources = float(t.loc[in_bal, G_COL].fillna(0).sum())
    tot = pd.Series(np.nan, index=t.columns)
    cons = pd.Series(np.nan, index=t.columns)
    for wc, rc in zip(wcols, rcols):
        w = t[wc].sum()
        r = coef[use_of_header[wc[0]]] * w
        tot[wc], tot[rc] = w, r
        cons[wc] = w - r
    tot[G_COL] = resources
    total_w = float(np.nansum([tot[c] for c in wcols]))
    total_r = float(np.nansum([tot[c] for c in rcols]))
    consumption = float(np.nansum([cons[c] for c in wcols]))
    bal = pd.Series(np.nan, index=t.columns)
    bal[G_COL] = resources - consumption
    summary = pd.DataFrame([tot, cons, bal], index=pd.MultiIndex.from_tuples(
        [(SUMMARY, ROW_TOTAL), (SUMMARY, ROW_CONS), (SUMMARY, ROW_BAL)], names=t.index.names))
    t = pd.concat([t, summary])

    # withdrawals left out by the Excel-template member lists
    omitted = filt(W, year, sbs, counties, uses_sel).value.sum() - Wf.value.sum()
    totals = {"withdrawal": total_w, "return": total_r, "consumption": consumption,
              "resources": resources, "balance": resources - consumption, "omitted": float(omitted)}
    return t, totals


# ----------------------------------------------------------------------------- rendering
FA = str.maketrans("0123456789.,", "۰۱۲۳۴۵۶۷۸۹٫٬")
USE_HEAD = ["#1d4ed8", "#0f766e", "#b45309", "#7c3aed", "#be185d", "#0369a1", "#4d7c0f", "#475569"]
GROUP_TINT = {"سد": "#dbeafe", "بازه رودخانه": "#cffafe", "آب زیرزمینی": "#fef3c7", "انتقالی": "#d1fae5",
              "تصفیه خانه": "#e5e7eb", SUMMARY: "#e2e8f0"}
RGB_W, RGB_R, RGB_POS, RGB_NEG = "37,99,235", "13,148,136", "5,150,105", "220,38,38"
COLOR_LEGEND = [("برداشت (پررنگ‌تر = بیشتر)", f"linear-gradient(to left, rgba({RGB_W},.9), rgba({RGB_W},.1))"),
                ("برگشت", f"linear-gradient(to left, rgba({RGB_R},.9), rgba({RGB_R},.1))"),
                ("حجم در دسترس (نوار)", "linear-gradient(to left, rgba(245,158,11,.55) 60%, #fff 60%)"),
                ("کنترل منفی (کسری)", f"rgba({RGB_NEG},.6)"), ("کنترل مثبت", f"rgba({RGB_POS},.55)")]


def _fmt(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return ""
    if abs(v) < 5e-5:
        return "·"
    return f"{v:,.2f}".translate(FA)


def _shade(v, vmax, rgb, log=True):
    if not isinstance(v, (int, float)) or np.isnan(v) or v <= 1e-6 or not vmax or vmax <= 0:
        return ""
    x = np.log1p(v) / np.log1p(vmax) if log else v / vmax
    a = 0.08 + 0.80 * min(max(x, 0), 1)
    return f"background-color: rgba({rgb},{a:.2f}); color: {'#fff' if a > 0.55 else '#0f172a'}"


def _tint(hex_color, a):
    h = hex_color.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{a})"


def to_html(t, conditional=True, log_scale=True):
    cols = list(t.columns)
    wcols = [c for c in cols if c[2] == KW]
    rcols = [c for c in cols if c[2] == KR]
    body = [i for i in t.index if i[0] != SUMMARY]
    sty = t.style.format(_fmt)

    def row_style(r):
        if r.name[0] != SUMMARY:
            return [""] * len(r)
        bg = {ROW_TOTAL: "#eef2f7", ROW_CONS: "#e2e8f0", ROW_BAL: "#fff7e0"}.get(r.name[1], "#eef2f7")
        return [f"background-color:{bg};font-weight:800"] * len(r)

    sty = sty.apply(row_style, axis=1)
    if conditional and body:
        bt = t.loc[body]
        wmax = float(np.nanmax(bt[wcols].values)) if wcols else 0
        rmax = float(np.nanmax(bt[rcols].values)) if rcols else 0
        gmax = float(np.nanmax(bt[G_COL].values)) if bt[G_COL].notna().any() else 0
        cmax = float(np.nanmax(np.abs(bt[CTRL_COL].values))) if len(bt) else 0
        if wcols:
            sty = sty.map(lambda v: _shade(v, wmax, RGB_W, log_scale), subset=pd.IndexSlice[body, wcols])
        if rcols:
            sty = sty.map(lambda v: _shade(v, rmax, RGB_R, log_scale), subset=pd.IndexSlice[body, rcols])

        def bar(v):
            if not isinstance(v, (int, float)) or np.isnan(v) or v <= 0 or gmax <= 0:
                return ""
            p = 100 * v / gmax
            return f"background: linear-gradient(to left, rgba(245,158,11,.5) {p:.0f}%, #fff {p:.0f}%); font-weight:700"

        def ctrl(v):
            if not isinstance(v, (int, float)) or np.isnan(v) or abs(v) < 5e-5 or cmax <= 0:
                return ""
            return _shade(abs(v), cmax, RGB_NEG if v < 0 else RGB_POS, False) + ";font-weight:700"

        sty = sty.map(bar, subset=pd.IndexSlice[body, [G_COL]])
        sty = sty.map(ctrl, subset=pd.IndexSlice[body, [CTRL_COL]])
    else:
        sty = sty.map(lambda v: "color:#b42318;font-weight:700" if isinstance(v, (int, float)) and v < -5e-5 else "",
                      subset=[G_COL, CTRL_COL])
    # balance cell
    bal = (SUMMARY, ROW_BAL)
    if bal in t.index:
        v = t.loc[bal, G_COL]
        sty = sty.map(lambda _: f"background-color:{'#fde2e1' if v < 0 else '#d1fae5'};"
                                f"color:{'#b42318' if v < 0 else '#047857'};font-weight:800;font-size:13.5px",
                      subset=pd.IndexSlice[[bal], [G_COL]])

    # coloured header bands per use, lighter per member, withdrawal/return row
    styles, uses = [], list(dict.fromkeys(c[0] for c in wcols))
    for k, u in enumerate(uses):
        color = USE_HEAD[k % len(USE_HEAD)]
        idx = [i for i, c in enumerate(cols) if c[0] == u]
        styles.append({"selector": f"th.col_heading.level0.col{idx[0]}", "props": f"background:{color};"})
        for i in idx:
            styles.append({"selector": f"th.col_heading.level1.col{i}", "props": f"background:{_tint(color, .75)};"})
            styles.append({"selector": f"th.col_heading.level2.col{i}",
                           "props": f"background:{_tint(color, .45 if cols[i][2] == KW else .3)};color:#0f172a;"})
    for c in (G_COL, CTRL_COL):
        i = cols.index(c)
        styles.append({"selector": f"th.col_heading.col{i}", "props": "background:#7c5a10;"})
    sty = sty.set_table_styles(styles, overwrite=False)
    sty = sty.map_index(lambda v: f"background-color:{GROUP_TINT.get(v, '#f8fafc')}", axis=0, level=0)
    return sty.set_table_attributes('class="wa-table"').to_html()


def to_excel_bytes(sheets, title=""):
    """sheets: {name: DataFrame}. Writes formatted workbook (merged multi-level headers)."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as xw:
        for name, df in sheets.items():
            start = 2 if title else 0
            df.to_excel(xw, sheet_name=name[:31], startrow=start)
            ws = xw.sheets[name[:31]]
            wb = xw.book
            ws.right_to_left()
            if title:
                ws.write(0, 0, title, wb.add_format({"bold": True, "font_size": 13}))
            num = wb.add_format({"num_format": "#,##0.00"})
            nlev = df.index.nlevels
            header_rows = df.columns.nlevels + (1 if df.columns.nlevels > 1 else 0)
            ws.set_column(0, nlev - 1, 22)
            ws.set_column(nlev, nlev + len(df.columns), 12, num)
            ws.freeze_panes(start + header_rows, nlev)
            # same colour coding as the dashboard (Excel conditional formatting)
            if df.columns.nlevels == 3:
                r0 = start + header_rows
                r1 = r0 + int((df.index.get_level_values(0) != SUMMARY).sum()) - 1
                for j, c in enumerate(df.columns):
                    col = nlev + j
                    colour = {KW: "#2563eb", KR: "#0d9488"}.get(c[2])
                    if colour:
                        ws.conditional_format(r0, col, r1, col, {"type": "2_color_scale", "min_color": "#FFFFFF",
                                                                 "max_color": colour})
                    elif c == G_COL:
                        ws.conditional_format(r0, col, r1, col, {"type": "data_bar", "bar_color": "#F59E0B"})
                    elif c == CTRL_COL:
                        ws.conditional_format(r0, col, r1, col, {"type": "3_color_scale", "min_color": "#F87171",
                                                                 "mid_type": "num", "mid_value": 0,
                                                                 "mid_color": "#FFFFFF", "max_color": "#34D399"})
    return buf.getvalue()
