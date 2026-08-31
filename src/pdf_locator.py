from __future__ import annotations

import base64
import io
import re
import shutil
import subprocess
import tempfile
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw
from pypdf import PdfReader


@dataclass(frozen=True)
class TextLocation:
    status: str
    message: str
    page_number: int
    query: str
    score: float = 0.0
    y_top_ratio: Optional[float] = None

    @property
    def confirmed(self) -> bool:
        return self.status in {"exact", "approximate"}


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).lower()
    value = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", value)
    return " ".join(value.split())


def page_count(pdf_path: Path) -> int:
    return len(PdfReader(str(pdf_path)).pages)


def _fragment_locations(page) -> Tuple[str, List[Tuple[str, float]]]:
    fragments: List[Tuple[str, float]] = []

    def visitor(text, cm, tm, _font_dict, _font_size):
        clean = normalize_text(str(text))
        if clean:
            # pypdf exposes a text matrix relative to the current PDF transform.
            # Combining both matrices yields the actual bottom-origin page Y.
            page_y = float(tm[4]) * float(cm[1]) + float(tm[5]) * float(cm[3]) + float(cm[5])
            fragments.append((clean, page_y))

    full_text = page.extract_text(visitor_text=visitor) or ""
    return normalize_text(full_text), fragments


def locate_text(pdf_path: Path, page_number: int, query: str) -> TextLocation:
    if not pdf_path.is_file():
        return TextLocation("missing_pdf", "Zotero PDF 文件不存在。", page_number, query)
    reader = PdfReader(str(pdf_path))
    if page_number < 1 or page_number > len(reader.pages):
        return TextLocation(
            "invalid_page", f"旧标签指向第 {page_number} 页，但 PDF 只有 {len(reader.pages)} 页。", page_number, query
        )
    if not query.strip():
        return TextLocation("page_only", "页码有效，但该候选没有可自动定位的文本。", page_number, query)

    page = reader.pages[page_number - 1]
    full_text, fragments = _fragment_locations(page)
    normalized_query = normalize_text(query)
    if not normalized_query:
        return TextLocation("page_only", "页码有效，但定位文本为空。", page_number, query)

    page_height = float(page.mediabox.height)
    best_score = 0.0
    best_y: Optional[float] = None
    for start in range(len(fragments)):
        combined = ""
        for end in range(start, min(start + 6, len(fragments))):
            combined = f"{combined} {fragments[end][0]}".strip()
            score = SequenceMatcher(None, normalized_query[:240], combined[:240]).ratio()
            query_tokens = set(normalized_query.split())
            combined_tokens = set(combined.split())
            # Measure how much of the requested locator is covered. Using the
            # shorter side would let a generic two-word fragment score 100%.
            coverage = len(query_tokens & combined_tokens) / max(1, len(query_tokens))
            score = max(score, coverage * 0.95)
            if score > best_score:
                best_score = score
                window = fragments[start : end + 1]
                # PDF drawing order is not always reading order. Anchor the
                # marker to the fragment carrying the most locator tokens,
                # rather than blindly using the first fragment in the window.
                best_y = max(
                    window,
                    key=lambda fragment: len(query_tokens & set(fragment[0].split())),
                )[1]

    if normalized_query in full_text:
        status = "exact"
        message = "已在原始 PDF 页中找到候选文本。"
    elif best_score >= 0.66:
        status = "approximate"
        message = "已在原始 PDF 页中找到高相似文本；请人工核对断行或连字符。"
    else:
        return TextLocation(
            "page_only",
            "页码有效，但没有在该页定位到候选文本；旧标签可能错页或文本已被错误切分。",
            page_number,
            query,
            best_score,
        )

    y_top_ratio = None
    if best_y is not None and page_height > 0:
        y_top_ratio = max(0.0, min(1.0, 1.0 - best_y / page_height))
    return TextLocation(status, message, page_number, query, best_score, y_top_ratio)


def render_page_png(pdf_path: Path, page_number: int, dpi: int = 144) -> bytes:
    executable = shutil.which("pdftoppm")
    if not executable:
        raise RuntimeError("未找到 pdftoppm。请使用 Codex bundled Poppler 或安装 Poppler。")
    if page_number < 1 or page_number > page_count(pdf_path):
        raise ValueError(f"Page {page_number} is outside the PDF page range.")
    with tempfile.TemporaryDirectory(prefix="neurotrace_pdf_") as tmp_dir:
        prefix = Path(tmp_dir) / "page"
        completed = subprocess.run(
            [
                executable, "-f", str(page_number), "-l", str(page_number), "-singlefile",
                "-r", str(dpi), "-png", str(pdf_path), str(prefix),
            ],
            capture_output=True,
            check=False,
            timeout=45,
        )
        if completed.returncode != 0:
            error = completed.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"PDF 页面渲染失败：{error or 'pdftoppm returned a non-zero status'}")
        output = prefix.with_suffix(".png")
        if not output.is_file():
            raise RuntimeError("PDF 页面渲染失败：pdftoppm 未生成 PNG 文件。")
        rendered = output.read_bytes()
        validate_png_bytes(rendered)
        return rendered


def validate_png_bytes(payload: bytes) -> Tuple[int, int]:
    """Validate a rendered preview before it is handed to the browser."""
    if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("PDF 页面预览不是有效的 PNG 数据。")
    try:
        with Image.open(io.BytesIO(payload)) as image:
            if image.format != "PNG":
                raise ValueError("PDF 页面预览格式不是 PNG。")
            dimensions = image.size
            image.verify()
    except (OSError, SyntaxError) as exc:
        raise ValueError("PDF 页面预览数据已损坏，请刷新后重试。") from exc
    if dimensions[0] < 1 or dimensions[1] < 1:
        raise ValueError("PDF 页面预览尺寸无效。")
    return dimensions


def png_data_uri(payload: bytes) -> str:
    """Return a stable browser source that does not use Streamlit's media cache."""
    validate_png_bytes(payload)
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def annotate_page(page_png: bytes, location: TextLocation) -> bytes:
    validate_png_bytes(page_png)
    image = Image.open(io.BytesIO(page_png)).convert("RGB")
    if location.y_top_ratio is not None:
        y = int(image.height * location.y_top_ratio)
        draw = ImageDraw.Draw(image, "RGBA")
        band = max(12, int(image.height * 0.012))
        draw.rectangle((0, max(0, y - band), image.width, min(image.height, y + band)), fill=(43, 91, 216, 42))
        draw.line((0, y, image.width, y), fill=(43, 91, 216, 210), width=max(2, image.width // 500))
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def crop_figure_or_table(page_png: bytes, location: TextLocation, item_type: str) -> bytes:
    validate_png_bytes(page_png)
    image = Image.open(io.BytesIO(page_png)).convert("RGB")
    if location.y_top_ratio is None:
        return annotate_page(page_png, location)
    y = int(image.height * location.y_top_ratio)
    margin = int(image.height * 0.035)
    if item_type == "table":
        top = max(0, y - margin)
        bottom = min(image.height, y + int(image.height * 0.48))
    else:
        top = max(0, y - int(image.height * 0.5))
        bottom = min(image.height, y + margin)
    if bottom - top < image.height * 0.15:
        return annotate_page(page_png, location)
    crop = image.crop((0, top, image.width, bottom))
    output = io.BytesIO()
    crop.save(output, format="PNG", optimize=True)
    return output.getvalue()
