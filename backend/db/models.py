from sqlalchemy import Column, Integer, String, Enum, Float, DateTime, ForeignKey, create_engine
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from datetime import datetime

Base = declarative_base()

class Account(Base):
    __tablename__ = 'accounts'
    
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    password_hash = Column(String, nullable=True) 
    role = Column(String, default='customer') # 'customer', 'agent', 'admin'
    plan = Column(String, nullable=False) # 'free', 'pro', 'enterprise'
    status = Column(String, nullable=False) # 'active', 'suspended', 'churned'
    mrr = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    account_manager = Column(String, nullable=True)
    
    billing_history = relationship('Billing', back_populates='account')

class Billing(Base):
    __tablename__ = 'billing'
    
    id = Column(String, primary_key=True)
    account_id = Column(String, ForeignKey('accounts.id'), nullable=False)
    invoice_date = Column(DateTime, nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(String, nullable=False) # 'paid', 'overdue', 'pending'
    stripe_invoice_id = Column(String, nullable=True)
    
    account = relationship('Account', back_populates='billing_history')

class Outage(Base):
    __tablename__ = 'outages'
    
    id = Column(String, primary_key=True)
    started_at = Column(DateTime, nullable=False)
    resolved_at = Column(DateTime, nullable=True)
    severity = Column(String, nullable=False) # 'p1', 'p2', 'p3'
    affected_components = Column(String, nullable=False)
    description = Column(String, nullable=False)

class Memory(Base):
    __tablename__ = 'memories'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String, index=True)
    content = Column(String, nullable=False)
    # SQLite doesn't have a native vector type, so we store embedding as a JSON list of floats
    embedding = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

engine = create_engine('sqlite:///./mindcx.db', connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)
