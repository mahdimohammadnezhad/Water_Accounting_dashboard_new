"""Robustness test: build a synthetic 'other basin' from the Mashhad files, but with a different structure
(3 sub-basins with text ids stored in lon/lat, other column and field names, files in sub-folders, a missing
Simaye Ab year, an extra use, unrelated files), then auto-detect it and run the health check.

    ..\\.venv\\Scripts\\python.exe tests\\make_test_basin.py  [output folder]

Needs the Mashhad raw data next to the dashboard folder. The generated config (configs/test_basin.yaml) is
removed at the end unless --keep is given.
"""
import shutil
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

import geopandas as gpd
import pandas as pd

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
DASH = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DASH))
from wa.text import fix_mojibake, norm  # noqa: E402

SRC = DASH.parent
args = [a for a in sys.argv[1:] if not a.startswith("--")]
OUT = Path(args[0]) if args else Path(tempfile.gettempdir()) / "wa_test_basin"
if OUT.exists():
    shutil.rmtree(OUT)
for d in ("gis/boundaries", "gis/other", "stats", "simaye ab"):
    (OUT / d).mkdir(parents=True)

sb = gpd.read_file(SRC / "shape" / "final_boundary_fixed.shp")
sb["Name"] = sb.layer.map({"1": "الف", "2": "الف", "3": "ب", "4": "ج"})
sb = sb.dissolve("Name", as_index=False)[["Name", "geometry"]]
sb["Area"] = 1.0
sb.to_crs(4326).to_file(OUT / "gis" / "boundaries" / "zirhoze_test.shp", encoding="utf-8")

ct = gpd.read_file(SRC / "shape" / "shahrestan.shp")
ct["SHAHR"] = ct.PER_NAM.map(lambda s: norm(fix_mojibake(s)))
ct[["SHAHR", "geometry"]].to_file(OUT / "gis" / "boundaries" / "shahrestan_test.shp", encoding="utf-8")

dp = gpd.read_file(SRC / "shape" / "selected_dams.shp")
dp["DamName"] = dp.Name
dp[["DamName", "geometry"]].to_file(OUT / "gis" / "dams_points.shp", encoding="utf-8")
gpd.read_file(SRC / "rivers" / "rivers.shp").head(300).to_file(OUT / "gis" / "other" / "rivers_part.shp")

ch = pd.read_excel(SRC / "CHAH_MASHAHD.xls")
ch = ch[ch["سال آبي"].isin(["1399-00", "1400-01", "1401-02", "1402-03"])]
w = pd.DataFrame({"سال": ch["سال آبي"], "شهرستان": ch["شهرستان"], "UTM_X": ch.MA_XUTM, "UTM_Y": ch.MA_YUTM,
                  "نوع مصرف": ch["نوع مصرف"], "برداشت": ch["برداشت واقعي"]})
w.loc[w.sample(200, random_state=1).index, "نوع مصرف"] = "فضای سبز"
w.to_excel(OUT / "stats" / "chah_test_basin.xlsx", index=False)

xl = pd.ExcelFile(SRC / "Amar_SAD.xlsx")
with pd.ExcelWriter(OUT / "stats" / "dam_statistics.xlsx") as xw:
    for sh in ["99-00", "00-01", "01-02", "02-03"]:
        xl.parse(sh, header=None).to_excel(xw, sheet_name=("13" if sh[0] == "9" else "14") + sh,
                                           header=False, index=False)
pd.DataFrame({"a": [1, 2], "b": [3, 4]}).to_excel(OUT / "stats" / "notes.xlsx", index=False)
for f in ["simabm_mashhad_99_00.pdf", "simabm_mashhad_00_01.pdf", "BILAN402-03.pdf"]:
    shutil.copy(SRC / "Bilan" / f, OUT / "simaye ab" / f)
print("synthetic basin written to", OUT)
for f in (DASH / "configs").glob("test_basin*.yaml"):  # leftovers of a previous --keep run
    f.unlink()

code = subprocess.call([sys.executable, str(DASH / "new_basin.py"), str(OUT), "--name", "حوضه آزمایشی",
                        "--key", "test_basin"])

# scenario B: no shapefiles at all (only the Excel files and PDFs) -> the study area is found from the well
# locations in the country-wide layer (configs/_regional.yaml) and counties come from that layer too
OUT_B = OUT.with_name(OUT.name + "_noshape")
if OUT_B.exists():
    shutil.rmtree(OUT_B)
shutil.copytree(OUT / "stats", OUT_B / "stats")
shutil.copytree(OUT / "simaye ab", OUT_B / "simaye ab")
code_b = subprocess.call([sys.executable, str(DASH / "new_basin.py"), str(OUT_B), "--name", "حوضه بدون شیپ‌فایل",
                          "--key", "test_basin_noshape"])
if "--keep" not in sys.argv:
    for f in (DASH / "configs").glob("test_basin*.yaml"):
        f.unlink()
    for d in (DASH / "data" / "processed").glob("test_basin*"):
        shutil.rmtree(d, ignore_errors=True)
print("\nRESULT:", "OK" if code == 0 and code_b == 0 else "FAILED", f"(with shapefiles: {code}, without: {code_b})")
sys.exit(code or code_b)
