import pytest
import json
from unittest.mock import MagicMock, patch
from backend.agent.graph import concierge_node
from backend.session.schema import SessionData
from langchain_core.messages import AIMessage

@patch('backend.agent.graph.get_memory_manager')
@patch('backend.agent.graph.get_llm_factory')
def test_concierge_node_entity_extraction(mock_llm_factory, mock_mem_manager):
    # Mock Memory Manager
    mock_mem_manager.return_value.search_memories.return_value = []
    
    # Mock LLM response
    mock_llm = MagicMock()
    mock_llm_factory.return_value.get_client.return_value = mock_llm
    
    # Simulate a JSON response from the LLM
    mock_llm.invoke.return_value = AIMessage(content='''
    ```json
    {
      "intent": "billing",
      "specialist": "billing_specialist",
      "context_note": "User asking about invoices and mentioned their name.",
      "resolved_entities": {"name": "John"}
    }
    ```
    ''')
    
    state = {
        "session": SessionData(session_id="s1", user_id="u1", tier="PRO"),
        "current_input": "My name is John, show me my invoices",
        "internal_messages": [],
        "tool_results": {}
    }
    
    new_state = concierge_node(state)
    
    assert new_state['session'].resolved_entities.get("name") == "John"
    assert new_state['session'].routing_decisions[-1].intent == "billing"
    assert new_state['session'].routing_decisions[-1].specialist == "billing_specialist"

@patch('backend.agent.graph.get_memory_manager')
@patch('backend.agent.graph.get_llm_factory')
def test_concierge_node_fallback(mock_llm_factory, mock_mem_manager):
    # Mock Memory Manager
    mock_mem_manager.return_value.search_memories.return_value = []
    
    # Mock LLM to fail
    mock_llm = MagicMock()
    mock_llm_factory.return_value.get_client.return_value = mock_llm
    mock_llm.invoke.side_effect = Exception("LLM Error")
    
    state = {
        "session": SessionData(session_id="s1", user_id="u1", tier="PRO"),
        "current_input": "invoice",
        "internal_messages": [],
        "tool_results": {}
    }
    
    new_state = concierge_node(state)
    
    # Should fallback to keyword matching
    assert new_state['session'].routing_decisions[-1].intent == "billing"
