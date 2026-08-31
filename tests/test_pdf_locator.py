import base64
import shutil

import pytest
from pypdf import PdfWriter

from src.pdf_locator import locate_text, page_count, png_data_uri, render_page_png, validate_png_bytes


def test_pdf_page_validation_and_render(tmp_path):
    pdf_path = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=400)
    with pdf_path.open("wb") as handle:
        writer.write(handle)

    assert page_count(pdf_path) == 1
    invalid = locate_text(pdf_path, 2, "Introduction")
    assert invalid.status == "invalid_page"
    missing_text = locate_text(pdf_path, 1, "Introduction")
    assert missing_text.status == "page_only"

    if not shutil.which("pdftoppm"):
        pytest.skip("Poppler is not available")
    rendered = render_page_png(pdf_path, 1)
    assert validate_png_bytes(rendered) == (600, 800)
    data_uri = png_data_uri(rendered)
    assert data_uri.startswith("data:image/png;base64,")
    assert base64.b64decode(data_uri.partition(",")[2]) == rendered


def test_rejects_invalid_png_payload():
    with pytest.raises(ValueError, match="PNG"):
        validate_png_bytes(b"not an image")
