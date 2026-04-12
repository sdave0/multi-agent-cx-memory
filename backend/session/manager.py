import redis
import os
from typing import Optional
from backend.session.schema import SessionData
from backend.logger import get_logger

logger = get_logger("session.manager")

redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
redis_client = redis.Redis.from_url(redis_url, decode_responses=True)


class SessionManager:
    SESSION_TTL = 86400  # 24 hours

    # Prefix used to mark state notes that should not be surfaced to new sessions.
    # Human-readable in Redis inspection and guaranteed not to appear in LLM-generated notes.
    _ESCALATION_PREFIX = "[ESCALATED] "
    _ALL_SESSIONS_KEY = "sessions:active"

    @staticmethod
    def get_session(session_id: str) -> Optional[SessionData]:
        try:
            data = redis_client.get(f"session:{session_id}")
            if data:
                return SessionData.model_validate_json(data)
        except redis.RedisError as e:
            logger.error(f"Redis error getting session {session_id}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Unexpected error getting session {session_id}: {e}", exc_info=True)
        return None

    @staticmethod
    def save_session(session_data: SessionData) -> None:
        try:
            session_key = f"session:{session_data.session_id}"
            redis_client.setex(
                session_key,
                SessionManager.SESSION_TTL,
                session_data.model_dump_json()
            )
            # Track in the set for the Logs dashboard
            redis_client.sadd(SessionManager._ALL_SESSIONS_KEY, session_data.session_id)
        except redis.RedisError as e:
            logger.error(f"Redis error saving session {session_data.session_id}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Unexpected error saving session {session_data.session_id}: {e}", exc_info=True)

    @staticmethod
    def list_all_session_ids() -> list[str]:
        """
        Returns all active session IDs from the tracking set.
        Prunes stale IDs that have expired from Redis to prevent set bloat.
        """
        try:
            all_ids = list(redis_client.smembers(SessionManager._ALL_SESSIONS_KEY))
            active_ids = []
            stale_ids = []
            
            for session_id in all_ids:
                if redis_client.exists(f"session:{session_id}"):
                    active_ids.append(session_id)
                else:
                    stale_ids.append(session_id)
            
            if stale_ids:
                redis_client.srem(SessionManager._ALL_SESSIONS_KEY, *stale_ids)
                logger.info(f"Pruned {len(stale_ids)} stale session IDs from active set.")
                
            return active_ids
        except redis.RedisError as e:
            logger.error(f"Redis error listing sessions: {e}", exc_info=True)
            return []

    @staticmethod
    def get_state_note(user_id: str) -> Optional[str]:
        """
        Retrieves the persistent cross-session state note for a user.

        Returns None if no note exists OR if the note has been tainted by a prior
        escalation — preventing poisoned context from leaking into a new session.
        """
        try:
            raw = redis_client.get(f"user_state:{user_id}")
            if not raw:
                return None
            if raw.startswith(SessionManager._ESCALATION_PREFIX):
                # Previous session ended in escalation. Suppress this note so it cannot
                # contaminate the context for a fresh session. The raw value is preserved
                # in Redis under the same key for audit/debugging purposes.
                logger.info(
                    f"Suppressing tainted state note for user '{user_id}' "
                    "(escalation marker present). Fresh session starts with no prior context."
                )
                return None
            return raw
        except redis.RedisError as e:
            logger.error(f"Redis error getting state note for user {user_id}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Unexpected error getting state note for user {user_id}: {e}", exc_info=True)
        return None

    @staticmethod
    def save_state_note(user_id: str, note: str) -> None:
        """
        Persists a clean, resolved-session summary as the user's cross-session state note.
        Sets a 30-day TTL to prevent abandoned notes from lingering forever.
        """
        try:
            redis_client.setex(f"user_state:{user_id}", 2592000, note)
            logger.info(f"State note saved for user '{user_id}' with 30-day TTL.")
        except redis.RedisError as e:
            logger.error(f"Redis error saving state note for user {user_id}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Unexpected error saving state note for user {user_id}: {e}", exc_info=True)

    @staticmethod
    def taint_state_note(user_id: str) -> None:
        """
        Marks the user's current state note as tainted following a session escalation.

        The existing note is prefixed with _ESCALATION_PREFIX in-place rather than
        being deleted, so it remains inspectable in Redis for debugging and auditing.
        Any subsequent call to get_state_note() will detect the prefix and return None,
        ensuring a degraded or failed session cannot pollute the next fresh session.

        If no prior note exists, the bare prefix marker is written so that the taint
        persists until the next successful resolved session overwrites it.
        """
        try:
            key = f"user_state:{user_id}"
            existing = redis_client.get(key)
            if existing and not existing.startswith(SessionManager._ESCALATION_PREFIX):
                redis_client.setex(key, 2592000, f"{SessionManager._ESCALATION_PREFIX}{existing}")
                logger.info(f"State note tainted for user '{user_id}' following session escalation.")
            elif not existing:
                # Write the bare marker so get_state_note returns None on the next session.
                redis_client.setex(key, 2592000, SessionManager._ESCALATION_PREFIX)
                logger.info(
                    f"Bare escalation marker written for user '{user_id}' (no prior note existed)."
                )
            else:
                logger.debug(f"State note for user '{user_id}' already tainted — skipping.")
        except redis.RedisError as e:
            logger.error(f"Redis error tainting state note for user {user_id}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Unexpected error tainting state note for user {user_id}: {e}", exc_info=True)
