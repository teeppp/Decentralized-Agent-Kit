from functools import wraps
from typing import Callable, Any, Optional
import logging
from dak_agent.wallet_manager import WalletManager

logger = logging.getLogger(__name__)

class PaymentRequiredError(Exception):
    """Raised when a tool requires payment."""
    def __init__(self, price: float, address: str, message: str):
        self.price = price
        self.address = address
        self.message = message
        super().__init__(f"Payment Required: {price} XYM to {address}")

class InvalidPaymentError(Exception):
    """Raised when the provided payment proof is invalid."""
    pass

class PaidToolWrapper:
    """
    Wraps a tool function to enforce payment.
    """
    def __init__(self, price: float, wallet_manager: WalletManager, recipient_address: Optional[str] = None):
        self.price = price
        self.wallet_manager = wallet_manager
        self.recipient_address = recipient_address or wallet_manager.get_address()

    def __call__(self, func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Check for payment_hash in kwargs
            payment_hash = kwargs.get('payment_hash')
            
            if not payment_hash:
                # No payment proof provided, raise Invoice
                logger.info(f"Payment required for {func.__name__}: {self.price} XYM")
                raise PaymentRequiredError(
                    price=self.price,
                    address=self.recipient_address,
                    message=f"Payment for {func.__name__}"
                )
            
            # Verify payment
            logger.info(f"Verifying payment {payment_hash} for {func.__name__}")
            if self.wallet_manager.verify_transaction(payment_hash, self.recipient_address, self.price):
                logger.info("Payment verified. Executing tool.")
                return func(*args, **kwargs)
            else:
                logger.warning(f"Invalid payment {payment_hash}")
                raise InvalidPaymentError(f"Payment verification failed for hash: {payment_hash}")
                
        return wrapper
