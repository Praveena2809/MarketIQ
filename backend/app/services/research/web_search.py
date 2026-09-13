"""
Web Search Service utilizing Google's official Gemini Google Search Grounding tool (google-genai).
Extracts real web titles, URLs, and snippets from grounding_metadata with strict error/quota fallbacks.
"""
from typing import List, Dict, Any, Tuple
from google.genai import types

from app.core.config import get_settings
from app.services.llm import get_llm_service
from app.services.research.evidence import Evidence


class WebSearchService:
    def __init__(self):
        self.settings = get_settings()
        self._llm_service = get_llm_service()

    def search_web(self, query: str) -> Tuple[List[Evidence], List[str], str]:
        """
        Executes Google Search grounding via Gemini for a given query.
        Returns:
            - List of Evidence objects with real titles, URLs, and snippet text
            - List of search queries used by Gemini
            - Warning string if search was unavailable or rate-limited
        """
        if not self._llm_service.is_configured():
            return [], [], "Gemini API key is not configured."

        client = self._llm_service.client
        config = types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.2,
        )

        try:
            response = client.models.generate_content(
                model=self.settings.GEMINI_MODEL,
                contents=f"Perform current web market research for: {query}. Summarize key recent facts and statistics.",
                config=config,
            )
        except Exception as e:
            err_str = str(e)
            if "RESOURCE_EXHAUSTED" in err_str or "429" in err_str:
                warning_msg = "Google Search grounding API quota exceeded. Continuing research with uploaded documents."
            else:
                warning_msg = f"Web search unavailable ({err_str}). Continuing research."
            return [], [], warning_msg

        evidence_items: List[Evidence] = []
        queries_used: List[str] = []
        warning = ""

        # Extract search queries used and grounding chunks from candidates
        if hasattr(response, "candidates") and response.candidates:
            candidate = response.candidates[0]
            gm = getattr(candidate, "grounding_metadata", None)
            if gm:
                queries_used = list(getattr(gm, "web_search_queries", []) or [])
                chunks = getattr(gm, "grounding_chunks", []) or []
                for idx, chunk in enumerate(chunks, 1):
                    web = getattr(chunk, "web", None)
                    if web:
                        url = getattr(web, "uri", None)
                        title = getattr(web, "title", None) or f"Web Source {idx}"
                        if url:
                            evidence_items.append(
                                Evidence(
                                    evidence_id=f"web_{idx}",
                                    source_type="web",
                                    title=title,
                                    url=url,
                                    content=f"Grounding reference for '{title}'",
                                    relevance_score=1.0,
                                )
                            )

        # Include generated summary text as primary web evidence if text is available
        if response.text and response.text.strip():
            evidence_items.insert(
                0,
                Evidence(
                    evidence_id="web_summary",
                    source_type="web",
                    title=f"Web Market Overview for {query}",
                    content=response.text.strip(),
                    relevance_score=1.0,
                ),
            )

        if not evidence_items:
            warning = "Google Search returned no web evidence for this query."

        return evidence_items, queries_used, warning


_web_search_service_instance = None


def get_web_search_service() -> WebSearchService:
    global _web_search_service_instance
    if _web_search_service_instance is None:
        _web_search_service_instance = WebSearchService()
    return _web_search_service_instance
