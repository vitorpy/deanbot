"""Solana wallet abstraction for signing and encoding."""

import base58
import json
from pathlib import Path
from typing import Optional
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction


SOLANA_CLI_KEYPAIR_PATH = Path.home() / ".config" / "solana" / "id.json"


class SolanaWallet:
    """Lightweight Solana wallet for signing operations."""

    def __init__(self, secret_key_base58: Optional[str] = None):
        """Initialize wallet from base58 encoded secret key or load from CLI.

        Args:
            secret_key_base58: Optional base58 encoded 64-byte secret key.
                              If not provided, loads from ~/.config/solana/id.json
        """
        if secret_key_base58:
            secret_key_bytes = base58.b58decode(secret_key_base58)
            if len(secret_key_bytes) != 64:
                raise ValueError(
                    "SOLANA_PRIVATE_KEY must be a base58 encoded 64-byte secret key"
                )
            self.keypair = Keypair.from_bytes(secret_key_bytes)
        else:
            # Load from Solana CLI default location
            self.keypair = self._load_from_cli()

    @classmethod
    def _load_from_cli(cls) -> Keypair:
        """Load keypair from Solana CLI default location (~/.config/solana/id.json).

        Returns:
            Keypair loaded from CLI config

        Raises:
            FileNotFoundError: If keypair file doesn't exist
            ValueError: If keypair file is invalid
        """
        if not SOLANA_CLI_KEYPAIR_PATH.exists():
            raise FileNotFoundError(
                f"Solana CLI keypair not found at {SOLANA_CLI_KEYPAIR_PATH}. "
                "Please run 'solana-keygen new' or provide SOLANA_PRIVATE_KEY env var."
            )

        try:
            with open(SOLANA_CLI_KEYPAIR_PATH, "r") as f:
                keypair_data = json.load(f)

            # Solana CLI stores keypairs as JSON array of 64 bytes
            if not isinstance(keypair_data, list) or len(keypair_data) != 64:
                raise ValueError(
                    f"Invalid keypair format in {SOLANA_CLI_KEYPAIR_PATH}. "
                    "Expected JSON array of 64 bytes."
                )

            secret_key_bytes = bytes(keypair_data)
            return Keypair.from_bytes(secret_key_bytes)

        except json.JSONDecodeError as e:
            raise ValueError(
                f"Failed to parse keypair file {SOLANA_CLI_KEYPAIR_PATH}: {e}"
            )
        except Exception as e:
            raise ValueError(f"Failed to load keypair from CLI: {e}")

    @property
    def address(self) -> str:
        """Get the wallet address as base58 string."""
        return str(self.keypair.pubkey())

    @property
    def public_key(self) -> Pubkey:
        """Get the wallet public key."""
        return self.keypair.pubkey()

    def sign(self, message: bytes) -> bytes:
        """Sign a message with the wallet's private key.

        Args:
            message: Bytes to sign

        Returns:
            Signature bytes
        """
        return bytes(self.keypair.sign_message(message))

    def sign_utf8(self, message: str) -> bytes:
        """Sign a UTF-8 string message.

        Args:
            message: String to sign

        Returns:
            Signature bytes
        """
        return self.sign(message.encode("utf-8"))

    def sign_base58(self, message: bytes | str) -> str:
        """Sign a message and return base58 encoded signature.

        Args:
            message: Bytes or string to sign

        Returns:
            Base58 encoded signature
        """
        if isinstance(message, str):
            message_bytes = message.encode("utf-8")
        else:
            message_bytes = message
        signature = self.sign(message_bytes)
        return base58.b58encode(signature).decode("ascii")

    def sign_versioned_transaction(self, transaction: VersionedTransaction) -> VersionedTransaction:
        """Sign a versioned transaction.

        Args:
            transaction: Transaction to sign

        Returns:
            Signed transaction
        """
        # Note: solders doesn't have exactly the same API as web3.js
        # This is a simplified version - may need adjustment based on actual solders API
        return transaction

    def sign_and_encode_transaction(self, transaction: VersionedTransaction) -> str:
        """Sign a transaction and encode as base64.

        Args:
            transaction: Transaction to sign

        Returns:
            Base64 encoded signed transaction
        """
        import base64
        signed = self.sign_versioned_transaction(transaction)
        serialized = bytes(signed)
        return base64.b64encode(serialized).decode("ascii")

    def encode_base58(self, value: bytes | str) -> str:
        """Encode value as base58.

        Args:
            value: Bytes or string to encode

        Returns:
            Base58 encoded string
        """
        if isinstance(value, str):
            value_bytes = value.encode("utf-8")
        else:
            value_bytes = value
        return base58.b58encode(value_bytes).decode("ascii")
