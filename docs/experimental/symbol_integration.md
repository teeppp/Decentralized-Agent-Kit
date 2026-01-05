# Symbol Blockchain Integration (Experimental)

This module integrates the Symbol Blockchain into the Decentralized Agent Kit, enabling agents to manage wallets, check balances, execute transactions, and most importantly, **autonomously pay for paid tools** via the AP2 (Agent-to-Payment) protocol.

## Concept: AI as an Autonomous Entrepreneur

The core idea is to give the AI agent "financial agency". By holding its own private key and managing funds (XYM), the agent can:

1.  **Sustain Itself**: Pay for its own API usage or computation costs.
2.  **Transact**: Autonomously pay for paid tools without human intervention.
3.  **Optimize**: Make decisions based on economic viability.

---

## AP2 Protocol: Agent-to-Payment

The AP2 protocol enables agents to autonomously pay for paid tools. This is the key innovation that allows agents to participate in a decentralized economy.

### How It Works

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│    Agent     │     │  Paid Tool   │     │ WalletManager│
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                    │
       │ 1. Call tool()     │                    │
       │───────────────────>│                    │
       │                    │                    │
       │ 2. PaymentRequired │                    │
       │    Error (10 XYM)  │                    │
       │<───────────────────│                    │
       │                    │                    │
       │ 3. send_transaction│                    │
       │────────────────────────────────────────>│
       │                    │                    │
       │ 4. TxHash          │                    │
       │<────────────────────────────────────────│
       │                    │                    │
       │ 5. Retry with      │                    │
       │    payment_hash    │                    │
       │───────────────────>│                    │
       │                    │                    │
       │ 6. Verify & Execute│                    │
       │<───────────────────│                    │
       │                    │                    │
       │ 7. Result          │                    │
       └────────────────────┴────────────────────┘
```

### Key Components

#### 1. `PaidToolWrapper` (Decorator)

Wraps a function to enforce payment. Located in `agent/skills/symbol_wallet/paid_tool.py`.

```python
@PaidToolWrapper(price=10.0, wallet_manager=get_wallet_manager())
def perform_premium_analysis(topic: str, payment_hash: Optional[str] = None) -> str:
    """Perform a premium analysis. Requires 10 XYM payment."""
    return f"Premium analysis for: {topic}"
```

When called without `payment_hash`, it raises `PaymentRequiredError`.

#### 2. `_on_tool_error` (Auto-Payment Handler)

Located in `agent/dak_agent/adaptive_agent.py`. This callback intercepts `PaymentRequiredError` and:

1.  Initializes `WalletManager` on-demand (if not already done).
2.  Sends the required payment.
3.  Returns instructions for the LLM to retry with the `payment_hash`.

```python
if isinstance(error, PaymentRequiredError):
    tx_hash = self._wallet_manager.send_transaction(error.address, error.price, error.message)
    return {
        "error": f"Payment Required. I have automatically paid {error.price} XYM. TxHash: {tx_hash}. Remaining balance: {remaining_balance} XYM. Please RETRY the tool call immediately with argument `payment_hash='{tx_hash}'`."
    }
```

#### 3. Auto Wallet Tools

When any skill is enabled, wallet info tools (`check_my_balance`, `get_my_address`) are automatically added. This ensures the LLM can always check its balance, even after context control operations.

---

## Setup

### Prerequisites

- A Symbol Testnet account (Private Key).
- Testnet XYM tokens (available via Faucet).

### Configuration

Add the following environment variables to your `.env` file:

```bash
# AP2 Protocol (required to enable the feature)
ENABLE_AP2_PROTOCOL=true

# Symbol Wallet Configuration
SYMBOL_PRIVATE_KEY=your_private_key_here
SYMBOL_NODE_URL=http://sym-test-01.opening-line.jp:3000  # Optional
SYMBOL_USE_MOCK=true  # For testing without real transactions
```

> [!WARNING]
> **Security Notice**: Never commit your private key to version control.

> [!IMPORTANT]
> **Feature Flag**: AP2 Protocol is **disabled by default**. You must explicitly set `ENABLE_AP2_PROTOCOL=true` to enable auto-payment and wallet integration features.

---

## Usage

### Enabling the Skill

The Symbol integration is implemented as an optional **Skill**.

```
User: "Enable the premium_service skill."
Agent: "'premium_service' enabled."
```

When enabled, the agent automatically gains access to:
- `perform_premium_analysis(topic, payment_hash)` - The paid tool
- `check_my_balance()` - Auto-added wallet info tool
- `get_my_address()` - Auto-added wallet info tool

### Example Interaction

**User**: "Analyze 'The Future of AI' using premium analysis."

**Agent** (internally):
1. Calls `perform_premium_analysis(topic="The Future of AI")`
2. Receives `PaymentRequiredError`
3. Auto-pays 10 XYM via `WalletManager`
4. Retries with `payment_hash`
5. Returns the analysis result

**User**: "What's my balance now?"

**Agent**: Calls `check_my_balance()` → "90 XYM"

---

## Demo

### Running the Demo

1.  **Start the Demo Environment**:
    ```bash
    docker compose -f docker-compose.demo.yml up --build
    ```

2.  **Open the UI**:
    Navigate to `http://localhost:3000` in your browser.

3.  **Trigger the AP2 Flow**:
    Send this prompt:
    > "Enable premium_service and analyze 'The Future of AI'."

4.  **Observe**:
    - Expand "Thinking Process" to see tool calls.
    - Note the auto-payment and retry with `payment_hash`.
    - Ask "What's my balance?" to confirm the wallet state.

### Mock Mode

For testing without real transactions, set `SYMBOL_USE_MOCK=true`. This simulates:
- Balance: 100 XYM (decrements on payment)
- Transactions: Returns mock hash `MOCK_TX_HASH_xxxx`
- Verification: Always returns `True`

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "残高を確認する機能はございません" | Wallet tools were not auto-added. Rebuild the agent container. |
| Agent asks for payment instead of paying | Check `skill.yaml` instructions. They should tell the agent to call the tool, not negotiate. |
| `PaymentRequiredError` not caught | Verify `on_tool_error_callback` is set in `AdaptiveAgent.__init__`. |
| Mock mode not working | Ensure `SYMBOL_USE_MOCK=true` in `.env` and the container is rebuilt. |

---

## Architecture

```
agent/
├── dak_agent/
│   ├── adaptive_agent.py    # Main agent with AP2 logic in _on_tool_error
│   └── wallet_manager.py    # Wallet operations (send, balance, verify)
└── skills/
    ├── symbol_wallet/
    │   ├── paid_tool.py     # PaidToolWrapper decorator
    │   ├── tools.py         # Wallet tools (check_my_balance, send_token, etc.)
    │   └── skill.yaml       # Skill definition
    └── premium_service/
        ├── tools.py         # Paid analysis tool
        └── skill.yaml       # Skill instructions (call tool directly, don't negotiate)
```
