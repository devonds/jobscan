"""PDF export for cover letters."""

import re
from pathlib import Path

import markdown
from weasyprint import CSS, HTML


class PDFExporter:
    """Export cover letters to PDF."""

    DEFAULT_CSS = """
    @page {
        size: letter;
        margin: 1in;
    }

    body {
        font-family: 'Georgia', 'Times New Roman', serif;
        font-size: 11pt;
        line-height: 1.6;
        color: #333;
    }

    p {
        margin-bottom: 1em;
    }

    h1, h2, h3 {
        margin-top: 0;
        margin-bottom: 0.5em;
    }

    ul, ol {
        margin-bottom: 1em;
        padding-left: 1.5em;
    }

    li {
        margin-bottom: 0.25em;
    }
    """

    def __init__(self, css: str | None = None) -> None:
        """Initialize the exporter.

        Args:
            css: Custom CSS for styling the PDF.
        """
        self.css = css or self.DEFAULT_CSS

    def export(
        self,
        content: str,
        output_dir: Path,
        company: str,
        position: str,
    ) -> Path:
        """Export cover letter to PDF.

        Args:
            content: The cover letter text (markdown or plain text).
            output_dir: Directory to save the PDF.
            company: Company name for the filename.
            position: Position title for the filename.

        Returns:
            Path to the generated PDF file.
        """
        # Convert markdown to HTML
        html_content = self._to_html(content)

        # Generate filename
        filename = self._generate_filename(company, position)
        output_path = output_dir / filename

        # Generate PDF
        html = HTML(string=html_content)
        css = CSS(string=self.css)
        html.write_pdf(output_path, stylesheets=[css])

        return output_path

    def _to_html(self, content: str) -> str:
        """Convert markdown content to HTML."""
        # Convert markdown to HTML
        html_body = markdown.markdown(
            content,
            extensions=["smarty"],  # Smart quotes and dashes
        )

        # Wrap in basic HTML structure
        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
</head>
<body>
{html_body}
</body>
</html>"""

    def _generate_filename(self, company: str, position: str) -> str:
        """Generate a safe filename for the PDF."""
        # Clean company and position for filename
        company_clean = self._sanitize_filename(company)
        position_clean = self._sanitize_filename(position)

        return f"cover_letter_{company_clean}_{position_clean}.pdf"

    def _sanitize_filename(self, name: str) -> str:
        """Sanitize a string for use in a filename."""
        # Replace spaces with underscores
        name = name.replace(" ", "_")
        # Remove any characters that aren't alphanumeric or underscores
        name = re.sub(r"[^\w]", "", name)
        # Truncate to reasonable length
        return name[:50].lower()


class PDFExportError(Exception):
    """Error exporting to PDF."""

    pass
