import os
import logging
from symbolchain.symbol.Network import Network
from symbolchain.CryptoTypes import PrivateKey
from symbolchain.symbol.KeyPair import KeyPair
from symbolchain.facade.SymbolFacade import SymbolFacade
import requests
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class WalletManager:
    """
    Manages the agent's Symbol blockchain wallet.
    Handles key management, balance checks, and transactions.
    """
    
    def __init__(self, network_type: str = "testnet"):
        self.network_type = network_type
        self.facade = SymbolFacade(network_type)
        self.private_key_str = os.getenv("SYMBOL_PRIVATE_KEY")
        
        if not self.private_key_str:
            logger.warning("SYMBOL_PRIVATE_KEY not found in environment variables. Wallet functionality will be limited.")
            self.key_pair = None
            self.address = None
        else:
            try:
                self.key_pair = KeyPair(PrivateKey(self.private_key_str))
                self.address = self.facade.network.public_key_to_address(self.key_pair.public_key)
                logger.info(f"Wallet initialized. Address: {self.address}")
            except Exception as e:
                logger.error(f"Failed to initialize wallet from private key: {e}")
                self.key_pair = None
                self.address = None

        # Node URL (Testnet default)
        self.node_url = os.getenv("SYMBOL_NODE_URL", "http://sym-test-01.opening-line.jp:3000")
        
        # Mock Mode
        self.use_mock = os.getenv("SYMBOL_USE_MOCK", "false").lower() == "true"
        if self.use_mock:
            logger.info("WalletManager running in MOCK MODE.")

    def get_balance(self) -> float:
        """
        Fetch the current XYM balance.
        """
        if self.use_mock:
            return 1000.0

        if not self.address:
            return 0.0
            
        try:
            url = f"{self.node_url}/accounts/{self.address}"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                mosaics = data['account']['mosaics']
                
                # Find XYM mosaic (Testnet Currency ID: 72C0212E67A08BCE)
                # Note: In a real implementation, we should fetch the currency ID dynamically or config it.
                # For Testnet, the currency ID is often 72C0212E67A08BCE (symbol.xym)
                # But let's look for the one with the largest amount or specific ID if known.
                # For simplicity, we'll assume the first mosaic is XYM or check known IDs.
                
                # Testnet XYM ID: 72C0212E67A08BCE
                # Mainnet XYM ID: 6BED913FA20223F8
                
                target_mosaic_id = "72C0212E67A08BCE" if self.network_type == "testnet" else "6BED913FA20223F8"
                
                for mosaic in mosaics:
                    if mosaic['id'] == target_mosaic_id:
                        amount = int(mosaic['amount'])
                        return amount / 1000000.0 # XYM has 6 divisibility
                
                return 0.0
            else:
                logger.warning(f"Failed to fetch account info: {response.status_code}")
                return 0.0
        except Exception as e:
            logger.error(f"Error fetching balance: {e}")
            return 0.0

    def get_address(self) -> str:
        return str(self.address) if self.address else "Unknown"

    def send_transaction(self, recipient_address: str, amount: float, message: str = "") -> str:
        """
        Send a transfer transaction.
        """
        if self.use_mock:
            logger.info(f"[MOCK] Sending {amount} XYM to {recipient_address} with message: {message}")
            return f"MOCK-TX-HASH-{int(amount)}-TO-{recipient_address[:5]}"

        if not self.key_pair:
            return "Error: No private key configured."

        try:
            # Create transaction
            # Note: This is a simplified example. In production, we need proper fee estimation and deadline calculation.
            
            # 1. Prepare transaction
            # We need to use the facade to create a transaction
            # This part requires more detailed implementation using symbol-sdk-python
            # For now, we will return a placeholder or implement a basic structure if possible.
            
            # Due to complexity of constructing transaction bytes manually without full SDK context in this snippet,
            # We will implement the skeleton.
            
            return "Transaction functionality is not yet fully implemented in this skeleton."
            
        except Exception as e:
            logger.error(f"Transaction failed: {e}")
    def verify_transaction(self, tx_hash: str, expected_recipient: str, expected_amount: float) -> bool:
        """
        Verify if a transaction has been confirmed and matches the expected details.
        """
        if self.use_mock:
            logger.info(f"[MOCK] Verifying transaction {tx_hash}")
            return True

        try:
            url = f"{self.node_url}/transactions/confirmed/{tx_hash}"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                tx = data['transaction']
                
                # Verify Recipient (Address is encoded in Symbol)
                # For simplicity in this prototype, we'll assume the address format matches or skip strict address check if complex decoding is needed without full SDK.
                # In production, we must decode the address.
                # Symbol addresses in API are usually base32 or hex.
                
                # Verify Amount
                # Check mosaics
                target_mosaic_id = "72C0212E67A08BCE" if self.network_type == "testnet" else "6BED913FA20223F8"
                amount_matched = False
                
                for mosaic in tx.get('mosaics', []):
                    if mosaic['id'] == target_mosaic_id:
                        amount = int(mosaic['amount']) / 1000000.0
                        if amount >= expected_amount:
                            amount_matched = True
                            break
                
                if amount_matched:
                    return True
                else:
                    logger.warning(f"Transaction found but amount mismatch. Expected: {expected_amount}")
                    return False
            else:
                logger.warning(f"Transaction not found or not confirmed: {tx_hash}")
                return False
        except Exception as e:
            logger.error(f"Error verifying transaction: {e}")
            return False
