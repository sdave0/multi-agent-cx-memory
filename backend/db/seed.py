import uuid
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from datetime import datetime, timedelta
from backend.db.models import SessionLocal, init_db, Account, Billing, Outage
from backend.auth import get_password_hash

def seed_db():
    init_db()
    db = SessionLocal()
    
    if db.query(Account).first() is not None:
        print("Database already seeded.")
        db.close()
        return

    pwd_hash = get_password_hash("mindcx2026")

    acct1_id = "acct_admin"
    acct2_id = "acct_customer"
    acct3_id = "acct_agent"
    
    acct1 = Account(id=acct1_id, name="Admin User", email="admin@mindcx.ai", role="admin", password_hash=pwd_hash, plan="enterprise", status="active", mrr=1500.0)
    acct2 = Account(id=acct2_id, name="Jonny Startup", email="jonny@startup.inc", role="customer", password_hash=pwd_hash, plan="free", status="active", mrr=0.0)
    acct3 = Account(id=acct3_id, name="Agent Smith", email="agent@mindcx.ai", role="agent", password_hash=pwd_hash, plan="pro", status="active", mrr=0.0)
    
    db.add_all([acct1, acct2, acct3])
    db.commit()
    
    bill1 = Billing(id="inv_" + str(uuid.uuid4())[:8], account_id=acct1_id, invoice_date=datetime.utcnow() - timedelta(days=30), amount=1500.0, status="paid")
    bill2 = Billing(id="inv_" + str(uuid.uuid4())[:8], account_id=acct1_id, invoice_date=datetime.utcnow(), amount=1500.0, status="pending")
    
    db.add_all([bill1, bill2])
    db.commit()
    
    outage1 = Outage(id="out_" + str(uuid.uuid4())[:8], started_at=datetime.utcnow() - timedelta(hours=2), resolved_at=None, severity="p2", affected_components="API Gateway", description="Elevated error rates on API endpoints.")
    
    db.add_all([outage1])
    db.commit()
    
    print("Database seeded successfully.")
    db.close()

if __name__ == "__main__":
    seed_db()
