import os
import json
import asyncio
import time
import csv
import math

# Force LIVE mode BEFORE importing any backend modules
os.environ["EVAL_MODE"] = "live"

import sys
sys.path.append(os.getcwd())

from backend.agent.graph import app as graph_app
from backend.session.schema import SessionData
from backend.logger import get_logger

from datetime import datetime

logger = get_logger("benchmark")

GOLDEN_PATH = os.path.join("evals", "golden_dataset.json")
BENCHMARKS_DIR = os.path.join("benchmarks", "results")

# We will generate timestamped file names inside run_benchmark()
# Simple pricing parameters (e.g. Gemini 1.5 Flash)
# $0.15 / 1M input, $0.60 / 1M output
INPUT_RATE = 0.15 / 1000000
OUTPUT_RATE = 0.60 / 1000000

def get_percentile(data, percentile):
    if not data:
        return 0.0
    data = sorted(data)
    index = (percentile / 100) * (len(data) - 1)
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return data[int(index)]
    weight = index - lower
    return data[lower] * (1 - weight) + data[upper] * weight

async def run_benchmark():
    os.makedirs(BENCHMARKS_DIR, exist_ok=True)
    
    with open(GOLDEN_PATH, "r") as f:
        fixtures = json.load(f)
        
    metrics_list = []
    
    for fix in fixtures:
        print(f"Running fixture: {fix['name']}...")
        
        session_id = f"bench_{fix.get('id', 'unk')}"
        
        session = SessionData(
            session_id=session_id,
            user_id="bench_user_1",
            tier=fix.get("user_tier", "PRO"),
            message_history=[{"role": "user", "content": fix["input_prompt"]}],
            tool_call_history=[],
            routing_decisions=[],
            relevant_memories=[]
        )
        
        state = {
            "session": session,
            "current_input": fix["input_prompt"],
            "internal_messages": [],
            "final_output": "",
            "retry_count": 0,
            "tool_results": {}
        }
        
        config = {"recursion_limit": 15}
        
        start_time = time.perf_counter()
        first_token_time = None
        
        input_tokens = 0
        output_tokens = 0
        retries = 0
        escalated = False
        resolved = False
        
        try:
            async for event in graph_app.astream_events(state, config=config, version="v2"):
                kind = event["event"]
                name = event.get("name", "")
                
                # Capture TTFT
                if kind == "on_chat_model_stream":
                    chunk = event["data"].get("chunk")
                    if chunk and chunk.content and first_token_time is None:
                        first_token_time = time.perf_counter()
                    
                    # Some clients stream usage_metadata in chunks
                    if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
                        input_tokens += chunk.usage_metadata.get("input_tokens", 0)
                        output_tokens += chunk.usage_metadata.get("output_tokens", 0)
                
                # Capture complete Token Usage if not caught in stream
                if kind == "on_chat_model_end":
                    output = event.get("data", {}).get("output")
                    if hasattr(output, "usage_metadata") and output.usage_metadata:
                        # Only add if we didn't add it dynamically in the stream
                        _in = output.usage_metadata.get("input_tokens", 0)
                        _out = output.usage_metadata.get("output_tokens", 0)
                        if input_tokens == 0 and output_tokens == 0:
                            input_tokens += _in
                            output_tokens += _out
                
                # Track Retries & Escalations
                if kind == "on_chain_end":
                    metadata = event.get("metadata", {})
                    node_name = metadata.get("langgraph_node")
                    data_out = event.get("data", {}).get("output", {})
                    
                    if node_name == "quality_lead" and isinstance(data_out, dict):
                        appraisal = data_out.get("quality_appraisal", "").strip().lower()
                        if appraisal == "retry":
                            retries += 1
                        elif appraisal == "escalate":
                            escalated = True
                            
                    # Track explicit state variables
                    if isinstance(data_out, dict) and "session" in data_out:
                        final_appr = data_out.get("quality_appraisal", "").strip().lower()
                        if final_appr == "pass" or data_out.get("final_output"):
                            resolved = True

        except Exception as e:
            logger.error(f"Error executing graph: {e}")
            escalated = True # Mark as fail
            
        end_time = time.perf_counter()
        
        ttft = (first_token_time - start_time) if first_token_time else 0.0
        total_latency = end_time - start_time
        
        # Calculate Costs
        base_cost = (input_tokens * INPUT_RATE) + (output_tokens * OUTPUT_RATE)
        
        effective_cost = 0.0
        wasted_spend = 0.0
        
        if resolved and not escalated:
            effective_cost = base_cost
        else:
            wasted_spend = base_cost
            
        metrics_list.append({
            "fixture_id": fix["id"],
            "ttft_sec": round(ttft, 3),
            "latency_sec": round(total_latency, 3),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "retries": retries,
            "escalated": escalated,
            "effective_cost": effective_cost,
            "wasted_spend": wasted_spend
        })
        
    print("\n--- BENCHMARK COMPLETE ---")
    
    import re
    version = 1
    if os.path.exists(BENCHMARKS_DIR):
        existing_files = os.listdir(BENCHMARKS_DIR)
        versions = []
        for f in existing_files:
            match = re.match(r"benchmark_v(\d+)\.md", f)
            if match:
                versions.append(int(match.group(1)))
        if versions:
            version = max(versions) + 1
            
    csv_path = os.path.join(BENCHMARKS_DIR, f"benchmark_data_v{version}.csv")
    md_path = os.path.join(BENCHMARKS_DIR, f"benchmark_v{version}.md")
    
    # Save CSV
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "fixture_id", "ttft_sec", "latency_sec", "input_tokens", 
            "output_tokens", "retries", "escalated", "effective_cost", "wasted_spend"
        ])
        writer.writeheader()
        writer.writerows(metrics_list)
        
    # Calculate Stats
    latencies =     [m["latency_sec"] for m in metrics_list]
    ttfts =         [m["ttft_sec"] for m in metrics_list if m["ttft_sec"] > 0]
    total_retries = sum(m["retries"] for m in metrics_list)
    total_effective = sum(m["effective_cost"] for m in metrics_list)
    total_wasted =  sum(m["wasted_spend"] for m in metrics_list)
    
    avg_retries = (total_retries / len(metrics_list)) if metrics_list else 0
    
    latency_p50 = get_percentile(latencies, 50)
    latency_p95 = get_percentile(latencies, 95)
    
    ttft_p50 = get_percentile(ttfts, 50)
    ttft_p95 = get_percentile(ttfts, 95)
    
    # Generate Markdown
    md_content = f"""# Agent Architecture Benchmark

This file outlines the real-world operational efficiency and execution latencies of the MindCX multi-agent graph.

## Aggregate Performance Metrics

| Metric | Measurement (n={len(metrics_list)}) |
|--------|-------------|
| **Latency P50** | {latency_p50:.2f}s |
| **Latency P95** | {latency_p95:.2f}s |
| **TTFT P50**    | {ttft_p50:.2f}s |
| **TTFT P95**    | {ttft_p95:.2f}s |
| **Avg Retries / Run** | {avg_retries:.2f} |
| **Total Effective Cost** | ${total_effective:.5f} |
| **Total Wasted Spend** | ${total_wasted:.5f} |

"""
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
        
    print(f"Data saved to {csv_path}")
    print(f"Report saved to {md_path}")


if __name__ == "__main__":
    asyncio.run(run_benchmark())
