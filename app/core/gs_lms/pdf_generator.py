"""PDF Generator for GS LMS Platform — Geography theme.

Produces professionally themed PDFs from completed topic content sections.
Implements a graceful fallback strategy for the HTML-to-PDF pipeline:

    1. WeasyPrint (best quality, requires system dependencies)
    2. xhtml2pdf / pisa (pure-Python, decent output)
    3. HTML bytes (always available, suitable for client-side rendering)

The Geography theme uses a blue/green color palette, professional typography,
proper margins, page numbers, and a table of contents for multi-section PDFs.

Public API:
    - generate_topic_pdf(sections, topic_title, subject_name) → bytes
    - render_html_template(sections, topic_title, subject_name) → str

Requirements traced: 8.1, 8.2, 8.3, 8.4, 8.5
"""

from __future__ import annotations

import html
import logging
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

@dataclass
class ContentBlock:
    """A single content block within a section.

    Attributes:
        block_type: The type of content (text, heading, list, code, image, etc.)
        content: The rendered content (HTML-safe text or raw markdown).
    """
    block_type: str
    content: str


@dataclass
class Section:
    """A completed content section ready for PDF rendering.

    Attributes:
        section_label: One of BASIC, ADVANCED, NCERT_LEVEL, EXAMINER_TRAPS.
        title: Human-readable section title.
        blocks: Ordered list of content blocks.
        display_order: Numeric ordering (1-4).
    """
    section_label: str
    title: str
    blocks: List[ContentBlock]
    display_order: int


# ---------------------------------------------------------------------------
# Geography Theme Constants
# ---------------------------------------------------------------------------

# Color palette: blues and greens appropriate for geography
THEME_COLORS = {
    "primary": "#1B5E20",       # Deep forest green (headings, accents)
    "secondary": "#0D47A1",     # Deep blue (sub-headings, links)
    "accent": "#2E7D32",        # Medium green (highlights)
    "bg_light": "#E8F5E9",      # Very light green (section backgrounds)
    "bg_header": "#1B5E20",     # Header background
    "text_primary": "#212121",  # Near-black body text
    "text_secondary": "#424242",  # Dark gray for secondary text
    "border": "#A5D6A7",        # Light green border
    "page_number": "#616161",   # Medium gray for page numbers
}

# Section label display names and colors
SECTION_THEME = {
    "BASIC": {"display": "Basic Concepts", "color": "#2E7D32"},
    "ADVANCED": {"display": "Advanced Analysis", "color": "#1565C0"},
    "NCERT_LEVEL": {"display": "NCERT-Level Coverage", "color": "#6A1B9A"},
    "EXAMINER_TRAPS": {"display": "Examiner Traps & Pitfalls", "color": "#BF360C"},
}


# ---------------------------------------------------------------------------
# HTML Template Rendering
# ---------------------------------------------------------------------------

def _escape(text: str) -> str:
    """HTML-escape text content."""
    return html.escape(text, quote=True)


def _render_block(block: ContentBlock) -> str:
    """Render a single content block to HTML."""
    bt = block.block_type.lower()
    content = block.content

    if bt == "heading":
        return f'<h3 class="content-heading">{_escape(content)}</h3>'
    elif bt == "subheading":
        return f'<h4 class="content-subheading">{_escape(content)}</h4>'
    elif bt == "list":
        # Content may already contain list items separated by newlines
        items = content.split("\n") if "\n" in content else [content]
        list_html = "\n".join(f"<li>{_escape(item.strip())}</li>" for item in items if item.strip())
        return f'<ul class="content-list">{list_html}</ul>'
    elif bt == "code":
        return f'<pre class="content-code"><code>{_escape(content)}</code></pre>'
    elif bt == "image":
        return f'<figure class="content-figure"><img src="{_escape(content)}" alt="Geography illustration" /></figure>'
    elif bt == "quote":
        return f'<blockquote class="content-quote">{_escape(content)}</blockquote>'
    elif bt == "html":
        # Pre-rendered HTML content — pass through directly
        return f'<div class="content-html">{content}</div>'
    else:
        # Default: paragraph text
        return f'<p class="content-text">{_escape(content)}</p>'


def _render_section_html(section: Section) -> str:
    """Render a single section to HTML."""
    theme = SECTION_THEME.get(section.section_label, {"display": section.title, "color": THEME_COLORS["primary"]})

    blocks_html = "\n".join(_render_block(block) for block in section.blocks)

    return f'''
    <div class="section" id="section-{section.display_order}">
        <div class="section-header" style="border-left: 4px solid {theme['color']};">
            <span class="section-label" style="color: {theme['color']};">{theme['display']}</span>
            <h2 class="section-title">{_escape(section.title)}</h2>
        </div>
        <div class="section-content">
            {blocks_html}
        </div>
    </div>
    '''


def _render_toc(sections: List[Section]) -> str:
    """Render a table of contents for multi-section PDFs."""
    if len(sections) <= 1:
        return ""

    items = []
    for section in sections:
        theme = SECTION_THEME.get(section.section_label, {"display": section.title, "color": THEME_COLORS["primary"]})
        items.append(
            f'<li class="toc-item">'
            f'<a href="#section-{section.display_order}">'
            f'<span class="toc-label" style="color: {theme["color"]};">{theme["display"]}</span>'
            f' — {_escape(section.title)}'
            f'</a></li>'
        )

    return f'''
    <div class="toc">
        <h2 class="toc-title">Table of Contents</h2>
        <ol class="toc-list">
            {"".join(items)}
        </ol>
    </div>
    '''


def render_html_template(
    sections: List[Section],
    topic_title: str,
    subject_name: str = "GS Geography",
) -> str:
    """Render the full HTML document with Geography theme.

    This produces a complete HTML document styled for PDF generation or
    standalone viewing. The Geography theme includes:
    - Blue/green color palette
    - Professional typography (serif headings, sans-serif body)
    - Proper margins, page numbers
    - Table of contents for multi-section PDFs
    - Section headers with colored labels

    Args:
        sections: List of completed Section objects to render.
        topic_title: The topic title for the document header.
        subject_name: Subject name (defaults to "GS Geography").

    Returns:
        Complete HTML string ready for PDF conversion.
    """
    sections_sorted = sorted(sections, key=lambda s: s.display_order)
    toc_html = _render_toc(sections_sorted)
    sections_html = "\n".join(_render_section_html(s) for s in sections_sorted)

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{_escape(topic_title)} — {_escape(subject_name)}</title>
    <style>
        /* Geography Theme — Professional PDF Styling */
        @page {{
            size: A4;
            margin: 2.5cm 2cm 2.5cm 2cm;
            @bottom-center {{
                content: counter(page);
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 9pt;
                color: {THEME_COLORS['page_number']};
            }}
        }}

        * {{
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
            font-size: 11pt;
            line-height: 1.6;
            color: {THEME_COLORS['text_primary']};
            margin: 0;
            padding: 0;
        }}

        /* Cover / Header */
        .document-header {{
            text-align: center;
            padding: 2cm 1cm;
            margin-bottom: 1.5cm;
            border-bottom: 3px solid {THEME_COLORS['primary']};
            page-break-after: avoid;
        }}

        .document-header .subject-name {{
            font-family: 'Georgia', 'Times New Roman', serif;
            font-size: 14pt;
            color: {THEME_COLORS['secondary']};
            text-transform: uppercase;
            letter-spacing: 2px;
            margin-bottom: 0.5cm;
        }}

        .document-header .topic-title {{
            font-family: 'Georgia', 'Times New Roman', serif;
            font-size: 24pt;
            color: {THEME_COLORS['primary']};
            margin: 0.5cm 0;
            font-weight: bold;
        }}

        .document-header .subtitle {{
            font-size: 10pt;
            color: {THEME_COLORS['text_secondary']};
            margin-top: 0.3cm;
        }}

        /* Table of Contents */
        .toc {{
            margin: 1cm 0 2cm 0;
            padding: 1cm;
            background: {THEME_COLORS['bg_light']};
            border-radius: 4px;
            page-break-after: always;
        }}

        .toc-title {{
            font-family: 'Georgia', 'Times New Roman', serif;
            font-size: 16pt;
            color: {THEME_COLORS['primary']};
            margin-bottom: 0.5cm;
        }}

        .toc-list {{
            list-style: none;
            padding-left: 0;
            counter-reset: toc-counter;
        }}

        .toc-item {{
            padding: 0.3cm 0;
            border-bottom: 1px dotted {THEME_COLORS['border']};
            counter-increment: toc-counter;
        }}

        .toc-item::before {{
            content: counter(toc-counter) ". ";
            color: {THEME_COLORS['primary']};
            font-weight: bold;
        }}

        .toc-item a {{
            color: {THEME_COLORS['text_primary']};
            text-decoration: none;
        }}

        .toc-label {{
            font-weight: 600;
        }}

        /* Sections */
        .section {{
            margin-bottom: 2cm;
            page-break-before: always;
        }}

        .section:first-of-type {{
            page-break-before: avoid;
        }}

        .section-header {{
            padding: 0.5cm 0 0.5cm 0.8cm;
            margin-bottom: 1cm;
        }}

        .section-label {{
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 10pt;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}

        .section-title {{
            font-family: 'Georgia', 'Times New Roman', serif;
            font-size: 18pt;
            color: {THEME_COLORS['primary']};
            margin: 0.3cm 0 0 0;
        }}

        /* Content blocks */
        .section-content {{
            padding: 0 0.5cm;
        }}

        .content-heading {{
            font-family: 'Georgia', 'Times New Roman', serif;
            font-size: 14pt;
            color: {THEME_COLORS['secondary']};
            margin: 1cm 0 0.4cm 0;
        }}

        .content-subheading {{
            font-family: 'Georgia', 'Times New Roman', serif;
            font-size: 12pt;
            color: {THEME_COLORS['accent']};
            margin: 0.8cm 0 0.3cm 0;
        }}

        .content-text {{
            margin: 0.4cm 0;
            text-align: justify;
        }}

        .content-list {{
            margin: 0.4cm 0 0.4cm 1cm;
            padding-left: 0.5cm;
        }}

        .content-list li {{
            margin: 0.2cm 0;
        }}

        .content-code {{
            background: #F5F5F5;
            border: 1px solid #E0E0E0;
            border-radius: 3px;
            padding: 0.5cm;
            font-family: 'Consolas', 'Courier New', monospace;
            font-size: 9pt;
            overflow-x: auto;
            margin: 0.5cm 0;
        }}

        .content-quote {{
            border-left: 3px solid {THEME_COLORS['accent']};
            padding: 0.3cm 0.8cm;
            margin: 0.5cm 0;
            background: {THEME_COLORS['bg_light']};
            font-style: italic;
            color: {THEME_COLORS['text_secondary']};
        }}

        .content-figure {{
            text-align: center;
            margin: 0.8cm 0;
        }}

        .content-figure img {{
            max-width: 100%;
            height: auto;
        }}

        .content-html {{
            margin: 0.4cm 0;
        }}

        /* Footer note */
        .document-footer {{
            margin-top: 2cm;
            padding-top: 0.5cm;
            border-top: 1px solid {THEME_COLORS['border']};
            text-align: center;
            font-size: 8pt;
            color: {THEME_COLORS['page_number']};
        }}
    </style>
</head>
<body>
    <div class="document-header">
        <div class="subject-name">{_escape(subject_name)}</div>
        <h1 class="topic-title">{_escape(topic_title)}</h1>
        <div class="subtitle">Comprehensive Study Material</div>
    </div>

    {toc_html}

    {sections_html}

    <div class="document-footer">
        Generated by {_escape(subject_name)} LMS &bull; For personal study use only
    </div>
</body>
</html>'''


# ---------------------------------------------------------------------------
# PDF Generation Pipeline (with graceful fallback)
# ---------------------------------------------------------------------------

def _generate_with_weasyprint(html_content: str) -> Optional[bytes]:
    """Attempt PDF generation via WeasyPrint (best quality)."""
    try:
        from weasyprint import HTML  # type: ignore[import-not-found]
        pdf_bytes = HTML(string=html_content).write_pdf()
        logger.info("PDF generated via WeasyPrint")
        return pdf_bytes
    except ImportError:
        logger.debug("WeasyPrint not available, trying next fallback")
        return None
    except Exception as e:
        logger.warning(f"WeasyPrint generation failed: {e}")
        return None


def _generate_with_xhtml2pdf(html_content: str) -> Optional[bytes]:
    """Attempt PDF generation via xhtml2pdf/pisa (pure-Python fallback)."""
    try:
        from io import BytesIO
        from xhtml2pdf import pisa  # type: ignore[import-not-found]

        buffer = BytesIO()
        pisa_status = pisa.CreatePDF(html_content, dest=buffer)

        if pisa_status.err:
            logger.warning(f"xhtml2pdf reported errors: {pisa_status.err}")
            return None

        pdf_bytes = buffer.getvalue()
        logger.info("PDF generated via xhtml2pdf")
        return pdf_bytes
    except ImportError:
        logger.debug("xhtml2pdf not available, falling back to HTML")
        return None
    except Exception as e:
        logger.warning(f"xhtml2pdf generation failed: {e}")
        return None


def _generate_html_fallback(html_content: str) -> bytes:
    """Return HTML bytes as final fallback (viewable in any browser)."""
    logger.info("Using HTML fallback for PDF content (no PDF library available)")
    return html_content.encode("utf-8")


def generate_topic_pdf(
    sections: List[Section],
    topic_title: str,
    subject_name: str = "GS Geography",
) -> bytes:
    """Generate a themed PDF for a topic from its completed content sections.

    Renders only the provided sections (caller is responsible for filtering
    to completed sections only). Applies the Geography theme with consistent
    color palette, typography, margins, page numbers, and TOC.

    The generation pipeline attempts, in order:
        1. WeasyPrint (highest quality, requires system deps)
        2. xhtml2pdf/pisa (pure-Python, decent quality)
        3. HTML bytes (always works, viewable in browser)

    Target: under 10 seconds for topics under 20 pages.

    Args:
        sections: List of completed Section objects to include in the PDF.
            Only these sections will be rendered. If fewer than 4 sections
            are provided, a partial PDF of completed sections is generated.
        topic_title: The topic title for the document header.
        subject_name: Subject name (defaults to "GS Geography").

    Returns:
        PDF content as bytes (or HTML bytes if no PDF library is available).

    Raises:
        ValueError: If sections list is empty.
    """
    if not sections:
        raise ValueError("At least one completed section is required to generate a PDF.")

    # Render the themed HTML template
    html_content = render_html_template(sections, topic_title, subject_name)

    # Try PDF generation pipeline with graceful fallback
    pdf_bytes = _generate_with_weasyprint(html_content)
    if pdf_bytes is not None:
        return pdf_bytes

    pdf_bytes = _generate_with_xhtml2pdf(html_content)
    if pdf_bytes is not None:
        return pdf_bytes

    # Final fallback: return HTML bytes
    return _generate_html_fallback(html_content)


# ---------------------------------------------------------------------------
# Utility Functions
# ---------------------------------------------------------------------------

def get_content_type(pdf_bytes: bytes) -> str:
    """Determine the content type based on the generated output.

    Args:
        pdf_bytes: The bytes returned by generate_topic_pdf.

    Returns:
        MIME type string: 'application/pdf' for actual PDFs,
        'text/html' for HTML fallback.
    """
    # PDF files start with %PDF
    if pdf_bytes[:4] == b"%PDF":
        return "application/pdf"
    return "text/html; charset=utf-8"


def get_file_extension(pdf_bytes: bytes) -> str:
    """Determine the file extension based on the generated output.

    Args:
        pdf_bytes: The bytes returned by generate_topic_pdf.

    Returns:
        File extension string: '.pdf' for actual PDFs, '.html' for fallback.
    """
    if pdf_bytes[:4] == b"%PDF":
        return ".pdf"
    return ".html"


def sections_from_db_records(db_sections: list) -> List[Section]:
    """Convert database content section records to Section dataclasses.

    Utility for API layer to transform ORM objects into the format expected
    by the PDF generator.

    Args:
        db_sections: List of GsLmsContentSection ORM objects (or dicts with
            section_label, title, blocks, display_order keys).

    Returns:
        List of Section dataclasses ready for PDF generation.
    """
    result = []
    for record in db_sections:
        # Support both ORM objects and dicts
        if isinstance(record, dict):
            section_label = record.get("section_label", "")
            title = record.get("title", "")
            raw_blocks = record.get("blocks", []) or []
            display_order = record.get("display_order", 0)
        else:
            section_label = getattr(record, "section_label", "")
            title = getattr(record, "title", "")
            raw_blocks = getattr(record, "blocks", []) or []
            display_order = getattr(record, "display_order", 0)

        # Convert section_label enum to string if needed
        if hasattr(section_label, "value"):
            section_label = section_label.value

        # Parse content blocks
        blocks = []
        for block_data in raw_blocks:
            if isinstance(block_data, dict):
                blocks.append(ContentBlock(
                    block_type=block_data.get("type", "text"),
                    content=block_data.get("content", ""),
                ))
            elif isinstance(block_data, ContentBlock):
                blocks.append(block_data)

        result.append(Section(
            section_label=section_label,
            title=title,
            blocks=blocks,
            display_order=display_order,
        ))

    return result


__all__ = [
    # Data structures
    "ContentBlock",
    "Section",
    # Theme constants
    "THEME_COLORS",
    "SECTION_THEME",
    # Public API
    "generate_topic_pdf",
    "render_html_template",
    # Utilities
    "get_content_type",
    "get_file_extension",
    "sections_from_db_records",
]
