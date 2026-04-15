import pytest
from unittest.mock import MagicMock, patch
from backend.agent.graph import get_tool_result, GraphState
from backend.session.schema import SessionData
from backend.agent.loop_guard import LoopGuard

@pytest.fixture
def mock_tools():
    with patch("backend.agent.graph.TOOLS_MAP") as mock:
        yield mock

@pytest.fixture
def state():
    session = SessionData(session_id="s1", user_id="u1", tier="PRO")
    return {
        "session": session,
        "tool_results": {}
    }

def test_get_tool_result_turn_cache(state, mock_tools):
    state["tool_results"]["test_tool"] = "cached_result"
    result = get_tool_result(state, "test_tool", {})
    assert result == "cached_result"
    mock_tools.__getitem__.assert_not_called()

def test_get_tool_result_cross_turn_cache(state, mock_tools):
    state["session"].tool_call_history.append({
        "tool": "test_tool",
        "params": {"id": 1},
        "result": "cross_turn_result"
    })
    result = get_tool_result(state, "test_tool", {"id": 1})
    assert result == "cross_turn_result"
    assert state["tool_results"]["test_tool"] == "cross_turn_result"
    mock_tools.__getitem__.assert_not_called()

def test_get_tool_result_retry_exhaustion(state, mock_tools):
    # Setup LoopGuard with max_retries=2
    # The actual instance in graph.py has max_retries=2
    from backend.agent.graph import loop_guard
    
    state["session"].tool_retry_counts = {"test_tool": 3}
    result = get_tool_result(state, "test_tool", {})
    assert "ToolExhaustedError" in result
    mock_tools.__getitem__.assert_called_with("test_tool")

def test_loop_guard_logic():
    lg = LoopGuard(max_retries=2)
    counts = {}
    assert lg.check_and_increment("tool1", counts) is True # 0 -> 1
    assert counts["tool1"] == 1
    assert lg.check_and_increment("tool1", counts) is True # 1 -> 2
    assert counts["tool1"] == 2
    # 3rd call should return False because current_count (2) >= max_retries (2)
    assert lg.check_and_increment("tool1", counts) is False
    assert counts["tool1"] == 2
