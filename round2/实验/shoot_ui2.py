"""Screenshots of the round-2 dispatcher UI (streamlit on :8599), driven with the system Edge.

    (in track2-desk-优化版)  streamlit run app/streamlit_app.py --server.port 8599
    python 实验/shoot_ui2.py     ->  ../04_界面/截图/*.png
"""
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.dont_write_bytecode = True
OUT = Path(__file__).resolve().parent.parent / "04_界面" / "截图"
OUT.mkdir(parents=True, exist_ok=True)
URL = "http://localhost:8599"


def settle(page, secs=2.0):
    time.sleep(secs)
    page.wait_for_load_state("networkidle")


def click_row(page, row, grid_idx=1):
    """The inbox is a canvas grid: hover, then click the row's checkbox (header 38px, rows 35px)."""
    grid = page.locator('[data-testid="stDataFrame"]').nth(grid_idx)
    box = grid.bounding_box()
    x, y = box["x"] + 20, box["y"] + 38 + 35 * row + 17
    page.mouse.move(x - 40, y, steps=5); page.mouse.move(x, y, steps=5)
    time.sleep(0.5)
    page.mouse.down(); time.sleep(0.15); page.mouse.up()
    settle(page)


def top(page):
    page.locator('[data-testid="stMain"]').evaluate("el => { el.scrollTop = 0 }")
    time.sleep(0.6)


def group(page, label):
    page.get_by_text(label, exact=False).first.click()
    settle(page)


with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    page = b.new_context(viewport={"width": 1600, "height": 1300}, device_scale_factor=2).new_page()
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.goto(URL)
    page.get_by_role("button", name="Load morning inbox").wait_for(timeout=40000)
    settle(page)
    page.get_by_role("button", name="Load morning inbox").click()
    settle(page, 4)
    top(page); page.screenshot(path=str(OUT / "1_to_confirm.png"))

    click_row(page, 3); top(page); page.screenshot(path=str(OUT / "2_card_safe.png"))

    page.get_by_role("button", name="in one click", exact=False).click()
    settle(page, 3)
    top(page); page.screenshot(path=str(OUT / "3_after_bulk_confirm.png"))

    group(page, "Needs a decision"); top(page); page.screenshot(path=str(OUT / "4_needs_decision.png"))
    group(page, "Ask requester"); top(page); page.screenshot(path=str(OUT / "5_ask.png"))
    group(page, "Done"); top(page); page.screenshot(path=str(OUT / "6_done.png"))

    page.get_by_role("tab", name="Simulator").click(); settle(page, 6)
    top(page); page.screenshot(path=str(OUT / "7_simulator.png"))
    page.get_by_role("tab", name="Audit log").click(); settle(page, 2)
    top(page); page.screenshot(path=str(OUT / "8_audit.png"))
    exc = page.locator('[data-testid="stException"]').count()
    b.close()
print("saved:", sorted(x.name for x in OUT.glob("*.png")))
print("streamlit exceptions on page:", exc, "| console errors:", len(errors), errors[:3])
