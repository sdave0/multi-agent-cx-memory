from typing import Dict, Any

class LoopGuard:
    def __init__(self, max_retries: int = 2):
        self.max_retries = max_retries

    def check_and_increment(self, tool_name: str, retry_counts: Dict[str, int]) -> bool:
        current_count = retry_counts.get(tool_name, 0)
        if current_count >= self.max_retries:
            return False
        retry_counts[tool_name] = current_count + 1
        return True
