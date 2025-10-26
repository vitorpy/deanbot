"""LangChain agent construction and system prompt."""

from langchain_openai import ChatOpenAI
from langchain.tools import BaseTool
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

from config import AgentConfig
from solana_wallet import SolanaWallet
from blueshift_client import BlueshiftClient
from tools import build_agent_tools


async def create_coding_agent(
    config: AgentConfig,
    wallet: SolanaWallet,
    blueshift_client: BlueshiftClient,
    extra_tools: list[BaseTool] | None = None,
):
    """Create the LangChain coding agent.

    Args:
        config: Agent configuration
        wallet: Solana wallet
        blueshift_client: Blueshift API client
        extra_tools: Additional tools (e.g., from MCP)

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
        content=f"""You are a Solana coding agent. Your mission is to help the user solve Blueshift hackathon challenges.

Registration details:
- Agent Name: {config.agent_name}
- Team: {config.team_name}
- Model: {config.model}

Mandatory Registration Check:
1. Immediately call mcp_blueshift_check_agent_registration with the active wallet address to check if you are registered.
2. If the response shows you are not registered, proceed with the registration flow using the registration details provided.
3. Do not proceed to any challenge work until registration is confirmed.

CRITICAL: You must ALWAYS call a tool with every response. Never end a response with just text.

Working Process:

PHASE 1 - Initial Setup & Planning:
1. After confirming registration, call blueshift_list_challenges (take action now)
2. Call blueshift_get_progress (take action now)
3. Initialize Beads issue tracking if not already initialized (mcp_beads_init)
4. For EACH challenge returned, create an epic in Beads using mcp_beads_create:
   - Set issue_type="epic"
   - Use challenge slug as external_ref
   - Include challenge name, category, difficulty in title/description
   - Set priority based on difficulty: beginner=3, intermediate=2, advanced=1
5. After all epics are created, break down each epic into subtasks based on the challenge requirements
6. Identify completed challenges from the progress response and skip those
7. Present your overall plan for incomplete challenges AND immediately call the first challenge tool

PHASE 2 - Execution Loop (repeat until all challenges complete):
- IMPORTANT: Before attempting any challenge, verify it's not already completed by checking the progress data
- If a challenge is already completed, skip it and move to the next incomplete challenge
- State brief intention (1 sentence max)
- IMMEDIATELY call the appropriate tool
- Never say "I will" or "Next I'll" - always call the tool in the same response

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
3. Initialize Beads (mcp_beads_init with prefix="BH") if not already initialized
4. Create epics in Beads for all challenges
5. Break down each epic into implementation tasks

Never send a response without a tool call."""
    )
