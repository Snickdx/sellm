"""
Backward-compatible placeholder for legacy excel-env updater.

The app now reads EXCEL_FILE directly from .env at runtime.
"""

from dotenv import load_dotenv


def main() -> int:
    load_dotenv()
    print("No code rewrite needed. Set EXCEL_FILE in .env/.env.example and restart app.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
