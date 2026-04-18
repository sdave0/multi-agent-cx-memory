from fastapi import FastAPI, Request, HTTPException, Security, Depends
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from backend.api import websocket, escalation
from backend.db.seed import seed_db
from backend.logger import get_logger
from backend.db.models import SessionLocal, Account
from backend.auth import verify_password, create_access_token, decode_access_token, security
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
import traceback
import os
from dotenv import load_dotenv

logger = get_logger("agent.main")

load_dotenv(os.path.join(os.path.dirname(__file__), 'config', '.env'))

# --- Startup Security Checks ---
REQUIRED_ENV = ["JWT_SECRET_KEY", "API_KEY", "REDIS_URL"]
missing = [env for env in REQUIRED_ENV if not os.environ.get(env)]
if missing:
    logger.critical(f"CRITICAL: Missing required environment variables: {missing}")
    raise RuntimeError(f"Missing environment variables: {missing}")

if not os.environ.get("GEMINI_API_KEY") and not os.environ.get("GOOGLE_API_KEY") and not os.environ.get("LLM_API_KEY"):
    raise RuntimeError("An LLM_API_KEY (or GEMINI/GOOGLE_API_KEY) must be explicitly present in the environment.")

# --- Auth Models & Dependencies ---
class LoginRequest(BaseModel):
    email: str
    password: str

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    payload = decode_access_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    db = SessionLocal()
    user = db.query(Account).filter(Account.id == user_id).first()
    db.close()
    
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

async def get_admin_user(current_user: Account = Depends(get_current_user)):
    if current_user.role not in ['agent', 'admin']:
        raise HTTPException(status_code=403, detail="Not authorized")
    return current_user

# Legacy API Key Security
API_KEY = os.environ.get("API_KEY")
if not API_KEY:
    raise RuntimeError("API_KEY is not set!")

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def get_api_key(api_key_header: str = Security(api_key_header)):
    if api_key_header == API_KEY:
        return api_key_header
    else:
        raise HTTPException(status_code=403, detail="Could not validate API Key")

# --- Database & Seeding ---
if os.environ.get("SEED_DB", "false").lower() == "true":
    try:
        seed_db()
        logger.info("Database seeded via SEED_DB=true.")
    except Exception as e:
        logger.error(f"Seed DB non-fatal issue: {e}", exc_info=True)
else:
    logger.info("Skipping database seed (SEED_DB != true).")

if not os.environ.get("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = os.environ.get("GEMINI_API_KEY") or os.environ.get("LLM_API_KEY", "")

app = FastAPI(title="Nexus Support Agent API")

# --- Runtime Hardening: CORS ---
allowed_origins_str = os.environ.get("ALLOWED_ORIGINS")
if allowed_origins_str:
    cors_origins = [o.strip() for o in allowed_origins_str.split(",")]
else:
    # Strict default for production; local dev can override via .env
    cors_origins = ["http://localhost:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
)

@app.post("/api/auth/login")
async def login(req: LoginRequest):
    db = SessionLocal()
    user = db.query(Account).filter(Account.email == req.email).first()
    db.close()
    
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    token = create_access_token(data={"sub": user.id, "role": user.role})
    return {
        "access_token": token, 
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "name": user.name,
            "role": user.role,
            "tier": user.plan
        }
    }

@app.get("/api/auth/me")
async def get_me(current_user: Account = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "name": current_user.name,
        "role": current_user.role,
        "tier": current_user.plan
    }

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Incoming HTTP request: {request.method} {request.url.path}")
    try:
        response = await call_next(request)
        logger.info(f"Response status: {response.status_code}")
        return response
    except Exception as e:
        logger.error(f"Unhandled HTTP Exception: {e}", exc_info=True)
        raise

app.include_router(websocket.router)
app.include_router(
    escalation.router, 
    prefix="/api/escalation",
    dependencies=[Depends(get_admin_user)]
)

@app.get("/")
def health_check():
    return {"status": "online", "service": "mindcx_support_agent"}
