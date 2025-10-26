"""Main entry point for the Blueshift agent."""

import asyncio
import sys
from datetime import datetime

from langchain_mcp_adapters.client import MultiServerMCPClient

from config import load_config
from solana_wallet import SolanaWallet
from blueshift_client import BlueshiftClient
from agent import create_coding_agent, build_system_prompt, build_initial_instructions
from qwen_auth import QwenTokenRefresher


async def main():
    """Main agent execution."""
    config = load_config()

    # Ensure we have a valid OAuth token (refresh if needed)
    token_refresher = QwenTokenRefresher()
    credentials = await token_refresher.ensure_valid_token()

    # Update config with potentially refreshed token
    config.qwen_access_token = credentials.access_token
    config.qwen_resource_url = credentials.resource_url

    wallet = SolanaWallet(config.solana_private_key)
    blueshift_client = BlueshiftClient(config.blueshift_api_url, wallet)

    # Initialize MCP client with both Blueshift and Beads servers
    mcp_client = MultiServerMCPClient(
        {
            "blueshift": {
                "transport": "streamable_http",
                "url": config.blueshift_mcp_url,
            },
            "beads": {
                "transport": "stdio",
                "command": "/home/vitorpy/.local/bin/beads-mcp",
                "args": [],
                "env": {
                    "BEADS_WORKSPACE_ROOT": "/home/vitorpy/code/deanbot",
                }
            }
        }
    )

    try:
        # Get MCP tools
        mcp_tools = await mcp_client.get_tools()

        # Create agent
        agent = await create_coding_agent(config, wallet, blueshift_client, mcp_tools)

        system_prompt = build_system_prompt(config, wallet)
        initial_instruction = build_initial_instructions()

        thread_id = f"solana-agent-{int(datetime.now().timestamp() * 1000)}"
        config_block = {"configurable": {"thread_id": thread_id}}

        print(f"🚀 Starting Solana coding agent for wallet {wallet.address}")
        print(f"🔗 Using API URL: {config.blueshift_api_url}")
        print(f"🔌 Using MCP server: {config.blueshift_mcp_url}")

        # Stream agent execution
        stream = agent.astream(
            {"messages": [system_prompt, initial_instruction]}, config_block
        )

        sys.stdout.write("🤖 Agent: ")
        sys.stdout.flush()

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
                            sys.stdout.write(content)
                            sys.stdout.flush()

                    # Print tool calls
                    if hasattr(message, "tool_calls") and message.tool_calls:
                        for tool_call in message.tool_calls:
                            tool_name = getattr(tool_call, "name", "unknown")
                            tool_args = getattr(tool_call, "args", {})
                            sys.stdout.write(f"\n🎯 Intent: Calling tool \"{tool_name}\"\n")
                            import json
                            sys.stdout.write(f"   Args: {json.dumps(tool_args, indent=2)}\n")
                            sys.stdout.flush()

            # Handle tool messages
            elif "tools" in chunk and "messages" in chunk["tools"]:
                tool_messages = []
                for message in chunk["tools"]["messages"]:
                    if hasattr(message, "content"):
                        tool_messages.append(str(message.content))

                if tool_messages:
                    output = "\n".join(tool_messages)
                    sys.stdout.write(f"🛠️ Tool Output:\n{output}\n")
                    sys.stdout.flush()

        print("\n✅ Agent run complete")

    except Exception as e:
        print(f"\n❌ Agent execution failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await blueshift_client.close()
        # MultiServerMCPClient doesn't need to be closed as of langchain-mcp-adapters 0.1.0


if __name__ == "__main__":
    asyncio.run(main())
