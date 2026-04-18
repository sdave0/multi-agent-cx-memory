import pytest
from unittest.mock import MagicMock, patch
from backend.llm.token_budget import TokenBudgetFilter, estimate_tokens

def test_estimate_tokens():
    # 4 chars per token approx
    assert estimate_tokens("1234") == 1
    assert estimate_tokens("12345678") == 2
    assert estimate_tokens("") == 0

@pytest.fixture
def mock_factory():
    with patch("backend.llm.token_budget.LLMClientFactory") as mock:
        factory_instance = mock.return_value
        factory_instance.get_token_limits.return_value = {"tool_result_summarization_threshold": 10}
        yield factory_instance

def test_token_budget_filter_no_truncation(mock_factory):
    filter = TokenBudgetFilter()
    # 40 chars should be 10 tokens
    short_text = "a" * 40
    assert filter.filter("test_tool", short_text) == short_text

def test_token_budget_filter_with_truncation(mock_factory):
    filter = TokenBudgetFilter()
    # 80 chars should be 20 tokens, threshold is 10
    long_text = "abcdefgh" * 10
    result = filter.filter("test_tool", long_text)
    
    assert "[TRUNCATED]" in result
    # Threshold 10 means approx 40 chars kept
    # Our implementation uses raw_result[-max_chars:]
    assert len(result.split("\n")[1]) == 40
    assert result.endswith("abcdefgh" * 5)
