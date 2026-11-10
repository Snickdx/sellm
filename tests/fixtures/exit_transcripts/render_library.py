"""Back-compat: render library bands via the shared renderer."""

from __future__ import annotations

import sys

from tests.fixtures.exit_transcripts.render_bands import main as _main


if __name__ == "__main__":
    # Default to library if no --scenario given.
    if "--scenario" not in sys.argv:
        sys.argv.extend(["--scenario", "library"])
    _main()
