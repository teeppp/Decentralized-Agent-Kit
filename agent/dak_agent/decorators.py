import functools
from typing import Optional, Callable, Any
from .errors import PaymentRequiredError
from .wallets.solana_wallet import get_solana_wallet_manager

def PaidToolWrapper(price: float, currency: str = "SOL", address: Optional[str] = None):
    """
    Decorator to mark a tool as requiring payment.
    
    Args:
        price: The amount required.
        currency: The currency (default: SOL).
        address: The recipient address. If None, uses the agent's wallet address.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Check if payment_hash is provided
            payment_hash = kwargs.get('payment_hash')
            
            # If payment_hash is provided, we assume payment is made.
            # In a real production system, we would VERIFY the transaction on-chain here.
            # For this demo/AP2 protocol, we trust the LLM has verified it or we verify it now.
            
            if payment_hash:
                # Verify transaction on-chain using wallet_manager
                wallet = get_solana_wallet_manager()
                
                # If address is not provided, use agent's address
                target_address = address
                if not target_address:
                    target_address = wallet.get_address()
                    
                if not wallet.verify_transaction(payment_hash, target_address, price):
                     raise PaymentRequiredError(
                        price=price,
                        address=target_address,
                        message=f"Payment verification failed for hash: {payment_hash}",
                        currency=currency
                    )
                return func(*args, **kwargs)
            
            # If no payment_hash, raise PaymentRequiredError
            target_address = address
            if not target_address:
                # Default to agent's own address
                wallet = get_solana_wallet_manager()
                target_address = wallet.get_address()
                
            raise PaymentRequiredError(
                price=price,
                address=target_address,
                message=f"Payment of {price} {currency} required for {func.__name__}",
                currency=currency
            )
        return wrapper
    return decorator
