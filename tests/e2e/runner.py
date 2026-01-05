import argparse
import asyncio
import logging
import sys
from typing import List
from tests.e2e.scenarios import SCENARIOS, Scenario
from tests.e2e.clients.bff_client import BffClient
from tests.e2e.clients.cli_client import CliClient
from tests.e2e.verifiers.langfuse_verifier import LangfuseVerifier

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def run_scenario(scenario: Scenario, client, verifier: LangfuseVerifier):
    logger.info(f"Running Scenario {scenario.id}: {scenario.name}")
    logger.info(f"Description: {scenario.description}")
    
    try:
        # Execute steps
        session_id = await client.start_session()
        logger.info(f"Session ID: {session_id}")
        
        for step in scenario.steps:
            logger.info(f"User Input: {step.user_input}")
            response = await client.send_message(session_id, step.user_input)
            logger.info(f"Agent Response: {response}")
            
            # Verify response content
            if step.expected_response_keyword:
                if step.expected_response_keyword not in response:
                    logger.error(f"FAILED: Expected keyword '{step.expected_response_keyword}' not found in response.")
                    return False
                else:
                    logger.info(f"Verified keyword: '{step.expected_response_keyword}'")
        
        # Verify Langfuse Logs
        logger.info("Verifying Langfuse logs...")
        trace_found = verifier.verify_trace(session_id)
        if not trace_found:
            logger.error("FAILED: Langfuse trace not found for this session.")
            return False
        
        logger.info(f"Scenario {scenario.id} PASSED")
        return True

    except Exception as e:
        logger.error(f"Scenario {scenario.id} FAILED with exception: {e}")
        return False

async def main():
    parser = argparse.ArgumentParser(description="E2E Test Runner")
    parser.add_argument("--target", choices=["bff", "cli"], required=True, help="Target interface to test")
    parser.add_argument("--scenario", type=str, help="Specific scenario ID to run (e.g., '01')")
    args = parser.parse_args()

    # Initialize Client
    if args.target == "bff":
        client = BffClient(base_url="http://localhost:3000")
    else:
        client = CliClient() # Implementation pending
        
    # Initialize Verifier
    verifier = LangfuseVerifier()

    # Select Scenarios
    scenarios_to_run = []
    if args.scenario:
        scenarios_to_run = [s for s in SCENARIOS if s.id == args.scenario]
    else:
        scenarios_to_run = SCENARIOS

    if not scenarios_to_run:
        logger.error("No scenarios found to run.")
        sys.exit(1)

    # Run Scenarios
    results = {}
    for scenario in scenarios_to_run:
        success = await run_scenario(scenario, client, verifier)
        results[scenario.id] = success

    # Report
    logger.info("\n=== Test Results ===")
    all_passed = True
    for sid, success in results.items():
        status = "PASSED" if success else "FAILED"
        logger.info(f"Scenario {sid}: {status}")
        if not success:
            all_passed = False
    
    if all_passed:
        logger.info("All tests passed successfully.")
        sys.exit(0)
    else:
        logger.error("Some tests failed.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
