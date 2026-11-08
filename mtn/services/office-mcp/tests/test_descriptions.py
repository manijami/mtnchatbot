"""The worked example in each tool description must pass the server's own strict validation."""
import json

import pytest

from office_mcp.schemas import PresentationSpec, SheetSpec, WordDocumentSpec
from office_mcp.tools import registry


def _first_json_object(text: str, marker: str) -> dict:
    start = text.index("{", text.index(marker))
    depth = 0
    for i, ch in enumerate(text[start:], start=start):
        depth += ch == "{"
        depth -= ch == "}"
        if depth == 0:
            return json.loads(text[start : i + 1])
    raise AssertionError("unterminated example")


@pytest.mark.parametrize(
    "tool,marker,model",
    [
        ("create_word_document", "Example", WordDocumentSpec),
        ("create_powerpoint_presentation", "Example", PresentationSpec),
        ("create_excel_workbook", "Example sheet", SheetSpec),
    ],
)
def test_description_examples_are_valid(tool, marker, model):
    example = _first_json_object(registry[tool].definition.description, marker)
    if model is PresentationSpec:
        example["target_slides"] = len(example["slides"]) + 1
    model.model_validate(example)


def test_revise_example_uses_visible_slide_paths():
    example = _first_json_object(registry["revise_office_file"].definition.description, "Example")
    paths = [c["path"] for c in example["changes"]]
    assert paths == ["/slide/2/bullets", "/slide/5/chart", "/slide/5/table"]
