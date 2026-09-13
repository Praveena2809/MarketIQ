"""
News research service: retrieves recent news from a configured news provider
(NewsAPI by default) and normalizes provider articles into evidence-safe records.

Provenance rules:
- Only the provider's JSON API is used. No scraping, no headless browsers,
  no page fetching.
- Only real provider metadata (title, url, publisher, publishedAt) is surfaced.
  Nothing is invented, summarized, or rewritten by an LLM.
- Articles without a URL are dropped - a news item without a real URL can
  never become evidence.
"""
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import urllib.error
import urllib.parse
import urllib.request

from app.core.config import get_settings

USER_AGENT = "MarketIQ/1.0 (AI market research assistant)"


@dataclass
class NewsArticle:
    """A single real article returned by the news provider."""

    title: str
    url: str
    source_name: str
    description: str
    published_at: Optional[datetime] = None
    content: Optional[str] = None


def _parse_published_at(raw: Optional[str]) -> Optional[datetime]:
    """Parse a provider ISO-8601 timestamp into a timezone-aware datetime.

    Malformed or missing dates become None; we never guess a date.
    """
    if not raw:
        return None
    try:
        value = raw
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


class NewsAPIProvider:
    """
    Minimal NewsAPI (newsapi.org/v2/everything) client using the standard
    library only - no extra dependencies, no scraping.
    """

    name = "newsapi"

    def __init__(self):
        self.settings = get_settings()

    def fetch_recent(self, query: str) -> Tuple[List[NewsArticle], str]:
        """
        Fetch recent, article-sorted news for a focused query.

        Returns:
            - List of NewsArticle objects (real, URL-bearing items only)
            - Warning string describing any unavailability (empty means OK)
        """
        api_key = (self.settings.NEWS_API_KEY or "").strip()
        if not api_key:
            return [], (
                "News research is not configured (NEWS_API_KEY missing); "
                "recent news was not checked."
            )
        if not query or not query.strip():
            return [], "No news query could be derived from the research question."

        params = {
            "q": query,
            "apiKey": api_key,
            "language": self.settings.NEWS_LANGUAGE,
            "sortBy": "publishedAt",
            "pageSize": str(self.settings.NEWS_RESULTS_PER_QUERY),
            "from": self._recent_from_date(),
        }

        try:
            payload = self._get_json(params)
        except Exception as e:
            return [], f"News research unavailable: {self._sanitize(str(e))}"

        articles = self._parse_articles(payload)
        if not articles:
            return [], "No recent news articles found for this query."

        return articles, ""

    def _recent_from_date(self) -> str:
        """Recency cutoff as YYYY-MM-DD (configurable via NEWS_RECENCY_DAYS)."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.settings.NEWS_RECENCY_DAYS)
        return cutoff.strftime("%Y-%m-%d")

    def _get_json(self, params: Dict[str, str]) -> Dict[str, Any]:
        """GET the provider endpoint and return parsed JSON. Raises ValueError on failure."""
        base = (self.settings.NEWS_BASE_URL or "https://newsapi.org/v2/everything").rstrip("/")
        url = f"{base}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=self.settings.NEWS_REQUEST_TIMEOUT) as response:
                raw = response.read().decode("utf-8", "replace")
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")[:500]
            except Exception:
                pass
            detail = self._provider_error_detail(body) or f"HTTP {e.code}"
            raise ValueError(f"News provider returned HTTP {e.code}: {self._sanitize(detail)}") from e
        except urllib.error.URLError as e:
            reason = getattr(e, "reason", None) or e
            raise ValueError(f"News provider request failed ({self._sanitize(str(reason))})") from e
        except json.JSONDecodeError as e:
            raise ValueError("News provider returned an unreadable response.") from e
        except Exception as e:
            raise ValueError(f"News provider request failed: {self._sanitize(str(e))}") from e

    def _parse_articles(self, payload: Any) -> List[NewsArticle]:
        """Extract real, URL-bearing articles. Never fabricates fields."""
        if not isinstance(payload, dict):
            return []
        if payload.get("status") != "ok":
            return []

        articles: List[NewsArticle] = []
        for raw in payload.get("articles") or []:
            if not isinstance(raw, dict):
                continue
            url = raw.get("url")
            title = raw.get("title")
            # A news item without a real URL (or title) is not evidence.
            if not url or not title:
                continue

            source = raw.get("source") or {}
            source_name = ""
            if isinstance(source, dict) and source.get("name"):
                source_name = str(source["name"]).strip()

            articles.append(
                NewsArticle(
                    title=str(title).strip(),
                    url=str(url),
                    source_name=source_name,
                    description=str(raw.get("description") or "").strip(),
                    published_at=_parse_published_at(raw.get("publishedAt")),
                    content=str(raw.get("content") or "").strip() or None,
                )
            )
        return articles

    def _provider_error_detail(self, body: str) -> Optional[str]:
        """Extract a human-readable message from a provider error body."""
        if not body:
            return None
        try:
            data = json.loads(body)
            if isinstance(data, dict) and data.get("message"):
                return str(data["message"]).strip()
        except Exception:
            pass
        cleaned = body.strip()
        return cleaned or None

    def _sanitize(self, text: str) -> str:
        """Redact the API key from any surfaced message."""
        key = self.settings.NEWS_API_KEY
        if key and text:
            return text.replace(key, "[REDACTED]")
        return text or ""


_news_provider_instance: Optional[NewsAPIProvider] = None


def get_news_provider() -> NewsAPIProvider:
    """Singleton getter for the configured news provider."""
    global _news_provider_instance
    if _news_provider_instance is None:
        name = (get_settings().NEWS_PROVIDER or "newsapi").lower()
        if name == "newsapi":
            _news_provider_instance = NewsAPIProvider()
        else:
            _news_provider_instance = NewsAPIProvider()
    return _news_provider_instance