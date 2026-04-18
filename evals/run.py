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
from contextlib import ExitStack

EVAL_MODE = os.getenv("EVAL_MODE", "mock").lower()

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
GOLDEN_PATH = os.path.join(os.path.dirname(__file__), "golden_dataset.json")

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
        
    def check_efficiency(self, tool_call_history: List[Dict[str, Any]]) -> tuple[bool, str]:
        # Step Count Limit (e.g., 10)
        if len(tool_call_history) > 10:
            return False, f"Inefficient: {len(tool_call_history)} steps taken (limit 10)"
            
        # Stutter Detection
        if len(tool_call_history) >= 3:
            for i in range(len(tool_call_history) - 2):
                t1 = tool_call_history[i]
                t2 = tool_call_history[i+1]
                t3 = tool_call_history[i+2]
                
                if t1.get("tool") == t2.get("tool") == t3.get("tool"):
                    if t1.get("params") == t2.get("params") == t3.get("params"):
                        return False, f"Infinite Looping: '{t1.get('tool')}' looped 3 times identically."
                        
        return True, ""

    def check_trajectory(self, actual_tools: List[str], required_steps: List[str], forbidden_tools: List[str]) -> bool:
        # Check forbidden tools
        for ft in forbidden_tools:
            if ft in actual_tools:
                return False
                
        # Check required logical sequence (subsequence check ensures correct order)
        it = iter(actual_tools)
        return all(step in it for step in required_steps)

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
            "current_input": fixture["input_prompt"],
            "internal_messages": [],
            "final_output": "",
            "retry_count": 0,
            "tool_results": {}
        }
        
        logger.info(f"Running fixture: {fixture['name']} (Mode: {EVAL_MODE})")
        token_stats = {"input_tokens": 0, "output_tokens": 0}
        
        # ---------------------------------------------------------
        # ENVIRONMENT INJECTION: Live vs Mock
        # ---------------------------------------------------------
        if EVAL_MODE == "live":
            from backend.llm.client_factory import LLMClientFactory
            real_factory = LLMClientFactory()
            mock_llm_factory = MagicMock()
            mock_llm_factory.get_call_delay = real_factory.get_call_delay
            
            class TrackedClient:
                def __init__(self, real_client, stats):
                    self.real_client = real_client
                    self.stats = stats
                def invoke(self, *args, **kwargs):
                    res = self.real_client.invoke(*args, **kwargs)
                    if hasattr(res, "usage_metadata") and res.usage_metadata:
                        self.stats["input_tokens"] += res.usage_metadata.get("input_tokens", 0)
                        self.stats["output_tokens"] += res.usage_metadata.get("output_tokens", 0)
                    return res
                    
            def get_tracked_client(name):
                return TrackedClient(real_factory.get_client(name), token_stats)
                
            mock_llm_factory.get_client.side_effect = get_tracked_client
        else:
            mock_llm_factory = MagicMock()
            mock_llm_factory.get_call_delay.return_value = 0
            expected_route = fixture.get("expected_route", {})
            mock_c = MagicMock()
            mock_c.invoke.return_value = MagicMock(content=json.dumps({"intent": expected_route.get("intent", "general"), "specialist": expected_route.get("specialist", "tech_specialist")}))
            mock_s = MagicMock()
            mock_s.invoke.return_value = MagicMock(content="Mock specialist response")
            mock_q = MagicMock()
            mock_q.invoke.return_value = MagicMock(content="PASS\n" if expected_route.get("outcome") == "resolved" else "RETRY\n")

            def mock_gc(name):
                if name == "concierge": return mock_c
                if name == "quality_lead": return mock_q
                return mock_s
            mock_llm_factory.get_client.side_effect = mock_gc

        mock_mem_mgr = MagicMock()
        mock_mem_mgr.search_memories.return_value = []

        with ExitStack() as stack:
            mock_get_account = stack.enter_context(patch("backend.agent.tools.get_account"))
            stack.enter_context(patch("backend.agent.graph.get_memory_manager", return_value=mock_mem_mgr))
            stack.enter_context(patch("backend.agent.graph.get_llm_factory", return_value=mock_llm_factory))
            stack.enter_context(patch("backend.session.manager.redis_client", mock_redis))
            
            mock_get_account.return_value = MagicMock(id=user_id, plan=tier.lower())
            
            tracked_mocks = {
                "backend.agent.tools.get_account": mock_get_account,
                "memory_manager.add_memory": mock_mem_mgr.add_memory
            }
            
            side_effects = fixture.get("expected_side_effects", [])
            for se in side_effects:
                target = se["mock_target"]
                if target not in tracked_mocks:
                    tracked_mocks[target] = stack.enter_context(patch(target))
            
            # Execute the graph synchronously for evals
            try:
                final_state = await graph_app.ainvoke(state)
            except Exception as e:
                logger.error(f"Error in fixture {fixture['id']}: {e}")
                return {
                    "id": fixture['id'], "passed": False, "error": str(e),
                    "actual": {"retries": 0, "tools": []}, "mode": EVAL_MODE, "tags": fixture.get("tags", []), "tokens": token_stats
                }
                
            # POST-FLIGHT SIDE-EFFECT VALIDATION
            passed_side_effects = True
            se_error_str = None
            for se in side_effects:
                target = se["mock_target"]
                mock_obj = tracked_mocks[target]
                args = se.get("expected_args")
                
                try:
                    if isinstance(args, dict):
                        mock_obj.assert_called_with(**args)
                    elif isinstance(args, list):
                        mock_obj.assert_called_with(*args)
                    else:
                        mock_obj.assert_called_with(args)
                except AssertionError as e:
                    se_error_str = f"DataPersistenceError: target '{target}' mismatched. Expected {args}"
                    logger.error(se_error_str)
                    passed_side_effects = False

        # Extract actual outcomes
        actual_specialist = final_state['session'].routing_decisions[-1].specialist if final_state['session'].routing_decisions else "none"
        actual_intent = final_state['session'].routing_decisions[-1].intent if final_state['session'].routing_decisions else "none"
        actual_outcome = final_state.get('quality_appraisal', 'unknown')
        retries = final_state.get('retry_count', 0)
        
        # Assertions
        expected_route = fixture.get("expected_route", {})
        passed_route = actual_specialist == expected_route.get("specialist")
        passed_outcome = actual_outcome == expected_route.get("outcome")
        
        actual_tools = [entry["tool"] for entry in state['session'].tool_call_history]
        required_steps = fixture.get("expected_trajectory", [])
        forbidden_tools = fixture.get("forbidden_tools", [])
        passed_trajectory = self.check_trajectory(actual_tools, required_steps, forbidden_tools)
        passed_efficiency, eff_error_str = self.check_efficiency(state['session'].tool_call_history)
        
        passed = passed_route and passed_outcome and passed_trajectory and passed_side_effects and passed_efficiency
        
        result = {
            "id": fixture["id"],
            "name": fixture["name"],
            "passed": passed,
            "mode": EVAL_MODE,
            "tags": fixture.get("tags", []),
            "tokens": token_stats,
            "actual": {
                "specialist": actual_specialist,
                "intent": actual_intent,
                "outcome": actual_outcome,
                "retries": retries,
                "tools": actual_tools
            },
            "expected_route": expected_route
        }
        
        final_errors = []
        if not passed_side_effects and se_error_str:
            final_errors.append(se_error_str)
        if not passed_efficiency and eff_error_str:
            final_errors.append(eff_error_str)
            logger.error(eff_error_str)
            
        if final_errors:
            result["error"] = " | ".join(final_errors)
            
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

    def save_markdown_report(self, filepath: str):
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("# MINDCX OFFLINE EVALUATION REPORT\n\n")
            f.write(f"**OVERALL ACCURACY:** {self.metrics['route_accuracy']:.2%}\n")
            f.write(f"**RETRY RATE:** {self.metrics['retry_rate']:.2f} per turn\n\n")
            f.write("| ID | STATUS | ACTUAL |\n")
            f.write("|---|---|---|\n")
            for r in self.results:
                status = "✅ PASS" if r["passed"] else "❌ FAIL"
                if "error" in r:
                    actual_str = f"ERROR: {r['error'][:30]}..."
                else:
                    actual_str = f"{r['actual'].get('specialist', 'none')} ({r['actual'].get('outcome', 'unknown')})"
                f.write(f"| {r['id']} | {status} | {actual_str} |\n")
        print(f"Markdown report saved to: {filepath}")

    async def run(self, target_tag: str = None):
        # Create results directory if it doesn't exist
        results_dir = os.path.join(os.path.dirname(__file__), "results")
        os.makedirs(results_dir, exist_ok=True)
        
        with open(GOLDEN_PATH, "r") as f:
            fixtures = json.load(f)
            
        required_keys = ["input_prompt", "expected_route", "expected_trajectory", "expected_side_effects", "tags"]
        
        for fix in fixtures:
            missing_keys = [k for k in required_keys if k not in fix]
            if missing_keys:
                logger.warning(f"Skipping fixture '{fix.get('id', 'unknown')}' due to missing schema fields: {missing_keys}")
                continue
                
            if target_tag and target_tag not in fix.get("tags", []):
                continue
                
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
        
        md_file = os.path.join(results_dir, "eval_report.md")
        self.save_markdown_report(md_file)
        
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
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", type=str, help="Filter test suite by tag")
    args = parser.parse_args()
    
    runner = EvalRunner()
    asyncio.run(runner.run(args.tag))
