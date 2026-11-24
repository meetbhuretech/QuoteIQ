"""Feature contract and extraction behaviour."""

from pathlib import Path

import ezdxf
import fitz

from app.domain.constants import FEATURE_COLUMNS
from app.services.extraction import parse_engineering_text
from app.services.features import build_features
from app.services.processors import extract_dxf, extract_image, extract_pdf


def test_feature_contract_excludes_price_and_matches_training_spec():
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[2] / "ml"))
    from quoteiq_ml.spec import FEATURE_COLUMNS as training_columns

    assert FEATURE_COLUMNS == training_columns
    assert "unit_price" not in FEATURE_COLUMNS
    inference = Path("app/services/inference.py").read_text()
    assert "GENERATOR_PRICE" not in inference
    assert "quoteiq_ml.train" not in inference
    assert "quoteiq_ml.synthetic" not in inference


def test_features_are_not_imputed():
    features, missing, _ = build_features(
        material_category="aluminium",
        density=2.7,
        units="mm",
        length=120,
        width=80,
        height=None,
        quantity=10,
        process="milling",
        machine_category="milling",
        hole_count=None,
        feature_count=4,
        tolerance_count=1,
        finishing_required=False,
        setup_complexity=None,
        volume_cm3=None,
        stock_fill_ratio=1,
    )
    assert features is None
    assert "bounding_box_dimensions" in missing
    assert "hole_count" in missing


def test_confirmed_box_uses_visible_bounding_surface():
    features, missing, assumptions = build_features(
        material_category="aluminium",
        density=2.7,
        units="mm",
        length=100,
        width=50,
        height=20,
        quantity=5,
        process="milling",
        machine_category="milling",
        hole_count=0,
        feature_count=2,
        tolerance_count=0,
        finishing_required=False,
        setup_complexity=3,
        volume_cm3=None,
        stock_fill_ratio=1,
    )
    assert missing == []
    assert features["volume_cm3"] == 100
    assert features["surface_area_cm2"] == 160
    assert any("bounding-box surface" in note for note in assumptions)


def test_parser_extracts_only_present_values():
    text = """
    PART NAME: BRACKET
    DRAWING NUMBER: BR-100
    MATERIAL: ALUMINIUM 6061
    UNITS: MM
    QTY: 12
    120 x 80 x 25
    DIA 10
    ±0.1
    NOTE: DEBURR EDGES
    """
    result = parse_engineering_text(text, source="bracket.pdf", method="test")
    assert result.part_name == "BRACKET"
    assert result.drawing_number == "BR-100"
    assert result.material == "Aluminium 6061"
    assert result.units == "mm"
    assert result.quantity == 12
    assert (result.length, result.width, result.height) == (120, 80, 25)
    assert result.diameter == 10
    assert result.tolerances == ["±0.1"]
    assert result.surface_finish is None
    assert all(item.confidence <= 0.8 for item in result.evidence)


def test_parser_does_not_invent_from_empty_notes():
    result = parse_engineering_text("SEE NOTES", source="empty.pdf", method="test")
    assert result.material is None
    assert result.length is None
    assert result.diameter is None
    assert any("not guessed" in item for item in result.missing_information)


def test_multiple_diameters_stay_unset():
    result = parse_engineering_text("DIA 10\nDIA 20", source="holes.pdf", method="test")
    assert result.diameter is None
    assert any(feature["type"] == "diameter_callouts" for feature in result.detected_features)


def test_pdf_and_dxf_processors(tmp_path: Path):
    pdf_path = tmp_path / "bracket.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_textbox(fitz.Rect(40, 40, 400, 300), "PART NAME: BRACKET\nMATERIAL: MILD STEEL\nUNITS: MM\n120 x 80 x 25\nQTY: 4")
    document.save(pdf_path)
    document.close()
    pdf_result = extract_pdf(pdf_path)
    assert pdf_result.material == "Mild Steel"
    assert pdf_result.length == 120
    assert pdf_result.preview_png is not None

    dxf_path = tmp_path / "plate.dxf"
    drawing = ezdxf.new()
    drawing.header["$INSUNITS"] = 4
    space = drawing.modelspace()
    space.add_line((0, 0), (100, 0))
    space.add_line((100, 0), (100, 50))
    space.add_line((100, 50), (0, 50))
    space.add_line((0, 50), (0, 0))
    for center in ((10, 10), (20, 10), (30, 10)):
        space.add_circle(center, 2)
    drawing.saveas(dxf_path)
    dxf_result = extract_dxf(dxf_path)
    assert dxf_result.diameter is None
    assert dxf_result.length == 100
    assert dxf_result.width == 50
    assert dxf_result.height is None
    entities = next(feature for feature in dxf_result.detected_features if feature["type"] == "dxf_entities")
    assert entities["circle_entities"] == 3
    assert dxf_result.units == "mm"


def test_blank_image_does_not_invent_dimensions(tmp_path: Path):
    import cv2
    import numpy as np

    image_path = tmp_path / "blank.png"
    cv2.imwrite(str(image_path), np.full((80, 80, 3), 255, dtype=np.uint8))
    result = extract_image(image_path)
    assert result.length is None
    assert result.material is None
    assert any(feature["type"] == "image_regions" for feature in result.detected_features)
