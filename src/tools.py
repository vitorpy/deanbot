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


class AnalyzeFailureSchema(BaseModel):
    """Schema for analyzing submission failure."""

    failure_dir: str = Field(..., description="Absolute path to failure directory (from failure_dir in submission response)")


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

        # Convert challenges with nested objects
        challenges_list = []
        for c in progress.challenges:
            challenge_dict = c.__dict__.copy()
            # Convert nested LatestAttempt object if present
            if challenge_dict.get("latest_attempt"):
                challenge_dict["latest_attempt"] = challenge_dict["latest_attempt"].__dict__
            challenges_list.append(challenge_dict)

        result = {
            "agent": progress.agent.__dict__ if progress.agent else None,
            "challenges": challenges_list,
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

            result = {
                "status": response.status_code,
                "ok": response.is_success,
                "body": text.decode()
            }

            # Auto-save failures
            if not response.is_success:
                failure_dir = await self._save_failure(slug, program_path, response, text)
                result["failure_dir"] = str(failure_dir)

            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, indent=2)

    async def _save_failure(self, slug: str, program_path: str, response, response_text: bytes) -> Path:
        """Save submission failure artifacts.

        Args:
            slug: Challenge slug
            program_path: Path to .so file
            response: HTTP response
            response_text: Response body bytes

        Returns:
            Path to failure directory
        """
        from datetime import datetime

        # Create failure directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_slug = slug.replace("/", "-")
        failure_root = Path.cwd() / "artifacts" / "failures"
        failure_root.mkdir(parents=True, exist_ok=True)

        failure_dir = failure_root / f"{safe_slug}_{timestamp}"
        failure_dir.mkdir(exist_ok=True)

        # Save program.so
        program_so_dest = failure_dir / "program.so"
        import shutil
        shutil.copy2(program_path, program_so_dest)

        # Save API response
        api_response = {
            "status": response.status_code,
            "headers": dict(response.headers),
            "body": response_text.decode(errors="replace"),
        }
        (failure_dir / "api_response.json").write_text(
            json.dumps(api_response, indent=2), encoding="utf-8"
        )

        # Try to find and copy source files
        # .so path is usually: {workspace}/target/deploy/{name}.so
        program_path_obj = Path(program_path)
        if program_path_obj.parts[-3:-1] == ("target", "deploy"):
            # Infer workspace directory
            workspace_dir = program_path_obj.parents[2]
            source_dir = workspace_dir / "source"

            if source_dir.exists():
                # Copy source files
                dest_source_dir = failure_dir / "source"
                shutil.copytree(source_dir, dest_source_dir)

        # Save metadata
        metadata = {
            "slug": slug,
            "timestamp": timestamp,
            "program_path": str(program_path),
            "workspace_inferred": str(workspace_dir) if 'workspace_dir' in locals() else None,
        }
        (failure_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )

        return failure_dir


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
                "sourceFiles": result.source_files,
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


class AnalyzeSubmissionFailureTool(BaseTool):
    """Tool to analyze submission failures."""

    name: str = "analyze_submission_failure"
    description: str = (
        "Analyzes a failed submission by examining the error, source code, and build logs. "
        "Searches knowledge base for similar issues and suggests fixes. "
        "Use this after a submission fails to understand why and how to fix it."
    )
    args_schema: type[BaseModel] = AnalyzeFailureSchema

    rag_tool: BaseTool  # Knowledge base search tool

    class Config:
        arbitrary_types_allowed = True

    def _run(self, failure_dir: str) -> str:
        """Analyze failure - sync wrapper."""
        import asyncio
        return asyncio.run(self._arun(failure_dir))

    async def _arun(self, failure_dir: str) -> str:
        """Analyze failure."""
        failure_path = Path(failure_dir)

        if not failure_path.exists():
            return f"Error: Failure directory not found: {failure_dir}"

        # Read API response
        api_response_file = failure_path / "api_response.json"
        if not api_response_file.exists():
            return f"Error: api_response.json not found in {failure_dir}"

        api_response = json.loads(api_response_file.read_text())
        error_message = api_response.get("body", "No error message")
        status_code = api_response.get("status", 0)

        # Read source files if available
        source_dir = failure_path / "source"
        lib_rs_content = None
        cargo_toml_content = None
        build_log_content = None

        if source_dir.exists():
            lib_rs_file = source_dir / "lib.rs"
            cargo_toml_file = source_dir / "Cargo.toml"
            build_log_file = source_dir / "build.log"

            if lib_rs_file.exists():
                lib_rs_content = lib_rs_file.read_text()
            if cargo_toml_file.exists():
                cargo_toml_content = cargo_toml_file.read_text()
            if build_log_file.exists():
                build_log_content = build_log_file.read_text()

        # Extract error type for KB search
        error_keywords = self._extract_error_keywords(error_message)

        # Search knowledge base
        kb_results = None
        if self.rag_tool and error_keywords:
            try:
                kb_query = f"solana anchor error {error_keywords}"
                kb_results = await self.rag_tool._arun(kb_query)
            except Exception as e:
                kb_results = f"KB search failed: {e}"

        # Build analysis
        analysis_lines = [
            f"# Failure Analysis",
            f"",
            f"## Error Details",
            f"- **Status Code**: {status_code}",
            f"- **Error Message**:",
            f"```",
            error_message,
            f"```",
            f"",
        ]

        if build_log_content:
            # Check for warnings in build log
            warnings = [line for line in build_log_content.split("\n") if "warning" in line.lower()]
            if warnings:
                analysis_lines.extend([
                    f"## Build Warnings",
                    "```",
                    *warnings[:10],  # Limit to 10 warnings
                    "```",
                    "",
                ])

        if kb_results:
            analysis_lines.extend([
                f"## Knowledge Base Search",
                f"Query: `{error_keywords}`",
                f"",
                kb_results,
                f"",
            ])

        if lib_rs_content:
            # Basic code analysis
            analysis_lines.extend([
                f"## Code Analysis",
                f"- Source file exists: lib.rs ({len(lib_rs_content)} bytes)",
                "",
            ])

        analysis_lines.extend([
            f"## Suggested Actions",
            f"1. Review the error message above",
            f"2. Check similar examples in knowledge base results",
            f"3. Verify program ID is: `declare_id!(\"22222222222222222222222222222222222222222222\");`",
            f"4. Verify anchor-lang version is 0.32.1 in Cargo.toml",
            f"5. Review build warnings if any",
            f"",
            f"## Artifacts Saved",
            f"- Location: `{failure_dir}`",
            f"- program.so: Available",
            f"- Source files: {'Available' if source_dir.exists() else 'Not available'}",
        ])

        analysis_text = "\n".join(analysis_lines)

        # Write analysis.md
        analysis_file = failure_path / "analysis.md"
        analysis_file.write_text(analysis_text, encoding="utf-8")

        return analysis_text

    def _extract_error_keywords(self, error_message: str) -> str:
        """Extract keywords from error message for KB search."""
        # Simple keyword extraction - look for common error patterns
        keywords = []

        error_lower = error_message.lower()

        if "compute" in error_lower:
            keywords.append("compute budget")
        if "account" in error_lower:
            keywords.append("account")
        if "instruction" in error_lower:
            keywords.append("instruction")
        if "deserialize" in error_lower or "serialize" in error_lower:
            keywords.append("serialization")
        if "constraint" in error_lower:
            keywords.append("constraint")
        if "seed" in error_lower or "pda" in error_lower:
            keywords.append("PDA seeds")

        return " ".join(keywords) if keywords else "error"


def build_orchestrator_tools(
    client: BlueshiftClient,
    wallet: SolanaWallet,
    config: "AgentConfig" = None,
    solana_mcp_tools: list = None,
    rag_tool: BaseTool = None,
    output_callback: callable = None,
) -> list[BaseTool]:
    """Build orchestrator agent tools (coordination only, no challenge-solving tools).

    The orchestrator spawns Python subagents for actual challenge solving.

    Args:
        client: Blueshift API client
        wallet: Solana wallet
        config: Agent configuration (for spawning subagents)
        solana_mcp_tools: Solana MCP tools to pass to subagents
        rag_tool: RAG knowledge base search tool to pass to subagents
        output_callback: Callback for subagent output

    Returns:
        List of coordination tools only
    """
    from subagent_runner import SolveChallengeTool

    tools = [
        GetWalletAddressTool(wallet=wallet),
        ListChallengesTool(client=client),
        GetProgressTool(client=client),
    ]

    # Add subagent spawner if we have the dependencies
    if config and solana_mcp_tools is not None:
        tools.append(
            SolveChallengeTool(
                config=config,
                wallet=wallet,
                blueshift_client=client,
                solana_mcp_tools=solana_mcp_tools,
                rag_tool=rag_tool,
                output_callback=output_callback,
            )
        )

    return tools


def build_agent_tools(client: BlueshiftClient, wallet: SolanaWallet, rag_tool: BaseTool = None) -> list[BaseTool]:
    """Build all agent tools (for challenge-solver subagents).

    Args:
        client: Blueshift API client
        wallet: Solana wallet
        rag_tool: Optional RAG knowledge base search tool

    Returns:
        List of all LangChain tools
    """
    tools = [
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

    if rag_tool:
        tools.append(rag_tool)
        # Add failure analysis tool (depends on rag_tool)
        tools.append(AnalyzeSubmissionFailureTool(rag_tool=rag_tool))

    return tools
