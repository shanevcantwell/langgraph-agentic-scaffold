# app/tests/specialists/schemas/test_base_schemas.py
import pytest
from pydantic import BaseModel, ValidationError
from app.src.specialists.schemas import SpecialistOutput, StatusEnum, WebContent

class AnotherMockPayload(BaseModel):
    """A different payload for testing."""
    item_id: int

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

@pytest.mark.parametrize("status", [
    StatusEnum.PENDING,
    StatusEnum.SELF_CORRECTING
])
def test_specialist_output_other_statuses(status):
    """Tests other status enums."""
    output = SpecialistOutput(status=status, rationale="In progress")
    assert output.status == status
    assert output.payload is None

def test_specialist_output_with_different_payload_type():
    """Tests that the generic SpecialistOutput works with different payload types."""
    payload_data = AnotherMockPayload(item_id=123)
    output = SpecialistOutput[AnotherMockPayload](
        status=StatusEnum.SUCCESS,
        rationale="Found item.",
        payload=payload_data
    )
    assert isinstance(output.payload, AnotherMockPayload)
    assert output.payload.item_id == 123

def test_specialist_output_allows_empty_rationale():
    """Tests that an empty string is a valid rationale."""
    output = SpecialistOutput(status=StatusEnum.SUCCESS, rationale="")
    assert output.rationale == ""

def test_specialist_output_success_with_none_payload():
    """Tests that a SUCCESS status can have a None payload."""
    output = SpecialistOutput(status=StatusEnum.SUCCESS, rationale="Operation complete, no data returned.")
    assert output.status == StatusEnum.SUCCESS
    assert output.payload is None

def test_web_content_schema_validation():
    """Explicitly tests the WebContent schema."""
    # Success
    content = WebContent(html_document="<p>Hello</p>")
    assert content.html_document == "<p>Hello</p>"

    # Failure (missing field)
    with pytest.raises(ValidationError):
        WebContent()
