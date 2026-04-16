"""Web automation tools."""
import re
import urllib.parse
import webbrowser

from utils.error_handler import ToolExecutionError
from utils.logger import get_logger

logger = get_logger(__name__)

_YOUTUBE_FILLER = re.compile(
    r"\b(play|put on|find|search|something|anything|stuff|videos?|on youtube|for me|please)\b",
    re.IGNORECASE,
)


def _clean_youtube_query(query: str) -> str:
    """Extract meaningful search terms; fall back to 'trending' if empty."""
    cleaned = _YOUTUBE_FILLER.sub("", query).strip()
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    if not cleaned or len(cleaned) < 2:
        logger.info(f"YouTube query '{query}' has no specific terms, defaulting to trending")
        return "trending"
    return cleaned


async def search_youtube(query: str, autoplay: bool = True) -> dict:
    """Open a YouTube search (or first result) in the default browser."""
    clean_query = _clean_youtube_query(query or "")
    logger.info(f"YouTube search: raw='{query}' clean='{clean_query}'")

    encoded = urllib.parse.quote_plus(clean_query)
    url = f"https://www.youtube.com/results?search_query={encoded}"

    webbrowser.open(url)
    return {"query": clean_query, "url": url, "autoplay": autoplay}


async def open_url(url: str) -> dict:
    """Open an arbitrary URL in the default browser."""
    if not url:
        raise ToolExecutionError("URL is empty")
    webbrowser.open(url)
    return {"url": url, "opened": True}


async def web_search(query: str, engine: str = "google") -> dict:
    """Search the web with the chosen engine."""
    encoded = urllib.parse.quote_plus(query)
    engines = {
        "google": f"https://www.google.com/search?q={encoded}",
        "duckduckgo": f"https://duckduckgo.com/?q={encoded}",
        "bing": f"https://www.bing.com/search?q={encoded}",
    }
    url = engines.get(engine, engines["google"])
    webbrowser.open(url)
    return {"query": query, "engine": engine, "url": url}
