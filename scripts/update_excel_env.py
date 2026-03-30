"""Compatibility entrypoint for app EXCEL_FILE env helper."""

from app.scripts.update_excel_env import main


if __name__ == "__main__":
    raise SystemExit(main())
