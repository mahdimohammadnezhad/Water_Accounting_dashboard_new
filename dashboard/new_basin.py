"""Create a basin config from a data folder (auto-detects the files), then run a health check.

    ..\\.venv\\Scripts\\python.exe new_basin.py "D:\\data\\Neyshabur" --name "محدوده مطالعاتی نیشابور" [--key neyshabur]

The folder must contain: a well-statistics Excel, a dam-statistics Excel (one sheet per water year),
the Simaye Ab PDFs and the shapefiles (sub-basins, counties, optional dam points). Sub-folders are fine.
"""
import argparse
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from wa.detect import scan, slug, write_config  # noqa: E402

ap = argparse.ArgumentParser(description="Create a basin config from a data folder")
ap.add_argument("folder")
ap.add_argument("--name", help="display name of the basin")
ap.add_argument("--key", help="short latin id (file name of the config)")
ap.add_argument("--no-check", action="store_true", help="do not run the health check")
args = ap.parse_args()

cfg, notes = scan(args.folder, name=args.name, key=args.key)
for n in notes:
    print("!", n)
path = write_config(cfg, args.folder, args.key or slug(Path(args.folder).name))
print(f"\nconfig written: {path}")
if not args.no_check:
    import subprocess
    subprocess.call([sys.executable, str(Path(__file__).parent / "check_basin.py"), str(path), "--rebuild"])
