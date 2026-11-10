"""Print or write human-readable exit-interview band transcripts.

  python -m tests.fixtures.exit_transcripts.render_bands --write
  python -m tests.fixtures.exit_transcripts.render_bands --scenario library --write
"""

from __future__ import annotations

import argparse
from pathlib import Path

from tests.fixtures.exit_transcripts.bands_loader import (
    list_scenario_slugs,
    load_bands,
    render_band_transcript,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--scenario", action="append", dest="scenarios")
    args = parser.parse_args()
    slugs = args.scenarios or list_scenario_slugs()
    root = Path(__file__).resolve().parent
    for slug in slugs:
        fixture = load_bands(slug)
        for band_key in fixture["bands"]:
            text = render_band_transcript(slug, band_key)
            if args.write:
                path = root / slug / f"transcript_{band_key}.md"
                path.write_text(text, encoding="utf-8")
                print(f"wrote {path}")
            else:
                print(text)
                print("---")


if __name__ == "__main__":
    main()
