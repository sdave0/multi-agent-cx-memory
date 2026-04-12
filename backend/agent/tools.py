import json
import datetime
from typing import Dict, Any, Union
from backend.db.models import SessionLocal, Account, Billing, Outage
import uuid
from backend.logger import get_logger
import functools

logger = get_logger("agent.tools")

class ToolError(Exception):
    pass

def tool_telemetry(func):
    @functools.wraps(func)
    def wrapper(self, params: Dict[str, Any]):
        logger.info(f"Executing tool {self.name} with params {params}")
        try:
            result = func(self, params)
            logger.info(f"Tool {self.name} completed successfully.")
            return result
        except ToolError as e:
            logger.warning(f"Expected ToolError in {self.name}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Critical unhandled exception in {self.name}: {str(e)}", exc_info=True)
            return ToolResult(f"Internal Critical Error during tool execution: {str(e)}")
    return wrapper

class ToolResult:
    def __init__(self, data: str):
        self.data = data

def get_account(account_id: str):
    db = SessionLocal()
    account = db.query(Account).filter(Account.id == account_id).first()
    db.close()
    return account

class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime.datetime, datetime.date)):
            return obj.isoformat()
        return super().default(obj)

def serialize(obj):
    if not obj:
        return "Not found"
    data = {k: v for k, v in obj.__dict__.items() if not k.startswith('_')}
    return json.dumps(data, cls=DateTimeEncoder)

class LookupAccountTool:
    name = "lookup_account"
    description = "Looks up basic account information and plan tier using an account ID."
    
    @tool_telemetry
    def execute(self, params: Dict[str, Any]) -> ToolResult:
        account_id = params.get("account_id")
        if not account_id:
            raise ToolError("Missing account_id")
        
        account = get_account(account_id)
        if not account:
            raise ToolError("account_not_found")
            
        return ToolResult(serialize(account))

class GetBillingHistoryTool:
    name = "get_billing_history"
    description = "Retrieves recent invoices. Restricted to pro/enterprise users."
    
    @tool_telemetry
    def execute(self, params: Dict[str, Any]) -> ToolResult:
        account_id = params.get("account_id")
        account = get_account(account_id)
        
        if not account:
            raise ToolError("account_not_found")
            
        if account.plan == "free":
            raise ToolError("Billing history is not available on the free tier.")
            
        db = SessionLocal()
        bills = db.query(Billing).filter(Billing.account_id == account_id).all()
        db.close()
        
        return ToolResult("\n".join([serialize(b) for b in bills]))

class CheckOutageStatusTool:
    name = "check_outage_status"
    description = "Checks for active or recent outages affecting platform components."
    
    @tool_telemetry
    def execute(self, params: Dict[str, Any]) -> ToolResult:
        db = SessionLocal()
        outages = db.query(Outage).all()
        db.close()
        return ToolResult("\n".join([serialize(o) for o in outages]) or "No active outages reported.")

class CreateTicketTool:
    name = "create_ticket"
    description = "Creates a support ticket for technical issues. Restricted to pro/enterprise users."
    
    @tool_telemetry
    def execute(self, params: Dict[str, Any]) -> ToolResult:
        account_id = params.get("account_id")
        account = get_account(account_id)
        
        if account and account.plan == "free":
            raise ToolError("Ticket creation is not available on the free tier. Please use the community forums.")
            
        issue_desc = params.get("description", "No description provided")
        ticket_id = f"TKT-{str(uuid.uuid4())[:6]}"
        return ToolResult(f"Ticket {ticket_id} created successfully. Description: {issue_desc}")

TOOLS_MAP = {
    "lookup_account": LookupAccountTool(),
    "get_billing_history": GetBillingHistoryTool(),
    "check_outage_status": CheckOutageStatusTool(),
    "create_ticket": CreateTicketTool()
}
