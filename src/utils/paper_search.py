"""
paper_search.py — 论文搜索封装
使用 literature-review skill 的搜索引擎 (Semantic Scholar, arXiv, CrossRef)。
中文查询自动翻译为英文以提高学术搜索效果。
"""

import asyncio
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _contains_chinese(text: str) -> bool:
    """Check if text contains Chinese characters."""
    return bool(re.search(r'[\u4e00-\u9fff]', text))


def _translate_query(query: str) -> str:
    """Translate Chinese query to English for academic search APIs.

    Uses a simple keyword extraction approach: keep English/alphanumeric
    tokens as-is, translate common Chinese academic terms.
    """
    if not _contains_chinese(query):
        return query

    # Extract English words/terms that are already in the query
    english_parts = re.findall(r'[a-zA-Z][a-zA-Z0-9\-_.]+', query)

    # Common Chinese→English academic term mapping
    _ZH_EN = {
        "机制": "mechanism", "模型": "model", "算法": "algorithm",
        "神经网络": "neural network", "深度学习": "deep learning",
        "机器学习": "machine learning", "强化学习": "reinforcement learning",
        "大语言模型": "large language model", "大模型": "large model",
        "注意力": "attention", "记忆": "memory", "推理": "reasoning",
        "训练": "training", "微调": "fine-tuning", "预训练": "pre-training",
        "生成": "generation", "检索": "retrieval", "优化": "optimization",
        "蛋白质": "protein", "基因": "gene", "基因组": "genome",
        "折叠": "folding", "测序": "sequencing", "突变": "mutation",
        "细胞": "cell", "药物": "drug", "分子": "molecular",
        "量子": "quantum", "计算": "computing", "安全": "safety",
        "对齐": "alignment", "评估": "evaluation", "基准": "benchmark",
        "知识": "knowledge", "图谱": "graph", "表示": "representation",
        "编码": "encoding", "解码": "decoding", "嵌入": "embedding",
        "架构": "architecture", "框架": "framework", "系统": "system",
        "视觉": "vision", "语言": "language", "多模态": "multimodal",
        "文本": "text", "图像": "image", "语音": "speech",
        "搜索": "search", "检测": "detection", "分类": "classification",
        "分割": "segmentation", "聚类": "clustering", "回归": "regression",
        "自动化": "automation", "智能": "intelligence", "认知": "cognitive",
        "记忆痕迹": "engram", "突触": "synapse", "神经元": "neuron",
        "可塑性": "plasticity", "长期记忆": "long-term memory",
        "工作记忆": "working memory", "遗忘": "forgetting",
        "压缩": "compression", "蒸馏": "distillation", "剪枝": "pruning",
        "稀疏": "sparse", "混合专家": "mixture of experts",
        "思维链": "chain of thought", "上下文学习": "in-context learning",
        "指令": "instruction", "代理": "agent", "工具使用": "tool use",
        # 生物医学 + AI 交叉领域
        "肿瘤": "tumor", "癌症": "cancer", "肠道": "gut intestinal",
        "微生物组": "microbiome", "单细胞": "single-cell",
        "空间转录组": "spatial transcriptomics", "转录组": "transcriptomics",
        "基因表达": "gene expression", "免疫": "immune", "病理": "pathology",
        "组学": "omics", "代谢": "metabolism",
    }

    # Try matching longer terms first
    remaining = query
    translated_parts = []
    for zh, en in sorted(_ZH_EN.items(), key=lambda x: len(x[0]), reverse=True):
        if zh in remaining:
            translated_parts.append(en)
            remaining = remaining.replace(zh, " ")

    # Combine English parts from original + translated terms
    all_parts = english_parts + translated_parts
    if all_parts:
        result = " ".join(all_parts)
        logger.info("Query translated: '%s' -> '%s'", query, result)
        return result

    # Fallback: return original query
    return query

# literature-review skill 路径
_SKILL_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "skills" / "literature-review" / "scripts"

# 平台名称映射 (兼容旧接口)
_PLATFORM_ALIAS = {
    "semantic_scholar": "semantic",
    "semantic": "semantic",
    "arxiv": "arxiv",
    "crossref": "crossref",
    # 旧 paper-search-mcp 平台映射到最接近的源
    "pubmed": "semantic",
    "biorxiv": "semantic",
    "medrxiv": "semantic",
    "google_scholar": "semantic",
    "iacr": "arxiv",
}

AVAILABLE_PLATFORMS = ["arxiv", "semantic_scholar", "crossref"]


def _get_skill_searchers():
    """Lazy-import searchers from literature-review skill."""
    if str(_SKILL_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SKILL_SCRIPTS))

    from paper_search import SemanticScholarSearcher, ArxivSearcher, CrossRefSearcher
    return {
        "semantic": SemanticScholarSearcher,
        "arxiv": ArxivSearcher,
        "crossref": CrossRefSearcher,
    }


def _paper_to_dict(paper) -> Dict:
    """Convert a literature-review Paper object to a flat dict."""
    authors = paper.authors
    if isinstance(authors, list):
        authors = ", ".join(authors)
    return {
        "title":          paper.title or "",
        "authors":        authors or "",
        "abstract":       paper.abstract or "",
        "doi":            paper.doi or "",
        "url":            paper.url or "",
        "pdf_url":        paper.pdf_url or "",
        "published_date": paper.published_date or "",
        "citations":      paper.citations or 0,
        "source":         paper.source or "",
    }


async def _search_one(searcher_cls, platform: str, query: str, max_results: int, year: Optional[str]) -> List[Dict]:
    """Search a single platform (sync searchers run in executor)."""
    loop = asyncio.get_event_loop()
    try:
        searcher = searcher_cls()

        def _do_search():
            kwargs: Dict[str, Any] = {"query": query, "max_results": max_results}
            if year is not None and platform == "semantic":
                kwargs["year"] = str(year)
            return searcher.search(**kwargs)

        results = await loop.run_in_executor(None, _do_search)
        return [_paper_to_dict(p) for p in results]
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

    Uses literature-review skill (Semantic Scholar, arXiv, CrossRef).

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

    # Translate Chinese queries to English for better academic search results
    search_query = _translate_query(query)
    if search_query != query:
        print(f"  \033[2m  查询翻译: {query} → {search_query}\033[0m", flush=True)

    searcher_map = _get_skill_searchers()

    # Deduplicate normalized platform names
    normalized = []
    seen = set()
    for plat in platforms:
        canonical = _PLATFORM_ALIAS.get(plat, plat)
        if canonical not in seen and canonical in searcher_map:
            seen.add(canonical)
            normalized.append(canonical)

    if not normalized:
        logger.warning("No valid platforms after normalization: %s", platforms)
        return []

    year_str = str(year) if year is not None else None
    tasks = [_search_one(searcher_map[plat], plat, search_query, max_results, year_str) for plat in normalized]

    results = await asyncio.gather(*tasks, return_exceptions=True)
    papers = []
    for r in results:
        if isinstance(r, list):
            papers.extend(r)
    return papers
