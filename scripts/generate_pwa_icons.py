"""Generate sellm PWA icons and favicons from brand SVG masters."""
from __future__ import annotations

import io
import tempfile
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "web" / "static"
BRAND = STATIC / "brand"
ICONS = STATIC / "icons"

MASTER_SVG = BRAND / "icon-master.svg"
MASKABLE_SVG = BRAND / "icon-maskable-master.svg"
MARK_SVG = BRAND / "logo-mark.svg"
MONO_SVG = BRAND / "logo-mark-mono.svg"


def rasterize_svg(svg_path: Path, size: int, out_path: Path | None = None) -> Image.Image:
    """Render an SVG to a square RGBA PNG via Chromium."""
    html = f"""<!DOCTYPE html>
<html><head><style>
  html,body{{margin:0;width:{size}px;height:{size}px;background:transparent;overflow:hidden}}
  img{{width:{size}px;height:{size}px;display:block}}
</style></head>
<body><img src="file:///{svg_path.as_posix()}" alt=""/></body></html>"""
    with tempfile.TemporaryDirectory() as tmp:
        page_path = Path(tmp) / "render.html"
        page_path.write_text(html, encoding="utf-8")
        with sync_playwright() as p:
            # Prefer system Chrome/Edge so we don't require `playwright install`.
            browser = None
            for channel in ("chrome", "msedge", "chromium"):
                try:
                    browser = p.chromium.launch(channel=channel)
                    break
                except Exception:
                    continue
            if browser is None:
                browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": size, "height": size}, device_scale_factor=1)
            page.goto(page_path.as_uri(), wait_until="networkidle")
            png_bytes = page.screenshot(type="png", omit_background=True)
            browser.close()
    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    if img.size != (size, size):
        img = img.resize((size, size), Image.Resampling.LANCZOS)
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path, format="PNG", optimize=True)
        print(f"wrote {out_path} {img.size}")
    return img


def save_png(img: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGBA").save(path, format="PNG", optimize=True)
    print(f"wrote {path} {img.size}")


def main() -> None:
    ICONS.mkdir(parents=True, exist_ok=True)
    for required in (MASTER_SVG, MASKABLE_SVG, MARK_SVG, MONO_SVG):
        if not required.is_file():
            raise SystemExit(f"Missing brand SVG: {required}")

    # Render masters once at high res, then downscale.
    master = rasterize_svg(MASTER_SVG, 1024, ICONS / "icon-master-1024.png")
    maskable = rasterize_svg(MASKABLE_SVG, 1024)
    mark = rasterize_svg(MARK_SVG, 1024)
    mono_src = rasterize_svg(MONO_SVG, 1024)

    for size, name in ((512, "icon-512.png"), (192, "icon-192.png")):
        save_png(master.resize((size, size), Image.Resampling.LANCZOS), ICONS / name)

    for size, name in ((512, "icon-maskable-512.png"), (192, "icon-maskable-192.png")):
        save_png(maskable.resize((size, size), Image.Resampling.LANCZOS), ICONS / name)

    # Monochrome master is already a white silhouette on transparent.
    for size, name in ((512, "icon-monochrome-512.png"), (192, "icon-monochrome-192.png")):
        save_png(mono_src.resize((size, size), Image.Resampling.LANCZOS), ICONS / name)

    for size, name in (
        (16, "favicon-16.png"),
        (32, "favicon-32.png"),
        (48, "favicon-48.png"),
        (180, "apple-touch-icon.png"),
    ):
        save_png(mark.resize((size, size), Image.Resampling.LANCZOS), STATIC / name)

    favs = [mark.resize((s, s), Image.Resampling.LANCZOS) for s in (16, 32, 48)]
    ico = STATIC / "favicon.ico"
    favs[0].save(ico, format="ICO", sizes=[(16, 16), (32, 32), (48, 48)], append_images=favs[1:])
    print(f"wrote {ico}")

    STATIC.joinpath("favicon.svg").write_text(MARK_SVG.read_text(encoding="utf-8"), encoding="utf-8")
    print("wrote favicon.svg (synced from logo-mark.svg)")
    print("done")


if __name__ == "__main__":
    main()
