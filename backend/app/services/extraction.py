"""Text interpretation for engineering drawings.

Values are emitted only when a pattern matches. Ambiguous matches stay unset
and are reported as candidates.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MATERIAL_RULES = (
    (re.compile(r"ALUMIN(?:IUM|UM)?[\s\-]*6061|\b6061\b", re.I), "Aluminium 6061"),
    (re.compile(r"ALUMIN(?:IUM|UM)?[\s\-]*7075|\b7075\b", re.I), "Aluminium 7075"),
    (re.compile(r"STAINLESS[\s\-]*STEEL[\s\-]*316|SS[\s\-]*316|SUS[\s\-]*316", re.I), "Stainless Steel 316"),
    (re.compile(r"STAINLESS[\s\-]*STEEL[\s\-]*304|SS[\s\-]*304|SUS[\s\-]*304", re.I), "Stainless Steel 304"),
    (re.compile(r"MILD[\s\-]*STEEL|\bA36\b", re.I), "Mild Steel"),
    (re.compile(r"\bBRASS\b", re.I), "Brass"),
    (re.compile(r"\bCOPPER\b", re.I), "Copper"),
)

AUTOMATIC_CONFIDENCE_CAP = 0.8


@dataclass
class Evidence:
    field_name: str
    value: str
    location: str | None
    method: str
    confidence: float
    source_document: str = ""


@dataclass
class ExtractionResult:
    part_name: str | None = None
    drawing_number: str | None = None
    material: str | None = None
    units: str | None = None
    length: float | None = None
    width: float | None = None
    height: float | None = None
    diameter: float | None = None
    thickness: float | None = None
    tolerances: list[str] = field(default_factory=list)
    surface_finish: str | None = None
    quantity: int | None = None
    manufacturing_notes: list[str] = field(default_factory=list)
    detected_features: list[dict] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    confidence_scores: dict = field(default_factory=dict)
    evidence: list[Evidence] = field(default_factory=list)
    pages: list[dict] = field(default_factory=list)
    preview_png: bytes | None = None


def _cap(confidence: float) -> float:
    return round(min(confidence, AUTOMATIC_CONFIDENCE_CAP), 4)


def _add(result: ExtractionResult, field_name: str, value, confidence: float, method: str, location: str | None) -> None:
    score = _cap(confidence)
    setattr(result, field_name, value)
    result.confidence_scores[field_name] = score
    result.evidence.append(Evidence(field_name, str(value), location, method, score))


def parse_engineering_text(text: str, *, source: str, method: str, location: str | None = None) -> ExtractionResult:
    result = ExtractionResult()
    if not text or not text.strip():
        result.missing_information.append("No text was available to extract specifications from.")
        _base_missing(result)
        return result

    part = re.search(r"PART\s*NAME\s*[:\-]\s*([^\n]{1,80})", text, re.I)
    if part:
        _add(result, "part_name", part.group(1).strip(" -:\t"), 0.7, method, location)

    drawing = re.search(r"(?:DRAWING|DWG)\s*(?:NUMBER|NO\.?|#)?\s*[:\-]\s*([A-Za-z0-9][A-Za-z0-9\-./]{1,40})", text, re.I)
    if drawing:
        _add(result, "drawing_number", drawing.group(1).strip(), 0.7, method, location)

    for pattern, name in MATERIAL_RULES:
        if pattern.search(text):
            _add(result, "material", name, 0.74, method, location)
            break

    has_mm = re.search(r"\bMM\b|MILLIMET", text, re.I) is not None
    has_in = re.search(r"\bINCH(?:ES)?\b", text, re.I) is not None
    if has_mm and has_in:
        result.missing_information.append("Both millimetre and inch unit marks were found. Units were not chosen.")
    elif has_mm:
        _add(result, "units", "mm", 0.66, method, location)
    elif has_in:
        _add(result, "units", "in", 0.66, method, location)

    triples = re.findall(r"(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)", text)
    doubles = re.findall(r"(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)(?!\s*[xX×])", text)
    if len(triples) == 1:
        length, width, height = (float(item) for item in triples[0])
        _add(result, "length", length, 0.66, method, location)
        _add(result, "width", width, 0.66, method, location)
        _add(result, "height", height, 0.66, method, location)
    elif len(triples) > 1:
        result.detected_features.append({"type": "dimension_triples", "values": triples, "note": "Multiple size callouts. None was selected."})
        result.missing_information.append("Multiple length × width × height callouts were found. Confirm the bounding box.")
    elif len(doubles) == 1:
        _add(result, "length", float(doubles[0][0]), 0.55, method, location)
        _add(result, "width", float(doubles[0][1]), 0.55, method, location)
        result.missing_information.append("Only two overall dimensions were found. Height was not set.")
    elif len(doubles) > 1:
        result.detected_features.append({"type": "dimension_pairs", "values": doubles, "note": "Multiple pairs. None was selected."})
        result.missing_information.append("Multiple dimension pairs were found. Confirm length and width.")

    diameters = re.findall(r"(?:Ø|⌀|DIA(?:METER)?\.?)\s*(\d+(?:\.\d+)?)", text, re.I)
    if len(diameters) == 1:
        _add(result, "diameter", float(diameters[0]), 0.6, method, location)
    elif len(diameters) > 1:
        result.detected_features.append({"type": "diameter_callouts", "values": diameters, "note": "Multiple diameters. Primary diameter was not selected."})
        result.missing_information.append("Multiple diameter callouts were found. Confirm the primary diameter if the part is turned.")

    thickness = re.search(r"\bTHICK(?:NESS)?\b\s*[:\-]?\s*(\d+(?:\.\d+)?)", text, re.I)
    if thickness:
        _add(result, "thickness", float(thickness.group(1)), 0.64, method, location)

    tolerances = re.findall(r"[±]\s*\d+(?:\.\d+)?", text)
    tolerances += re.findall(r"\+\d+(?:\.\d+)?\s*/\s*-\d+(?:\.\d+)?", text)
    if tolerances:
        result.tolerances = tolerances
        result.confidence_scores["tolerances"] = _cap(0.7)
        result.evidence.append(Evidence("tolerances", ", ".join(tolerances), location, method, _cap(0.7)))

    finish = re.search(r"\bRA\s*(\d+(?:\.\d+)?)", text, re.I)
    if finish:
        _add(result, "surface_finish", f"Ra {finish.group(1)}", 0.62, method, location)

    quantity = re.search(r"\b(?:QTY|QUANTITY)\b\s*[:\-]?\s*(\d{1,6})\b", text, re.I)
    if quantity:
        _add(result, "quantity", int(quantity.group(1)), 0.68, method, location)

    notes = [item.strip() for item in re.findall(r"\bNOTE\s*\d*\s*[:\-]\s*([^\n]+)", text, re.I)]
    result.manufacturing_notes = [note for note in notes if note]
    if result.manufacturing_notes:
        result.confidence_scores["manufacturing_notes"] = _cap(0.6)
        result.evidence.append(
            Evidence("manufacturing_notes", " | ".join(result.manufacturing_notes), location, method, _cap(0.6))
        )

    for item in result.evidence:
        item.source_document = source
    _base_missing(result)
    return result


def _base_missing(result: ExtractionResult) -> None:
    labels = {
        "part_name": "Part name was not found.",
        "drawing_number": "Drawing number was not found.",
        "material": "Material was not found. It was not guessed.",
        "units": "Units were not found.",
        "quantity": "Quantity was not found.",
    }
    for field_name, message in labels.items():
        if getattr(result, field_name) in (None, "", []):
            if message not in result.missing_information:
                result.missing_information.append(message)
    if result.length is None or result.width is None or result.height is None:
        message = "A complete bounding box (length, width, and height) was not confirmed from the drawing."
        if message not in result.missing_information and not any("bounding box" in item.lower() or "height was not set" in item.lower() for item in result.missing_information):
            result.missing_information.append(message)
    process_note = "Manufacturing process must be confirmed by an engineer. Geometry alone does not determine the process."
    if process_note not in result.missing_information:
        result.missing_information.append(process_note)

