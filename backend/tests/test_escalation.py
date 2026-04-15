import pytest
import json
from unittest.mock import MagicMock, patch
from backend.api.escalation import escalate_session
from backend.session.schema import SessionData

@pytest.fixture
def mock_redis():
    with patch("backend.api.escalation.redis_client") as mock:
        yield mock

@pytest.fixture
def mock_session_mgr():
    with patch("backend.api.escalation.SessionManager") as mock:
        yield mock

def test_escalate_session_new(mock_redis, mock_session_mgr):
    session = SessionData(session_id="s1", user_id="u1", tier="PRO")
    mock_session_mgr.return_value.get_session.return_value = session
    mock_redis.lrange.return_value = [] # Empty queue
    
    res = escalate_session("s1", "reason1")
    
    assert res == {"status": "escalated"}
    mock_redis.rpush.assert_called()
    payload = json.loads(mock_redis.rpush.call_args[0][1])
    assert payload["session_id"] == "s1"
    assert payload["reason"] == "reason1"

def test_escalate_session_duplicate(mock_redis, mock_session_mgr):
    session = SessionData(session_id="s1", user_id="u1", tier="PRO")
    mock_session_mgr.return_value.get_session.return_value = session
    
    # Existing item in queue
    item = json.dumps({"session_id": "s1", "reason": "other"})
    mock_redis.lrange.return_value = [item]
    
    res = escalate_session("s1", "reason2")
    
    assert res == {"status": "already_escalated"}
    mock_redis.rpush.assert_not_called()

def test_escalate_session_not_found(mock_redis, mock_session_mgr):
    mock_session_mgr.return_value.get_session.return_value = None
    
    with pytest.raises(Exception): # FastAPI HTTPException
        escalate_session("s1", "reason1")
