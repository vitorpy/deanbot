"""Blueshift API client for challenge management and submissions."""

from typing import Literal
from dataclasses import dataclass
import httpx

from solana_wallet import SolanaWallet


@dataclass
class ChallengeSummary:
    """Summary of a challenge."""

    slug: str
    name: str
    category: str
    challenge_type: Literal["program", "client"]
    submission_endpoint: str
    problem_description: str


@dataclass
class LatestAttempt:
    """Latest attempt information."""

    passed: bool
    cu_consumed: int | None
    binary_size: int | None
    attempt_time: str


@dataclass
class ProgressEntry:
    """Progress entry for a challenge."""

    slug: str
    name: str
    category: str
    challenge_type: Literal["program", "client"]
    submission_endpoint: str
    problem_description: str
    attempt_count: int
    completed: bool
    latest_attempt: LatestAttempt | None = None


@dataclass
class Agent:
    """Agent information."""

    agent_name: str
    team: str
    address: str
    model: str | None
    registered_at: str


@dataclass
class ProgressResponse:
    """Response from progress endpoint."""

    agent: Agent | None
    challenges: list[ProgressEntry]


@dataclass
class ClientSubmissionSuccess:
    """Successful client submission response."""

    success: bool
    results: list[dict]


@dataclass
class ClientSubmissionError:
    """Error response from client submission."""

    error: str
    message: str


class BlueshiftClient:
    """Client for interacting with Blueshift API."""

    def __init__(self, base_url: str, wallet: SolanaWallet):
        """Initialize client.

        Args:
            base_url: Base URL for Blueshift API
            wallet: Solana wallet for signing
        """
        self.base_url = base_url.rstrip("/")
        self.wallet = wallet
        self.client = httpx.AsyncClient(timeout=30.0)

    def _endpoint(self, pathname: str) -> str:
        """Build full endpoint URL.

        Args:
            pathname: URL path

        Returns:
            Full endpoint URL
        """
        return f"{self.base_url}{pathname}"

    async def list_challenges(self) -> list[ChallengeSummary]:
        """List all available challenges.

        Returns:
            List of challenge summaries
        """
        url = self._endpoint("/v1/challenges")
        response = await self.client.get(url)
        response.raise_for_status()
        payload = response.json()
        return [ChallengeSummary(**c) for c in payload["challenges"]]

    async def get_challenge(self, namespace: str, key: str) -> ChallengeSummary:
        """Get a specific challenge.

        Args:
            namespace: Challenge namespace
            key: Challenge key

        Returns:
            Challenge summary
        """
        url = self._endpoint(f"/v1/challenges/{namespace}/{key}")
        response = await self.client.get(url)
        response.raise_for_status()
        payload = response.json()
        return ChallengeSummary(**payload["challenge"])

    async def get_progress(self, address: str | None = None) -> ProgressResponse:
        """Get agent progress.

        Args:
            address: Optional wallet address (defaults to client wallet)

        Returns:
            Progress response
        """
        addr = address or self.wallet.address
        url = self._endpoint(f"/v1/agents/{addr}/progress")
        response = await self.client.get(url)

        if response.status_code == 404:
            return ProgressResponse(agent=None, challenges=[])

        response.raise_for_status()
        payload = response.json()

        agent = Agent(**payload["agent"]) if payload.get("agent") else None
        challenges = []
        for c in payload.get("challenges", []):
            latest = None
            if c.get("latest_attempt"):
                latest = LatestAttempt(**c["latest_attempt"])
            challenges.append(
                ProgressEntry(
                    slug=c["slug"],
                    name=c["name"],
                    category=c["category"],
                    challenge_type=c["challenge_type"],
                    submission_endpoint=c["submission_endpoint"],
                    problem_description=c["problem_description"],
                    attempt_count=c["attempt_count"],
                    completed=c["completed"],
                    latest_attempt=latest,
                )
            )

        return ProgressResponse(agent=agent, challenges=challenges)

    async def submit_program_challenge(
        self, slug: str, program_buffer: bytes
    ) -> httpx.Response:
        """Submit a program challenge.

        Args:
            slug: Challenge slug
            program_buffer: Compiled .so program bytes

        Returns:
            HTTP response
        """
        url = self._endpoint(f"/v1/challenges/program/{slug}")

        file_name = f"{slug}-submission.so"
        signature_base58 = self.wallet.sign_base58(program_buffer)

        files = {"program": (file_name, program_buffer, "application/octet-stream")}
        data = {"signature": signature_base58, "address": self.wallet.address}

        response = await self.client.post(url, files=files, data=data)
        return response

    async def submit_client_challenge(
        self, slug: str, transaction_base64: str
    ) -> dict:
        """Submit a client challenge.

        Args:
            slug: Challenge slug
            transaction_base64: Base64 encoded signed transaction

        Returns:
            Response payload (success or error)
        """
        url = self._endpoint(f"/v1/challenges/client/{slug}")

        body = {"transaction": transaction_base64, "address": self.wallet.address}

        response = await self.client.post(url, json=body)
        payload = response.json()

        if response.is_success and "success" in payload and isinstance(payload.get("results"), list):
            return {
                "ok": True,
                "status": response.status_code,
                "body": payload,
            }

        error_body = (
            payload
            if "error" in payload and "message" in payload
            else {"error": "Invalid response", "message": str(payload)}
        )

        return {
            "ok": False,
            "status": response.status_code,
            "body": error_body,
        }

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
