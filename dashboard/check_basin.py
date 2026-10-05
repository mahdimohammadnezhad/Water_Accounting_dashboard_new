"""Health check: build each basin and compute every year x county basis x table layout.

    ..\\.venv\\Scripts\\python.exe check_basin.py                 # all configs in configs/
    ..\\.venv\\Scripts\\python.exe check_basin.py configs\\x.yaml --rebuild

Exit code 0 = the dashboard can show every combination without errors.
"""
import argparse
import sys
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from wa.build import get_base  # noqa: E402
from wa.config import GROUP_ORDER, list_configs, load_config  # noqa: E402
from wa.engine import compute  # noqa: E402
from wa.table import LAYOUTS, build_table, to_excel_bytes, to_html  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("configs", nargs="*")
ap.add_argument("--rebuild", action="store_true")
args = ap.parse_args()
paths = [Path(p) for p in args.configs] or list_configs()
failed = False
for path in paths:
    print("=" * 80, f"\n{path.name}")
    try:
        cfg = load_config(path)
        base = get_base(cfg, force=args.rebuild, log=lambda m: print("  ", m))
        meta = base["meta"]
        for w in meta["report"]["warnings"]:
            print("   warning:", w["en"] if isinstance(w, dict) else w)
        uses = meta["uses"]
        print(f"   years: {meta['years']}\n   sub-basins: {meta['sub_basins']}\n   uses: {[u['name'] for u in uses]}")
        modes = [m for m, ok in (("attribute", meta["has_county_attr"]), ("geo", meta["has_county_geo"])) if ok] or ["geo"]
        rows = []
        for mode in modes:
            W, RET, RES = compute(base, cfg, uses, mode)
            counties = sorted(set(W.county.dropna()) | set(RES.county.dropna()))
            for y in meta["years"]:
                for lay in LAYOUTS:
                    t, tot = build_table(base, cfg, uses, W, RET, RES, y, meta["sub_basins"] + ["نامشخص"], counties,
                                         [u["name"] for u in uses], lay, GROUP_ORDER, lay == "excel")
                    vals = t.select_dtypes("number").to_numpy(dtype=float)
                    assert not np.isinf(vals).any(), "infinite values"
                    if lay == "excel":
                        to_html(t)
                        to_html(t, lang="en")
                        to_excel_bytes({"t": t}, "check")
                        rows.append({"mode": mode, "year": y, **{k: round(v, 2) for k, v in tot.items()}})
                # every sub-basin and county alone
                for sb in meta["sub_basins"]:
                    build_table(base, cfg, uses, W, RET, RES, y, [sb], counties, [u["name"] for u in uses],
                                "county", GROUP_ORDER, False)
                for c in counties:
                    build_table(base, cfg, uses, W, RET, RES, y, meta["sub_basins"], [c], [u["name"] for u in uses],
                                "sub_basin", GROUP_ORDER, False)
        print(pd.DataFrame(rows).to_string(index=False))
        print("   OK")
    except Exception:  # noqa: BLE001
        failed = True
        print("   FAILED\n", traceback.format_exc())
sys.exit(1 if failed else 0)
