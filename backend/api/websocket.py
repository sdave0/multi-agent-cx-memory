from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, Any, Optional
from backend.session.manager import SessionManager, redis_client
from backend.session.lock import SessionLock
from backend.logger import get_logger
from langfuse.langchain import CallbackHandler
from langchain_core.runnables import RunnableConfig
from backend.auth import decode_access_token
from backend.agent.summarization import SummarizationAgent
import traceback
import json

logger = get_logger("api.websocket")

router = APIRouter()
active_connections: Dict[str, WebSocket] = {}
summarizer = SummarizationAgent()

class ConnectionManager:
    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        active_connections[session_id] = websocket
        logger.info(f"WebSocket connected: {session_id}")

    def disconnect(self, session_id: str):
        if session_id in active_connections:
            del active_connections[session_id]
            logger.info(f"WebSocket disconnected: {session_id}")

    async def emit_event(self, session_id: str, event_type: str, payload: Dict[str, Any]):
        if session_id in active_connections:
            try:
                await active_connections[session_id].send_json({
                    "type": event_type,
                    **payload
                })
            except Exception as e:
                logger.error(f"Error emitting event {event_type} to {session_id}: {e}", exc_info=True)

manager = ConnectionManager()

@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str, token: Optional[str] = None):
    # If token is not provided as query param, client might send it as first message
    if not token:
        await websocket.accept()
        await websocket.close(code=4001, reason="Authentication token missing")
        return

    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
    except Exception as e:
        await websocket.accept()
        await websocket.close(code=4002, reason=f"Invalid token: {str(e)}")
        return

    await manager.connect(websocket, session_id)
    
    # Initialize or get session once on connect
    sess_mgr = SessionManager()
    session = sess_mgr.get_session(session_id)
    
    # Ownership Check: If session exists, ensure it belongs to this user
    if session and session.user_id != user_id:
        await manager.emit_event(session_id, "error", {"message": "Unauthorized access to session"})
        manager.disconnect(session_id)
        await websocket.close(code=4003)
        return

    if not session:
        from backend.session.schema import SessionData
        from backend.db.models import SessionLocal, Account
        
        db = SessionLocal()
        try:
            user = db.query(Account).filter(Account.id == user_id).first()
            tier = user.plan.upper() if user else "PRO"
        except Exception as e:
            logger.error(f"Error fetching user: {e}")
            tier = "PRO"
        finally:
            db.close()
            
        session = SessionData(session_id=session_id, user_id=user_id, tier=tier)
        session.state_note = sess_mgr.get_state_note(user_id)
        sess_mgr.save_session(session)
    
    # Emit session info for sidebar initialization
    await manager.emit_event(session_id, "session_info", {
        "user_id": session.user_id,
        "tier": session.tier
    })

    try:
        while True:
            data = await websocket.receive_json()
            # Refresh session object from Redis to pick up any external changes (like HITL takeover)
            session = sess_mgr.get_session(session_id) or session
            
            if session.mode == "human":
                await manager.emit_event(session_id, "human_takeover", {"message": "Agent relay mode."})
                continue
            
            input_text = data.get("text", "")
            logger.info(f"Received message for session {session_id}: {input_text}")
            
            session.message_history.append({"role": "user", "content": input_text})
            
            try:
                with SessionLock(session_id):
                    from backend.agent.graph import app as graph_app
                    
                    langfuse_handler = CallbackHandler()
                    
                    state = {
                        "session": session,
                        "current_input": input_text,
                        "internal_messages": [],
                        "final_output": "",
                        "retry_count": 0
                    }
                    
                    final_appraisal = "UNKNOWN"
                    final_ai_message = ""
                    last_agent_role = "ai"
                    
                    config: RunnableConfig = {
                        "recursion_limit": 10,
                        "callbacks": [langfuse_handler],
                        "metadata": {
                            "langfuse_session_id": session_id,
                            "langfuse_user_id": session.user_id,
                            "langfuse_tags": [session.tier, "websocket"]
                        }
                    }
                    
                    async for event in graph_app.astream_events(state, config=config, version="v2"):
                        kind = event["event"]
                        tags = event.get("tags", [])
                        
                        if kind == "on_chat_model_stream":
                            content = event["data"]["chunk"].content
                            if content:
                                if not isinstance(content, str):
                                    if isinstance(content, list):
                                        content = "".join([c.get("text", "") if isinstance(c, dict) else str(c) for c in content])
                                    else:
                                        content = str(content)
                                
                                agent_role = None
                                for t in tags:
                                    if t in ["billing_specialist", "tech_specialist"]:
                                        agent_role = t
                                        break
                                
                                if agent_role:
                                    display_label = agent_role.replace("_", " ").upper()
                                    last_agent_role = agent_role
                                    await manager.emit_event(session_id, "token", {"data": content, "agent": display_label})
                                    final_ai_message += content

                        elif kind == "on_tool_start":
                            await manager.emit_event(session_id, "tool_start", {"tool": event["name"]})
                        
                        elif kind == "on_tool_end":
                            await manager.emit_event(session_id, "tool_end", {"result": event["data"].get("output")})

                        elif kind == "on_chain_end":
                            node_name = event.get("metadata", {}).get("langgraph_node")
                            output = event.get("data", {}).get("output")
                            
                            if not node_name or not output or not isinstance(output, dict):
                                continue

                            if node_name == "concierge" and "session" in output:
                                try:
                                    decision = output['session'].routing_decisions[-1]
                                    await manager.emit_event(session_id, "routing_decision", {"info": f"Routing to {decision.specialist.replace('_', ' ').title()}..."})
                                except (KeyError, IndexError):
                                    pass
                            
                            elif node_name == "quality_lead":
                                final_appraisal = output.get('quality_appraisal', "UNKNOWN")
                                logger.info(f"Quality Lead verdict: {final_appraisal.upper()}")

                                if final_appraisal == "retry":
                                    await manager.emit_event(session_id, "retry_clear", {
                                        "agent": last_agent_role.replace("_", " ").upper()
                                    })
                                    final_ai_message = ""

                                elif final_appraisal == "escalate":
                                    sess_mgr.taint_state_note(session.user_id)
                                    from backend.api.escalation import escalate_session
                                    escalate_session(session_id, "Automated escalation triggered by Quality Lead.")
                                    await manager.emit_event(session_id, "escalation", {
                                        "reason": "Quality assurance threshold not met.",
                                        "ticket": f"ESC-{session_id[-4:]}"
                                    })
                                    session.mode = "human"
                                    sess_mgr.save_session(session)
                                    logger.info(f"Escalation complete for {session_id}. Terminating turn processing.")
                                    break
                            
                            elif node_name in ["billing_specialist", "tech_specialist"]:
                                await manager.emit_event(session_id, "token", {"data": "\n\n", "agent": node_name.replace("_", " ").upper()})

                    if session.mode != "human" and final_ai_message:
                        session.message_history.append({"role": last_agent_role, "content": final_ai_message})
                    
                    sess_mgr.save_session(session)
                    await manager.emit_event(session_id, "response_end", {"confidence": 0.95})
            except Exception as e:
                logger.error(f"Error during graph execution for session {session_id}: {e}", exc_info=True)
                await manager.emit_event(session_id, "error", {"message": "An internal error occurred during processing."})

    except WebSocketDisconnect:
        if session.mode != "human" and len(session.message_history) > 4:
            try:
                import asyncio
                # Offload to a background thread to prevent blocking the async event loop
                asyncio.create_task(asyncio.to_thread(summarizer.execute_and_save, session))
                logger.info(f"Background summarization task dispatched for {session_id} on disconnect.")
            except Exception as e:
                logger.error(f"Failed to dispatch final summary for {session_id}: {e}")
        
        manager.disconnect(session_id)
    except Exception as e:
        logger.error(f"Unexpected WebSocket error for session {session_id}: {e}", exc_info=True)
        manager.disconnect(session_id)
