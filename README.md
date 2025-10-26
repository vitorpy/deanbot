# Blueshift Agent - Python LangChain Implementation

This is a Python-based LangChain agent for the Blueshift Agentic Hackathon, equivalent to the Node.js sample agent.

It demonstrates how the Agentic Hackathon MCP server works with your agent's local tools.

## Features

- **LangChain ReAct Agent**: Uses LangGraph with ChatOpenAI for intelligent tool orchestration
- **MCP Integration**: Connects to Blueshift MCP server via `langchain-mcp-adapters`
- **12 Custom Tools**: Wallet operations, challenge management, Anchor program building
- **Async Architecture**: Built with `asyncio` and `httpx` for efficient I/O
- **Type Safety**: Uses Pydantic for configuration validation and tool schemas

## Prerequisites

- Python 3.10+
- Qwen OAuth authentication (authenticate with [Qwen Code](https://code.qwen.ai) first)
- Anchor CLI installed
- Solana CLI with configured keypair (or provide base58 secret key via env var)

## Authentication Setup

Before running the agent, you need to authenticate with Qwen and configure your Solana wallet:

### 1. Qwen OAuth Setup

The agent uses Qwen's LLM (qwen3-coder-plus) via OAuth authentication. You need to authenticate first using the Qwen Code CLI:

```bash
# Install Qwen Code CLI (if not already installed)
npm install -g @qwen/code

# Authenticate with Qwen
qwen auth
```

This will create `~/.qwen/oauth_creds.json` with your OAuth credentials. The Python agent will automatically load these credentials.

### 2. Solana Wallet Setup

The agent loads your Solana keypair from the CLI default location. If you don't have a Solana keypair yet:

```bash
# Install Solana CLI (if not already installed)
# See: https://docs.solana.com/cli/install-solana-cli-tools

# Generate a new keypair
solana-keygen new
```

This creates `~/.config/solana/id.json`. The Python agent will automatically load this keypair.

**Alternative**: If you prefer to use a different keypair, set the `SOLANA_PRIVATE_KEY` environment variable with your base58-encoded secret key.

## Quick Start

1. **Clone or navigate to this directory**:

   ```bash
   cd blueshift-python-agent
   ```

2. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**:

   ```bash
   cp .env.example .env
   # Edit .env with your values
   ```

   | Variable             | Description                                                                |
   | -------------------- | -------------------------------------------------------------------------- |
   | `API_URL`            | Blueshift API base URL (defaults to `https://ai-api.blueshift.gg`)        |
   | `SOLANA_PRIVATE_KEY` | Optional: Base58 secret key (defaults to `~/.config/solana/id.json`)      |
   | `LLM_MODEL`          | Model identifier (default: `qwen3-coder-plus`)                             |
   | `LLM_TEMPERATURE`    | Temperature for LLM (default: 0.2)                                         |
   | `AGENT_NAME`         | Agent name for registration (default: "LangChain Solana Agent")            |
   | `AGENT_TEAM`         | Team name for registration (default: "Local Development")                  |

   **Note**: Qwen OAuth credentials are loaded automatically from `~/.qwen/oauth_creds.json`.

4. **Start the agent**:

   ```bash
   python src/main.py
   ```

   The client will connect to `${API_URL}/v1` for REST calls and `${API_URL}/mcp` for MCP tools.

## Project Structure

```
blueshift-python-agent/
├── src/
│   ├── main.py              # Entry point with MCP client and streaming
│   ├── config.py            # Configuration loader with Pydantic validation
│   ├── solana_wallet.py     # Wallet abstraction for signing
│   ├── blueshift_client.py  # Async REST wrapper for Blueshift APIs
│   ├── agent.py             # LangChain agent construction and system prompt
│   ├── tools.py             # 12 LangChain tools (BaseTool subclasses)
│   └── anchor_builder.py    # Anchor program scaffolding and building
├── requirements.txt         # Python dependencies
├── .env.example            # Environment variable template
└── README.md               # This file
```

## Tools Available

### Wallet Tools
- `wallet_get_address` - Get the wallet's base58 address
- `wallet_sign_bytes` - Sign arbitrary bytes and return base58 signature
- `wallet_encode_base58` - Encode bytes to base58

### Challenge Tools
- `blueshift_list_challenges` - List all available challenges
- `blueshift_get_challenge` - Get details for a specific challenge
- `blueshift_get_progress` - Get current agent progress

### Submission Tools
- `blueshift_attempt_program` - Submit a compiled program challenge
- `blueshift_attempt_client` - Submit a client transaction challenge

### Anchor Development Tools
- `anchor_create_program` - Scaffold, build, and get .so artifact
- `read_file` - Read file contents (for inspecting generated files)
- `write_file` - Write/modify files (for updating Anchor code)
- `run_anchor_build` - Rebuild an existing Anchor workspace

## Client Challenge Submission

- `POST /v1/challenges/client/{slug}` without a trailing slash
- JSON body: `{"transaction":"<base64 VersionedTransaction>","address":"<agent wallet address>"}`
- The transaction must already include a signature from the provided address
- `200 OK` responses include `success` plus a `results` array describing every instruction execution
- Error responses (`400`, `404`, `500`) return `{"error":string,"message":string}`

## Program Challenge Submission

- `POST /v1/challenges/program/{slug}` without a trailing slash
- Multipart form with fields:
  - `program`: compiled `.so` binary (file upload)
  - `signature`: base58 signature of the program bytes produced by the submitting wallet
  - `address`: base58 wallet address used for registration
- A successful response returns `200 OK` with the submission outcome payload

## Differences from TypeScript Version

While this Python implementation is functionally equivalent to the TypeScript version, there are some key differences:

1. **LLM Provider**: Uses Qwen (qwen3-coder-plus) via OAuth vs OpenRouter in the original
2. **Wallet Loading**: Auto-loads from Solana CLI (`~/.config/solana/id.json`) vs requiring env var
3. **Module System**: Python uses standard imports vs TypeScript ES modules
4. **Async Syntax**: Python uses `async/await` with `asyncio` vs JavaScript's native promises
5. **Type System**: Pydantic models for validation vs Zod schemas
6. **HTTP Client**: `httpx` (async) vs `fetch` API
7. **Solana Library**: `solders` vs `@solana/web3.js`

The agent logic, system prompt, and tool behavior are identical.

## Development

To modify the agent:

1. **Add new tools**: Edit `src/tools.py` and add your `BaseTool` subclass
2. **Change system prompt**: Edit `build_system_prompt()` in `src/agent.py`
3. **Adjust LLM settings**: Modify `config.py` or set environment variables

## Troubleshooting

- **"Qwen credentials not found"**: Run `qwen auth` to authenticate with Qwen OAuth
- **"Solana CLI keypair not found"**: Run `solana-keygen new` or set `SOLANA_PRIVATE_KEY` env var
- **Import errors**: Make sure you're running from the project root with `python src/main.py`
- **Anchor build fails**: Ensure Anchor CLI is installed and in your PATH
- **MCP connection issues**: Verify the API_URL is correct and accessible
- **Type errors**: Ensure Python 3.10+ is being used

## License

ISC
