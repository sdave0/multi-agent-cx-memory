from typing import Dict, Any, TypedDict, List
from langgraph.graph import StateGraph, END
from backend.session.schema import SessionData
import time

class GraphState(TypedDict):
    session: SessionData
    current_input: str
    internal_messages: List[Dict[str, Any]]
    final_output: str
    quality_appraisal: str
    retry_count: int
    tool_results: Dict[str, str]

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from backend.llm.client_factory import LLMClientFactory
from backend.agent.tools import TOOLS_MAP, ToolError
from backend.session.schema import RoutingDecision
from backend.agent.loop_guard import LoopGuard
from backend.agent.context import ContextManager
from backend.agent.memory import MemoryManager
from backend.llm.token_budget import TokenBudgetFilter
from backend.logger import get_logger

logger = get_logger("agent.graph")
loop_guard = LoopGuard(max_retries=2)
context_manager = ContextManager()
memory_manager = MemoryManager()
llm_factory = LLMClientFactory()
call_delay = llm_factory.get_call_delay()
token_filter = TokenBudgetFilter()

def get_tool_result(state: GraphState, tool_name: str, params: Dict[str, Any]) -> str:
    """Helper to execute tools with caching in GraphState and persistence in session history."""
    if 'tool_results' not in state:
        state['tool_results'] = {}
        
    # 1. Check current turn cache (GraphState)
    if tool_name in state['tool_results']:
        logger.info(f"Using turn-cached result for tool: {tool_name}")
        return state['tool_results'][tool_name]
    
    # 2. Check cross-turn history (SessionData)
    # Using json.dumps with sort_keys=True to ensure stable hash-like comparison
    import json
    params_str = json.dumps(params, sort_keys=True) if params else "{}"
    for entry in reversed(state['session'].tool_call_history):
        cached_params = entry.get('params', {})
        cached_params_str = json.dumps(cached_params, sort_keys=True) if cached_params else "{}"
        if entry.get('tool') == tool_name and cached_params_str == params_str:
            logger.info(f"Using cross-turn cached result for tool: {tool_name}")
            result = entry.get('result', '')
            state['tool_results'][tool_name] = result
            return result

    # 3. Execute tool if not cached
    tool = TOOLS_MAP[tool_name]
    if not loop_guard.check_and_increment(tool_name, state['session'].tool_retry_counts):
        logger.warning(f"ToolExhaustedError: {tool_name} retries exceeded")
        return f"ToolExhaustedError: {tool_name} usage limit reached."

    try:
        raw_data = tool.execute(params).data
        result = token_filter.filter(tool_name, raw_data)
        
        # Cache for current turn
        state['tool_results'][tool_name] = result
        
        # Persist for future turns
        state['session'].tool_call_history.append({
            "tool": tool_name,
            "params": params,
            "result": result,
            "timestamp": time.time()
        })
        return result
    except ToolError as e:
        logger.warning(f"ToolError in {tool_name}: {e}")
        return f"Tool Error: {str(e)}"

import json
import os
import re

def load_prompt(name: str) -> str:
    path = os.path.join(os.path.dirname(__file__), "prompts", f"{name}.txt")
    if os.path.exists(path):
        with open(path, "r") as f:
            return f.read().strip()
    return ""

# Patterns applied to raw user input as a safety net when LLM JSON parse fails
# or when the LLM succeeds but omits resolved_entities.
_ENTITY_PATTERNS = [
    ("user_name", re.compile(
        r"(?:my name is|i(?:'m| am)|call me|this is)\s+([A-Za-z]+)",
        re.IGNORECASE
    )),
    ("user_email", re.compile(
        r"[\w.+-]+@[\w-]+\.[\w.]+"
    )),
]

def _extract_entities_regex(text: str) -> dict:
    """Extract well-known entities from raw user text via regex.
    Returns only keys that were actually found."""
    found = {}
    for key, pattern in _ENTITY_PATTERNS:
        m = pattern.search(text)
        if m:
            found[key] = m.group(1) if m.lastindex else m.group(0)
    return found

def concierge_node(state: GraphState, config: RunnableConfig = None):
    logger.info("Executing concierge_node")
    user_input = state['current_input']
    user_id = state['session'].user_id

    # 1. Semantic Memory Search
    # Fetch relevant facts from previous sessions using embeddings
    memories = memory_manager.search_memories(user_id, user_input)
    if memories:
        # Avoid duplicates if we already fetched them this session
        new_mems = [m for m in memories if m not in state['session'].relevant_memories]
        state['session'].relevant_memories.extend(new_mems)

    # 2. Trivial intent classifier (regex/logic bypass)
    TRIVIAL_GREETINGS = {"hi", "hello", "hey", "greetings", "morning", "afternoon", "evening", "sup", "yo"}
    TRIVIAL_ACK = {"thanks", "thank you", "ok", "okay", "yes", "no", "great", "perfect", "awesome", "cool", "understood", "thx"}

    clean_input = user_input.strip().lower().strip("!?.")
    
    # Check for name introduction (e.g., "my name is jonny")
    regex_entities = _extract_entities_regex(user_input)
    is_name_intro = "user_name" in regex_entities and len(clean_input.split()) <= 5
    
    if clean_input in TRIVIAL_GREETINGS or clean_input in TRIVIAL_ACK or is_name_intro:
        intent = "greeting" if clean_input in TRIVIAL_GREETINGS else ("name_introduction" if is_name_intro else "acknowledgment")
        logger.info(f"Trivial intent detected: {intent}. Bypassing LLM.")
        
        # Save name if extracted
        if "user_name" in regex_entities:
            state['session'].resolved_entities.update(regex_entities)
            
        state['session'].routing_decisions.append(RoutingDecision(
            intent=intent, 
            tier=state['session'].tier, 
            specialist="tech_specialist", 
            context_note=f"Trivial {intent} detected by lightweight classifier."
        ))
        return state

    # 3. LLM for intent, entity extraction, and memory formation
    llm = llm_factory.get_client("concierge")

    formatted_context = context_manager.format_for_specialist(state['session'])
    base_prompt = load_prompt("concierge")
    
    system_instruction = (
        f"{base_prompt}\n\n"
        "IMPORTANT:\n"
        "1. In your JSON response, include a 'resolved_entities' object with NEW hard facts (name, email, account_id).\n"
        "2. Include an 'extracted_memories' list (strings) with any NEW semantic facts worth remembering across sessions "
        "(e.g., 'User mentioned their site went down last Tuesday', 'User prefers concise billing summaries'). "
        "Only extract facts that aren't already in the provided context."
    )
    
    prompt = f"Context:\n{formatted_context}\n\nUser input: {user_input}"
    
    try:
        res = llm.invoke([SystemMessage(content=system_instruction), HumanMessage(content=prompt)], config=config)
        
        # 1. Extract raw text from the LLM response (handle strings, dicts, or lists)
        content = res.content
        if isinstance(content, str):
            res_text = content
        elif isinstance(content, list):
            # LangChain sometimes returns a list of content blocks
            res_text = "".join([c.get("text", "") if isinstance(c, dict) else str(c) for c in content])
        elif isinstance(content, dict):
            # Sometimes a single dict with 'text' key
            res_text = content.get("text", str(content))
        else:
            res_text = str(content)
            
        # 2. Aggressive JSON cleaning
        if "```json" in res_text:
            res_text = res_text.split("```json")[1].split("```")[0].strip()
        elif "```" in res_text:
            parts = res_text.split("```")
            if len(parts) >= 3:
                res_text = parts[1].strip()
            else:
                res_text = parts[0].strip()
        
        if "{" in res_text:
            res_text = res_text[res_text.find("{"):res_text.rfind("}")+1]
            
        user_input_lower = user_input.lower()
        try:
            data = json.loads(res_text)
        except json.JSONDecodeError as je:
            logger.error(f"Failed to parse LLM JSON: {je}. Raw: {res_text}")
            # Fallback to simple regex/keyword if JSON fails
            intent = "general"
            specialist = "tech_specialist"
            if "billing" in user_input_lower:
                intent = "billing_inquiry"
                specialist = "billing_specialist"
            data = {"intent": intent, "specialist": specialist, "context_note": "Fallback due to JSON error"}
            
        intent = data.get("intent", "general").lower()
        specialist = data.get("specialist", "tech_specialist")
        context_note = data.get("context_note", "")
        
        # Exact entities (Hard facts)
        new_entities = data.get("resolved_entities", {})
        regex_entities = _extract_entities_regex(user_input)
        merged = {**new_entities, **regex_entities}
        if merged:
            state['session'].resolved_entities.update(merged)
 
        # Semantic memories (Fuzzy facts)
        new_mems = data.get("extracted_memories", [])
        for mem in new_mems:
            if mem not in state['session'].relevant_memories:
                memory_manager.add_memory(user_id, mem)
                state['session'].relevant_memories.append(mem)

    except Exception as e:
        logger.error(f"Failed to process concierge request: {e}. Falling back to simple routing.")
        # Fallback routing
        intent = "billing" if any(k in user_input.lower() for k in ['bill', 'invoice', 'payment']) else "support"
        specialist = "billing_specialist" if intent == "billing" else "tech_specialist"
        context_note = f"Fallback routing used due to error: {str(e)}"
        regex_entities = _extract_entities_regex(user_input)
        if regex_entities:
            state['session'].resolved_entities.update(regex_entities)
            logger.info(f"Regex-extracted entities (fallback): {regex_entities}")

    state['session'].routing_decisions.append(RoutingDecision(
        intent=intent, 
        tier=state['session'].tier, 
        specialist=specialist,
        context_note=context_note
    ))
    return state

def billing_node(state: GraphState, config: RunnableConfig = None):
    logger.info("Executing billing_node")
    llm = llm_factory.get_client("billing_specialist")
    
    # Initialize turn-cache if missing
    if 'tool_results' not in state: state['tool_results'] = {}
    
    # Check if we already have account info in context or resolved_entities
    tool_name = "lookup_account"
    account_info = get_tool_result(state, tool_name, {"account_id": state['session'].user_id})
    
    history_info = ""
    hist_tool_name = "get_billing_history"
    # Only call if the user is asking about history or if we don't have it yet
    user_input_lower = state['current_input'].lower()
    if any(k in user_input_lower for k in ["invoice", "history", "bill", "past"]):
        if state['session'].tier.upper() in ["PRO", "ENTERPRISE"]:
            history_info = get_tool_result(state, hist_tool_name, {"account_id": state['session'].user_id})

    # Multi-intent: if user also asks about outages in the same message, fetch it here
    # rather than forcing a re-route. get_tool_result uses the cross-turn cache so
    # this is free if tech_node already ran it in a previous turn.
    OUTAGE_KEYWORDS = ["outage", "down", "outages", "incident", "status", "disruption"]
    outage_info = ""
    if any(k in user_input_lower for k in OUTAGE_KEYWORDS):
        outage_tool = "check_outage_status"
        outage_info = get_tool_result(state, outage_tool, {})
        logger.info("billing_node: fetched outage status for multi-intent message")

    # Build tool context — include outage block only when relevant
    tool_context = f"Account Info: {account_info}"
    if history_info:
        tool_context += f"\nBilling History: {history_info}"
    if outage_info:
        tool_context += f"\nOutage Status: {outage_info}"
    chat_context = context_manager.format_for_specialist(state['session'])
    
    base_prompt = load_prompt("billing_specialist")
    prompt = f"Chat History & State:\n{chat_context}\n\nTool Context: {tool_context}\n\nUser says: {state['current_input']}. Respond helpfully and succinctly about billing."
    res = llm.invoke([SystemMessage(content=base_prompt), HumanMessage(content=prompt)], config=config)
    if call_delay > 0:
        logger.info(f"Delaying for {call_delay} seconds after billing specialist LLM call.")
        time.sleep(call_delay)
    
    # Handle list-type content safely
    final_text = res.content if isinstance(res.content, str) else str(res.content)
    
    state['final_output'] = final_text
    state['internal_messages'].append({
        "role": "billing_specialist", 
        "content": final_text, 
        "tool": f"{tool_name} & {hist_tool_name}" if history_info else tool_name, 
        "tool_result": tool_context
    })
    return state

def tech_node(state: GraphState, config: RunnableConfig = None):
    logger.info("Executing tech_node")
    llm = llm_factory.get_client("tech_specialist")
    user_input_lower = state['current_input'].lower()
    
    # Initialize turn-cache if missing
    if 'tool_results' not in state: state['tool_results'] = {}
    
    # Only check outage when the user's message contains a technical/outage signal.
    # get_tool_result handles cross-turn caching, so this won't re-call if already fetched.
    tool_name = "check_outage_status"
    OUTAGE_KEYWORDS = ["outage", "down", "error", "slow", "timeout", "issue", "bug", "report", "not working", "broken"]
    if any(k in user_input_lower for k in OUTAGE_KEYWORDS):
        outage_info = get_tool_result(state, tool_name, {})
    else:
        # Fall back to the most recent cached result if available, else skip
        outage_info = next(
            (e.get('result', '') for e in reversed(state['session'].tool_call_history) if e.get('tool') == tool_name),
            "No outage check performed for this query."
        )
            
    ticket_info = ""
    ticket_tool_name = "create_ticket"
    
    # Automatically create a ticket if the user explicitly reports a bug or requests a ticket
    if any(keyword in user_input_lower for keyword in ["ticket", "report", "issue", "bug"]):
        if state['session'].tier.upper() in ["PRO", "ENTERPRISE"]:
            ticket_info = get_tool_result(state, ticket_tool_name, {
                "account_id": state['session'].user_id, 
                "description": state['current_input']
            })
        else:
            ticket_info = "User is on Free tier. Cannot create support tickets. Please direct them to the community forums."

    tool_context = f"Outage Info: {outage_info}\nTicket Status: {ticket_info}" if ticket_info else f"Outage Info: {outage_info}"
    chat_context = context_manager.format_for_specialist(state['session'])
    
    base_prompt = load_prompt("tech_specialist")
    prompt = f"Chat History & State:\n{chat_context}\n\nTool Context: {tool_context}\n\nUser says: {state['current_input']}. Respond helpfully and succinctly about tech support."
    res = llm.invoke([SystemMessage(content=base_prompt), HumanMessage(content=prompt)], config=config)
    if call_delay > 0:
        logger.info(f"Delaying for {call_delay} seconds after tech specialist LLM call.")
        time.sleep(call_delay)
    
    # Handle list-type content safely
    final_text = res.content if isinstance(res.content, str) else str(res.content)

    state['final_output'] = final_text
    state['internal_messages'].append({
        "role": "tech_specialist", 
        "content": final_text, 
        "tool": f"{tool_name} & {ticket_tool_name}" if ticket_info else tool_name, 
        "tool_result": tool_context
    })
    return state

# Intents that are inherently conversational/factual and do not require an LLM quality check.
# Accepting these immediately prevents the RETRY loop pattern that caused specialists to
# emit repeated lines (e.g. a name confirmation running 3 times through the graph).
_FAST_PASS_INTENTS = frozenset({
    "greeting",
    "acknowledgment",
    "general",          # trivial exchanges: name introductions, profile acknowledgments
    "clarification",
})


def quality_node(state: GraphState, config: RunnableConfig = None):
    logger.info("Executing quality_node")

    last_internal = state['internal_messages'][-1] if state['internal_messages'] else {}
    last_msg = last_internal.get('content', '')
    tool_ctx = last_internal.get('tool_result', 'No tools used')
    intent = state['session'].routing_decisions[-1].intent if state['session'].routing_decisions else 'unknown'
    user_q = state['current_input']
    retry_count = state.get('retry_count', 0)

    # ── Guard 1: Explicit human escalation request ────────────────────────────
    if intent == "human_escalation":
        logger.info("Human escalation intent detected by concierge. Bypassing quality check.")
        state['quality_appraisal'] = "escalate"
        return state

    # ── Guard 2: Tool exhaustion ──────────────────────────────────────────────
    if "ToolExhaustedError" in last_msg:
        logger.warning("ToolExhaustedError found in specialist output. Escalating immediately.")
        state['quality_appraisal'] = "escalate"
        return state

    # ── Guard 3: Max retry budget exceeded ────────────────────────────────────
    if retry_count >= 2:
        logger.warning(f"Max specialist retries ({retry_count}) reached. Escalating to preserve LLM quota.")
        state['quality_appraisal'] = "escalate"
        return state

    # ── Fast-pass: skip LLM for trivial/conversational intents ────────────────
    # These exchanges are short by design and a correct-but-brief answer is always
    # acceptable. Running the quality LLM on them was causing unnecessary RETRY loops.
    if intent.lower() in _FAST_PASS_INTENTS:
        logger.info(f"Quality fast-pass: intent '{intent}' is conversational. Marking resolved.")
        state['quality_appraisal'] = "resolved"
        return state

    # ── Full LLM quality evaluation ───────────────────────────────────────────
    llm = llm_factory.get_client("quality_lead")
    # Load system prompt from the authoritative external file so prompt changes
    # don't require a code deployment.
    system_prompt = load_prompt("quality_lead")

    evaluation_prompt = (
        f"User intent: {intent}\n"
        f"User question: {user_q}\n"
        f"Tool data available: {tool_ctx}\n"
        f"Specialist response: {last_msg}\n\n"
        "Apply your evaluation rules and reply with PASS or RETRY on the first line."
    )

    res = llm.invoke(
        [SystemMessage(content=system_prompt), HumanMessage(content=evaluation_prompt)],
        config=config
    )
    if call_delay > 0:
        logger.info(f"Delaying {call_delay}s after quality_lead LLM call.")
        time.sleep(call_delay)

    res_text = res.content if isinstance(res.content, str) else str(res.content)
    # Parse only the first line so that extra reasoning lines don't accidentally
    # contain 'pass' and cause a false positive (e.g. "RETRY\nReasoning: ... bypass ...").
    first_line = res_text.strip().splitlines()[0].lower() if res_text.strip() else ""

    if "pass" in first_line:
        state['quality_appraisal'] = "resolved"
        logger.info("Quality Lead verdict: PASS")
    else:
        state['quality_appraisal'] = "retry"
        state['retry_count'] = retry_count + 1
        # Log full reasoning to server logs — it must never appear in the user-facing chat.
        logger.info(
            f"Quality Lead verdict: RETRY (attempt {state['retry_count']}/2). "
            f"Full response: {res_text.strip()}"
        )

    return state

def router(state: GraphState):
    # Removed call_delay sleep (non-LLM function)
    if state['session'].routing_decisions:
        return state['session'].routing_decisions[-1].specialist
    return "escalate"

def quality_router(state: GraphState):
    # Removed call_delay sleep (non-LLM function)
    appraisal = state.get('quality_appraisal', END)
    if appraisal == "retry" and state['session'].routing_decisions:
        return state['session'].routing_decisions[-1].specialist
    return appraisal

workflow = StateGraph(GraphState)

workflow.add_node("concierge", concierge_node)
workflow.add_node("billing_specialist", billing_node)
workflow.add_node("tech_specialist", tech_node)
workflow.add_node("quality_lead", quality_node)

workflow.set_entry_point("concierge")
workflow.add_conditional_edges("concierge", router, {
    "billing_specialist": "billing_specialist",
    "tech_specialist": "tech_specialist",
    "general": "tech_specialist",   # Catch-all: 'general' intent routes to tech without burning a quality_lead call
    "escalate": "quality_lead"
})
workflow.add_edge("billing_specialist", "quality_lead")
workflow.add_edge("tech_specialist", "quality_lead")
workflow.add_conditional_edges("quality_lead", quality_router, {
    "resolved": END,
    "escalate": END,
    "billing_specialist": "billing_specialist",
    "tech_specialist": "tech_specialist"
})

app = workflow.compile()
