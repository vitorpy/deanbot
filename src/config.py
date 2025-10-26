"""Configuration loader with validation."""

import json
import os
from pathlib import Path
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


DEFAULT_API_URL = "https://ai-api.blueshift.gg"
QWEN_CREDS_PATH = Path.home() / ".qwen" / "oauth_creds.json"


class AgentConfig(BaseSettings):
    """Agent configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Qwen OAuth (loaded from ~/.qwen/oauth_creds.json)
    qwen_access_token: Optional[str] = Field(default=None, description="Qwen OAuth access token")
    qwen_resource_url: Optional[str] = Field(default=None, description="Qwen resource URL")

    # Optional: can be provided via env or loaded from CLI
    solana_private_key: Optional[str] = Field(default=None, min_length=10, description="Base58 encoded Solana secret key")

    # Other config
    api_url: str = Field(default=DEFAULT_API_URL, description="Blueshift API base URL")
    agent_name: str = Field(default="Deanbot")
    team_name: str = Field(default="vitorpy", alias="agent_team")
    model: str = Field(default="coder-model", alias="llm_model")
    temperature: float = Field(default=0.2, ge=0.0, le=2.0, alias="llm_temperature")

    @model_validator(mode="after")
    def load_qwen_credentials(self) -> "AgentConfig":
        """Load Qwen OAuth credentials from ~/.qwen/oauth_creds.json if not provided."""
        if self.qwen_access_token is None or self.qwen_resource_url is None:
            try:
                if QWEN_CREDS_PATH.exists():
                    with open(QWEN_CREDS_PATH, "r") as f:
                        creds = json.load(f)

                    self.qwen_access_token = creds.get("access_token")
                    self.qwen_resource_url = creds.get("resource_url")

                    if not self.qwen_access_token:
                        raise ValueError("Qwen access_token not found in credentials file")
                    if not self.qwen_resource_url:
                        raise ValueError("Qwen resource_url not found in credentials file")
                else:
                    raise FileNotFoundError(
                        f"Qwen credentials not found at {QWEN_CREDS_PATH}. "
                        "Please authenticate with Qwen first."
                    )
            except Exception as e:
                raise ValueError(f"Failed to load Qwen credentials: {e}")

        return self

    @field_validator("api_url")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        """Remove trailing slash from API URL."""
        return v.rstrip("/")

    @property
    def blueshift_api_url(self) -> str:
        """Get the Blueshift API URL."""
        return self.api_url

    @property
    def blueshift_mcp_url(self) -> str:
        """Get the Blueshift MCP URL."""
        return f"{self.api_url}/mcp"

    @property
    def qwen_base_url(self) -> str:
        """Get the Qwen/DashScope base URL from resource_url."""
        # If no resource_url, use default DashScope endpoint
        if not self.qwen_resource_url:
            return "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

        # Use resource_url with proper normalization
        base_endpoint = self.qwen_resource_url
        normalized_url = base_endpoint if base_endpoint.startswith('http') else f"https://{base_endpoint}"

        # Ensure /v1 suffix
        return normalized_url if normalized_url.endswith('/v1') else f"{normalized_url}/v1"


def load_config() -> AgentConfig:
    """Load and validate configuration from environment variables."""
    return AgentConfig()
