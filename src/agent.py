"""LangChain agent construction and system prompt."""

from langchain_openai import ChatOpenAI
from langchain.tools import BaseTool
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

from config import AgentConfig
from solana_wallet import SolanaWallet
from blueshift_client import BlueshiftClient
from tools import build_agent_tools, build_orchestrator_tools


async def create_coding_agent(
    config: AgentConfig,
    wallet: SolanaWallet,
    blueshift_client: BlueshiftClient,
    extra_tools: list[BaseTool] | None = None,
    orchestrator: bool = False,
):
    """Create the LangChain coding agent.

    Args:
        config: Agent configuration
        wallet: Solana wallet
        blueshift_client: Blueshift API client
        extra_tools: Additional tools (e.g., from MCP)
        orchestrator: If True, only include orchestrator tools (coordination only)

    Returns:
        LangGraph agent
    """
    llm = ChatOpenAI(
        model=config.model,
        temperature=config.temperature,
        streaming=True,
        api_key=config.qwen_access_token,
        base_url=config.qwen_base_url,
    )

    # Use different tool sets for orchestrator vs solver agents
    if orchestrator:
        # Orchestrator gets minimal tools - will be enhanced with subagent spawner in main.py
        core_tools = build_orchestrator_tools(blueshift_client, wallet)
    else:
        core_tools = build_agent_tools(blueshift_client, wallet)

    combined_tools = [*core_tools, *(extra_tools or [])]

    memory = MemorySaver()

    return create_react_agent(llm, combined_tools, checkpointer=memory)


def build_system_prompt(config: AgentConfig, wallet: SolanaWallet) -> SystemMessage:
    """Build the system prompt for the agent.

    Args:
        config: Agent configuration
        wallet: Solana wallet

    Returns:
        System message
    """
    return SystemMessage(
        content=f"""You are an orchestrator agent for Blueshift hackathon challenges. Your job is to coordinate subagents that solve individual challenges.

Registration details:
- Agent Name: {config.agent_name}
- Team: {config.team_name}
- Model: {config.model}
- Wallet: {wallet.address}

Available MCP Servers (Orchestrator):
- Blueshift: Challenge management and submissions (mcp_blueshift_*)

Subagent Configuration:
- Subagents have access to: Blueshift MCP + Solana MCP (for documentation/context)
- Each subagent gets fresh recursion limit (25 steps)
- Subagents are isolated and autonomous

Mandatory Registration Check:
1. Immediately call mcp_blueshift_check_agent_registration with the active wallet address to check if you are registered.
2. If the response shows you are not registered, proceed with the registration flow using the registration details provided.
3. Do not proceed to any challenge work until registration is confirmed.

CRITICAL: You must ALWAYS call a tool with every response. Never end a response with just text.

Working Process:

PHASE 1 - Initial Setup:
1. After confirming registration, call blueshift_list_challenges
2. Call blueshift_get_progress
3. Identify all incomplete challenges (skip completed ones)
4. Report to user: "Found X incomplete challenges: [list]"

PHASE 2 - Sequential Challenge Solving:
For each incomplete challenge (one at a time, in order):

1. Spawn a challenge-solver subagent using solve_challenge_with_subagent:
   - challenge_slug: The slug (e.g., "anchor/vault")
   - challenge_name: Human-readable name
   - challenge_category: Category (anchor, pinocchio, etc.)
   - difficulty: Difficulty level (beginner, intermediate, advanced)

2. Wait for subagent result (this may take several minutes)

3. Handle result:
   - If result contains "✅ SUCCESS": Log success and move to next challenge
   - If result contains "❌ FAILURE": **STOP IMMEDIATELY** and report to user:
     "❌ Challenge [slug] failed"
     "Stopping execution. Please investigate and restart when ready."
     Then exit/halt (do not continue to next challenge)

CRITICAL FAILURE HANDLING:
- Do NOT retry failed challenges
- Do NOT continue to next challenge after a failure
- STOP and report failure to user
- Let user decide what to do next

Available Tool:
- solve_challenge_with_subagent: Spawns a fresh Python agent with full tools + Solana MCP to solve ONE challenge

Building Anchor Programs:
1. Prepare complete Cargo.toml and lib.rs content with your solution
2. CRITICAL: ALWAYS use declare_id!("22222222222222222222222222222222222222222222"); as the program ID
3. IMPORTANT: Always specify anchor-lang = "0.32.1" in the Cargo.toml dependencies
4. IMPORTANT: Do NOT add solana-program as a separate dependency - it's included with anchor-lang
5. Call anchor_create_program with programName, cargoToml, and libRs (it will build automatically)
6. Call blueshift_attempt_program with the .so artifact from the build result
7. Move to next challenge

Modifying Anchor Programs:
- Use read_file to inspect existing Cargo.toml or lib.rs files in a workspace
- Use write_file to modify Cargo.toml or lib.rs with updated content
- CRITICAL: ALWAYS use declare_id!("22222222222222222222222222222222222222222222"); as the program ID
- IMPORTANT: Ensure anchor-lang = "0.32.1" is specified in Cargo.toml dependencies
- IMPORTANT: Do NOT add solana-program as a separate dependency - it's included with anchor-lang
- After modifying files, use run_anchor_build to rebuild the program and get the new .so artifact
- File paths should be absolute (e.g., /path/to/workspace/programs/program-name/src/lib.rs)

Example - GOOD (always has a tool call):
"Getting Anchor Memo details" → [calls blueshift_get_challenge]

Example - BAD (no tool call, agent will stop):
"Executing step 1: Getting details for challenge A"
"Now I will scaffold the workspace"

ABSOLUTE RULE: Every single response MUST include a tool call. If you're not calling a tool, you're doing it wrong.
"""
    )


def build_initial_instructions() -> HumanMessage:
    """Build the initial instructions for the agent.

    Returns:
        Human message
    """
    return HumanMessage(
        content="""Start by calling mcp_blueshift_check_agent_registration to confirm your wallet is registered. If not registered, complete the registration flow before anything else.

Once registration is confirmed:
1. Call blueshift_list_challenges
2. Call blueshift_get_progress
3. Report incomplete challenges to user
4. For each incomplete challenge, spawn a subagent using solve_challenge_with_subagent
5. If any subagent returns FAILURE, STOP immediately and report to user (no retry, no continue)

Never send a response without a tool call."""
    )
