#!/usr/bin/env python3
"""
Deep Read Script for Literature Review Skill
Enables thorough reading and analysis of PDF papers
"""

import sys
import os
import re
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

# Try to import PDF libraries
try:
    from PyPDF2 import PdfReader
    HAS_PYPDF2 = True
except ImportError:
    HAS_PYPDF2 = False

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False


def extract_text_pypdf2(pdf_path: str) -> str:
    """Extract text using PyPDF2"""
    if not HAS_PYPDF2:
        return ""
    try:
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n\n"
        return text
    except Exception as e:
        print(f"[ERROR] PyPDF2 extraction failed: {e}")
        return ""


def extract_text_pymupdf(pdf_path: str) -> str:
    """Extract text using PyMuPDF (better quality)"""
    if not HAS_PYMUPDF:
        return ""
    try:
        doc = fitz.open(pdf_path)
        text = ""
        for page in doc:
            text += page.get_text() + "\n\n"
        doc.close()
        return text
    except Exception as e:
        print(f"[ERROR] PyMuPDF extraction failed: {e}")
        return ""


def extract_text(pdf_path: str) -> str:
    """Extract text from PDF using available libraries"""
    if not os.path.exists(pdf_path):
        print(f"[ERROR] File not found: {pdf_path}")
        return ""

    # Try PyMuPDF first (better quality)
    if HAS_PYMUPDF:
        text = extract_text_pymupdf(pdf_path)
        if text.strip():
            return text

    # Fallback to PyPDF2
    if HAS_PYPDF2:
        text = extract_text_pypdf2(pdf_path)
        if text.strip():
            return text

    print("[ERROR] No PDF library available. Install PyPDF2 or PyMuPDF.")
    return ""


def extract_structure(text: str) -> Dict:
    """Extract paper structure (sections, figures, tables)"""
    structure = {
        'sections': [],
        'figures': [],
        'tables': [],
        'equations': [],
        'references': []
    }

    # Common section patterns
    section_patterns = [
        r'(?:^|\n)\s*(\d+\.?\s+(?:Introduction|Background|Related Work|Methods?|Methodology|'
        r'Results?|Discussion|Conclusion[s]?|Abstract|Summary|Appendix|References|Bibliography))',
        r'(?:^|\n)\s*(Abstract|Introduction|Conclusion[s]?)\s*(?:\n|$)',
    ]

    for pattern in section_patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE)
        for match in matches:
            section_title = match.group(1).strip()
            if section_title not in structure['sections']:
                structure['sections'].append(section_title)

    # Figure references
    figure_pattern = r'(?:Figure|Fig\.?)\s*(\d+[a-zA-Z]?)'
    structure['figures'] = list(set(re.findall(figure_pattern, text, re.IGNORECASE)))

    # Table references
    table_pattern = r'(?:Table|Tab\.?)\s*(\d+[a-zA-Z]?)'
    structure['tables'] = list(set(re.findall(table_pattern, text, re.IGNORECASE)))

    # Equation references
    eq_pattern = r'(?:Equation|Eq\.?)\s*(\d+)'
    structure['equations'] = list(set(re.findall(eq_pattern, text, re.IGNORECASE)))

    return structure


def extract_key_info(text: str) -> Dict:
    """Extract key information from paper"""
    info = {
        'title': '',
        'authors': [],
        'abstract': '',
        'keywords': [],
        'doi': '',
        'venue': '',
        'year': ''
    }

    # Try to find title (usually first non-empty line or before authors)
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if lines:
        # Title is often the first substantial line
        for line in lines[:5]:
            if len(line) > 20 and len(line) < 200:
                info['title'] = line
                break

    # Extract DOI
    doi_pattern = r'(?:doi:|DOI:|https?://doi\.org/)?\s*(10\.\d{4,}/[^\s]+)'
    doi_match = re.search(doi_pattern, text)
    if doi_match:
        info['doi'] = doi_match.group(1).rstrip('.')

    # Extract abstract
    abstract_patterns = [
        r'(?:Abstract|ABSTRACT)\s*[:\n]\s*(.+?)(?=\n\n|\n(?:Introduction|INTRODUCTION|1\.|Keywords|KEYWORDS))',
        r'(?:ABSTRACT)\s*(.+?)(?=\n\s*\n)',
    ]
    for pattern in abstract_patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            info['abstract'] = match.group(1).strip()[:2000]
            break

    # Extract keywords
    kw_pattern = r'(?:Keywords|KEYWORDS|Index Terms)\s*[:\n]\s*(.+?)(?=\n\n|\n\s*\n)'
    kw_match = re.search(kw_pattern, text)
    if kw_match:
        keywords = kw_match.group(1).strip()
        info['keywords'] = [k.strip() for k in re.split(r'[;,]', keywords) if k.strip()]

    # Try to find year
    year_pattern = r'\b(20\d{2})\b'
    years = re.findall(year_pattern, text[:2000])  # Look in first 2000 chars
    if years:
        info['year'] = max(years)  # Most likely publication year

    return info


def generate_reading_notes(text: str, paper_title: str = "") -> str:
    """Generate structured reading notes"""
    notes = f"# Deep Reading Notes\n\n"
    notes += f"**Paper**: {paper_title or 'Unknown'}\n"
    notes += f"**Date Read**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
    notes += "---\n\n"

    # Extract key info
    info = extract_key_info(text)
    structure = extract_structure(text)

    # Paper Info Section
    notes += "## Paper Information\n\n"
    if info['title']:
        notes += f"**Title**: {info['title']}\n\n"
    if info['doi']:
        notes += f"**DOI**: [{info['doi']}](https://doi.org/{info['doi']})\n\n"
    if info['year']:
        notes += f"**Year**: {info['year']}\n\n"
    if info['keywords']:
        notes += f"**Keywords**: {', '.join(info['keywords'])}\n\n"

    # Structure Overview
    notes += "## Paper Structure\n\n"
    if structure['sections']:
        notes += "**Sections**:\n"
        for section in structure['sections']:
            notes += f"- {section}\n"
        notes += "\n"
    if structure['figures']:
        notes += f"**Figures**: {', '.join(structure['figures'])}\n\n"
    if structure['tables']:
        notes += f"**Tables**: {', '.join(structure['tables'])}\n\n"

    # Abstract
    if info['abstract']:
        notes += "## Abstract\n\n"
        notes += f"{info['abstract']}\n\n"

    # Full Text (divided into sections)
    notes += "## Full Text Content\n\n"
    notes += "```\n"
    # Limit to first 15000 chars for readability
    if len(text) > 15000:
        notes += text[:15000] + "\n\n... [Truncated for readability] ...\n"
        notes += f"\n[Total length: {len(text)} characters]\n"
    else:
        notes += text
    notes += "```\n\n"

    # Analysis Prompts
    notes += "## Analysis Prompts\n\n"
    notes += "Use the following prompts to guide your deep reading:\n\n"
    notes += "1. **Main Contribution**: What is the primary contribution of this paper?\n"
    notes += "2. **Methodology**: What methods does the paper use? Are they appropriate?\n"
    notes += "3. **Key Findings**: What are the main results? Do they support the claims?\n"
    notes += "4. **Limitations**: What limitations does the paper acknowledge? What additional limitations can you identify?\n"
    notes += "5. **Relevance**: How does this paper relate to your research?\n"
    notes += "6. **Future Work**: What future directions does the paper suggest?\n"
    notes += "7. **Questions**: What questions does this paper raise for your research?\n\n"

    # Citation
    notes += "## Citation\n\n"
    notes += "```\n"
    notes += f"[Add formatted citation here after verification]\n"
    notes += "```\n"

    return notes


def main():
    """Command-line interface"""
    if len(sys.argv) < 2:
        print("Usage: python deep_read.py <pdf_file> [options]")
        print("\nOptions:")
        print("  --output FILE       Save reading notes to file")
        print("  --format FORMAT     Output format (markdown, json)")
        print("  --extract-only      Only extract text, no analysis")
        print("  --section SECTION   Extract specific section (abstract, intro, methods, results, discussion)")
        print("\nExamples:")
        print("  python deep_read.py paper.pdf")
        print("  python deep_read.py paper.pdf --output notes.md")
        print("  python deep_read.py paper.pdf --section abstract")
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_file = None
    output_format = 'markdown'
    extract_only = False
    section = None

    i = 2
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == '--output' and i + 1 < len(sys.argv):
            output_file = sys.argv[i + 1]
            i += 2
        elif arg == '--format' and i + 1 < len(sys.argv):
            output_format = sys.argv[i + 1]
            i += 2
        elif arg == '--extract-only':
            extract_only = True
            i += 1
        elif arg == '--section' and i + 1 < len(sys.argv):
            section = sys.argv[i + 1]
            i += 2
        else:
            i += 1

    # Check PDF libraries
    if not HAS_PYPDF2 and not HAS_PYMUPDF:
        print("[ERROR] No PDF library found. Install one of:")
        print("  pip install PyPDF2")
        print("  pip install PyMuPDF")
        sys.exit(1)

    print(f"[INFO] Extracting text from: {pdf_path}")
    text = extract_text(pdf_path)

    if not text.strip():
        print("[ERROR] Could not extract text from PDF")
        sys.exit(1)

    print(f"[INFO] Extracted {len(text)} characters")

    if extract_only:
        output = text
    elif section:
        # Extract specific section
        section_patterns = {
            'abstract': r'(?:Abstract|ABSTRACT)\s*[:\n]\s*(.+?)(?=\n\n|\n(?:Introduction|INTRODUCTION|1\.))',
            'intro': r'(?:1\.?\s*)?Introduction\s*[:\n]\s*(.+?)(?=\n\d+\.|\n(?:Methods?|Results?|Background))',
            'methods': r'(?:Methods?|Methodology)\s*[:\n]\s*(.+?)(?=\n\d+\.|\n(?:Results?|Discussion))',
            'results': r'Results?\s*[:\n]\s*(.+?)(?=\n\d+\.|\n(?:Discussion|Conclusion))',
            'discussion': r'Discussion\s*[:\n]\s*(.+?)(?=\n\d+\.|\n(?:Conclusion|References))',
        }
        pattern = section_patterns.get(section.lower())
        if pattern:
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                output = match.group(1).strip()
            else:
                output = f"[Section '{section}' not found]"
        else:
            output = f"[Unknown section: {section}]"
    else:
        # Generate full reading notes
        output = generate_reading_notes(text)

    # Output
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(output)
        print(f"[OK] Notes saved to: {output_file}")
    else:
        print("\n" + "="*60 + "\n")
        print(output)


if __name__ == "__main__":
    main()
