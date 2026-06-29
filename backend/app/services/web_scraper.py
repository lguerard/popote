import re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup


async def scrape_url(url: str) -> tuple[str, str | None]:
    """Returns (page_text, thumbnail_url)."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        html = await page.content()
        await browser.close()

    soup = BeautifulSoup(html, "html.parser")

    # Extract thumbnail from og:image
    thumbnail = None
    og_image = soup.find("meta", property="og:image")
    if og_image:
        thumbnail = og_image.get("content")

    # Remove noise
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe", "noscript"]):
        tag.decompose()

    # Prefer article/main content
    content_el = soup.find("article") or soup.find("main") or soup.body
    text = content_el.get_text(separator="\n", strip=True) if content_el else ""

    # Collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text[:15000], thumbnail
