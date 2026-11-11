"""Capture genuine sellm landing screenshots for the PWA manifest."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "app" / "web" / "static" / "screenshots"
BASE = "http://127.0.0.1:8765"


def wait_ready(timeout: float = 90.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(f"{BASE}/", timeout=2.0).status_code < 500:
                return
        except Exception:
            pass
        time.sleep(1.0)
    raise RuntimeError("sellm server did not become ready")


def main() -> int:
    SHOTS.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.api.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8765",
        ],
        cwd=str(ROOT),
        env=dict(os.environ),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        wait_ready()
        with sync_playwright() as p:
            browser = None
            for channel in ("chrome", "msedge", "chromium"):
                try:
                    browser = p.chromium.launch(channel=channel)
                    break
                except Exception:
                    continue
            if browser is None:
                browser = p.chromium.launch()

            mobile = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
            mobile.set_default_timeout(60000)
            mobile.goto(f"{BASE}/", wait_until="commit")
            mobile.wait_for_timeout(2000)
            mobile.screenshot(path=str(SHOTS / "mobile-home.png"))

            desktop = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
            desktop.set_default_timeout(60000)
            desktop.goto(f"{BASE}/", wait_until="commit")
            desktop.wait_for_timeout(2000)
            desktop.screenshot(path=str(SHOTS / "desktop-home.png"), timeout=120000)
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()

    # Normalize to declared manifest sizes
    m = Image.open(SHOTS / "mobile-home.png").convert("RGB").resize((390, 844), Image.Resampling.LANCZOS)
    m.save(SHOTS / "mobile-home.png", format="PNG", optimize=True)
    m.save(SHOTS / "mobile-home.webp", format="WEBP", quality=84, method=6)
    d = Image.open(SHOTS / "desktop-home.png").convert("RGB").resize((1440, 900), Image.Resampling.LANCZOS)
    d.save(SHOTS / "desktop-home.png", format="PNG", optimize=True)
    d.save(SHOTS / "desktop-home.webp", format="WEBP", quality=84, method=6)
    print("wrote mobile-home + desktop-home (png/webp)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
