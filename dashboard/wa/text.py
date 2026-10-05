"""Persian text helpers: one canonical spelling for every name coming from Excel/shapefiles."""
import math
import re

_CHAR_MAP = str.maketrans({
    "ي": "ی", "ى": "ی", "ك": "ک",
    "\u200F": "", "\u200E": "", " ": " ",
    "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4", "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
})


def norm(s):
    """Unify Arabic/Persian letters and whitespace so 'كشاورزي' == 'کشاورزی'."""
    if s is None or (isinstance(s, float) and math.isnan(s)):
        return s
    if isinstance(s, float) and s.is_integer():
        s = int(s)
    s = str(s).translate(_CHAR_MAP)
    return re.sub(r"\s+", " ", s).strip()


def fix_mojibake(s, encoding="cp1256"):
    """Shapefile names stored as cp1256 bytes but decoded as latin-1 ('ãÔåÏ' -> 'مشهد')."""
    if not isinstance(s, str):
        return s
    try:
        return s.encode("latin-1").decode(encoding)
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


_ARABIC = re.compile(r"[؀-ۿ]")
_LATIN1_HIGH = re.compile(r"[\u0080-ÿ]")


def looks_mojibake(values):
    """True when Persian names were decoded with the wrong code page (no Arabic letters, many Ã-ÿ chars)."""
    vals = [v for v in values if isinstance(v, str) and v.strip()]
    if not vals:
        return False
    bad = sum(1 for v in vals if not _ARABIC.search(v) and _LATIN1_HIGH.search(v))
    return bad >= 0.5 * len(vals)


def auto_fix_names(values, encoding="auto"):
    """Repair a list of names: encoding='auto' fixes only if it looks like cp1256 mojibake."""
    if encoding in (None, False, "none"):
        return list(values)
    if encoding == "auto":
        if not looks_mojibake(values):
            return list(values)
        encoding = "cp1256"
    return [fix_mojibake(v, encoding) for v in values]


def has_persian(s):
    return isinstance(s, str) and bool(_ARABIC.search(s))


def match_column(columns, aliases):
    """Pick the column whose normalized name equals (then contains) one of the aliases."""
    cols = {norm(c).lower(): c for c in columns}
    for a in aliases:
        k = norm(a).lower()
        if k in cols:
            return cols[k]
    for a in aliases:
        k = norm(a).lower()
        for nc, c in cols.items():
            if len(k) > 2 and k in nc:
                return c
    return None


def norm_year(s):
    """'1395-96', '95-96', '00-01', '1395', 1395 -> '1395-96'."""
    if s is None or (isinstance(s, float) and math.isnan(s)):
        return None
    parts = re.findall(r"\d+", norm(s))
    if not parts:
        return None
    y = parts[0]
    if len(y) <= 2:
        y = int(y)
        y = 1400 + y if y < 50 else 1300 + y
    else:
        y = int(y)
    return f"{y}-{(y + 1) % 100:02d}"


def sheet_year(name):
    """Water year from a sheet name like '94-95', '1394-95', '1400_01' (None for 'Sheet1')."""
    s = norm(name) or ""
    m = re.search(r"(\d{2,4})\s*[-_/–]\s*(\d{2,4})", s) or re.fullmatch(r"\s*(1[34]\d\d)\s*", s)
    return norm_year(m.group(1)) if m else None


def natural_key(s):
    """Sort '2' before '10' and numbers before text."""
    s = str(s)
    return (0, int(s), "") if s.isdigit() else (1, 0, s)
