import asyncio
import os
import sys

# Add cli/src to path
# Assuming running from root
sys.path.append(os.path.join(os.getcwd(), "cli/src"))
# Also try adding just "src" if running from cli dir
sys.path.append(os.path.join(os.getcwd(), "src"))

from client import AgentClient

def test_mode_switch():
    client = AgentClient(base_url="http://localhost:8000")
    
    print("--- Starting Mode Switch Test ---")
    
    # Message 1
    print("\nSending Message 1...")
    response1 = client.run_task("Hello, who are you?")
    print(f"Response 1: {str(response1)[:100]}...")
    
    # Message 2
    print("\nSending Message 2...")
    response2 = client.run_task("What tools do you have?")
    print(f"Response 2: {str(response2)[:100]}...")
    
    # Message 3 (Should trigger switch before or during this)
    print("\nSending Message 3 (Should trigger switch)...")
    response3 = client.run_task("Tell me a joke.")
    print(f"Response 3: {str(response3)[:100]}...")

    print("\n--- Test Complete ---")

if __name__ == "__main__":
    test_mode_switch()
