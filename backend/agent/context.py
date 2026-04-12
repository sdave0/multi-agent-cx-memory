from backend.session.schema import SessionData
from backend.session.manager import SessionManager
from backend.llm.client_factory import LLMClientFactory


class ContextManager:
    def __init__(self):
        factory = LLMClientFactory()
        self.max_history_turns = factory.get_token_limits().get('max_history_turns', 10)

    def format_for_specialist(self, session: SessionData) -> str:
        """
        Builds the full context string injected into every specialist and quality-lead prompt.

        Sections (in order):
          1. Previous-session state note  — omitted if absent or tainted (escalation marker).
          2. Cross-session semantic memories — relevant facts retrieved via embeddings.
          3. Resolved entities (hard facts) — name, email, account_id etc.
          4. Recent tool call results  — most-recent result per tool, newest last.
          5. Current session chat history — last N turns, with agent role labels.
        """
        context: list[str] = []

        # ── 1. State note (cross-session summary) ────────────────────────────────────
        # Defence-in-depth: even if get_state_note is bypassed, never inject a tainted
        # note into a specialist's context window.
        state_note = session.state_note
        if state_note:
            if state_note.startswith(SessionManager._ESCALATION_PREFIX):
                # Tainted note slipped through — silently discard it.
                pass
            else:
                context.append("PREVIOUS SESSION SUMMARY:")
                context.append(state_note)
                context.append("")

        # ── 2. Semantic memories ──────────────────────────────────────────────────────
        if session.relevant_memories:
            context.append("CROSS-SESSION USER CONTEXT (SEMANTIC MEMORY):")
            for mem in session.relevant_memories:
                context.append(f"  - {mem}")
            context.append("")

        # ── 3. Resolved entities ──────────────────────────────────────────────────────
        if session.resolved_entities:
            context.append("RESOLVED ENTITIES (VERIFIED FACTS):")
            for key, val in session.resolved_entities.items():
                context.append(f"  - {key}: {val}")
            context.append("")

        # ── 4. Tool results ───────────────────────────────────────────────────────────
        if session.tool_call_history:
            context.append("RECENT TOOL RESULTS (SOURCE OF TRUTH):")
            # Show the most-recent result for each unique tool, preserving recency order.
            seen_tools: set[str] = set()
            for entry in reversed(session.tool_call_history):
                tool_name = entry.get("tool")
                if tool_name and tool_name not in seen_tools:
                    context.append(f"  [{tool_name}]: {entry.get('result', '')}")
                    seen_tools.add(tool_name)
            context.append("")

        # ── 5. Chat history ───────────────────────────────────────────────────────────
        history = session.message_history
        if len(history) > self.max_history_turns:
            history = history[-self.max_history_turns:]

        context.append("CURRENT SESSION CHAT HISTORY:")
        for msg in history:
            # Use the stored role verbatim (e.g. "billing_specialist", "user") so the LLM
            # sees a meaningful speaker label rather than a generic "ai" tag, which was
            # causing pattern-mirroring (repeated lines) in the previous implementation.
            raw_role = msg.get("role", "unknown")
            display_role = raw_role.replace("_", " ").upper()
            content = msg.get("content", "")
            context.append(f"[{display_role}]: {content}")

        return "\n".join(context)
