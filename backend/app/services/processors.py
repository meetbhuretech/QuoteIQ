"""Format-specific drawing processors.

Each processor returns the shared extraction result. Failures raise, and the
pipeline records them instead of inventing specifications.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.services.extraction import ExtractionResult, parse_engineering_text

logger = logging.getLogger(__name__)


def extract_pdf(path: Path) -> ExtractionResult:
    import fitz

    document = fitz.open(path)
    try:
        blocks: list[dict] = []
        pages: list[dict] = []
        preview = None
        full_text: list[str] = []
        for index, page in enumerate(document):
            text = page.get_text("text") or ""
            full_text.append(text)
            width = float(page.rect.width)
            height = float(page.rect.height)
            payload = page.get_text("dict")
            for block in payload.get("blocks", []):
                if block.get("type") != 0:
                    continue
                parts = []
                for line in block.get("lines", []):
                    parts.append("".join(span.get("text", "") for span in line.get("spans", [])))
                block_text = " ".join(part for part in parts if part).strip()
                if not block_text:
                    continue
                bbox = block.get("bbox", (0, 0, 0, 0))
                in_title = bbox[0] > width * 0.55 and bbox[1] > height * 0.55
                blocks.append(
                    {
                        "text": block_text,
                        "page": index + 1,
                        "bbox": [round(float(v), 2) for v in bbox],
                        "in_title": in_title,
                    }
                )
            excerpt = " ".join(text.split())[:500]
            pages.append({"page_number": index + 1, "width": width, "height": height, "text_excerpt": excerpt})
            if index == 0:
                pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
                preview = pixmap.tobytes("png")
        joined = "\n".join(full_text)
        if joined.strip():
            result = parse_engineering_text(joined, source=path.name, method="pymupdf_text")
            _prefer_title_block(result, blocks)
            result.missing_information.append("Embedded PDF text was used. OCR was not required for this file.")
        else:
            result = _ocr_rendered_pages(document, path.name)
            result.missing_information.append("The PDF had no embedded text. OCR was attempted on rendered pages.")
        result.pages = pages
        result.preview_png = preview
        result.detected_features.append({"type": "pdf_pages", "count": document.page_count})
        return result
    finally:
        document.close()


def _prefer_title_block(result: ExtractionResult, blocks: list[dict]) -> None:
    for evidence in result.evidence:
        for block in blocks:
            if evidence.value.lower() in block["text"].lower() and block["in_title"]:
                evidence.method = "pymupdf_title_block_region"
                evidence.location = f"page {block['page']} bbox {block['bbox']}"
                evidence.confidence = min(0.8, round(evidence.confidence + 0.08, 4))
                result.confidence_scores[evidence.field_name] = evidence.confidence
                break
            if evidence.value.lower() in block["text"].lower() and evidence.location is None:
                evidence.location = f"page {block['page']} bbox {block['bbox']}"


def _ocr_rendered_pages(document, source: str) -> ExtractionResult:
    import fitz

    texts = []
    for page in document:
        pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        texts.append(_ocr_png_bytes(pixmap.tobytes("png")))
    joined = "\n".join(texts)
    if not joined.strip():
        result = parse_engineering_text("", source=source, method="ocr_unavailable")
        result.missing_information.append("OCR produced no text. Specifications were not inferred.")
        return result
    return parse_engineering_text(joined, source=source, method="tesseract_ocr")


def _ocr_png_bytes(payload: bytes) -> str:
    try:
        import pytesseract
        from PIL import Image
        import io

        return pytesseract.image_to_string(Image.open(io.BytesIO(payload))) or ""
    except Exception as exc:
        logger.info("OCR unavailable: %s", exc.__class__.__name__)
        return ""


def extract_dxf(path: Path) -> ExtractionResult:
    import ezdxf

    document = ezdxf.readfile(path)
    modelspace = document.modelspace()
    xs: list[float] = []
    ys: list[float] = []
    counts = {"LINE": 0, "ARC": 0, "CIRCLE": 0, "LWPOLYLINE": 0, "POLYLINE": 0, "DIMENSION": 0}
    layers: set[str] = set()
    texts: list[str] = []
    dimension_values: list[str] = []
    for entity in modelspace:
        layer = getattr(entity.dxf, "layer", "")
        if layer:
            layers.add(str(layer))
        kind = entity.dxftype()
        if kind in counts:
            counts[kind] += 1
        try:
            if kind == "LINE":
                xs += [float(entity.dxf.start.x), float(entity.dxf.end.x)]
                ys += [float(entity.dxf.start.y), float(entity.dxf.end.y)]
            elif kind == "CIRCLE":
                radius = float(entity.dxf.radius)
                center = entity.dxf.center
                xs += [float(center.x) - radius, float(center.x) + radius]
                ys += [float(center.y) - radius, float(center.y) + radius]
            elif kind == "ARC":
                radius = float(entity.dxf.radius)
                center = entity.dxf.center
                xs += [float(center.x) - radius, float(center.x) + radius]
                ys += [float(center.y) - radius, float(center.y) + radius]
            elif kind in {"LWPOLYLINE", "POLYLINE"}:
                points = list(entity.get_points("xy")) if kind == "LWPOLYLINE" else [(point[0], point[1]) for point in entity.points()]
                for point in points:
                    xs.append(float(point[0]))
                    ys.append(float(point[1]))
            elif kind == "DIMENSION":
                raw = getattr(entity.dxf, "text", None) or ""
                if raw:
                    dimension_values.append(str(raw))
            elif kind == "TEXT":
                texts.append(str(entity.dxf.text))
            elif kind == "MTEXT":
                texts.append(str(entity.text))
        except Exception:
            logger.debug("Skipped DXF entity %s", kind, exc_info=True)

    result = parse_engineering_text("\n".join(texts), source=path.name, method="ezdxf_text")
    units = _dxf_units(document)
    if units and result.units is None:
        result.units = units
        result.confidence_scores["units"] = 0.5
        result.missing_information = [item for item in result.missing_information if not item.startswith("Units were")]
    if xs and ys and result.length is None and result.width is None:
        from app.services.extraction import Evidence

        length = round(max(xs) - min(xs), 4)
        width = round(max(ys) - min(ys), 4)
        result.length = length
        result.width = width
        result.confidence_scores["length"] = 0.45
        result.confidence_scores["width"] = 0.45
        result.evidence.append(Evidence("length", str(length), "modelspace extents", "ezdxf_extents", 0.45, path.name))
        result.evidence.append(Evidence("width", str(width), "modelspace extents", "ezdxf_extents", 0.45, path.name))
        result.missing_information.append(
            "Length and width are DXF extents, not confirmed dimensions. Height was not set from 2D geometry."
        )
    result.detected_features.append(
        {
            "type": "dxf_entities",
            "counts": counts,
            "layers": sorted(layers),
            "circle_entities": counts["CIRCLE"],
            "note": "Circle entities are hole candidates only. They were not counted as confirmed drilled holes.",
        }
    )
    if dimension_values:
        result.detected_features.append(
            {"type": "dxf_dimensions", "values": dimension_values[:30], "note": "Dimension text was not assigned to length, width, or height."}
        )
    result.missing_information.append("DXF geometry does not by itself select milling, turning, drilling, or finishing.")
    result.pages = [{"page_number": 1, "width": None, "height": None, "text_excerpt": "\n".join(texts)[:500]}]
    return result


def _dxf_units(document) -> str | None:
    try:
        code = int(document.header.get("$INSUNITS", 0))
    except Exception:
        return None
    if code == 4:
        return "mm"
    if code == 1:
        return "in"
    return None


def extract_image(path: Path) -> ExtractionResult:
    import cv2

    image = cv2.imread(str(path))
    if image is None:
        raise ValueError("The image could not be decoded.")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, h=10)
    threshold = cv2.adaptiveThreshold(denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 8)
    contours, _ = cv2.findContours(threshold, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    significant = [contour for contour in contours if cv2.contourArea(contour) > 400]
    success, encoded = cv2.imencode(".png", threshold)
    preview = encoded.tobytes() if success else None
    text, ocr_method = _ocr_array(threshold)
    result = parse_engineering_text(text, source=path.name, method=ocr_method)
    result.preview_png = preview
    result.detected_features.append(
        {
            "type": "image_regions",
            "contour_count": len(significant),
            "note": "Contour count marks potential drawing regions. It is not a feature or hole count.",
        }
    )
    if ocr_method != "tesseract_ocr":
        result.missing_information.append("OCR engine was unavailable. No specifications were inferred from the image.")
    elif not text.strip():
        result.missing_information.append("OCR returned no text. Dimensions and material were not inferred.")
    return result


def _ocr_array(image) -> tuple[str, str]:
    try:
        import pytesseract
        from PIL import Image

        text = pytesseract.image_to_string(Image.fromarray(image)) or ""
        return text, "tesseract_ocr"
    except Exception as exc:
        logger.info("Image OCR unavailable: %s", exc.__class__.__name__)
        return "", "ocr_unavailable"
