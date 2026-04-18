import pytest
from unittest.mock import MagicMock, patch
from backend.session.manager import SessionManager

@pytest.fixture
def mock_redis():
    with patch("backend.session.manager.redis_client") as mock:
        yield mock

def test_get_state_note_not_exists(mock_redis):
    mock_redis.get.return_value = None
    assert SessionManager.get_state_note("user123") is None
    mock_redis.get.assert_called_with("user_state:user123")

def test_get_state_note_exists_clean(mock_redis):
    mock_redis.get.return_value = "This is a clean note"
    assert SessionManager.get_state_note("user123") == "This is a clean note"

def test_get_state_note_exists_tainted(mock_redis):
    mock_redis.get.return_value = "[ESCALATED] This is a tainted note"
    # Should return None because it's tainted
    assert SessionManager.get_state_note("user123") is None

def test_taint_state_note_new(mock_redis):
    mock_redis.get.return_value = None
    SessionManager.taint_state_note("user123")
    # Should write the bare prefix
    mock_redis.setex.assert_called_with("user_state:user123", 2592000, "[ESCALATED] ")

def test_taint_state_note_existing(mock_redis):
    mock_redis.get.return_value = "Existing note"
    SessionManager.taint_state_note("user123")
    # Should prefix existing note
    mock_redis.setex.assert_called_with("user_state:user123", 2592000, "[ESCALATED] Existing note")

def test_taint_state_note_already_tainted(mock_redis):
    mock_redis.get.return_value = "[ESCALATED] already"
    SessionManager.taint_state_note("user123")
    # Should not call setex again
    mock_redis.setex.assert_not_called()
