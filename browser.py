"""
JARVIS — Web Browsing Module
Playwright-based web browsing with local processing only.

Built from CLAUDE.md by RJ - https://itsbrook.com
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger("jarvis.browser")

_browser = None
_context = None


async def _get_browser():
    """Lazy-initialize Playwright browser."""
    global _browser, _context
    if _browser is None:
        try:
            from playwright.async_api import async_playwright
            pw = await async_playwright().start()
            _browser = await pw.chromium.launch(headless=True)
            _context = await _browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) JARVIS/1.0",
            )
        except Exception as e:
            logger.error(f"Failed to launch browser: {e}")
            raise
    return _context


async def browse_url(url: str) -> dict:
    """Visit a URL and extract page content."""
    context = await _get_browser()
    page = await context.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        title = await page.title()
        content = await page.content()
        # Extract visible text
        text = await page.evaluate("""() => {
            const body = document.body;
            if (body) {
                return body.innerText.substring(0, 10000);
            }
            return '';
        }""")
        return {
            "url": url,
            "title": title,
            "text": text[:5000],  # Limit text size
            "success": True,
        }
    except Exception as e:
        logger.warning(f"Browse error for {url}: {e}")
        return {"url": url, "title": "", "text": "", "success": False, "error": str(e)}
    finally:
        await page.close()


async def search_web(query: str, num_results: int = 5) -> list[dict]:
    """Search the web using DuckDuckGo (no API key needed)."""
    context = await _get_browser()
    page = await context.new_page()
    results = []
    try:
        search_url = f"https://duckduckgo.com/html/?q={query}"
        await page.goto(search_url, wait_until="domcontentloaded", timeout=15000)
        
        # Extract search results
        results = await page.evaluate(f"""() => {{
            const items = [];
            const links = document.querySelectorAll('.result__a');
            const snippets = document.querySelectorAll('.result__snippet');
            for (let i = 0; i < Math.min(links.length, {num_results}); i++) {{
                items.push({{
                    title: links[i]?.innerText || '',
                    url: links[i]?.href || '',
                    snippet: snippets[i]?.innerText || ''
                }});
            }}
            return items;
        }}""")
    except Exception as e:
        logger.warning(f"Search error: {e}")
    finally:
        await page.close()
    return results


async def take_screenshot(url: str, full_page: bool = False) -> Optional[bytes]:
    """Take a screenshot of a URL."""
    context = await _get_browser()
    page = await context.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        screenshot = await page.screenshot(full_page=full_page)
        return screenshot
    except Exception as e:
        logger.warning(f"Screenshot error for {url}: {e}")
        return None
    finally:
        await page.close()


async def extract_text(url: str, selector: str = "body") -> str:
    """Extract text content from a URL."""
    context = await _get_browser()
    page = await context.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        text = await page.evaluate(f"""() => {{
            const el = document.querySelector('{selector}');
            return el ? el.innerText.substring(0, 10000) : '';
        }}""")
        return text or ""
    except Exception as e:
        logger.warning(f"Extract text error for {url}: {e}")
        return ""
    finally:
        await page.close()


async def close_browser():
    """Close the browser instance."""
    global _browser
    if _browser:
        await _browser.close()
        _browser = None