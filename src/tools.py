"""LangChain tools for Blueshift agent."""

import json
from pathlib import Path
from typing import Optional, Literal

from langchain.tools import BaseTool
from pydantic import BaseModel, Field

from solana_wallet import SolanaWallet
from blueshift_client import BlueshiftClient
from anchor_builder import create_anchor_program, run_anchor_build


# Tool Schemas


class EmptySchema(BaseModel):
    """Empty schema for tools with no parameters."""

    pass


class NamespaceKeySchema(BaseModel):
    """Schema for namespace and key."""

    namespace: str = Field(..., min_length=1)
    key: str = Field(..., min_length=1)


class ChallengeSlugSchema(BaseModel):
    """Schema for challenge slug."""

    slug: str = Field(..., min_length=1)


class SignBytesSchema(BaseModel):
    """Schema for signing bytes."""

    data: str = Field(..., description="Input data to sign")
    encoding: Literal["base64", "utf8", "hex"] = Field(
        default="base64", description="Encoding of input data"
    )


class EncodeBase58Schema(BaseModel):
    """Schema for base58 encoding."""

    data: str = Field(..., description="Input data to encode")
    encoding: Literal["base64", "utf8", "hex"] = Field(
        default="base64", description="Encoding of input data"
    )


class AttemptProgramSchema(BaseModel):
    """Schema for program challenge attempt."""

    slug: str = Field(..., min_length=1)
    program_path: str = Field(..., description="Absolute path to .so file")


class AttemptClientSchema(BaseModel):
    """Schema for client challenge attempt."""

    slug: str = Field(..., min_length=1)
    transaction_base64: str = Field(..., min_length=1, description="Base64 encoded transaction")


class CreateAnchorProgramSchema(BaseModel):
    """Schema for creating Anchor program."""

    program_name: str = Field(..., min_length=1)
    cargo_toml: str = Field(..., min_length=1, description="Complete Cargo.toml content")
    lib_rs: str = Field(..., min_length=1, description="Complete lib.rs content")


class ReadFileSchema(BaseModel):
    """Schema for reading a file."""

    file_path: str = Field(..., description="Absolute path to file")


class WriteFileSchema(BaseModel):
    """Schema for writing a file."""

    file_path: str = Field(..., description="Absolute path to file")
    content: str = Field(..., description="File content")


class RunAnchorBuildSchema(BaseModel):
    """Schema for running anchor build."""

    workspace_dir: str = Field(..., description="Absolute path to workspace directory")


# Tools


class GetWalletAddressTool(BaseTool):
    """Tool to get wallet address."""

    name: str = "wallet_get_address"
    description: str = "Returns the active Solana wallet address (base58)."
    args_schema: type[BaseModel] = EmptySchema

    wallet: SolanaWallet

    def _run(self) -> str:
        """Get wallet address."""
        return self.wallet.address

    async def _arun(self) -> str:
        """Async version."""
        return self._run()


class SignBytesTool(BaseTool):
    """Tool to sign bytes."""

    name: str = "wallet_sign_bytes"
    description: str = "Signs arbitrary bytes with the active wallet and returns base58 signature."
    args_schema: type[BaseModel] = SignBytesSchema

    wallet: SolanaWallet

    def _run(self, data: str, encoding: str = "base64") -> str:
        """Sign bytes."""
        import base64

        if encoding == "utf8":
            data_bytes = data.encode("utf-8")
        elif encoding == "hex":
            data_bytes = bytes.fromhex(data.replace("0x", ""))
        else:  # base64
            data_bytes = base64.b64decode(data)

        return self.wallet.sign_base58(data_bytes)

    async def _arun(self, data: str, encoding: str = "base64") -> str:
        """Async version."""
        return self._run(data, encoding)


class EncodeBase58Tool(BaseTool):
    """Tool to encode base58."""

    name: str = "wallet_encode_base58"
    description: str = "Encodes provided bytes into base58."
    args_schema: type[BaseModel] = EncodeBase58Schema

    wallet: SolanaWallet

    def _run(self, data: str, encoding: str = "base64") -> str:
        """Encode base58."""
        import base64

        if encoding == "utf8":
            data_bytes = data.encode("utf-8")
        elif encoding == "hex":
            data_bytes = bytes.fromhex(data.replace("0x", ""))
        else:  # base64
            data_bytes = base64.b64decode(data)

        return self.wallet.encode_base58(data_bytes)

    async def _arun(self, data: str, encoding: str = "base64") -> str:
        """Async version."""
        return self._run(data, encoding)


class ListChallengesTool(BaseTool):
    """Tool to list challenges."""

    name: str = "blueshift_list_challenges"
    description: str = "Lists all available Blueshift coding challenges."
    args_schema: type[BaseModel] = EmptySchema

    client: BlueshiftClient

    def _run(self) -> str:
        """List challenges - sync wrapper."""
        import asyncio

        return asyncio.run(self._arun())

    async def _arun(self) -> str:
        """List challenges."""
        challenges = await self.client.list_challenges()
        return json.dumps([c.__dict__ for c in challenges], indent=2)


class GetChallengeTool(BaseTool):
    """Tool to get challenge details."""

    name: str = "blueshift_get_challenge"
    description: str = "Fetches details for a specific challenge by namespace and key."
    args_schema: type[BaseModel] = NamespaceKeySchema

    client: BlueshiftClient

    def _run(self, namespace: str, key: str) -> str:
        """Get challenge - sync wrapper."""
        import asyncio

        return asyncio.run(self._arun(namespace, key))

    async def _arun(self, namespace: str, key: str) -> str:
        """Get challenge."""
        challenge = await self.client.get_challenge(namespace, key)
        return json.dumps(challenge.__dict__, indent=2)


class GetProgressTool(BaseTool):
    """Tool to get agent progress."""

    name: str = "blueshift_get_progress"
    description: str = "Returns the current progress for the agent wallet."
    args_schema: type[BaseModel] = EmptySchema

    client: BlueshiftClient

    def _run(self) -> str:
        """Get progress - sync wrapper."""
        import asyncio

        return asyncio.run(self._arun())

    async def _arun(self) -> str:
        """Get progress."""
        progress = await self.client.get_progress()
        result = {
            "agent": progress.agent.__dict__ if progress.agent else None,
            "challenges": [c.__dict__ for c in progress.challenges],
        }
        return json.dumps(result, indent=2)


class AttemptProgramTool(BaseTool):
    """Tool to submit program challenge."""

    name: str = "blueshift_attempt_program"
    description: str = "Submits a program challenge attempt. Provide slug and path to .so file."
    args_schema: type[BaseModel] = AttemptProgramSchema

    client: BlueshiftClient

    def _run(self, slug: str, program_path: str) -> str:
        """Submit program - sync wrapper."""
        import asyncio

        return asyncio.run(self._arun(slug, program_path))

    async def _arun(self, slug: str, program_path: str) -> str:
        """Submit program."""
        try:
            program_buffer = Path(program_path).read_bytes()
            response = await self.client.submit_program_challenge(slug, program_buffer)
            text = await response.aread()

            return json.dumps(
                {"status": response.status_code, "ok": response.is_success, "body": text.decode()},
                indent=2,
            )
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, indent=2)


class AttemptClientTool(BaseTool):
    """Tool to submit client challenge."""

    name: str = "blueshift_attempt_client"
    description: str = "Submits a client challenge attempt. Provide slug and transaction."
    args_schema: type[BaseModel] = AttemptClientSchema

    client: BlueshiftClient

    def _run(self, slug: str, transaction_base64: str) -> str:
        """Submit client - sync wrapper."""
        import asyncio

        return asyncio.run(self._arun(slug, transaction_base64))

    async def _arun(self, slug: str, transaction_base64: str) -> str:
        """Submit client."""
        result = await self.client.submit_client_challenge(slug, transaction_base64)
        return json.dumps(result, indent=2)


class CreateAnchorProgramTool(BaseTool):
    """Tool to create Anchor program."""

    name: str = "anchor_create_program"
    description: str = (
        "Scaffolds an Anchor workspace, replaces lib.rs and Cargo.toml, builds, "
        "and returns workspace path and .so artifact."
    )
    args_schema: type[BaseModel] = CreateAnchorProgramSchema

    def _run(self, program_name: str, cargo_toml: str, lib_rs: str) -> str:
        """Create program - sync wrapper."""
        import asyncio

        return asyncio.run(self._arun(program_name, cargo_toml, lib_rs))

    async def _arun(self, program_name: str, cargo_toml: str, lib_rs: str) -> str:
        """Create program."""
        result = await create_anchor_program(program_name, cargo_toml, lib_rs)

        build_dict = None
        if result.build:
            build_dict = {
                "success": result.build.success,
                "stdout": result.build.stdout,
                "stderr": result.build.stderr,
                "programSoPath": result.build.program_so_path,
                "keypairPath": result.build.keypair_path,
                "errorMessage": result.build.error_message,
            }

        return json.dumps(
            {
                "workspaceDir": result.workspace_dir,
                "files": result.files,
                "build": build_dict,
            },
            indent=2,
        )


class ReadFileTool(BaseTool):
    """Tool to read a file."""

    name: str = "read_file"
    description: str = "Reads the contents of a file. Use this to inspect generated Anchor files."
    args_schema: type[BaseModel] = ReadFileSchema

    def _run(self, file_path: str) -> str:
        """Read file."""
        try:
            return Path(file_path).read_text(encoding="utf-8")
        except Exception as e:
            return f"Error reading file: {e}"

    async def _arun(self, file_path: str) -> str:
        """Async version."""
        return self._run(file_path)


class WriteFileTool(BaseTool):
    """Tool to write a file."""

    name: str = "write_file"
    description: str = (
        "Writes content to a file, overwriting completely. "
        "Use this to modify Anchor lib.rs, Cargo.toml, etc."
    )
    args_schema: type[BaseModel] = WriteFileSchema

    def _run(self, file_path: str, content: str) -> str:
        """Write file."""
        try:
            Path(file_path).write_text(content, encoding="utf-8")
            return f"Successfully wrote {len(content)} bytes to {file_path}"
        except Exception as e:
            return f"Error writing file: {e}"

    async def _arun(self, file_path: str, content: str) -> str:
        """Async version."""
        return self._run(file_path, content)


class RunAnchorBuildTool(BaseTool):
    """Tool to run anchor build."""

    name: str = "run_anchor_build"
    description: str = "Runs 'anchor build' in the workspace and returns .so file path."
    args_schema: type[BaseModel] = RunAnchorBuildSchema

    def _run(self, workspace_dir: str) -> str:
        """Run build - sync wrapper."""
        import asyncio

        return asyncio.run(self._arun(workspace_dir))

    async def _arun(self, workspace_dir: str) -> str:
        """Run build."""
        result = await run_anchor_build(workspace_dir)
        return json.dumps(result, indent=2)


def build_agent_tools(client: BlueshiftClient, wallet: SolanaWallet) -> list[BaseTool]:
    """Build all agent tools.

    Args:
        client: Blueshift API client
        wallet: Solana wallet

    Returns:
        List of LangChain tools
    """
    return [
        GetWalletAddressTool(wallet=wallet),
        SignBytesTool(wallet=wallet),
        EncodeBase58Tool(wallet=wallet),
        ListChallengesTool(client=client),
        GetChallengeTool(client=client),
        GetProgressTool(client=client),
        AttemptProgramTool(client=client),
        AttemptClientTool(client=client),
        CreateAnchorProgramTool(),
        ReadFileTool(),
        WriteFileTool(),
        RunAnchorBuildTool(),
    ]
