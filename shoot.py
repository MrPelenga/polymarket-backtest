"""Captures de la page du portfolio (desktop/mobile, clair/sombre) pour vérification."""
import sys
from playwright.sync_api import sync_playwright

BASE = "http://localhost:4173"
pages = sys.argv[1:] or ["/projets/7", "/projets"]
with sync_playwright() as p:
    b = p.chromium.launch()
    for theme in ("light", "dark"):
        for name, vp in (("desktop", {"width": 1440, "height": 900}), ("mobile", {"width": 390, "height": 844})):
            ctx = b.new_context(viewport=vp, device_scale_factor=1)
            ctx.add_init_script(f"localStorage.setItem('theme', '{theme}')")
            pg = ctx.new_page()
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.on("console", lambda m: m.type == "error" and errors.append(m.text))
            for path in pages:
                pg.goto(BASE + path, wait_until="networkidle")
                pg.wait_for_timeout(1500)
                slug = path.strip("/").replace("/", "_") or "home"
                pg.screenshot(path=f"shots/{slug}_{name}_{theme}.png", full_page=True)
                # Clic sur chaque onglet du tableau de bord, s'il y en a
                tabs = pg.locator("[data-pbi-tab]")
                for i in range(tabs.count()):
                    tabs.nth(i).click()
                    pg.wait_for_timeout(700)
                    pg.screenshot(path=f"shots/{slug}_{name}_{theme}_tab{i}.png", full_page=True)
                ow = pg.evaluate("document.documentElement.scrollWidth - window.innerWidth")
                print(f"{path} {name} {theme}: debordement horizontal = {ow}px, erreurs = {errors}")
            ctx.close()
    b.close()
