# Solana Integration for AP2/x402 Protocol

This module integrates **Solana blockchain** into the Decentralized Agent Kit for AP2 (Agent-to-Payment) protocol compliance.

## Key Difference: LLM Decides Payments

Unlike auto-payment systems, this implementation follows AP2 principles:

> **"Verifiable Intent, Not Inferred Action"**

The LLM receives payment requests and **decides** whether to pay based on:
- User consent
- Intent Mandate (pre-authorized conditions)

**No automatic payment occurs.**

---

## Configuration

```bash
# Enable mock mode for development (no real transactions)
SOLANA_USE_MOCK=true

# Network: devnet, mainnet, or custom RPC URL
SOLANA_NETWORK=devnet

# Private key (base58 or JSON array format)
#SOLANA_PRIVATE_KEY=your_key_here

# Custom RPC (optional)
#SOLANA_RPC_URL=https://api.devnet.solana.com
```

---

## Available Tools

| Tool | Description |
|------|-------------|
| `check_solana_balance()` | Check SOL balance |
| `get_solana_address()` | Get wallet public address |
| `send_sol_payment(recipient, amount)` | Send SOL to recipient |
| `verify_sol_payment(tx_signature, ...)` | Verify transaction on-chain |

---

## Payment Flow

```
1. Tool raises PaymentRequiredError
2. _on_tool_error informs LLM of payment details
3. LLM decides: ask user OR call send_sol_payment
4. After payment: LLM retries tool with payment_hash
```

---

## Testing

```bash
cd agent && uv run python -c "
import os
os.environ['SOLANA_USE_MOCK'] = 'true'
from skills.solana_wallet.tools import check_solana_balance
print(check_solana_balance())
"
```

Output:
```
## Solana Wallet Balance
**Address**: `MockSoLAddress...`
**Balance**: 10.000000 SOL
**Network**: devnet
```

---

## Files

| File | Description |
|------|-------------|
| `dak_agent/solana_wallet_manager.py` | Core wallet operations |
| `skills/solana_wallet/tools.py` | Agent tools |
| `skills/solana_wallet/skill.yaml` | Skill definition |
