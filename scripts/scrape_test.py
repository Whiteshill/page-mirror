import os
import sys

from playwright.sync_api import sync_playwright

url = os.environ.get("GROUP_URL", "").strip()
if not url:
    sys.exit("The GROUP_URL secret is missing or empty.")

with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context(
        viewport={"width": 1280, "height": 1600},
        locale="en-GB",
    )
    page = context.new_page()

    response = page.goto(url, wait_until="domcontentloaded", timeout=60000)
    print("HTTP status:", response.status if response else "no response")
    page.wait_for_timeout(8000)

    print("Redirected to a login page:", "login" in page.url)
    print("Page title:", page.title())

    text = page.inner_text("body")
    print("Visible text length:", len(text))

    lowered = text.lower()
    for phrase in ("log in", "create new account", "you must log in", "see more on facebook"):
        if phrase in lowered:
            print("Login wall wording found:", phrase)

    blocks = page.locator('div[role="article"]')
    count = blocks.count()
    print("Post-like blocks found:", count)

    for i in range(min(count, 10)):
        snippet = " ".join(blocks.nth(i).inner_text().split())[:300]
        print(f"--- Block {i + 1} ---")
        print(snippet)

    page.screenshot(path="page-screenshot.png")
    browser.close()
