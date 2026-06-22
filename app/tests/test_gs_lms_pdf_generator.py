"""Tests for the GS LMS PDF generator (Task 9.1).

Tests the pure rendering and generation functions in
``app.core.gs_lms.pdf_generator``:
* ``render_html_template`` — themed HTML output with Geography styling
* ``generate_topic_pdf`` — PDF/HTML bytes output with fallback pipeline
* ``get_content_type`` / ``get_file_extension`` — output format detection
* ``sections_from_db_records`` — ORM/dict conversion utility
* Section rendering: TOC, section headers, content blocks, theme application

Requirements traced: 8.1, 8.2, 8.3, 8.4, 8.5
"""

from __future__ import annotations

import pytest

from app.core.gs_lms.pdf_generator import (
    ContentBlock,
    Section,
    THEME_COLORS,
    SECTION_THEME,
    generate_topic_pdf,
    render_html_template,
    get_content_type,
    get_file_extension,
    sections_from_db_records,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_section(
    section_label: str = "BASIC",
    title: str = "Introduction to Geomorphology",
    blocks: list | None = None,
    display_order: int = 1,
) -> Section:
    """Create a Section with default values for testing."""
    if blocks is None:
        blocks = [
            ContentBlock(block_type="text", content="This is introductory content about geomorphology."),
            ContentBlock(block_type="heading", content="Key Concepts"),
            ContentBlock(block_type="text", content="Geomorphology studies landforms and processes."),
        ]
    return Section(
        section_label=section_label,
        title=title,
        blocks=blocks,
        display_order=display_order,
    )


def _make_full_topic_sections() -> list[Section]:
    """Create all 4 sections for a complete topic."""
    return [
        _make_section(
            section_label="BASIC",
            title="Basic Concepts of Plate Tectonics",
            display_order=1,
            blocks=[
                ContentBlock(block_type="text", content="Earth's lithosphere is divided into tectonic plates."),
                ContentBlock(block_type="list", content="Continental plates\nOceanic plates\nMixed plates"),
            ],
        ),
        _make_section(
            section_label="ADVANCED",
            title="Advanced Plate Dynamics",
            display_order=2,
            blocks=[
                ContentBlock(block_type="text", content="Plate boundaries determine geological activity."),
                ContentBlock(block_type="heading", content="Convergent Boundaries"),
                ContentBlock(block_type="text", content="Where plates move toward each other."),
            ],
        ),
        _make_section(
            section_label="NCERT_LEVEL",
            title="NCERT-Level Understanding",
            display_order=3,
            blocks=[
                ContentBlock(block_type="text", content="As per NCERT Class 11 Geography textbook."),
                ContentBlock(block_type="quote", content="The earth's crust is not a single piece."),
            ],
        ),
        _make_section(
            section_label="EXAMINER_TRAPS",
            title="Common Examiner Traps",
            display_order=4,
            blocks=[
                ContentBlock(block_type="text", content="UPSC often confuses convergent and divergent."),
                ContentBlock(block_type="code", content="Mnemonic: CCC = Convergent Creates Chains"),
            ],
        ),
    ]


# ===========================================================================
# render_html_template — Geography Theme Output
# ===========================================================================

class TestRenderHtmlTemplate:
    """Tests for render_html_template (Requirement 8.2, 8.3)."""

    def test_returns_valid_html_document(self):
        """Output is a complete HTML document with DOCTYPE and required elements."""
        sections = [_make_section()]
        result = render_html_template(sections, "Plate Tectonics")

        assert "<!DOCTYPE html>" in result
        assert "<html" in result
        assert "</html>" in result
        assert "<head>" in result
        assert "<body>" in result

    def test_includes_topic_title_in_header(self):
        """Topic title appears in the document header."""
        sections = [_make_section()]
        result = render_html_template(sections, "Weathering & Erosion")

        assert "Weathering &amp; Erosion" in result

    def test_includes_subject_name(self):
        """Subject name appears in the header."""
        sections = [_make_section()]
        result = render_html_template(sections, "Test Topic", "GS Geography")

        assert "GS Geography" in result

    def test_custom_subject_name(self):
        """Custom subject name is rendered correctly."""
        sections = [_make_section()]
        result = render_html_template(sections, "Test", "Custom Subject")

        assert "Custom Subject" in result

    def test_geography_theme_colors_in_css(self):
        """Geography theme color palette is applied in the CSS."""
        sections = [_make_section()]
        result = render_html_template(sections, "Test Topic")

        # Check that key theme colors are present in the CSS
        assert THEME_COLORS["primary"] in result
        assert THEME_COLORS["secondary"] in result

    def test_typography_includes_serif_and_sans_serif(self):
        """Professional typography uses serif for headings, sans-serif for body."""
        sections = [_make_section()]
        result = render_html_template(sections, "Test Topic")

        # Serif font for headings
        assert "Georgia" in result
        # Sans-serif for body
        assert "Segoe UI" in result or "Helvetica" in result or "Arial" in result

    def test_page_margins_specified(self):
        """Page margins are defined in the @page rule."""
        sections = [_make_section()]
        result = render_html_template(sections, "Test Topic")

        assert "@page" in result
        assert "margin" in result

    def test_page_numbers_in_css(self):
        """Page number counter is configured."""
        sections = [_make_section()]
        result = render_html_template(sections, "Test Topic")

        assert "counter(page)" in result

    def test_toc_rendered_for_multiple_sections(self):
        """Table of contents appears when multiple sections are provided."""
        sections = _make_full_topic_sections()
        result = render_html_template(sections, "Full Topic")

        assert "Table of Contents" in result
        assert "toc" in result

    def test_no_toc_for_single_section(self):
        """No TOC when only one section is provided (partial PDF)."""
        sections = [_make_section()]
        result = render_html_template(sections, "Single Section")

        # The TOC heading element should not be present (CSS comment still has the text)
        assert '<h2 class="toc-title">Table of Contents</h2>' not in result
        assert '<div class="toc">' not in result

    def test_section_labels_rendered(self):
        """Each section shows its label (Basic, Advanced, etc.)."""
        sections = _make_full_topic_sections()
        result = render_html_template(sections, "Test")

        assert "Basic Concepts" in result
        assert "Advanced Analysis" in result
        assert "NCERT-Level Coverage" in result
        assert "Examiner Traps" in result

    def test_sections_ordered_by_display_order(self):
        """Sections appear in display_order regardless of input order."""
        # Provide sections in reverse order
        sections = list(reversed(_make_full_topic_sections()))
        result = render_html_template(sections, "Test")

        # Basic should appear before Advanced in the output
        basic_pos = result.find("Basic Concepts")
        advanced_pos = result.find("Advanced Analysis")
        ncert_pos = result.find("NCERT-Level Coverage")
        traps_pos = result.find("Examiner Traps")

        assert basic_pos < advanced_pos < ncert_pos < traps_pos

    def test_content_blocks_rendered(self):
        """Content blocks are rendered in the HTML output."""
        sections = [_make_section(blocks=[
            ContentBlock(block_type="text", content="Rivers shape landscapes."),
            ContentBlock(block_type="heading", content="Fluvial Processes"),
        ])]
        result = render_html_template(sections, "Rivers")

        assert "Rivers shape landscapes." in result
        assert "Fluvial Processes" in result

    def test_html_escaping_in_content(self):
        """Special characters in content are properly HTML-escaped."""
        sections = [_make_section(blocks=[
            ContentBlock(block_type="text", content="Temperature < 0°C & pressure > 1 atm"),
        ])]
        result = render_html_template(sections, "Climate <Zone>")

        assert "&lt;" in result
        assert "&amp;" in result
        assert "Climate &lt;Zone&gt;" in result

    def test_list_block_renders_items(self):
        """List content blocks render as HTML lists."""
        sections = [_make_section(blocks=[
            ContentBlock(block_type="list", content="Item one\nItem two\nItem three"),
        ])]
        result = render_html_template(sections, "Test")

        assert "<ul" in result
        assert "<li>" in result
        assert "Item one" in result
        assert "Item two" in result
        assert "Item three" in result

    def test_code_block_renders_as_pre(self):
        """Code content blocks render as preformatted text."""
        sections = [_make_section(blocks=[
            ContentBlock(block_type="code", content="def calculate(): pass"),
        ])]
        result = render_html_template(sections, "Test")

        assert "<pre" in result
        assert "<code>" in result
        assert "def calculate(): pass" in result

    def test_quote_block_renders_as_blockquote(self):
        """Quote content blocks render as blockquotes."""
        sections = [_make_section(blocks=[
            ContentBlock(block_type="quote", content="The earth is dynamic."),
        ])]
        result = render_html_template(sections, "Test")

        assert "<blockquote" in result
        assert "The earth is dynamic." in result

    def test_section_color_coding(self):
        """Each section type has its distinct color in the output."""
        sections = _make_full_topic_sections()
        result = render_html_template(sections, "Test")

        # Check that section-specific colors appear
        assert SECTION_THEME["BASIC"]["color"] in result
        assert SECTION_THEME["ADVANCED"]["color"] in result
        assert SECTION_THEME["NCERT_LEVEL"]["color"] in result
        assert SECTION_THEME["EXAMINER_TRAPS"]["color"] in result

    def test_page_break_css_for_sections(self):
        """CSS includes page-break rules for section separation."""
        sections = _make_full_topic_sections()
        result = render_html_template(sections, "Test")

        assert "page-break" in result

    def test_footer_rendered(self):
        """Document footer is included with subject name."""
        sections = [_make_section()]
        result = render_html_template(sections, "Test", "GS Geography")

        assert "document-footer" in result
        assert "GS Geography" in result


# ===========================================================================
# generate_topic_pdf — PDF generation with fallback
# ===========================================================================

class TestGenerateTopicPdf:
    """Tests for generate_topic_pdf (Requirements 8.1, 8.4, 8.5)."""

    def test_raises_on_empty_sections(self):
        """ValueError raised when no sections provided."""
        with pytest.raises(ValueError, match="At least one completed section"):
            generate_topic_pdf([], "Empty Topic")

    def test_returns_bytes(self):
        """Output is always bytes."""
        sections = [_make_section()]
        result = generate_topic_pdf(sections, "Test Topic")

        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_single_section_partial_pdf(self):
        """Partial PDF generated when only some sections are completed (Req 8.4)."""
        sections = [_make_section(section_label="BASIC", display_order=1)]
        result = generate_topic_pdf(sections, "Partial Topic")

        assert isinstance(result, bytes)
        assert len(result) > 0
        # Should contain the section content
        assert b"BASIC" in result or b"Basic" in result

    def test_full_topic_all_four_sections(self):
        """Full PDF contains all four sections (Req 8.1)."""
        sections = _make_full_topic_sections()
        result = generate_topic_pdf(sections, "Complete Topic")

        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_output_contains_topic_title(self):
        """Generated output includes the topic title."""
        sections = [_make_section()]
        result = generate_topic_pdf(sections, "Volcanic Activity")

        assert b"Volcanic Activity" in result

    def test_output_contains_subject_name(self):
        """Generated output includes the subject name."""
        sections = [_make_section()]
        result = generate_topic_pdf(sections, "Test", "GS Geography")

        assert b"GS Geography" in result

    def test_two_sections_partial(self):
        """Two completed sections produce valid output."""
        sections = [
            _make_section(section_label="BASIC", display_order=1),
            _make_section(section_label="ADVANCED", title="Advanced Concepts", display_order=2),
        ]
        result = generate_topic_pdf(sections, "Partial")

        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_three_sections_partial(self):
        """Three completed sections produce valid output."""
        sections = _make_full_topic_sections()[:3]
        result = generate_topic_pdf(sections, "Three Sections")

        assert isinstance(result, bytes)
        assert len(result) > 0


# ===========================================================================
# get_content_type / get_file_extension
# ===========================================================================

class TestContentTypeDetection:
    """Tests for get_content_type and get_file_extension."""

    def test_pdf_content_type(self):
        """Actual PDF bytes return application/pdf."""
        pdf_header = b"%PDF-1.4 rest of content"
        assert get_content_type(pdf_header) == "application/pdf"

    def test_html_content_type(self):
        """HTML bytes return text/html."""
        html_bytes = b"<!DOCTYPE html><html>...</html>"
        assert get_content_type(html_bytes) == "text/html; charset=utf-8"

    def test_pdf_file_extension(self):
        """PDF bytes return .pdf extension."""
        pdf_header = b"%PDF-1.7 content"
        assert get_file_extension(pdf_header) == ".pdf"

    def test_html_file_extension(self):
        """HTML bytes return .html extension."""
        html_bytes = b"<!DOCTYPE html>..."
        assert get_file_extension(html_bytes) == ".html"

    def test_generated_output_type(self):
        """Output from generate_topic_pdf has a valid content type."""
        sections = [_make_section()]
        result = generate_topic_pdf(sections, "Test")

        content_type = get_content_type(result)
        assert content_type in ("application/pdf", "text/html; charset=utf-8")

    def test_generated_output_extension(self):
        """Output from generate_topic_pdf has a valid file extension."""
        sections = [_make_section()]
        result = generate_topic_pdf(sections, "Test")

        ext = get_file_extension(result)
        assert ext in (".pdf", ".html")


# ===========================================================================
# sections_from_db_records — conversion utility
# ===========================================================================

class TestSectionsFromDbRecords:
    """Tests for sections_from_db_records utility."""

    def test_empty_input_returns_empty(self):
        """Empty list returns empty list."""
        assert sections_from_db_records([]) == []

    def test_converts_dict_records(self):
        """Dict records are properly converted to Section objects."""
        records = [
            {
                "section_label": "BASIC",
                "title": "Basics of Climate",
                "blocks": [
                    {"type": "text", "content": "Climate is average weather."},
                    {"type": "heading", "content": "Temperature Zones"},
                ],
                "display_order": 1,
            }
        ]
        result = sections_from_db_records(records)

        assert len(result) == 1
        assert isinstance(result[0], Section)
        assert result[0].section_label == "BASIC"
        assert result[0].title == "Basics of Climate"
        assert len(result[0].blocks) == 2
        assert result[0].blocks[0].block_type == "text"
        assert result[0].blocks[0].content == "Climate is average weather."
        assert result[0].display_order == 1

    def test_converts_enum_section_label(self):
        """Enum section_label values are converted to strings."""
        from app.core.gs_lms.models import GsLmsSectionLabelEnum

        records = [
            {
                "section_label": GsLmsSectionLabelEnum.ADVANCED,
                "title": "Advanced Climate",
                "blocks": [],
                "display_order": 2,
            }
        ]
        result = sections_from_db_records(records)

        assert result[0].section_label == "ADVANCED"

    def test_handles_none_blocks(self):
        """None blocks field is treated as empty list."""
        records = [
            {
                "section_label": "BASIC",
                "title": "Test",
                "blocks": None,
                "display_order": 1,
            }
        ]
        result = sections_from_db_records(records)

        assert result[0].blocks == []

    def test_handles_object_with_attributes(self):
        """Objects with attributes (ORM-like) are properly converted."""

        class FakeOrmSection:
            section_label = "NCERT_LEVEL"
            title = "NCERT Coverage"
            blocks = [{"type": "text", "content": "As per NCERT."}]
            display_order = 3

        result = sections_from_db_records([FakeOrmSection()])

        assert len(result) == 1
        assert result[0].section_label == "NCERT_LEVEL"
        assert result[0].title == "NCERT Coverage"
        assert len(result[0].blocks) == 1
        assert result[0].display_order == 3

    def test_multiple_records(self):
        """Multiple records are all converted."""
        records = [
            {"section_label": "BASIC", "title": "Basic", "blocks": [], "display_order": 1},
            {"section_label": "ADVANCED", "title": "Advanced", "blocks": [], "display_order": 2},
            {"section_label": "NCERT_LEVEL", "title": "NCERT", "blocks": [], "display_order": 3},
            {"section_label": "EXAMINER_TRAPS", "title": "Traps", "blocks": [], "display_order": 4},
        ]
        result = sections_from_db_records(records)

        assert len(result) == 4
        assert [s.section_label for s in result] == ["BASIC", "ADVANCED", "NCERT_LEVEL", "EXAMINER_TRAPS"]

    def test_preserves_content_block_data(self):
        """Content block type and content are preserved through conversion."""
        records = [
            {
                "section_label": "BASIC",
                "title": "Test",
                "blocks": [
                    {"type": "heading", "content": "Important"},
                    {"type": "list", "content": "A\nB\nC"},
                    {"type": "code", "content": "x = 1"},
                    {"type": "quote", "content": "Earth is round."},
                ],
                "display_order": 1,
            }
        ]
        result = sections_from_db_records(records)
        blocks = result[0].blocks

        assert len(blocks) == 4
        assert blocks[0].block_type == "heading"
        assert blocks[0].content == "Important"
        assert blocks[1].block_type == "list"
        assert blocks[2].block_type == "code"
        assert blocks[3].block_type == "quote"
        assert blocks[3].content == "Earth is round."
