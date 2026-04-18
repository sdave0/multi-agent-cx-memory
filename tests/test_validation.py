import pytest
from backend.session.schema import SessionData

def test_poisoned_data():
    """Checks that SessionData correctly handles state_note when it arrives as a list of components."""
    
    # Simulate the raw data that was causing the crash during the early prototyping phase
    poisoned_raw = {
        "session_id": "sess_test",
        "user_id": "user_123",
        "tier": "PRO",
        "state_note": [
            {"type": "text", "text": "The user has a billing issue."},
            {"type": "text", "text": "Investigation is ongoing."}
        ]
    }
    
    # This correctly validates because of our custom validator in SessionData
    session = SessionData.model_validate(poisoned_raw)
    assert session.state_note == "The user has a billing issue. Investigation is ongoing."
