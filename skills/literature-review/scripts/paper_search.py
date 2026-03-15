#!/usr/bin/env python3
"""
Paper Search Script for Literature Review Skill
Integrates multiple academic databases (Semantic Scholar, arXiv, PubMed, etc.)
Based on paper-search-mcp functionality
"""

import sys
import os
import json
import time
import random
import re
import requests
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, field, asdict
from pathlib import Path

# Load .env file if exists
def load_env():
    """Load environment variables from .env file"""
    env_paths = [
        Path(__file__).parent.parent / ".env",  # skill directory
        Path(__file__).parent / ".env",  # scripts directory
        Path.cwd() / ".env",  # current working directory
    ]
    for env_path in env_paths:
        if env_path.exists():
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip()
                        if key and value and key not in os.environ:
                            os.environ[key] = value

load_env()

# Try to import PyPDF2 for PDF reading
try:
    from PyPDF2 import PdfReader
    HAS_PYPDF2 = True
except ImportError:
    HAS_PYPDF2 = False


@dataclass
class Paper:
    """Standardized paper format with core fields for academic sources"""
    paper_id: str
    title: str
    authors: List[str]
    abstract: str
    doi: str
    published_date: Optional[str] = None
    pdf_url: str = ""
    url: str = ""
    source: str = ""
    updated_date: Optional[str] = None
    categories: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    citations: int = 0
    references: List[str] = field(default_factory=list)
    extra: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert paper to dictionary format"""
        return {
            'paper_id': self.paper_id,
            'title': self.title,
            'authors': '; '.join(self.authors) if self.authors else '',
            'abstract': self.abstract,
            'doi': self.doi,
            'published_date': self.published_date or '',
            'pdf_url': self.pdf_url,
            'url': self.url,
            'source': self.source,
            'updated_date': self.updated_date or '',
            'categories': '; '.join(self.categories) if self.categories else '',
            'keywords': '; '.join(self.keywords) if self.keywords else '',
            'citations': self.citations,
            'references': '; '.join(self.references) if self.references else '',
            'extra': str(self.extra) if self.extra else ''
        }


class SemanticScholarSearcher:
    """Semantic Scholar paper search implementation"""

    BASE_URL = "https://api.semanticscholar.org/graph/v1"

    def __init__(self, api_key: str = None):
        # Try multiple sources for API key
        if api_key:
            self.api_key = api_key
        else:
            self.api_key = (
                os.getenv("SEMANTIC_SCHOLAR_API_KEY") or
                os.getenv("SS_API_KEY") or
                ""
            )
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": random.choice([
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            ])
        })

    def _parse_date(self, date_str: str) -> Optional[str]:
        """Parse date from Semantic Scholar format"""
        try:
            return datetime.strptime(date_str.strip(), "%Y-%m-%d").strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            return None

    def _extract_pdf_url(self, item: Dict) -> str:
        """Extract PDF URL from Semantic Scholar response"""
        pdf_url = ""
        if item.get('openAccessPdf'):
            open_access = item['openAccessPdf']
            if open_access.get('url'):
                pdf_url = open_access['url']
            elif open_access.get('disclaimer'):
                # Extract URL from disclaimer
                urls = re.findall(r'https?://[^\s,)]+', open_access['disclaimer'])
                for url in urls:
                    if 'unpaywall.org' not in url:
                        if 'arxiv.org/abs/' in url:
                            pdf_url = url.replace('/abs/', '/pdf/')
                        else:
                            pdf_url = url
                        break
        return pdf_url

    def search(self, query: str, year: str = None, max_results: int = 10) -> List[Paper]:
        """
        Search Semantic Scholar

        Args:
            query: Search query string
            year: Optional year filter (e.g., '2019', '2016-2020', '2010-', '-2015')
            max_results: Maximum number of results
        """
        papers = []

        try:
            fields = ["title", "abstract", "year", "citationCount", "authors",
                      "url", "publicationDate", "externalIds", "fieldsOfStudy", "openAccessPdf"]

            params = {
                "query": query,
                "limit": max_results,
                "fields": ",".join(fields),
            }
            if year:
                params["year"] = year

            headers = {"x-api-key": self.api_key} if self.api_key else {}
            response = self.session.get(f"{self.BASE_URL}/paper/search",
                                        params=params, headers=headers, timeout=30)

            if response.status_code == 429:
                print("[WARN] Rate limited by Semantic Scholar API")
                return papers

            response.raise_for_status()
            data = response.json()
            results = data.get('data', [])

            for item in results:
                authors = [a.get('name', '') for a in item.get('authors', [])]

                # Get DOI
                doi = ""
                if item.get('externalIds') and item['externalIds'].get('DOI'):
                    doi = item['externalIds']['DOI']

                paper = Paper(
                    paper_id=item.get('paperId', ''),
                    title=item.get('title', ''),
                    authors=authors,
                    abstract=item.get('abstract', ''),
                    doi=doi,
                    published_date=self._parse_date(item.get('publicationDate', '')),
                    pdf_url=self._extract_pdf_url(item),
                    url=item.get('url', ''),
                    source="semantic_scholar",
                    categories=item.get('fieldsOfStudy', []) or [],
                    citations=item.get('citationCount', 0),
                )
                papers.append(paper)

        except Exception as e:
            print(f"[ERROR] Semantic Scholar search: {e}")

        return papers[:max_results]

    def get_paper(self, paper_id: str) -> Optional[Paper]:
        """Get paper details by ID"""
        try:
            fields = ["title", "abstract", "year", "citationCount", "authors",
                      "url", "publicationDate", "externalIds", "fieldsOfStudy", "openAccessPdf"]
            params = {"fields": ",".join(fields)}
            headers = {"x-api-key": self.api_key} if self.api_key else {}

            response = self.session.get(f"{self.BASE_URL}/paper/{paper_id}",
                                        params=params, headers=headers, timeout=30)

            if response.status_code != 200:
                return None

            item = response.json()
            authors = [a.get('name', '') for a in item.get('authors', [])]
            doi = item.get('externalIds', {}).get('DOI', '') if item.get('externalIds') else ''

            return Paper(
                paper_id=item.get('paperId', ''),
                title=item.get('title', ''),
                authors=authors,
                abstract=item.get('abstract', ''),
                doi=doi,
                published_date=self._parse_date(item.get('publicationDate', '')),
                pdf_url=self._extract_pdf_url(item),
                url=item.get('url', ''),
                source="semantic_scholar",
                categories=item.get('fieldsOfStudy', []) or [],
                citations=item.get('citationCount', 0),
            )
        except Exception as e:
            print(f"[ERROR] Get paper details: {e}")
            return None


class ArxivSearcher:
    """arXiv paper search implementation"""

    BASE_URL = "http://export.arxiv.org/api/query"

    def search(self, query: str, max_results: int = 10) -> List[Paper]:
        """Search arXiv"""
        papers = []

        try:
            import feedparser

            params = {
                'search_query': query,
                'max_results': max_results,
                'sortBy': 'relevance',
                'sortOrder': 'descending'
            }
            response = requests.get(self.BASE_URL, params=params, timeout=30)
            feed = feedparser.parse(response.content)

            for entry in feed.entries:
                authors = [a.name for a in entry.authors]
                pdf_url = next((l.href for l in entry.links if l.type == 'application/pdf'), '')

                paper = Paper(
                    paper_id=entry.id.split('/')[-1],
                    title=entry.title,
                    authors=authors,
                    abstract=entry.summary,
                    doi=entry.get('doi', ''),
                    published_date=entry.get('published', ''),
                    pdf_url=pdf_url,
                    url=entry.id,
                    source='arxiv',
                    categories=[t.term for t in entry.tags] if hasattr(entry, 'tags') else [],
                )
                papers.append(paper)

        except ImportError:
            print("[WARN] feedparser not installed, skipping arXiv search")
        except Exception as e:
            print(f"[ERROR] arXiv search: {e}")

        return papers


class CrossRefSearcher:
    """CrossRef paper search implementation"""

    BASE_URL = "https://api.crossref.org"

    def search(self, query: str, max_results: int = 10) -> List[Paper]:
        """Search CrossRef"""
        papers = []

        try:
            params = {
                'query': query,
                'rows': min(max_results, 100),
                'sort': 'relevance',
                'order': 'desc'
            }

            response = requests.get(f"{self.BASE_URL}/works", params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            for item in data.get('message', {}).get('items', []):
                # Extract authors
                authors = []
                for author in item.get('author', []):
                    given = author.get('given', '')
                    family = author.get('family', '')
                    if given and family:
                        authors.append(f"{given} {family}")
                    elif family:
                        authors.append(family)

                # Extract date
                date_parts = item.get('published', {}).get('date-parts', [[]])
                pub_date = ''
                if date_parts and date_parts[0]:
                    parts = date_parts[0]
                    if len(parts) >= 3:
                        pub_date = f"{parts[0]}-{parts[1]:02d}-{parts[2]:02d}"
                    elif len(parts) >= 1:
                        pub_date = str(parts[0])

                # Extract PDF URL
                pdf_url = ''
                for link in item.get('link', []):
                    if link.get('content-type', '').lower() == 'application/pdf':
                        pdf_url = link.get('URL', '')
                        break

                paper = Paper(
                    paper_id=item.get('DOI', ''),
                    title=item.get('title', [''])[0] if item.get('title') else '',
                    authors=authors,
                    abstract=item.get('abstract', ''),
                    doi=item.get('DOI', ''),
                    published_date=pub_date,
                    pdf_url=pdf_url,
                    url=item.get('URL', f"https://doi.org/{item.get('DOI', '')}"),
                    source='crossref',
                    citations=item.get('is-referenced-by-count', 0),
                    extra={
                        'publisher': item.get('publisher', ''),
                        'journal': item.get('container-title', [''])[0] if item.get('container-title') else '',
                    }
                )
                papers.append(paper)

        except Exception as e:
            print(f"[ERROR] CrossRef search: {e}")

        return papers


def search_all(query: str, sources: List[str] = None, max_results: int = 10,
               year: str = None) -> List[Paper]:
    """
    Search all available sources

    Args:
        query: Search query
        sources: List of sources to search (default: all)
        max_results: Max results per source
        year: Year filter (for Semantic Scholar)
    """
    if sources is None:
        sources = ['semantic', 'arxiv', 'crossref']

    all_papers = []

    if 'semantic' in sources:
        print("[INFO] Searching Semantic Scholar...")
        searcher = SemanticScholarSearcher()
        papers = searcher.search(query, year=year, max_results=max_results)
        all_papers.extend(papers)
        print(f"  Found {len(papers)} papers")

    if 'arxiv' in sources:
        print("[INFO] Searching arXiv...")
        searcher = ArxivSearcher()
        papers = searcher.search(query, max_results=max_results)
        all_papers.extend(papers)
        print(f"  Found {len(papers)} papers")

    if 'crossref' in sources:
        print("[INFO] Searching CrossRef...")
        searcher = CrossRefSearcher()
        papers = searcher.search(query, max_results=max_results)
        all_papers.extend(papers)
        print(f"  Found {len(papers)} papers")

    return all_papers


def format_results_markdown(papers: List[Paper], query: str, abstract_limit: int = 0) -> str:
    """Format results as Markdown

    Args:
        papers: List of Paper objects
        query: Search query string
        abstract_limit: Maximum characters for abstract (0 = no limit, default)
    """
    md = f"# Search Results: {query}\n\n"
    md += f"**Search Date**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
    md += f"**Total Results**: {len(papers)}\n\n"
    md += "---\n\n"

    for i, paper in enumerate(papers, 1):
        # Clean title of problematic characters
        title = paper.title.encode('ascii', 'replace').decode('ascii') if paper.title else ''
        authors = '; '.join(paper.authors[:5]) if paper.authors else ''
        authors = authors.encode('ascii', 'replace').decode('ascii')

        # Abstract handling - no truncation by default (abstract_limit=0)
        if paper.abstract:
            if abstract_limit > 0 and len(paper.abstract) > abstract_limit:
                abstract = paper.abstract[:abstract_limit] + "..."
            else:
                abstract = paper.abstract
        else:
            abstract = ''
        abstract = abstract.encode('ascii', 'replace').decode('ascii') if abstract else ''

        md += f"## {i}. {title}\n\n"
        md += f"**Authors**: {authors}{'...' if len(paper.authors) > 5 else ''}\n\n"
        md += f"**Source**: {paper.source}\n\n"
        md += f"**Published**: {paper.published_date or 'N/A'}\n\n"

        if paper.doi:
            md += f"**DOI**: [{paper.doi}](https://doi.org/{paper.doi})\n\n"

        if paper.pdf_url:
            md += f"**PDF**: [Download]({paper.pdf_url})\n\n"

        if paper.url:
            md += f"**URL**: [Link]({paper.url})\n\n"

        if paper.citations:
            md += f"**Citations**: {paper.citations}\n\n"

        if abstract:
            md += f"**Abstract**:\n\n{abstract}\n\n"

        md += "---\n\n"

    return md


def format_results_json(papers: List[Paper]) -> str:
    """Format results as JSON"""
    return json.dumps([p.to_dict() for p in papers], indent=2, ensure_ascii=False)


def deduplicate(papers: List[Paper]) -> List[Paper]:
    """Remove duplicate papers by DOI or title"""
    seen_dois = set()
    seen_titles = set()
    unique = []

    for paper in papers:
        doi = paper.doi.lower().strip() if paper.doi else ''
        title = paper.title.lower().strip() if paper.title else ''

        if doi and doi in seen_dois:
            continue
        if not doi and title and title in seen_titles:
            continue

        if doi:
            seen_dois.add(doi)
        if title:
            seen_titles.add(title)
        unique.append(paper)

    return unique


def main():
    """Command-line interface"""
    if len(sys.argv) < 2:
        print("Usage: python paper_search.py <query> [options]")
        print("\nOptions:")
        print("  --sources LIST      Comma-separated sources (semantic,arxiv,crossref)")
        print("  --max N             Max results per source (default: 10)")
        print("  --year YEAR         Year filter for Semantic Scholar")
        print("  --format FORMAT     Output format (markdown, json)")
        print("  --output FILE       Output file")
        print("  --dedupe            Remove duplicates")
        print("  --pdf-only          Only show papers with PDF links")
        print("  --abstract-limit N  Truncate abstracts to N characters (0=no limit, default: 0)")
        print("  --full              Show full abstracts (same as --abstract-limit 0)")
        sys.exit(1)

    # Parse arguments
    query = sys.argv[1]
    sources = ['semantic', 'arxiv', 'crossref']
    max_results = 10
    year = None
    output_format = 'markdown'
    output_file = None
    dedupe = False
    pdf_only = False
    abstract_limit = 0  # No limit by default

    i = 2
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == '--sources' and i + 1 < len(sys.argv):
            sources = sys.argv[i + 1].split(',')
            i += 2
        elif arg == '--max' and i + 1 < len(sys.argv):
            max_results = int(sys.argv[i + 1])
            i += 2
        elif arg == '--year' and i + 1 < len(sys.argv):
            year = sys.argv[i + 1]
            i += 2
        elif arg == '--format' and i + 1 < len(sys.argv):
            output_format = sys.argv[i + 1]
            i += 2
        elif arg == '--output' and i + 1 < len(sys.argv):
            output_file = sys.argv[i + 1]
            i += 2
        elif arg == '--dedupe':
            dedupe = True
            i += 1
        elif arg == '--pdf-only':
            pdf_only = True
            i += 1
        elif arg == '--abstract-limit' and i + 1 < len(sys.argv):
            abstract_limit = int(sys.argv[i + 1])
            i += 2
        elif arg == '--full':
            abstract_limit = 0
            i += 1
        else:
            i += 1

    # Search
    print(f"\n{'='*60}")
    print(f"Searching for: {query}")
    print(f"Sources: {', '.join(sources)}")
    print(f"{'='*60}\n")

    papers = search_all(query, sources, max_results, year)

    # Filter PDF only
    if pdf_only:
        papers = [p for p in papers if p.pdf_url]
        print(f"\nFiltered to {len(papers)} papers with PDF links")

    # Deduplicate
    if dedupe:
        original_count = len(papers)
        papers = deduplicate(papers)
        print(f"\nDeduplicated: {original_count} -> {len(papers)} papers")

    # Format output
    if output_format == 'json':
        output = format_results_json(papers)
    else:
        output = format_results_markdown(papers, query, abstract_limit=abstract_limit)

    # Write output
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(output)
        print(f"\n[OK] Results saved to: {output_file}")
    else:
        print(output)


if __name__ == "__main__":
    main()
