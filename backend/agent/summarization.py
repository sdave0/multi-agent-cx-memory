import os
from langchain_core.prompts import PromptTemplate
from backend.llm.client_factory import LLMClientFactory
from backend.session.manager import SessionManager
from backend.session.schema import SessionData
import time

class SummarizationAgent:
    def __init__(self):
        self.factory = LLMClientFactory()
        self.llm = self.factory.get_client("summarization")
        self.call_delay = self.factory.get_call_delay()
        
        prompt_path = os.path.join(os.path.dirname(__file__), 'prompts', 'summarization.txt')
        with open(prompt_path, 'r') as f:
            base_prompt = f.read()
            
        self.prompt = PromptTemplate.from_template(
            base_prompt + "\n\nUser ID: {user_id}\nHistory:\n{history}\n\nPrevious Note:\n{previous_note}"
        )
        self.chain = self.prompt | self.llm

    def execute_and_save(self, session: SessionData, config: dict = None) -> str:
        manager = SessionManager()
        prev_note = manager.get_state_note(session.user_id) or "None"

        # Selective Context Windowing (last 10 turns) + Clean Serialization
        history = session.message_history
        if len(history) > 10:
            history = history[-10:]

        history_lines = []
        for msg in history:
            role = msg.get('role', 'unknown').upper()
            content = msg.get('content', '')
            history_lines.append(f"[{role}]: {content}")

        history_str = "\n".join(history_lines)

        response = self.chain.invoke({
            "user_id": session.user_id,
            "history": history_str,
            "previous_note": prev_note
        }, config=config)
        
        if self.call_delay > 0:
            time.sleep(self.call_delay)
        
        # Safe content extraction for newer Gemini models (handles string or block list)
        new_note = response.content
        if isinstance(new_note, list):
            # Extract text blocks and join them
            new_note = " ".join([block.get("text", "") for block in new_note if isinstance(block, dict)])
        elif not isinstance(new_note, str):
            new_note = str(new_note)
            
        manager.save_state_note(session.user_id, new_note)
        return new_note
