"""Subagent runner for challenge solving."""

import asyncio
from langchain.tools import BaseTool
from pydantic import BaseModel, Field

from config import AgentConfig
from solana_wallet import SolanaWallet
from blueshift_client import BlueshiftClient
from agent import create_coding_agent, build_system_prompt
from langchain_core.messages import SystemMessage, HumanMessage


class SolveChallengeTool(BaseTool):
    """Tool to spawn a subagent that solves a specific challenge."""

    name: str = "solve_challenge_with_subagent"
    description: str = (
        "Spawns a fresh subagent to solve a specific challenge. "
        "The subagent has full access to challenge-solving tools including Solana MCP. "
        "Use this to delegate actual challenge solving. "
        "Args: challenge_slug (e.g., 'anchor/vault'), challenge_name, challenge_category, difficulty"
    )

    config: AgentConfig
    wallet: SolanaWallet
    blueshift_client: BlueshiftClient
    solana_mcp_tools: list
    rag_tool: BaseTool
    output_callback: callable

    class Config:
        arbitrary_types_allowed = True

    class InputSchema(BaseModel):
        challenge_slug: str = Field(..., description="Challenge slug (e.g., 'anchor/vault')")
        challenge_name: str = Field(..., description="Human-readable challenge name")
        challenge_category: str = Field(..., description="Category (anchor, pinocchio, etc.)")
        difficulty: str = Field(..., description="Difficulty level")

    args_schema: type[BaseModel] = InputSchema

    def _run(
        self,
        challenge_slug: str,
        challenge_name: str,
        challenge_category: str,
        difficulty: str,
    ) -> str:
        """Sync wrapper."""
        return asyncio.run(
            self._arun(challenge_slug, challenge_name, challenge_category, difficulty)
        )

    async def _arun(
        self,
        challenge_slug: str,
        challenge_name: str,
        challenge_category: str,
        difficulty: str,
    ) -> str:
        """Spawn a subagent to solve the challenge."""
        # Notify via callback
        if self.output_callback:
            self.output_callback(
                f"🚀 Spawning subagent for {challenge_slug}",
                is_task=True
            )

        # Build subagent-specific prompt
        subagent_prompt = self._build_subagent_prompt(
            challenge_slug, challenge_name, challenge_category, difficulty
        )

        # Build full tools including RAG
        from tools import build_agent_tools
        base_tools = build_agent_tools(self.blueshift_client, self.wallet, self.rag_tool)
        all_tools = [*base_tools, *self.solana_mcp_tools]

        # Create fresh subagent with full tools + Solana MCP + RAG
        subagent = await create_coding_agent(
            self.config,
            self.wallet,
            self.blueshift_client,
            extra_tools=all_tools,
            orchestrator=False,  # Full toolset
        )

        # Run subagent with fresh recursion limit
        thread_id = f"subagent-{challenge_slug.replace('/', '-')}"
        config_block = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": 50,  # Higher limit for subagent
        }

        # Collect subagent output
        result_lines = []

        try:
            async for chunk in subagent.astream(
                {"messages": [subagent_prompt]}, config_block
            ):
                if not isinstance(chunk, dict):
                    continue

                # Capture subagent messages
                if "agent" in chunk and "messages" in chunk["agent"]:
                    for message in chunk["agent"]["messages"]:
                        if hasattr(message, "content") and message.content:
                            content = str(message.content)
                            if content.strip():
                                result_lines.append(content)
                                if self.output_callback:
                                    self.output_callback(content[:200], is_task=True)

                        # Log tool calls
                        if hasattr(message, "tool_calls") and message.tool_calls:
                            for tool_call in message.tool_calls:
                                tool_name = tool_call["name"]
                                msg = f"  → {tool_name}"
                                result_lines.append(msg)
                                if self.output_callback:
                                    self.output_callback(msg, is_task=True)

                # Capture tool outputs
                elif "tools" in chunk and "messages" in chunk["tools"]:
                    for message in chunk["tools"]["messages"]:
                        if hasattr(message, "content"):
                            output = str(message.content)
                            # Truncate for display
                            display_output = output if len(output) <= 500 else output[:500] + "..."
                            result_lines.append(f"Tool: {output[:100]}")
                            if self.output_callback:
                                self.output_callback(f"📋 {display_output}", is_task=True)

            # Check final result
            final_output = "\n".join(result_lines)

            # Determine success/failure with multiple checks
            success = self._check_success(final_output)

            if success:
                result = f"✅ SUCCESS: Challenge {challenge_slug} completed"
                if self.output_callback:
                    self.output_callback(result, is_task=True)
                return result
            else:
                result = f"❌ FAILURE: Challenge {challenge_slug} failed\n{final_output[-500:]}"
                if self.output_callback:
                    self.output_callback(result, is_task=True)
                return result

    def _check_success(self, output: str) -> bool:
        """Check if the output indicates success.

        Args:
            output: Combined output from all tool calls

        Returns:
            True if success indicators found, False otherwise
        """
        output_lower = output.lower()

        # Check for explicit success indicators
        if "passed" in output_lower:
            return True
        if "✅" in output:
            return True

        # Check for failure indicators
        if '"ok": false' in output_lower or "'ok': false" in output_lower:
            return False
        if '"status": 4' in output or '"status": 5' in output:  # 4xx, 5xx status codes
            return False
        if "❌" in output:
            return False

        # Check for SUCCESS in final message
        if "success" in output_lower and "challenge" in output_lower:
            return True

        # Default to failure if unclear
        return False

        except Exception as e:
            error_msg = f"❌ SUBAGENT ERROR: {challenge_slug} - {str(e)}"
            if self.output_callback:
                self.output_callback(error_msg, is_task=True)
            return error_msg

    def _build_subagent_prompt(
        self, slug: str, name: str, category: str, difficulty: str
    ) -> SystemMessage:
        """Build prompt for subagent."""
        namespace, key = slug.split("/")

        return SystemMessage(
            content=f"""You are a challenge-solver subagent. Solve this ONE challenge:

Challenge: {name} ({slug})
Category: {category}
Difficulty: {difficulty}

Available Tools:
- Blueshift MCP: blueshift_get_challenge, blueshift_attempt_program, blueshift_attempt_client
- Solana MCP: mcp_solana_* (use these to look up Solana/Anchor documentation and examples)
- Knowledge Base: search_knowledge_base (search local examples: anchor-escrow, pinocchio-memo, sbpf-asm, anchor-memo-optimized + Anchor docs)
- Failure Analysis: analyze_submission_failure (analyze failed submissions, get fix suggestions)
- Anchor Tools: anchor_create_program, run_anchor_build
- File Tools: read_file, write_file
- Wallet Tools: wallet_get_address, wallet_sign_bytes, wallet_encode_base58

Your task:
1. Get full details: call blueshift_get_challenge("{namespace}", "{key}")
2. Read the problem_description carefully
3. Search knowledge base for similar examples: search_knowledge_base("relevant query")
4. If needed, use Solana MCP tools (mcp_solana_*) for additional documentation
5. Design your solution based on examples found
6. Implement using anchor_create_program (for Anchor/Pinocchio/Assembly) or write TypeScript client
7. Submit using blueshift_attempt_program (programs) or blueshift_attempt_client (client)
8. If submission fails (ok: false in response):
   a. Call analyze_submission_failure(failure_dir) with the failure_dir from the response
   b. Read the analysis carefully
   c. Decide: Either retry with fixes based on analysis OR return FAILURE if unfixable
   d. If retrying, mention "Retrying with fix: [description]"

Critical requirements:
- For Anchor: Use declare_id!("22222222222222222222222222222222222222222222");
- For Anchor: Specify anchor-lang = "0.32.1" in Cargo.toml
- Do NOT add solana-program separately - included with anchor-lang
- Keep compute usage under limits specified in problem description

When done, your final message should clearly state SUCCESS or FAILURE.

IMPORTANT: You must ALWAYS call a tool with every response. Start now by getting the challenge details."""
        )
