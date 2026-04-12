import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.session.manager import SessionManager, redis_client
from backend.logger import get_logger

logger = get_logger("api.escalation")

router = APIRouter()

ESCALATION_QUEUE_KEY = "escalation:queue"

class TakeoverRequest(BaseModel):
    session_id: str
    agent_id: str

class AgentMessage(BaseModel):
    text: str
    agent_id: str

@router.post("/agent-message/{session_id}")
async def send_agent_message(session_id: str, req: AgentMessage):
    logger.info(f"Agent {req.agent_id} sending message to session {session_id}")
    try:
        sess_mgr = SessionManager()
        session = sess_mgr.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
            
        if session.mode != "human":
             raise HTTPException(status_code=400, detail="Session is not in human mode")

        # Save to history
        session.message_history.append({"role": "agent", "content": req.text, "agent_id": req.agent_id})
        sess_mgr.save_session(session)
        
        # Push to customer WS
        try:
            from backend.api.websocket import manager as ws_manager
            await ws_manager.emit_event(
                session_id,
                "token",
                {"data": req.text, "agent": "HUMAN AGENT"}
            )
            # Send an extra token for newline/end
            await ws_manager.emit_event(
                session_id,
                "token",
                {"data": "\n\n", "agent": "HUMAN AGENT"}
            )
            await ws_manager.emit_event(session_id, "response_end", {})
        except Exception as ws_err:
            logger.error(f"Failed to push agent message to WS: {ws_err}")
            
        return {"status": "sent"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending agent message: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.get("/sessions")
def list_sessions():
    """Lists all active session metadata for the Logs page (scalable lookup)."""
    try:
        sess_mgr = SessionManager()
        session_ids = sess_mgr.list_all_session_ids()
        sessions = []
        
        for session_id in session_ids:
            data = redis_client.get(f"session:{session_id}")
            if data:
                try:
                    s = json.loads(data)
                    # Outcome logic based on current state
                    outcome = "Resolved"
                    if s.get("mode") == "human":
                        outcome = "Escalated"
                    elif any(d.get("intent") == "escalate" for d in s.get("routing_decisions", [])):
                        outcome = "Escalated"
                    
                    sessions.append({
                        "session_id": s.get("session_id"),
                        "user_id": s.get("user_id"),
                        "tier": s.get("tier"),
                        "turns": len(s.get("message_history", [])),
                        "specialist": s["routing_decisions"][-1].get("specialist", "None") if s.get("routing_decisions") else "None",
                        "outcome": outcome,
                        "last_active": s.get("routing_decisions")[-1].get("timestamp") if s.get("routing_decisions") else None
                    })
                except Exception as parse_err:
                    logger.warning(f"Failed to parse session {session_id}: {parse_err}")
            else:
                # Key expired but ID remains in the set - cleanup can happen periodically or here
                # To keep it simple, we just ignore expired sessions in the view
                pass
        
        # Sort newest first
        sessions.sort(key=lambda x: x["session_id"], reverse=True)
        return {"sessions": sessions}
    except Exception as e:
        logger.error(f"Error listing sessions: {e}")
        return {"sessions": [], "error": str(e)}

@router.get("/session/{session_id}")
def get_session_detail(session_id: str):
    """Returns full session data for a specific session."""
    try:
        sess_mgr = SessionManager()
        session = sess_mgr.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return session.model_dump()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.get("/queue")
def get_escalation_queue():
    try:
        items = redis_client.lrange(ESCALATION_QUEUE_KEY, 0, -1)
        queue = [json.loads(item) for item in items]
        return {"queue": queue}
    except Exception as e:
        logger.error(f"Error fetching escalation queue: {e}")
        return {"queue": [], "error": str(e)}

@router.post("/escalate/{session_id}")
def escalate_session(session_id: str, reason: str):
    logger.info(f"Received escalation request for session {session_id}. Reason: {reason}")
    try:
        sess_mgr = SessionManager()
        session = sess_mgr.get_session(session_id)
        if not session:
            logger.warning(f"Escalation failed: Session {session_id} not found.")
            raise HTTPException(status_code=404, detail="Session not found")
            
        payload = {
            "session_id": session_id,
            "reason": reason,
            "tier": session.tier
        }
        
        # Check if already in queue to avoid duplicates
        existing_items = redis_client.lrange(ESCALATION_QUEUE_KEY, 0, -1)
        for item in existing_items:
            if json.loads(item)["session_id"] == session_id:
                logger.info(f"Session {session_id} already in escalation queue.")
                return {"status": "already_escalated"}

        redis_client.rpush(ESCALATION_QUEUE_KEY, json.dumps(payload))
        logger.info(f"Session {session_id} escalated successfully (FIFO).")
        return {"status": "escalated"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during escalation for session {session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.post("/resolve/{session_id}")
async def resolve_session(session_id: str):
    """
    Called when a human agent finishes assisting. 
    Flips the session back to AI mode and triggers a final summary.
    """
    logger.info(f"Resolving session {session_id}")
    try:
        sess_mgr = SessionManager()
        session = sess_mgr.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # 1. Flip mode back to AI (or 'resolved' state if preferred)
        session.mode = "ai"
        
        # 2. Trigger final summarization so the NEXT session has the human's resolution context
        try:
            from backend.agent.summarization import SummarizationAgent
            summarizer = SummarizationAgent()
            # This will overwrite the [ESCALATED] taint with a clean resolution summary
            new_note = summarizer.execute_and_save(session)
            session.state_note = new_note
            logger.info(f"Human interaction summarized for {session_id}.")
        except Exception as sum_err:
            logger.error(f"Failed to summarize human resolution for {session_id}: {sum_err}")

        sess_mgr.save_session(session)

        # 3. Notify customer
        try:
            from backend.api.websocket import manager as ws_manager
            await ws_manager.emit_event(
                session_id,
                "token",
                {"data": "\n\n**This session has been resolved by our team.** I am back to assist you with any further automated queries.", "agent": "SYSTEM"}
            )
        except: pass

        return {"status": "resolved"}
    except Exception as e:
        logger.error(f"Error resolving session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.post("/takeover")
async def takeover_session(req: TakeoverRequest):
    logger.info(f"Received takeover request for session {req.session_id} by agent {req.agent_id}")
    try:
        sess_mgr = SessionManager()
        session = sess_mgr.get_session(req.session_id)
        if not session:
            logger.warning(f"Takeover failed: Session {req.session_id} not found.")
            raise HTTPException(status_code=404, detail="Session not found")
            
        session.mode = "human"
        sess_mgr.save_session(session)
        
        # Remove from Redis queue
        items = redis_client.lrange(ESCALATION_QUEUE_KEY, 0, -1)
        for item in items:
            if json.loads(item)["session_id"] == req.session_id:
                redis_client.lrem(ESCALATION_QUEUE_KEY, 0, item)

        # Local import breaks the circular dependency (websocket.py imports escalate_session).
        try:
            from backend.api.websocket import manager as ws_manager
            await ws_manager.emit_event(
                req.session_id,
                "human_takeover",
                {"message": "A human agent has joined the session. You are now connected to our expert support team."}
            )
            logger.info(f"Pushed human_takeover event to session {req.session_id}.")
        except Exception as push_err:
            # Non-fatal: session is already in human mode even if WS push fails
            logger.warning(f"Could not push human_takeover to session {req.session_id}: {push_err}")
        
        logger.info(f"Session {req.session_id} successfully taken over by human agent {req.agent_id}.")
        return {"status": "success", "mode": "human"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during takeover for session {req.session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")

