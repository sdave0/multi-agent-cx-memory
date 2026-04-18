import pytest
from backend.session.schema import SessionData
from backend.agent.context import ContextManager

def test_format_for_specialist_includes_tools():
    cm = ContextManager()
    session = SessionData(
        session_id="sess_123",
        user_id="acct_063e26f3",
        tier="ENTERPRISE",
        resolved_entities={"name": "John"},
        tool_call_history=[
            {"tool": "check_outage_status", "result": "API Gateway P2 outage", "timestamp": 12345},
            {"tool": "lookup_account", "result": "Acme Corp", "timestamp": 12346}
        ]
    )
    
    formatted = cm.format_for_specialist(session)
    
    # Check for Entities
    assert "RESOLVED ENTITIES (VERIFIED FACTS):" in formatted
    assert "  - name: John" in formatted
    
    # Check for Tools
    assert "RECENT TOOL RESULTS (SOURCE OF TRUTH):" in formatted
    assert "  [check_outage_status]: API Gateway P2 outage" in formatted
    assert "  [lookup_account]: Acme Corp" in formatted

def test_tool_deduplication():
    cm = ContextManager()
    session = SessionData(
        session_id="sess_123",
        user_id="acct_063e26f3",
        tier="ENTERPRISE",
        tool_call_history=[
            {"tool": "check_outage_status", "result": "OLD OUTAGE", "timestamp": 100},
            {"tool": "check_outage_status", "result": "NEW OUTAGE", "timestamp": 200}
        ]
    )
    
    formatted = cm.format_for_specialist(session)
    assert "NEW OUTAGE" in formatted
    assert "OLD OUTAGE" not in formatted
