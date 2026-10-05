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


def natural_key(s):
    """Sort '2' before '10' and numbers before text."""
    s = str(s)
    return (0, int(s), "") if s.isdigit() else (1, 0, s)
