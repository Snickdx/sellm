"""Validate sellm PWA assets (manifest, icons, root filenames)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "web" / "static"
ERRORS: list[str] = []


def fail(msg: str) -> None:
    ERRORS.append(msg)
    print(f"FAIL: {msg}")


def ok(msg: str) -> None:
    print(f"OK:   {msg}")


def main() -> int:
    # Never allow webmanifest
    if (STATIC / "manifest.webmanifest").exists():
        fail("manifest.webmanifest must not exist")
    else:
        ok("no manifest.webmanifest")

    manifest_path = STATIC / "manifest.json"
    if not manifest_path.is_file():
        fail("missing manifest.json")
        return 1

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"manifest.json invalid JSON: {exc}")
        return 1
    ok("manifest.json parses")

    for key in ("name", "short_name", "start_url", "scope", "display", "icons"):
        if key not in data or data[key] in ("", None, []):
            fail(f"manifest missing/empty field: {key}")
        else:
            ok(f"manifest.{key}")

    if data.get("display") != "standalone":
        fail("display must be standalone")

    for icon in data.get("icons", []):
        src = icon.get("src", "")
        rel = src.lstrip("/")
        path = STATIC / rel
        if not path.is_file():
            fail(f"missing icon file for {src}")
            continue
        with Image.open(path) as im:
            declared = icon.get("sizes", "")
            if "x" in declared:
                w, h = declared.lower().split("x", 1)
                if im.size != (int(w), int(h)):
                    fail(f"{src} size {im.size} != declared {declared}")
                else:
                    ok(f"{src} size {declared}")
            if icon.get("type") == "image/png" and im.format != "PNG":
                fail(f"{src} is {im.format}, expected PNG")
            purpose = icon.get("purpose", "any")
            if "maskable" in purpose and "maskable" not in path.name:
                fail(f"{src} declared maskable but filename is not maskable-dedicated")
            if purpose == "any" and "maskable" in path.name:
                fail(f"{src} is maskable asset but purpose=any")

    required_root = [
        "favicon.ico",
        "favicon.svg",
        "favicon-16.png",
        "favicon-32.png",
        "favicon-48.png",
        "apple-touch-icon.png",
        "sw.js",
        "offline.html",
    ]
    for name in required_root:
        if (STATIC / name).is_file():
            ok(name)
        else:
            fail(f"missing {name}")

    index = (ROOT / "app" / "web" / "templates" / "index.html").read_text(encoding="utf-8")
    admin = (ROOT / "app" / "web" / "templates" / "admin.html").read_text(encoding="utf-8")
    for label, html in (("index.html", index), ("admin.html", admin)):
        if 'href="/manifest.json"' not in html:
            fail(f"{label} missing manifest link")
        else:
            ok(f"{label} links manifest.json")
        if "serviceWorker" not in html or "unregister" not in html:
            fail(f"{label} missing service worker unregister/cleanup")
        else:
            ok(f"{label} unregisters service worker")
        if "serviceWorker.register" in html or 'register("/sw.js")' in html:
            fail(f"{label} still registers service worker")
        if "manifest.webmanifest" in html:
            fail(f"{label} references manifest.webmanifest")

    shots = data.get("screenshots") or []
    if not shots:
        print("WARN: screenshots not in manifest")
    for shot in shots:
        src = shot.get("src", "")
        rel = src.lstrip("/")
        path = STATIC / rel
        if not path.is_file():
            fail(f"missing screenshot {src}")
            continue
        with Image.open(path) as im:
            declared = shot.get("sizes", "")
            if "x" in declared:
                w, h = declared.lower().split("x", 1)
                if im.size != (int(w), int(h)):
                    fail(f"{src} size {im.size} != declared {declared}")
                else:
                    ok(f"{src} size {declared}")

    brand_required = [
        "brand/logo-mark.svg",
        "brand/logo-mark-mono.svg",
        "brand/logo-horizontal-dark.svg",
        "brand/logo-horizontal-light.svg",
        "brand/logo-wordmark-dark.svg",
        "brand/logo-wordmark-light.svg",
        "brand/icon-master.svg",
        "brand/icon-maskable-master.svg",
        "brand/BRAND.md",
    ]
    for rel in brand_required:
        if (STATIC / rel).is_file():
            ok(rel)
        else:
            fail(f"missing {rel}")

    if ERRORS:
        print(f"\n{len(ERRORS)} failure(s)")
        return 1
    print("\nAll PWA checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
