"""
paper_search.py — 论文搜索封装
直接调用 paper-search-mcp 的 searcher，不依赖 PaperTalker 后端。
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 平台 → Searcher 类映射
_PLATFORM_MAP = {
    "arxiv":            "paper_search_mcp.academic_platforms.arxiv.ArxivSearcher",
    "pubmed":           "paper_search_mcp.academic_platforms.pubmed.PubMedSearcher",
    "biorxiv":          "paper_search_mcp.academic_platforms.biorxiv.BioRxivSearcher",
    "medrxiv":          "paper_search_mcp.academic_platforms.medrxiv.MedRxivSearcher",
    "google_scholar":   "paper_search_mcp.academic_platforms.google_scholar.GoogleScholarSearcher",
    "iacr":             "paper_search_mcp.academic_platforms.iacr.IACRSearcher",
    "semantic_scholar": "paper_search_mcp.academic_platforms.semantic.SemanticSearcher",
    "crossref":         "paper_search_mcp.academic_platforms.crossref.CrossRefSearcher",
}

AVAILABLE_PLATFORMS = list(_PLATFORM_MAP.keys())


def _import_searcher(platform: str):
    """Lazy-import a searcher class by platform name."""
    path = _PLATFORM_MAP.get(platform)
    if not path:
        raise ValueError(f"Unknown platform: {platform}")
    module_path, cls_name = path.rsplit(".", 1)
    import importlib
    mod = importlib.import_module(module_path)
    return getattr(mod, cls_name)()


async def _search_one(searcher, platform: str, query: str, max_results: int, year: Optional[int]) -> List[Dict]:
    """Search a single platform (sync searchers run in executor)."""
    loop = asyncio.get_event_loop()
    try:
        kwargs: Dict[str, Any] = {"query": query, "max_results": max_results}
        if year is not None:
            kwargs["year"] = year
        results = await loop.run_in_executor(None, lambda: searcher.search(**kwargs))
        papers = []
        for p in results:
            papers.append({
                "title":          getattr(p, "title", ""),
                "authors":        ", ".join(getattr(p, "authors", [])) if isinstance(getattr(p, "authors", []), list) else str(getattr(p, "authors", "")),
                "abstract":       getattr(p, "abstract", ""),
                "doi":            getattr(p, "doi", ""),
                "url":            getattr(p, "url", ""),
                "pdf_url":        getattr(p, "pdf_url", "") or getattr(p, "pdfUrl", ""),
                "published_date": str(getattr(p, "published_date", "")),
                "citations":      getattr(p, "citation_count", 0) or getattr(p, "citations", 0) or 0,
                "source":         platform,
            })
        return papers
    except Exception as e:
        logger.warning("Search on %s failed: %s", platform, e)
        return []


async def search_papers(
    query: str,
    platforms: List[str] | None = None,
    max_results: int = 10,
    year: Optional[int] = None,
) -> List[Dict]:
    """
    Search papers across multiple platforms concurrently.

    Args:
        query: Search query
        platforms: List of platform IDs (default: arxiv + semantic_scholar)
        max_results: Max results per platform
        year: Filter by year (optional)

    Returns:
        List of paper dicts with title, authors, url, pdf_url, doi, etc.
    """
    if platforms is None:
        platforms = ["arxiv", "semantic_scholar"]

    tasks = []
    for plat in platforms:
        try:
            searcher = _import_searcher(plat)
            tasks.append(_search_one(searcher, plat, query, max_results, year))
        except Exception as e:
            logger.warning("Cannot init searcher for %s: %s", plat, e)

    if not tasks:
        return []

    results = await asyncio.gather(*tasks, return_exceptions=True)
    papers = []
    for r in results:
        if isinstance(r, list):
            papers.extend(r)
    return papers
