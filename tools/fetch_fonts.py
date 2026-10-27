"""Re-download the bundled OFL fonts (only needed if assets/fonts/ is missing).

    python tools/fetch_fonts.py [--dir assets/fonts]

All families are SIL OFL 1.1 and are fetched from google/fonts. The repository already
contains them; this script exists so a stripped checkout can be repaired without a browser.
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

FONTS = {
    "Inter-Variable.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/inter/Inter%5Bopsz,wght%5D.ttf",
    "SpaceGrotesk-Variable.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/spacegrotesk/SpaceGrotesk%5Bwght%5D.ttf",
    "Silkscreen-Regular.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/silkscreen/Silkscreen-Regular.ttf",
    "Silkscreen-Bold.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/silkscreen/Silkscreen-Bold.ttf",
    "NotoNastaliqUrdu-Variable.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/notonastaliqurdu/NotoNastaliqUrdu%5Bwght%5D.ttf",
    "NotoNaskhArabic-Variable.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/notonaskharabic/NotoNaskhArabic%5Bwght%5D.ttf",
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="assets/fonts")
    args = ap.parse_args(argv)
    target = Path(args.dir)
    target.mkdir(parents=True, exist_ok=True)
    failures = 0
    for name, url in FONTS.items():
        dest = target / name
        if dest.exists() and dest.stat().st_size > 10_000:
            print(f"ok    {name} (already present)")
            continue
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                data = resp.read()
            if len(data) < 10_000:
                raise ValueError(f"only {len(data)} bytes")
            dest.write_bytes(data)
            print(f"added {name} ({len(data) / 1e6:.1f} MB)")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL  {name}: {exc}")
    if failures:
        print("\nSome fonts could not be downloaded. Copy them manually into", target)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
