from dak_agent.wallet_manager import WalletManager
from .paid_tool import PaidToolWrapper
from typing import Optional

# Global instance to share state if needed, or instantiate per call
# For simplicity, we'll instantiate a manager. In a real app, this should be a singleton managed by the Agent.
# However, since tools are standalone functions, we need a way to access the agent's wallet.
# The AdaptiveAgent will handle the WalletManager instance and inject it or we can use a singleton pattern here.

_wallet_manager = None

def get_wallet_manager():
    global _wallet_manager
    if _wallet_manager is None:
        _wallet_manager = WalletManager()
    return _wallet_manager

def check_my_balance() -> str:
    """
    Check the current balance of your wallet.
    Returns:
        str: The balance in XYM.
    """
    wm = get_wallet_manager()
    balance = wm.get_balance()
    return f"{balance} XYM"

def get_my_address() -> str:
    """
    Get your public wallet address.
    Returns:
        str: The Symbol address.
    """
    wm = get_wallet_manager()
    return wm.get_address()

def send_token(recipient_address: str, amount: float, message: str = "") -> str:
    """
    Send XYM tokens to another address.
    Args:
        recipient_address: The address to send to.
        amount: The amount of XYM to send.
        message: Optional message to include in the transaction.
    """
    wm = get_wallet_manager()
    return wm.send_transaction(recipient_address, amount, message)

# Premium Tool Example
# This tool requires payment to run.
# The wrapper will check for 'payment_hash' and verify it.
# If missing, it raises PaymentRequiredError, triggering the Agent's auto-payment logic.

@PaidToolWrapper(price=10.0, wallet_manager=get_wallet_manager())
def premium_analysis(query: str, payment_hash: Optional[str] = None) -> str:
    """
    Perform a premium deep analysis. Requires 10 XYM payment.
    Args:
        query: The topic to analyze.
        payment_hash: The transaction hash of the payment (Auto-filled by Agent).
    """
    return f"PREMIUM ANALYSIS for '{query}':\nVerified Payment: {payment_hash}\nResult: This is a high-value insight generated after payment verification."
