import time
from backend.session.manager import redis_client

class SessionLock:
    def __init__(self, session_id: str, timeout: int = 30):
        self.lock_key = f"session:{session_id}:lock"
        self.timeout = timeout
        self.acquired = False

    def acquire(self, blocking: bool = True) -> bool:
        while True:
            acquired = redis_client.set(self.lock_key, "locked", nx=True, ex=self.timeout)
            if acquired:
                self.acquired = True
                return True
            if not blocking:
                return False
            time.sleep(0.1)

    def release(self) -> None:
        if self.acquired:
            redis_client.delete(self.lock_key)
            self.acquired = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
