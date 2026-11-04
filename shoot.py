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
                # Vignette du projet : haut du rapport, au format 16:9
                rep = pg.locator("[data-pbi-report]")
                if rep.count() and name == "desktop" and theme == "light":
                    bb = rep.bounding_box()
                    pg.screenshot(path="shots/card.png", full_page=True,
                                  clip={"x": bb["x"], "y": bb["y"], "width": bb["width"], "height": bb["width"] * 9 / 16})
                # Clic sur chaque onglet du tableau de bord, s'il y en a
                tabs = pg.locator("[data-pbi-tab]")
                for i in range(tabs.count()):
                    tabs.nth(i).click()
                    pg.wait_for_timeout(700)
                    pg.screenshot(path=f"shots/{slug}_{name}_{theme}_tab{i}.png", full_page=True)
                ow = pg.evaluate("document.documentElement.scrollWidth - window.innerWidth")
                print(f"{path} {name} {theme}: debordement horizontal = {ow}px, erreurs = {errors}")
            if name == "desktop" and theme == "light":
                pg.goto(BASE + "/projets/7", wait_until="networkidle")
                pg.get_by_role("button", name="EN").first.click()
                pg.wait_for_timeout(800)
                pg.screenshot(path="shots/projets_7_desktop_light_en.png", full_page=True)
            ctx.close()
    b.close()
