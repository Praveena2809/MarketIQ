"""
News Research Agent: derives focused, bounded news searches from a user query and
normalizes real provider articles into the project's Evidence architecture.

Persistence and reporting follow the same rules as the rest of the research
pipeline: only real article metadata (title, URL, publisher, publication date)
is used. If the provider is unconfigured, unreachable, or quota-limited the
agent returns no fabricated evidence and reports an explicit "news unchecked"
warning that flows into the final synthesis.
"""
from typing import List, Optional, Tuple

from app.core.config import get_settings
from app.services.llm import get_llm_service
from app.services.news.news_provider import get_news_provider
from app.services.research.evidence import Evidence


class NewsResearchAgent:
    def __init__(self):
        self.settings = get_settings()
        self.provider = get_news_provider()

    def gather_news_evidence(self, query: str) -> Tuple[List[Evidence], Optional[str]]:
        """
        Retrieve recent news relevant to a user query.

        Returns:
            - List of normalized Evidence objects (source_type="news"),
              each carrying a real provider URL.
            - Warning string if news is unavailable/unchecked (None if OK).
        """
        api_key = (self.settings.NEWS_API_KEY or "").strip()
        if not api_key:
            return [], (
                "News research is not configured (NEWS_API_KEY missing); "
                "recent news was not checked."
            )

        queries = self._derive_news_queries(query)
        articles = []
        warnings: List[str] = []

        for search_query in queries:
            items, warning = self.provider.fetch_recent(search_query)
            articles.extend(items)
            if warning:
                warnings.append(warning)

        if not articles:
            return [], warnings[0] if warnings else "No recent news articles available."

        # Deduplicate by URL and keep the most recent set, bounded by config.
        seen_urls = set()
        unique: List = []
        for article in articles:
            if article.url in seen_urls:
                continue
            seen_urls.add(article.url)
            unique.append(article)
        articles = unique[: self.settings.NEWS_RESULTS_PER_QUERY]

        evidence: List[Evidence] = []
        for idx, article in enumerate(articles, 1):
            evidence.append(
                Evidence(
                    evidence_id=f"news_{idx}",
                    source_type="news",
                    title=article.title,
                    content=article.description,
                    url=article.url,
                    publisher=article.source_name,
                    published_at=article.published_at.isoformat() if article.published_at else None,
                    relevance_score=round(max(0.5, 1.0 - (idx - 1) * 0.05), 2),
                )
            )

        return evidence, None

    def _derive_news_queries(self, query: str) -> List[str]:
        """
        Derive the bounded list of news searches (<= NEWS_QUERY_LIMIT).

        The primary search is a focused keyword query derived from the user
        question (via the existing LLMService when available, with a
        deterministic cleaned fallback) rather than the full sentence. A
        second broader search is only added when NEWS_QUERY_LIMIT allows.
        """
        cleaned = self._clean_query(query)
        focused = self._llm_derive(cleaned) or cleaned

        queries = [focused]
        limit = max(1, int(self.settings.NEWS_QUERY_LIMIT))
        if limit >= 2 and cleaned and cleaned != focused:
            queries.append(cleaned)
        return queries[:limit]

    def _clean_query(self, query: Optional[str]) -> str:
        """Deterministic fallback: collapse whitespace and bound query length."""
        text = (query or "").strip()
        text = " ".join(text.split())
        max_len = 120
        if len(text) > max_len:
            text = text[:max_len].rsplit(" ", 1)[0]
        return text

    def _llm_derive(self, cleaned: str) -> Optional[str]:
        """
        Derive one focused news search query via the existing LLMService.
        Fails soft: any error or unusable output falls back to the cleaned query.
        """
        llm = get_llm_service()
        if not llm.is_configured():
            return None
        try:
            raw = llm.generate_text(
                prompt=(
                    f'Convert this market research question into ONE concise keyword search query '
                    f'for a news search engine. Reply with the query only - no quotes, no explanation, '
                    f'max 60 characters:\n"{cleaned}"'
                ),
                temperature=0.0,
            )
        except Exception:
            return None

        candidate = " ".join((raw or "").split())
        for prefix in ("News search query:", "Search query:", "Query:"):
            if candidate.lower().startswith(prefix.lower()):
                candidate = candidate[len(prefix):].strip()
        candidate = candidate.strip("\"'").strip()

        if not candidate:
            return None
        if len(candidate) > 200:
            return None
        if candidate.lower() in ("n/a", "none", "not applicable"):
            return None
        return candidate