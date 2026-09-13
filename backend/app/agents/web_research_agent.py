"""
Web Research Agent generating focused sub-queries and gathering web evidence via Gemini Search Grounding.
"""
from typing import List, Tuple, Optional
from app.core.config import get_settings
from app.services.research.web_search import get_web_search_service
from app.services.research.evidence import Evidence


class WebResearchAgent:
    def __init__(self):
        self.settings = get_settings()
        self.web_search_service = get_web_search_service()

    def gather_web_evidence(self, query: str) -> Tuple[List[Evidence], Optional[str]]:
        """
        Gathers web evidence for the primary query.
        Returns:
            - List of normalized Evidence objects
            - Warning string if rate limited or unavailable
        """
        # Execute Google Search grounding for primary query
        evidence_items, queries_used, warning = self.web_search_service.search_web(query)
        return evidence_items, warning if warning else None
