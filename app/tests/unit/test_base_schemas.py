# Audited on Sept 23, 2025
# app/tests/specialists/schemas/test_base_schemas.py
import pytest
from pydantic import BaseModel, ValidationError
from app.src.specialists.schemas import SpecialistOutput, StatusEnum, WebContent

def test_specialist_output_success():
    """Tests successful creation of a SpecialistOutput with a payload."""
    payload_data = WebContent(html_document="<html></html>")
    output = SpecialistOutput[WebContent](
        status=StatusEnum.SUCCESS,
        rationale="Generated HTML successfully.",
        payload=payload_data
    )
    assert output.status == StatusEnum.SUCCESS
    assert output.rationale == "Generated HTML successfully."
    assert isinstance(output.payload, WebContent)
    assert output.payload.html_document == "<html></html>"

def test_specialist_output_failure():
    """Tests creation of a SpecialistOutput for a failure case with no payload."""
    output = SpecialistOutput(
        status=StatusEnum.FAILURE,
        rationale="Could not generate content due to safety filters."
    )
    assert output.status == StatusEnum.FAILURE
    assert output.payload is None

def test_specialist_output_missing_fields():
    """Tests that Pydantic validation catches missing required fields."""
    with pytest.raises(ValidationError):
        # Missing 'status' and 'rationale'
        SpecialistOutput()
