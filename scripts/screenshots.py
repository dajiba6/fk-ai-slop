"""Screenshots of a running demo site for the README.

    uv run python scripts/demo_data.py /tmp/fk-demo
    FK_DATA_DIR=/tmp/fk-demo FK_EMBED_MODEL= uv run fk rebuild
    FK_DATA_DIR=/tmp/fk-demo FK_EMBED_MODEL= FK_PORT=8097 ADMIN_KEY=demo uv run fk serve &
    uv run python scripts/screenshots.py http://127.0.0.1:8097 demo docs/images
"""
import hashlib
import hmac
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def main(base, key, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    token = hmac.new(key.encode(), b"fk-admin", hashlib.sha256).hexdigest()
    with sync_playwright() as p:
        browser = p.chromium.launch()

        def page(width, height, scale):
            context = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=scale,
                                          locale="zh-CN")
            context.add_cookies([{"name": "fk_admin", "value": token, "url": base}])
            return context.new_page()

        home = page(1440, 900, 1.5)
        home.goto(f"{base}/")
        home.wait_for_timeout(2000)
        home.screenshot(path=out / "home.png")
        home.locator("div.fixed.z-40 > button").click()
        home.wait_for_timeout(500)
        home.screenshot(path=out / "summary-dock.png", clip={"x": 900, "y": 420, "width": 540, "height": 480})

        search = page(1280, 820, 1.5)
        search.goto(f"{base}/search?q=telephone&mode=keyword")
        search.wait_for_timeout(2000)
        search.screenshot(path=out / "search.png")

        mobile = page(390, 844, 2)
        mobile.goto(f"{base}/")
        mobile.wait_for_timeout(2000)
        mobile.screenshot(path=out / "mobile.png")

        admin = page(1280, 900, 1.5)
        admin.goto(f"{base}/admin")
        admin.wait_for_timeout(2000)
        admin.screenshot(path=out / "admin.png")
        # Opening a post marks it read, so it goes last.
        post = page(1280, 1500, 1.5)
        post.goto(f"{base}/p/pod-ep42longsig")
        post.wait_for_timeout(2000)
        post.screenshot(path=out / "post.png")

        browser.close()
    print("\n".join(str(path) for path in sorted(out.glob("*.png"))))


if __name__ == "__main__":
    main(*(sys.argv[1:4] if len(sys.argv) > 3 else ("http://127.0.0.1:8097", "demo", "docs/images")))
