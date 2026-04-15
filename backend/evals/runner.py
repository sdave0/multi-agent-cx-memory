import asyncio
import json
import os
import sys
import time
from datetime import datetime
from typing import List, Dict, Any
from unittest.mock import MagicMock, patch

# Add the project root to sys.path
sys.path.append(os.getcwd())

from unittest.mock import MagicMock, patch

# Patch Redis before any other imports that might use it
import redis
mock_redis = MagicMock(spec=redis.Redis)
with patch("redis.Redis.from_url", return_value=mock_redis):
    from backend.agent.graph import app as graph_app
    from backend.session.schema import SessionData, RoutingDecision

from backend.logger import get_logger

logger = get_logger("evals.runner")

# Regression threshold: 5% drop in accuracy is a failure
ACCURACY_THRESHOLD = 0.95
BASELINE_PATH = os.path.join(os.path.dirname(__file__), "baseline.json")
FIXTURES_PATH = os.path.join(os.path.dirname(__file__), "fixtures.json")

class EvalRunner:
    def __init__(self):
        self.results = []
        self.metrics = {
            "route_accuracy": 0.0,
            "retry_rate": 0.0,
            "escalation_precision": 0.0,
            "tool_error_handling": 0.0,
            "total_passed": 0
        }

    async def run_fixture(self, fixture: Dict[str, Any]):
        session_id = f"eval_{fixture['id']}"
        user_id = "eval_user_1"
        tier = fixture.get("user_tier", "PRO")
        
        session = SessionData(
            session_id=session_id,
            user_id=user_id,
            tier=tier,
            message_history=[],
            tool_call_history=[],
            routing_decisions=[],
            relevant_memories=[]
        )
        
        state = {
            "session": session,
            "current_input": fixture["input"],
            "internal_messages": [],
            "final_output": "",
            "retry_count": 0,
            "tool_results": {}
        }
        
        logger.info(f"Running fixture: {fixture['name']}")
        
        # Mocking external side effects
        with patch("backend.agent.tools.get_account") as mock_get_account, \
             patch("backend.agent.memory.MemoryManager.search_memories") as mock_search, \
             patch("backend.agent.memory.MemoryManager.add_memory") as mock_add, \
             patch("backend.session.manager.redis_client", mock_redis):
            
            mock_get_account.return_value = MagicMock(id=user_id, plan=tier.lower())
            mock_search.return_value = []
            
            # Execute the graph synchronously for evals
            try:
                final_state = await graph_app.ainvoke(state)
            except Exception as e:
                logger.error(f"Error in fixture {fixture['id']}: {e}")
                return {"id": fixture['id'], "passed": False, "error": str(e), "actual": {"retries": 0}}

        # Extract actual outcomes
        actual_specialist = final_state['session'].routing_decisions[-1].specialist if final_state['session'].routing_decisions else "none"
        actual_intent = final_state['session'].routing_decisions[-1].intent if final_state['session'].routing_decisions else "none"
        actual_outcome = final_state.get('quality_appraisal', 'unknown')
        retries = final_state.get('retry_count', 0)
        
        # Assertions
        expected = fixture["expected"]
        passed_route = actual_specialist == expected.get("specialist")
        passed_outcome = actual_outcome == expected.get("outcome")
        
        passed = passed_route and passed_outcome
        
        result = {
            "id": fixture["id"],
            "name": fixture["name"],
            "passed": passed,
            "actual": {
                "specialist": actual_specialist,
                "intent": actual_intent,
                "outcome": actual_outcome,
                "retries": retries
            },
            "expected": expected
        }
        
        return result

    def calculate_metrics(self):
        total = len(self.results)
        if total == 0: return
        
        correct_routes = sum(1 for r in self.results if r["passed"])
        total_retries = sum(r["actual"]["retries"] for r in self.results)
        
        self.metrics["route_accuracy"] = correct_routes / total
        self.metrics["retry_rate"] = total_retries / total
        self.metrics["total_passed"] = correct_routes
        
        # In a real scenario, we'd have more granular metrics
        # For this task, we simplify.
        
    def print_report(self):
        print("\n" + "="*60)
        print(" MINDCX OFFLINE EVALUATION REPORT")
        print("="*60)
        print(f"{'ID':<20} | {'STATUS':<10} | {'ACTUAL':<20}")
        print("-" * 60)
        for r in self.results:
            status = "PASS" if r["passed"] else "FAIL"
            if "error" in r:
                actual_str = f"ERROR: {r['error'][:30]}..."
            else:
                actual_str = f"{r['actual'].get('specialist', 'none')} ({r['actual'].get('outcome', 'unknown')})"
            print(f"{r['id']:<20} | {status:<10} | {actual_str:<20}")
        
        print("-" * 60)
        print(f"OVERALL ACCURACY: {self.metrics['route_accuracy']:.2%}")
        print(f"RETRY RATE:       {self.metrics['retry_rate']:.2f} per turn")
        print("="*60 + "\n")

    async def run(self):
        # Create results directory if it doesn't exist
        results_dir = os.path.join(os.path.dirname(__file__), "results")
        os.makedirs(results_dir, exist_ok=True)
        
        with open(FIXTURES_PATH, "r") as f:
            fixtures = json.load(f)
            
        for fix in fixtures:
            res = await self.run_fixture(fix)
            self.results.append(res)
            
        self.calculate_metrics()
        self.print_report()
        
        # Save timestamped results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_file = os.path.join(results_dir, f"run_{timestamp}.json")
        output = {
            "timestamp": datetime.now().isoformat(),
            "metrics": self.metrics,
            "results": self.results
        }
        with open(result_file, "w") as f:
            json.dump(output, f, indent=2)
        print(f"Full results saved to: {result_file}")
        
        # Regression check
        if os.path.exists(BASELINE_PATH):
            with open(BASELINE_PATH, "r") as f:
                baseline = json.load(f)
                
            old_acc = baseline.get("route_accuracy", 0)
            if self.metrics["route_accuracy"] < (old_acc * ACCURACY_THRESHOLD):
                print(f"REGRESSION DETECTED! Current accuracy {self.metrics['route_accuracy']:.2%} is below threshold (Baseline: {old_acc:.2%})")
                sys.exit(1)
            else:
                print("Regression check: PASSED")
        else:
            # Save current as baseline if none exists
            with open(BASELINE_PATH, "w") as f:
                json.dump(self.metrics, f, indent=2)
            print("No baseline found. Created new baseline from current results.")

if __name__ == "__main__":
    runner = EvalRunner()
    asyncio.run(runner.run())
