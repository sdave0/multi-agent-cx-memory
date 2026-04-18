import os
import json
import glob
from collections import defaultdict
from datetime import datetime

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
DASHBOARD_PATH = os.path.join(RESULTS_DIR, "eval_dashboard.md")

def find_latest_run():
    files = glob.glob(os.path.join(RESULTS_DIR, "run_*.json"))
    if not files:
        return None
    return max(files, key=os.path.getmtime)

def generate_report():
    latest_file = find_latest_run()
    if not latest_file:
        print("No run results found. Please run the evaluation harness first.")
        return

    print(f"Loading results from: {os.path.basename(latest_file)}")
    with open(latest_file, "r") as f:
        data = json.load(f)

    results = data.get("results", [])
    if not results:
        print("No test results in file.")
        return

    # Calculate Tag-based Success Rate
    tag_counts = defaultdict(lambda: {"total": 0, "passed": 0})
    total_steps = 0
    total_input_tokens = 0
    total_output_tokens = 0
    eval_mode = results[0].get("mode", "mock")

    for r in results:
        passed = r.get("passed", False)
        for tag in r.get("tags", ["untagged"]):
            tag_counts[tag]["total"] += 1
            if passed:
                tag_counts[tag]["passed"] += 1
                
        actual = r.get("actual", {})
        total_steps += len(actual.get("tools", []))
        
        tokens = r.get("tokens", {})
        total_input_tokens += tokens.get("input_tokens", 0)
        total_output_tokens += tokens.get("output_tokens", 0)

    num_fixtures = len(results)
    avg_steps = total_steps / num_fixtures if num_fixtures else 0

    # Calculate Cost
    # Assuming standard rates: $0.15 / 1M input tokens, $0.60 / 1M output tokens
    RATE_IN = 0.15 / 1_000_000
    RATE_OUT = 0.60 / 1_000_000

    if eval_mode == "live":
        cost_type = "Actual Cost"
        total_cost = (total_input_tokens * RATE_IN) + (total_output_tokens * RATE_OUT)
    else:
        cost_type = "Projected Cost (Mock)"
        # Impute missing tokens natively based on heuristics
        imputed_in = total_steps * 350
        imputed_out = total_steps * 50
        total_cost = (imputed_in * RATE_IN) + (imputed_out * RATE_OUT)

    # Console Output
    print("\n" + "="*60)
    print(" LLMOPS DASHBOARD ")
    print("="*60)
    print(f"Mode:            {eval_mode.upper()}")
    print(f"{cost_type}:   ${total_cost:.5f}")
    print(f"Avg Steps/Run:   {avg_steps:.2f}")
    print("\n--- Success Rate by Tag ---")
    for tag, counts in tag_counts.items():
        rate = counts["passed"] / counts["total"]
        print(f" {tag:<15}: {rate:7.1%} ({counts['passed']}/{counts['total']})")
    print("="*60 + "\n")

    # Markdown Export
    with open(DASHBOARD_PATH, "w", encoding="utf-8") as f:
        f.write("# 🚀 LLMOps Dashboard\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"- **Mode:** `{eval_mode.upper()}`\n")
        f.write(f"- **{cost_type}:** `${total_cost:.5f}`\n")
        f.write(f"- **Avg Steps Per Fixture:** `{avg_steps:.2f}`\n\n")
        
        f.write("## Tag Performance\n\n")
        f.write("| Tag | Success Rate | Passed / Total |\n")
        f.write("|-----|--------------|----------------|\n")
        for tag, counts in tag_counts.items():
            rate = counts['passed'] / counts['total']
            icon = "✅" if rate == 1.0 else ("⚠️" if rate > 0.7 else "❌")
            f.write(f"| `{tag}` | {icon} {rate:.1%} | {counts['passed']} / {counts['total']} |\n")

    print(f"Dashboard exported to: {DASHBOARD_PATH}")

if __name__ == "__main__":
    generate_report()
