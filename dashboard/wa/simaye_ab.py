"""Read the first table («بیلان آب محدوده مطالعاتی») of the Simaye Ab (سیمای آب) PDFs.

The table has three columns: موضوع | سال آبی (values) | توضیحات. Some PDFs use a legacy Persian font whose
extracted letters are scrambled (حجم -> حجن), but the numbers are always intact, so the table is read
structurally from the value column:
    ... | حجم آب تجدیدشونده | سطحی | زیرزمینی | برگشتی | تغذیه از جریان سطحی | تغییر ذخیره آبخوان (کسری) | ...
  * renewable total / surface / ground = the first three consecutive values with total = surface + ground
  * groundwater storage change (ΔS)    = the value three rows below the groundwater renewable
  * transfer from Doosti dam            = the number after «شامل» in the notes column
"""
import re
import unicodedata
from pathlib import Path

import pdfplumber

from .text import norm, norm_year

NUM = re.compile(r"^[-−–]?\d+(?:[./٫]\d+)?[-−–]?$")
INCLUDES = {"شامل", "ضاهل"}  # 'ضاهل' = «شامل» in the legacy font


def _clean(s):
    return norm(unicodedata.normalize("NFKC", s or "")) or ""


def _number(s):
    s = _clean(s).replace(" ", "")
    if not NUM.match(s):
        return None
    v = float(re.sub(r"[-−–]", "", s).replace("/", ".").replace("٫", "."))
    return -v if re.search(r"[-−–]", s) else v


def _cx(w):
    return (w["x0"] + w["x1"]) / 2


def _value_column(nums, tol=25):
    """Largest group of numbers sharing (roughly) the same x position = the «سال آبی» column."""
    best = []
    for w, _ in nums:
        grp = [(u, v) for u, v in nums if abs(_cx(u) - _cx(w)) <= tol]
        if len(grp) > len(best):
            best = grp
    return sorted(best, key=lambda t: t[0]["top"])


def parse_page(page):
    words = page.extract_words()
    nums = [(w, _number(w["text"])) for w in words]
    nums = [(w, v) for w, v in nums if v is not None and w["x0"] > 20]  # skip the vertical side banner
    if len(nums) < 6:
        return None
    col = _value_column(nums)
    vals = [v for _, v in col]

    def adds_up(i):
        return i + 2 < len(vals) and vals[i + 1] > 0 and vals[i + 2] > 0 and \
            abs(vals[i] - vals[i + 1] - vals[i + 2]) <= max(0.25, 0.002 * vals[i])

    hits = [i for i in range(len(vals) - 2) if adds_up(i)]
    if not hits:
        return None
    # rainfall volume = ET + renewable: the triple with the largest total; renewable is its third value
    r = max(hits, key=lambda i: vals[i]) + 2
    if r >= len(vals):
        return None
    out = {"renew_total": vals[r]}
    if adds_up(r):
        out["renew_surface"], out["renew_ground"] = vals[r + 1], vals[r + 2]
        ds_i = r + 5
    else:  # surface value missing from the PDF text layer (1395-96): derive it
        out["renew_ground"] = vals[r + 1]
        out["renew_surface"] = round(vals[r] - vals[r + 1], 3)
        out["derived"] = "سطحی = تجدیدشونده − زیرزمینی"
        ds_i = r + 4
    if ds_i < len(vals):
        out["delta_s_reported"] = vals[ds_i]
    # transfer: number right after «شامل» (to its left on the same line, RTL)
    for w in words:
        if _clean(w["text"])[::-1] in INCLUDES or _clean(w["text"]) in INCLUDES:
            same = [(u, _number(u["text"])) for u in words
                    if abs(u["top"] - w["top"]) < 4 and u["x1"] <= w["x0"] + 1 and _number(u["text"]) is not None]
            if same:
                out["doosti_transfer"] = max(same, key=lambda t: t[0]["x1"])[1]
                break
    m = None
    for w in words:
        m = re.fullmatch(r"(1[34]\d\d)-(\d\d)", _clean(w["text"]))
        if m:
            break
    out["year"] = f"{m.group(1)}-{m.group(2)}" if m else None
    return out


def year_from_name(name):
    m = re.findall(r"(\d{2,4})[_-](\d{2})", name)
    if not m:
        return None
    y = m[-1][0]
    if len(y) == 3:  # 'BILAN402-03'
        y = "1" + y
    return norm_year(y)


def read_pdf(path):
    path = Path(path)
    with pdfplumber.open(path) as pdf:
        for n, page in enumerate(pdf.pages[:8], start=1):
            out = parse_page(page)
            if out:
                out["year"] = out.get("year") or year_from_name(path.name)
                out["file"] = path.name
                out["page"] = n
                return out
    return None


def read_folder(folder, pattern="*.pdf", assume_deficit=True):
    """All PDFs in a folder -> one row per water year. With assume_deficit, ΔS is always taken as a
    storage loss (some PDFs print the deficit without a minus sign, e.g. 1398-99: 163.9)."""
    rows, notes = [], []
    for p in sorted(Path(folder).glob(pattern)):
        r = read_pdf(p)
        if not r:
            notes.append(f"جدول بیلان در {p.name} پیدا نشد.")
            continue
        if r.get("derived"):
            notes.append(f"{p.name}: عدد سطحی در متن PDF نبود؛ {r['derived']} ({r['renew_surface']}).")
        ds = r.get("delta_s_reported")
        if ds is not None:
            if assume_deficit and ds > 0:
                notes.append(f"{p.name}: تغییر ذخیره آبخوان بدون علامت منفی ({ds}) آمده و کسری در نظر گرفته شد.")
            r["delta_s"] = -abs(ds) if assume_deficit else ds
        rows.append(r)
    return rows, notes
