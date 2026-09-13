"""
Competitor Research Agent.

Identifies competitors using ONLY the already-gathered research evidence pool
(the web/news/document evidence collected by ResearchAgent) and, only where
necessary and strictly bounded, gathers additional focused per-competitor
evidence by reusing the existing WebResearchAgent (off by default),
NewsResearchAgent, and DocumentResearchAgent.

This agent NEVER re-runs the query-level web/news/document research passes.
Competitor names must pass evidence-containment (they appear verbatim in the
existing evidence), bounded by MAX_COMPETITORS (default 5). Every returned
evidence item is re-tagged with a competitor-scoped evidence id
(comp_<slug>_<type>_N) so per-competitor citations in the final synthesis are
unambiguous. All provenance rules of the rest of the pipeline are preserved:
real URLs/publishers/dates only; URL-less web/news items are skipped by
SourceTracker; and no names, shares, or figures are ever fabricated.
"""
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.core.config import get_settings
from app.agents.web_research_agent import WebResearchAgent
from app.agents.news_research_agent import NewsResearchAgent
from app.agents.document_research_agent import DocumentResearchAgent
from app.services.research.competitor_identification import CompetitorIdentificationService
from app.services.research.evidence import Evidence

_MAX_COMPETITOR_QUERY_CHARS = 160


@dataclass
class CompetitorResearchResult:
    """Outcome of the competitor research pass.

    - identified: competitor names that survived evidence-containment.
    - contexts:   mapping competitor name -> competitor-scoped evidence.
    - evidence:   flattened competitor-scoped evidence (re-tagged + URL-deduped).
    - warning:    honest degradation note (None when all good).
    """

    identified: List[str] = field(default_factory=list)
    contexts: Dict[str, List[Evidence]] = field(default_factory=dict)
    evidence: List[Evidence] = field(default_factory=list)
    warning: Optional[str] = None


def _slugify(name: str) -> str:
    """ASCII-safe slug used to scope competitor evidence ids."""
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()
    return slug[:40] or "competitor"


class CompetitorResearchAgent:
    def __init__(self):
        self.settings = get_settings()
        self.identifier = CompetitorIdentificationService()
        self.web_agent = WebResearchAgent()
        self.news_agent = NewsResearchAgent()
        self.doc_agent = DocumentResearchAgent()

    def execute_competitor_research(
        self,
        query: str,
        existing_evidence: List[Evidence],
        document_ids: Optional[List[str]] = None,
    ) -> CompetitorResearchResult:
        """
        Phase 1: identify competitors from the existing evidence pool only.
        Phase 2: bounded, focused per-competitor gathering (only where
                configured/available; web grounding off by default).
        """
        names, ident_warning = self.identifier.identify(query, existing_evidence)
        names = names[: max(0, int(self.settings.MAX_COMPETITORS))]

        if not names:
            return CompetitorResearchResult(
                identified=[],
                contexts={},
                evidence=[],
                warning=ident_warning or "No competitors could be identified.",
            )

        warnings: List[str] = []
        if ident_warning:
            warnings.append(ident_warning)

        contexts: Dict[str, List[Evidence]] = {}
        all_evidence: List[Evidence] = []
        seen_urls = set()

        for name in names:
            focused = self._gather_focused_evidence(query, name, existing_evidence, document_ids)
            scoped = self._tag_evidence(name, focused, seen_urls)
            contexts[name] = scoped
            all_evidence.extend(scoped)

        if not all_evidence:
            warnings.append(
                "No additional competitor-specific evidence could be gathered; "
                "competitor findings will rely on the original research evidence."
            )

        merged_warning = " | ".join(w.strip() for w in warnings if w and w.strip())
        return CompetitorResearchResult(
            identified=names,
            contexts=contexts,
            evidence=all_evidence,
            warning=merged_warning or None,
        )

    @staticmethod
    def _covered_by_web_or_news(name: str, existing_evidence: List[Evidence]) -> bool:
        """True when the competitor already has web/news coverage in the pool."""
        key = name.lower()
        for e in existing_evidence:
            if e.source_type in ("web", "news") and key in f"{e.title} {e.content}".lower():
                return True
        return False

    @staticmethod
    def _focused_query(query: str, name: str) -> str:
        """Bounds a focused per-competitor query to a sane length."""
        cleaned = " ".join((query or "").split())
        if len(cleaned) > _MAX_COMPETITOR_QUERY_CHARS:
            cleaned = cleaned[:_MAX_COMPETITOR_QUERY_CHARS].rsplit(" ", 1)[0]
        return f"{name} - context: {cleaned}"

    def _gather_focused_evidence(
        self,
        query: str,
        name: str,
        existing_evidence: List[Evidence],
        document_ids: Optional[List[str]],
    ) -> List[Evidence]:
        """
        Focused per-competitor gathering with the minimal-call policy:
        - Web search grounding is quota-scarce: skipped unless explicitly
          enabled AND the competitor already lacks web/news coverage.
        - News only when the news provider is configured (it is internally
          bounded by NEWS_QUERY_LIMIT / NEWS_RESULTS_PER_QUERY).
        - Document RAG only when the user attached documents.
        """
        focused: List[Evidence] = []

        if self.settings.COMPETITOR_FOCUSED_WEB_SEARCH and not self._covered_by_web_or_news(name, existing_evidence):
            items, _ = self.web_agent.gather_web_evidence(self._focused_query(query, name))
            focused.extend(items)

        if (self.settings.NEWS_API_KEY or "").strip():
            items, _ = self.news_agent.gather_news_evidence(name)
            focused.extend(items)

        if document_ids:
            focused.extend(
                self.doc_agent.gather_document_evidence(
                    self._focused_query(query, name),
                    document_ids=document_ids,
                )
            )

        return focused

    @staticmethod
    def _tag_evidence(
        name: str,
        evidence_list: List[Evidence],
        seen_urls: set,
    ) -> List[Evidence]:
        """
        Re-tags evidence with competitor-scoped ids (comp_<slug>_<type>_N) and
        deduplicates by URL against the already-collected global set, so the
        same URL is never attached to two competitors.
        """
        slug = _slugify(name)
        per_type = {"web": 0, "news": 0, "document": 0}
        tagged: List[Evidence] = []

        for item in evidence_list:
            etype = item.source_type if item.source_type in per_type else "web"
            if item.url:
                if item.url in seen_urls:
                    continue
                seen_urls.add(item.url)
            per_type[etype] += 1
            tagged.append(
                Evidence(
                    **{**item.__dict__, "evidence_id": f"comp_{slug}_{etype}_{per_type[etype]}"}
                )
            )
        return tagged