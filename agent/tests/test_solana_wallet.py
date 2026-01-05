import unittest
from unittest.mock import MagicMock, patch
import os
import sys

# Add parent directory to path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dak_agent.wallets.solana_wallet import SolanaWalletManager

class TestSolanaWalletManager(unittest.TestCase):
    def setUp(self):
        # Force mock mode for testing
        self.patcher = patch.dict(os.environ, {"SOLANA_USE_MOCK": "true"})
        self.patcher.start()
        self.wallet = SolanaWalletManager()

    def tearDown(self):
        self.patcher.stop()

    def test_initialization_mock(self):
        self.assertTrue(self.wallet.use_mock)
        self.assertEqual(self.wallet.get_balance(), 1000.0)

    def test_get_address(self):
        address = self.wallet.get_address()
        self.assertTrue(address.startswith("MockSoL"))

    def test_send_transaction_mock(self):
        initial_balance = self.wallet.get_balance()
        recipient = "RecipientAddress123"
        amount = 10.0
        
        tx_hash = self.wallet.send_transaction(recipient, amount)
        
        self.assertTrue(tx_hash.startswith("MockTx_"))
        self.assertEqual(self.wallet.get_balance(), initial_balance - amount)

    def test_verify_transaction_mock(self):
        tx_hash = "MockTx_123"
        self.assertTrue(self.wallet.verify_transaction(tx_hash, "any", 1.0))

if __name__ == '__main__':
    unittest.main()
