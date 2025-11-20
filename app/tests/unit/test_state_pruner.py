
import pytest
from app.src.utils.state_pruner import generate_success_report
from app.src.specialists.schemas._archiver import SuccessReport
from datetime import datetime

def test_generate_success_report_renders_images():
    report_data = SuccessReport(
        final_user_response="Done",
        routing_history=[],
        artifacts={
            "test_image.png": "base64data",
            "other_file.txt": "text content"
        },
        scratchpad={},
        conversation_summary="Summary",
        timestamp=datetime.now()
    )
    
    report = generate_success_report(report_data)
    
    # Check for image tag
    assert "### 🖼️ test_image.png" in report
    assert "![test_image.png](base64data)" in report
    
    # Check for text block
    assert "### 📄 other_file.txt" in report
    assert "```\ntext content\n```" in report

def test_generate_success_report_detects_base64_string():
    report_data = SuccessReport(
        final_user_response="Done",
        routing_history=[],
        artifacts={
            "unknown_ext_file": "data:image/png;base64,somedata"
        },
        scratchpad={},
        conversation_summary="Summary",
        timestamp=datetime.now()
    )
    
    report = generate_success_report(report_data)
    
    assert "### 🖼️ unknown_ext_file" in report
    assert "![unknown_ext_file](data:image/png;base64,somedata)" in report
