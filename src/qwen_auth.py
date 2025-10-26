"""Qwen OAuth token refresh utilities."""

import json
import httpx
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


# OAuth Endpoints
QWEN_OAUTH_BASE_URL = "https://chat.qwen.ai"
QWEN_OAUTH_TOKEN_ENDPOINT = f"{QWEN_OAUTH_BASE_URL}/api/v1/oauth2/token"
QWEN_OAUTH_CLIENT_ID = "f0304373b74a44d2b584a3fb70ca9e56"

# Credentials file path
QWEN_CREDS_PATH = Path.home() / ".qwen" / "oauth_creds.json"


@dataclass
class QwenCredentials:
    """Qwen OAuth credentials."""
    access_token: str
    refresh_token: str
    token_type: str
    resource_url: str
    expiry_date: int


class QwenTokenRefresher:
    """Handles Qwen OAuth token refresh."""

    def __init__(self, credentials_path: Path = QWEN_CREDS_PATH):
        self.credentials_path = credentials_path

    def load_credentials(self) -> QwenCredentials:
        """Load credentials from file."""
        with open(self.credentials_path, "r") as f:
            data = json.load(f)
        return QwenCredentials(**data)

    def save_credentials(self, credentials: QwenCredentials) -> None:
        """Save credentials to file."""
        data = {
            "access_token": credentials.access_token,
            "refresh_token": credentials.refresh_token,
            "token_type": credentials.token_type,
            "resource_url": credentials.resource_url,
            "expiry_date": credentials.expiry_date,
        }
        with open(self.credentials_path, "w") as f:
            json.dump(data, f, indent=2)

    async def refresh_access_token(self, refresh_token: str) -> QwenCredentials:
        """Refresh the access token using refresh token.

        Args:
            refresh_token: The refresh token to use

        Returns:
            Updated credentials

        Raises:
            Exception: If token refresh fails
        """
        body_data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": QWEN_OAUTH_CLIENT_ID,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                QWEN_OAUTH_TOKEN_ENDPOINT,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
                data=body_data,
            )

            if not response.ok:
                error_data = await response.aread()
                # Handle 400 errors which might indicate refresh token expiry
                if response.status_code == 400:
                    raise Exception(
                        f"Refresh token expired or invalid. Please use 'qwen auth' to re-authenticate. "
                        f"Error: {error_data.decode()}"
                    )
                raise Exception(
                    f"Token refresh failed: {response.status_code} {response.reason_phrase}. "
                    f"Response: {error_data.decode()}"
                )

            response_data = response.json()

            # Check if the response indicates an error
            if "error" in response_data:
                raise Exception(
                    f"Token refresh failed: {response_data.get('error')} - "
                    f"{response_data.get('error_description', 'No details provided')}"
                )

            # Handle successful response
            import time
            new_credentials = QwenCredentials(
                access_token=response_data["access_token"],
                token_type=response_data.get("token_type", "Bearer"),
                # Use new refresh token if provided, otherwise preserve existing one
                refresh_token=response_data.get("refresh_token", refresh_token),
                resource_url=response_data.get("resource_url", "portal.qwen.ai"),
                expiry_date=int(time.time() * 1000) + int(response_data["expires_in"] * 1000),
            )

            return new_credentials

    async def ensure_valid_token(self) -> QwenCredentials:
        """Ensure we have a valid access token, refreshing if necessary.

        Returns:
            Valid credentials
        """
        credentials = self.load_credentials()

        # Check if token is expired (with 5 minute buffer)
        import time
        current_time_ms = int(time.time() * 1000)
        buffer_ms = 5 * 60 * 1000  # 5 minutes

        if current_time_ms >= (credentials.expiry_date - buffer_ms):
            print("🔄 Access token expired, refreshing...")
            credentials = await self.refresh_access_token(credentials.refresh_token)
            self.save_credentials(credentials)
            print("✅ Token refreshed successfully")

        return credentials
