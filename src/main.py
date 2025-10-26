"""Main entry point for the Blueshift agent."""

import asyncio
import sys
import json
from datetime import datetime

from langchain_mcp_adapters.client import MultiServerMCPClient
from rich.console import Console
from rich.traceback import Traceback

from config import load_config
from solana_wallet import SolanaWallet
from blueshift_client import BlueshiftClient
from agent import create_coding_agent, build_system_prompt, build_initial_instructions
from qwen_auth import QwenTokenRefresher
from rag import initialize_rag


async def main():
    """Main agent execution."""
    console = Console()

    config = load_config()

    # Ensure we have a valid OAuth token (refresh if needed)
    token_refresher = QwenTokenRefresher()
    credentials = await token_refresher.ensure_valid_token()

    # Update config with potentially refreshed token
    config.qwen_access_token = credentials.access_token
    config.qwen_resource_url = credentials.resource_url

    wallet = SolanaWallet(config.solana_private_key)
    blueshift_client = BlueshiftClient(config.blueshift_api_url, wallet)

    # Initialize MCP clients
    # Orchestrator: Only Blueshift MCP
    orchestrator_mcp_client = MultiServerMCPClient(
        {
            "blueshift": {
                "transport": "streamable_http",
                "url": config.blueshift_mcp_url,
            }
        }
    )

    # Subagents: Blueshift + Solana MCP
    subagent_mcp_client = MultiServerMCPClient(
        {
            "blueshift": {
                "transport": "streamable_http",
                "url": config.blueshift_mcp_url,
            },
            "solana": {
                "transport": "streamable_http",
                "url": "https://mcp.solana.com/mcp",
            }
        }
    )

    try:
        # Initialize RAG knowledge base
        console.print("📚 Initializing knowledge base...")
        rag = initialize_rag()
        rag_tool = rag.get_retriever_tool()
        console.print("✅ Knowledge base ready\n")

        # Get MCP tools for both
        orchestrator_mcp_tools = await orchestrator_mcp_client.get_tools()
        subagent_mcp_tools = await subagent_mcp_client.get_tools()

        # Initialize output callback
        def output_callback(message: str, is_task: bool = False):
            """Callback for subagent output."""
            prefix = "[cyan][SUBAGENT][/cyan]" if is_task else "[yellow][ORCHESTRATOR][/yellow]"
            console.print(f"{prefix} {message}")

        # Build orchestrator tools with subagent spawner
        from tools import build_orchestrator_tools
        orchestrator_tools = build_orchestrator_tools(
            blueshift_client,
            wallet,
            config=config,
            solana_mcp_tools=subagent_mcp_tools,
            rag_tool=rag_tool,
            output_callback=output_callback,
        )

        # Combine with MCP tools
        all_orchestrator_tools = [*orchestrator_tools, *orchestrator_mcp_tools]

        # Create orchestrator agent
        agent = await create_coding_agent(
            config, wallet, blueshift_client,
            extra_tools=all_orchestrator_tools,
            orchestrator=True
        )

        system_prompt = build_system_prompt(config, wallet)
        initial_instruction = build_initial_instructions()

        thread_id = f"solana-agent-{int(datetime.now().timestamp() * 1000)}"
        config_block = {"configurable": {"thread_id": thread_id}}

        console.print(f"🚀 Starting Solana coding agent (orchestrator) for wallet [cyan]{wallet.address}[/cyan]")
        console.print(f"🔗 Using API URL: [yellow]{config.blueshift_api_url}[/yellow]")
        console.print(f"🔌 Orchestrator MCP: [yellow]Blueshift[/yellow]")
        console.print(f"🔌 Subagent MCP: [yellow]Blueshift + Solana[/yellow]\n")

        # Stream agent execution
        stream = agent.astream(
            {"messages": [system_prompt, initial_instruction]}, config_block
        )

        async for chunk in stream:
            if not isinstance(chunk, dict):
                continue

            # Handle agent messages
            if "agent" in chunk and "messages" in chunk["agent"]:
                for message in chunk["agent"]["messages"]:
                    # Print text content
                    if hasattr(message, "content") and message.content:
                        content = str(message.content)
                        if content.strip():
                            console.print(f"[yellow][ORCHESTRATOR][/yellow] {content}")

                    # Print tool calls
                    if hasattr(message, "tool_calls") and message.tool_calls:
                        for tool_call in message.tool_calls:
                            tool_name = tool_call["name"]
                            tool_args = tool_call["args"]

                            # Check if this is a subagent spawn
                            if tool_name == "solve_challenge_with_subagent":
                                console.print(f"[cyan][SUBAGENT][/cyan] 🚀 Spawning subagent")
                                console.print(f"[cyan][SUBAGENT][/cyan] Challenge: {tool_args.get('challenge_slug', 'N/A')}")
                            else:
                                console.print(f"[yellow][ORCHESTRATOR][/yellow] 🎯 Calling: [cyan]{tool_name}[/cyan]")
                                if tool_args:
                                    console.print(f"[yellow][ORCHESTRATOR][/yellow]    Args: {json.dumps(tool_args)[:100]}")

            # Handle tool messages
            elif "tools" in chunk and "messages" in chunk["tools"]:
                for message in chunk["tools"]["messages"]:
                    if hasattr(message, "content"):
                        output = str(message.content)
                        # Truncate long outputs
                        if len(output) > 500:
                            output = output[:500] + "..."
                        console.print(f"[yellow][ORCHESTRATOR][/yellow] 🛠️ Tool Output: {output}")

        console.print("\n✅ Agent run complete")

    except Exception as e:
        console.print("\n❌ [bold red]Agent execution failed[/bold red]")
        console.print(Traceback())

        # Drop into REPL for debugging
        console.print("\n[yellow]💥 Dropping into Python REPL for debugging...[/yellow]")
        console.print("[dim]Available variables: agent, config, wallet, blueshift_client, mcp_client, console[/dim]")
        console.print("[dim]Type exit() or Ctrl+D to quit[/dim]\n")

        import code
        code.interact(local=locals(), banner="")
    finally:
        await blueshift_client.close()
        # MCP clients don't need explicit cleanup


if __name__ == "__main__":
    asyncio.run(main())
