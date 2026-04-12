from backend.llm.client_factory import LLMClientFactory
from backend.logger import get_logger

logger = get_logger("llm.token_budget")

def estimate_tokens(text: str) -> int:
    return len(text) // 4

class TokenBudgetFilter:
    def __init__(self):
        self.factory = LLMClientFactory()
        self.limits = self.factory.get_token_limits()
        self.threshold = self.limits.get("tool_result_summarization_threshold", 800)

    def filter(self, tool_name: str, raw_result: str) -> str:
        if estimate_tokens(raw_result) <= self.threshold:
            return raw_result
        
        logger.info(f"Tool {tool_name} result exceeds token threshold ({self.threshold} tokens). Truncating...")
        # Simple truncation: slice last N chars (approximate 1 token = 4 chars)
        max_chars = self.threshold * 4
        truncated_result = raw_result[-max_chars:]
        return f"... [TRUNCATED] ...\n{truncated_result}"
