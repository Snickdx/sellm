"""App-local entrypoint for EXCEL_FILE env helper."""

from setup.scripts.update_excel_env import main


if __name__ == "__main__":
    raise SystemExit(main())

