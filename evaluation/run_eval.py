import argparse
import yaml
import asyncio
import sys
import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from dotenv import load_dotenv
from utils import ApiClient, Assertor

# Load .env from parent directory
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
load_dotenv(env_path, override=True)

# Add current directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

@dataclass
class EvalResult:
    scenario_id: str
    description: str
    status: str  # PASS, FAIL, SKIP, MANUAL
    agent_response_text: str
    reason: str = ""
    verification_method: str = "N/A"
    evaluator_reasoning: str = ""

async def run_scenario(client: ApiClient, scenario: Dict[str, Any]) -> EvalResult:
    scenario_id = scenario['id']
    description = scenario.get('description', '')
    print(f"Running: {scenario_id}...")
    
    session_id = await client.create_session()
    last_response = []
    agent_text = ""
    
    # Execute Turns
    for i, turn in enumerate(scenario['turns']):
        if 'role' in turn:
            role = turn['role']
            content = turn.get('content', '')
            
            if role == 'user':
                last_response = await client.send_message(session_id, content)
                agent_text = Assertor.get_text_from_response(last_response)
                
        elif 'expected' in turn:
            expectation = turn['expected']
            exp_type = expectation.get('type')
            
            # --- Universal Semantic Evaluation ---
            # We evaluate the agent's response against the scenario description and user intent.
            # This runs for ALL scenarios.
            
            # Context construction
            context = f"Scenario: {description}\nUser Input: {scenario['turns'][i-1]['content']}"
            instruction = "Did the agent correctly satisfy the user's request and the scenario goal?"
            
            # If there is a specific semantic instruction, use that instead
            if exp_type == 'semantic_check':
                instruction = expectation.get('instruction')

            # Run Semantic Check
            is_semantic_pass, reasoning = await Assertor.check_semantic(last_response, instruction, context)
            
            # --- Hard Constraints (Specific Assertions) ---
            
            # 1. Text Match
            if exp_type == 'text_match':
                keyword = expectation.get('keyword')
                if not Assertor.check_text_match(last_response, keyword):
                    return EvalResult(scenario_id, description, "FAIL", agent_text, f"Keyword '{keyword}' not found.", "Text Match + Semantic", reasoning)
                    
            # 2. Tool Call
            elif exp_type == 'tool_call':
                tool_name = expectation.get('tool_name')
                args_contains = expectation.get('args_contains')
                if not Assertor.check_tool_call(last_response, tool_name, args_contains):
                    if "[ENFORCER_BLOCKED]" in agent_text:
                         return EvalResult(scenario_id, description, "FAIL (Blocked)", agent_text, f"Tool '{tool_name}' blocked by Enforcer.", "Tool Call + Semantic", reasoning)
                    return EvalResult(scenario_id, description, "FAIL", agent_text, f"Tool '{tool_name}' not called.", "Tool Call + Semantic", reasoning)
            
            # 3. Semantic Check (Specific)
            elif exp_type == 'semantic_check':
                if not is_semantic_pass:
                     return EvalResult(scenario_id, description, "FAIL", agent_text, "Semantic check failed.", "Semantic Check (Gemini)", reasoning)

            # If Hard Constraints passed, check Semantic Result
            if not is_semantic_pass:
                return EvalResult(scenario_id, description, "FAIL (Semantic)", agent_text, "Hard constraints passed, but semantic evaluation failed.", "Semantic Check (Gemini)", reasoning)
            
            return EvalResult(scenario_id, description, "PASS", agent_text, "", "Semantic Check (Gemini)", reasoning)
            
    return EvalResult(scenario_id, description, "PASS", agent_text, "", "No Expectation")

async def main():
    # Determine default path relative to script location
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_scenarios = os.path.join(script_dir, "scenarios.yaml")
    
    parser = argparse.ArgumentParser(description="Run Agent Evaluation Scenarios")
    parser.add_argument("--file", default=default_scenarios, help="Path to scenarios YAML file")
    parser.add_argument("--tags", help="Comma-separated list of tags to filter scenarios")
    parser.add_argument("--url", help="Agent API URL")
    
    args = parser.parse_args()
    
    # Load Scenarios
    try:
        with open(args.file, 'r') as f:
            scenarios = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Error: File {args.file} not found.")
        return
    
    # Filter by tags
    if args.tags:
        target_tags = set(args.tags.split(','))
        scenarios = [s for s in scenarios if set(s.get('tags', [])).intersection(target_tags)]
    
    if not scenarios:
        print("No scenarios found.")
        return

    # Setup Client
    base_url = args.url if args.url else os.getenv("AGENT_URL", "http://localhost:8000")
    client = ApiClient(base_url)
    
    results: List[EvalResult] = []
    
    try:
        for scenario in scenarios:
            result = await run_scenario(client, scenario)
            results.append(result)
    finally:
        await client.close()
        
    # Generate Report
    print("\n" + "="*100)
    print(f"{'ID':<25} | {'Status':<15} | {'Method':<20} | {'Description'}")
    print("-" * 100)
    
    passed_count = 0
    failed_count = 0
    manual_count = 0
    
    for r in results:
        status_color = ""
        if r.status == "PASS":
            status_str = "PASS"
            passed_count += 1
        elif r.status == "MANUAL":
            status_str = "MANUAL CHECK"
            manual_count += 1
        else:
            status_str = r.status
            failed_count += 1
            
        print(f"{r.scenario_id:<25} | {status_str:<15} | {r.verification_method:<20} | {r.description}")

    print("="*100)
    
    # Detailed Failures / Manual Checks
    print("\n## Details (Failures & Manual Checks)\n")
    for r in results:
        if r.status != "PASS":
            print(f"### {r.scenario_id}: {r.description}")
            print(f"**Status**: {r.status}")
            print(f"**Method**: {r.verification_method}")
            print(f"**Reason**: {r.reason}")
            print(f"**Evaluator Reasoning**:\n{r.evaluator_reasoning}")
            print(f"**Agent Response**:\n> {r.agent_response_text.replace(chr(10), chr(10)+'> ')}")
            print("-" * 40)

    # Generate Markdown Report File
    report_path = os.path.join(os.getcwd(), "evaluation_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Agent Evaluation Report\n\n")
        f.write(f"**Date**: {os.popen('date').read().strip()}\n")
        f.write(f"**Total Scenarios**: {len(results)}\n")
        f.write(f"**Passed**: {passed_count} | **Failed**: {failed_count} | **Manual Check**: {manual_count}\n\n")
        
        f.write("## Summary\n\n")
        f.write("| ID | Status | Method | Description |\n")
        f.write("| :--- | :--- | :--- | :--- |\n")
        for r in results:
            status_icon = "✅" if r.status == "PASS" else "⚠️" if r.status == "MANUAL" else "❌"
            f.write(f"| {r.scenario_id} | {status_icon} {r.status} | {r.verification_method} | {r.description} |\n")
        
        f.write("\n## Details\n\n")
        for r in results:
            # Always show details if there is reasoning, or if failed
            f.write(f"### {r.scenario_id}\n")
            f.write(f"- **Description**: {r.description}\n")
            f.write(f"- **Status**: {r.status}\n")
            f.write(f"- **Method**: {r.verification_method}\n")
            f.write(f"- **Reason**: {r.reason}\n")
            f.write(f"- **Evaluator Reasoning**:\n\n> {r.evaluator_reasoning.replace(chr(10), chr(10)+'> ')}\n\n")
            f.write(f"- **Agent Response**:\n\n```\n{r.agent_response_text}\n```\n\n")
            f.write("---\n")
    
    print(f"\nReport generated at: {report_path}")

if __name__ == "__main__":
    asyncio.run(main())
