import json
import os
import numpy as np
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from backend.db.models import Memory, SessionLocal
from backend.llm.client_factory import LLMClientFactory
from backend.logger import get_logger

logger = get_logger("agent.memory")

# Ensure GOOGLE_API_KEY is set if GEMINI_API_KEY is present
if not os.environ.get("GOOGLE_API_KEY") and os.environ.get("GEMINI_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = os.environ.get("GEMINI_API_KEY")

class MemoryManager:
    def __init__(self):
        factory = LLMClientFactory()
        provider = factory.provider
        
        # Load embedding model based on provider
        if provider == 'gemini':
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
            # Updated to use the recommended modern embedding model
            self.embeddings = GoogleGenerativeAIEmbeddings(
                model="gemini-embedding-001",
                task_type="retrieval_document"
            )
        elif provider == 'openai':
            from langchain_openai import OpenAIEmbeddings
            self.embeddings = OpenAIEmbeddings()
        else:
            # Fallback or error
            raise ValueError(f"No embedding model configured for provider: {provider}")

    def add_memory(self, user_id: str, content: str):
        """Generates an embedding and saves the memory to the DB."""
        if not content.strip():
            return

        try:
            logger.info(f"Adding semantic memory for user {user_id}: {content[:50]}...")
            # Use embed_documents for the 'storage' side of asymmetric embeddings
            vector = self.embeddings.embed_documents([content])[0]
            
            db: Session = SessionLocal()
            try:
                # Deduplication check: Don't add if exactly same content already exists
                existing = db.query(Memory).filter(Memory.user_id == user_id, Memory.content == content).first()
                if existing:
                    logger.debug(f"Memory already exists for user {user_id}. Skipping.")
                    return

                new_mem = Memory(
                    user_id=user_id,
                    content=content,
                    embedding=json.dumps(vector)
                )
                db.add(new_mem)
                db.commit()
                
                count = db.query(Memory).filter(Memory.user_id == user_id).count()
                if count > 100:
                    oldest = db.query(Memory).filter(Memory.user_id == user_id).order_by(Memory.created_at.asc()).first()
                    if oldest:
                        db.delete(oldest)
                        db.commit()
                        logger.info(f"Pruned oldest memory for user {user_id} to maintain 100-row cap.")
                        
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Failed to add semantic memory: {e}", exc_info=True)

    def search_memories(self, user_id: str, query: str, limit: int = 5) -> List[str]:
        """Searches for relevant memories using cosine similarity."""
        try:
            # Use task_type="retrieval_query" for the query side
            query_vector = self.embeddings.embed_query(query)
            
            db: Session = SessionLocal()
            try:
                all_memories = db.query(Memory).filter(Memory.user_id == user_id).order_by(Memory.created_at.desc()).limit(200).all()
                
                scored_memories = []
                for mem in all_memories:
                    mem_vector = json.loads(mem.embedding)
                    score = self._cosine_similarity(query_vector, mem_vector)
                    scored_memories.append((score, mem.content))
                
                # Sort by score descending
                scored_memories.sort(key=lambda x: x[0], reverse=True)
                
                # Return top results above a threshold
                results = [content for score, content in scored_memories[:limit] if score > 0.7]
                logger.info(f"Found {len(results)} relevant semantic memories for user {user_id}.")
                return results
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Failed to search semantic memories: {e}", exc_info=True)
            return []

    def _cosine_similarity(self, v1: List[float], v2: List[float]) -> float:
        """Calculates cosine similarity between two vectors."""
        a = np.array(v1)
        b = np.array(v2)
        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(dot_product / (norm_a * norm_b))
