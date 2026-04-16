"""Web search via Google (scrape top results) and local file search."""
import asyncio
import os
import re
import subprocess
import sys
from typing import List

import requests

from utils.error_handler import ToolExecutionError
from utils.logger import get_logger

logger = get_logger(__name__)

SEARCH_URL = "https://www.google.com/search"
DDG_URL = "https://html.duckduckgo.com/html/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
TIMEOUT = 10


def brief_summary(results: List[dict], max_words: int = 50) -> str:
    """Condense search results into a short spoken summary."""
    if not results:
        return "No results found."

    best = results[0]
    snippet = best.get("snippet", "")
    title = best.get("title", "")

    if snippet:
        words = snippet.split()
        if len(words) > max_words:
            text = " ".join(words[:max_words]) + "..."
        else:
            text = snippet
        return text

    return title or "No clear answer found."


async def web_search(query: str, num_results: int = 3, open_browser: bool = False) -> dict:
    """Search Google and extract the top result snippets."""
    if isinstance(num_results, str):
        try:
            num_results = int(num_results)
        except (ValueError, TypeError):
            num_results = 3
    num_results = max(1, min(int(num_results), 10))
    loop = asyncio.get_event_loop()

    if open_browser:
        try:
            import webbrowser
            url = f"https://www.google.com/search?q={requests.utils.quote(query)}"
            await loop.run_in_executor(None, webbrowser.open, url)
            return {
                "query": query,
                "results": [],
                "summary": f"Opened Google search for '{query}' in browser.",
                "brief": f"Opened search results for {query} in your browser.",
            }
        except Exception as e:
            logger.error(f"Failed to open browser: {e}")

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        raise ToolExecutionError(
            "beautifulsoup4 not installed -- run: pip install beautifulsoup4"
        )

    results = await _try_google(query, num_results, loop, BeautifulSoup)
    source = "google"
    if not results:
        logger.info(f"Google returned 0 results for '{query}', trying DuckDuckGo")
        results = await _try_duckduckgo(query, num_results, loop, BeautifulSoup)
        source = "duckduckgo" if results else source

    summary = "; ".join(
        f"{r['title']}: {r['snippet'][:100]}" for r in results[:3]
    ) or f"No results found for '{query}'"

    brief = brief_summary(results)
    logger.info(f"Web search '{query}': {len(results)} results (source={source})")

    return {
        "query": query,
        "results": results,
        "summary": summary,
        "brief": brief,
        "source": source,
    }


async def _try_google(query: str, num_results: int, loop, BeautifulSoup) -> List[dict]:
    try:
        resp = await loop.run_in_executor(
            None,
            lambda: requests.get(
                SEARCH_URL,
                params={"q": query, "num": num_results, "hl": "en"},
                headers=HEADERS,
                timeout=TIMEOUT,
            ),
        )
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"Google search HTTP failed: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    results: List[dict] = []

    blocks = (
        soup.select("div.g")
        or soup.select("div.tF2Cxc")
        or soup.select("div.MjjYud")
        or soup.select("div[data-hveid]")
    )

    for g in blocks:
        title_el = g.select_one("h3")
        snippet_el = g.select_one(
            "div.VwiC3b, div[data-sncf], span.aCOpRe, div.IsZvec, "
            "div.lyLwlc, div.yDYNvb"
        )
        link_el = g.select_one("a[href]")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
        link = link_el["href"] if link_el else ""
        if title and not any(r["title"] == title for r in results):
            results.append({"title": title, "snippet": snippet, "url": link})
        if len(results) >= num_results:
            break

    if not results:
        featured = soup.select_one("div.IZ6rdc, div.hgKElc, div[data-md], div.kp-blk")
        if featured:
            results.append({
                "title": "Featured snippet",
                "snippet": featured.get_text(" ", strip=True)[:300],
                "url": "",
            })
    return results


async def _try_duckduckgo(query: str, num_results: int, loop, BeautifulSoup) -> List[dict]:
    try:
        resp = await loop.run_in_executor(
            None,
            lambda: requests.post(
                DDG_URL,
                data={"q": query},
                headers=HEADERS,
                timeout=TIMEOUT,
            ),
        )
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"DuckDuckGo search HTTP failed: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    results: List[dict] = []
    for r in soup.select("div.result, div.web-result"):
        title_el = r.select_one("a.result__a, h2 a")
        snippet_el = r.select_one(".result__snippet, .result-snippet")
        if not title_el:
            continue
        title = title_el.get_text(" ", strip=True)
        link = title_el.get("href", "")
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
        if title:
            results.append({"title": title, "snippet": snippet, "url": link})
        if len(results) >= num_results:
            break
    return results


async def local_file_search(query: str, directory: str = "") -> dict:
    """Search for files on the local machine using Windows Search or find."""
    loop = asyncio.get_event_loop()

    def _search():
        if sys.platform == "win32":
            search_dir = directory or os.path.expanduser("~")
            try:
                result = subprocess.run(
                    ["where", "/r", search_dir, f"*{query}*"],
                    capture_output=True, text=True, timeout=15,
                )
                files = [
                    f.strip() for f in result.stdout.strip().split("\n")
                    if f.strip()
                ][:10]
                return files
            except Exception:
                pass

        search_dir = directory or os.path.expanduser("~")
        matches = []
        needle = query.lower()
        try:
            for root, dirs, filenames in os.walk(search_dir):
                for fname in filenames:
                    if needle in fname.lower():
                        matches.append(os.path.join(root, fname))
                        if len(matches) >= 10:
                            return matches
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                if len(matches) >= 10:
                    break
        except PermissionError:
            pass
        return matches

    try:
        files = await loop.run_in_executor(None, _search)
    except Exception as e:
        raise ToolExecutionError(f"Local search failed: {e}") from e

    if files:
        summary = f"Found {len(files)} file(s): " + ", ".join(
            os.path.basename(f) for f in files[:5]
        )
    else:
        summary = f"No files found matching '{query}'"

    logger.info(f"Local search '{query}': {len(files)} results")
    return {
        "query": query,
        "files": files,
        "count": len(files),
        "summary": summary,
    }
