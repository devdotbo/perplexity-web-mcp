---
name: perplexity-web-mcp
description: "Search the web and query AI models via Perplexity AI using perplexity-web-mcp-cli. Supports CLI commands (pwm ask, pwm research), MCP tools (pplx_*), and Anthropic/OpenAI-compatible API server. Use when the user mentions \"perplexity\", \"pplx\", \"pwm\", \"web search with AI\", \"deep research\", \"search the internet\", or wants to query premium models like GPT-5.4, GPT-5.5, Claude, Gemini, Nemotron through Perplexity's web interface."
metadata:
  version: "0.10.7"
  author: "Jacob BD"
---

# Perplexity Web MCP

Search the web and query premium AI models through Perplexity AI.

## Quick Reference

Run `pwm --ai` for comprehensive AI-optimized documentation covering all
commands, models, MCP tools, auth flows, and error recovery.

```bash
pwm --ai                # Full AI reference (RECOMMENDED first step)
pwm --help              # CLI help
pwm login --check       # Check auth status
```

## Critical Rules

1. **Authenticate first**: Run `pwm login` before any queries
2. **Tokens last ~30 days**: Re-run `pwm login` on 403 errors
3. **Default to `claude_opus` with `--thinking --intent detailed`** -- always use the best model
4. **Always output to file** -- pipe to `/tmp/pwm-*.txt`, never dump into conversation context
5. **Never use Deep Research autonomously** -- only when the user explicitly asks

## Default Invocation

Every `pwm ask` call uses these flags -- no exceptions:

```bash
pwm ask "question" -m claude_opus --thinking --intent detailed > /tmp/pwm-TASKID.txt
```

- `-m claude_opus` -- always explicit model, never bare `pwm ask` or auto/sonar
- `--thinking` -- always enabled
- `--intent detailed` -- always detailed (the standard research tier)
- Output piped to `/tmp/pwm-*.txt` -- never dump raw content into conversation context
- No `-s` flag by default -- no additional source focus unless the query specifically needs it
- No `--json` by default -- raw markdown is cleaner for file output. Add `--json` only when programmatic parsing is needed.

### Rate Limiting and Parallelism

0.5 requests per second = 1 request every 2 seconds. When launching parallel requests, stagger by `sleep 2` between each launch. Parallel execution is the default for independent queries.

```bash
# Parallel pattern with 2s stagger
pwm ask "Q1" -m claude_opus --thinking --intent detailed > /tmp/pwm-q1.txt &
sleep 2
pwm ask "Q2" -m claude_opus --thinking --intent detailed > /tmp/pwm-q2.txt &
sleep 2
pwm ask "Q3" -m claude_opus --thinking --intent detailed > /tmp/pwm-q3.txt &
wait
```

### Quota

Pro Search quota is ~600/day -- more than enough for normal work. Skip `pwm usage` for routine `pwm ask` calls.

Only check `pwm usage` before:
- Premium source queries (`-s cbinsights`, `-s pitchbook`, etc.) -- monthly limits, can exhaust
- `pwm research` (Deep Research) -- costs 1 Deep Research credit per call
- `pwm council` -- costs N Pro Searches (1 per model)
- Heavy batch runs (20+ queries in one session)

| Tier | Cost | Resets | Pool |
|------|------|--------|------|
| **Pro Search** (claude_opus detailed) | 1 Pro Search | Daily | ~600/day |
| **Council** (N models) | N Pro Searches | Daily | ~600/day (shared) |
| **Deep Research** | 1 Deep Research | Daily | ~200/day |
| **Premium sources** (cbinsights, pitchbook, etc.) | 1 per source | Monthly | ~50/month each |

### When to Use Other Models

Use `-m gpt54 --thinking` for second opinions or multi-model critique. Each call costs 1 Pro Search -- same as claude_opus.

## Premium Source Protocol (MANDATORY)

Four sources have monthly limits and must be treated as scarce resources:
`cbinsights`, `pitchbook`, `statista`, `wiley`.

### Rules

1. **Do NOT use premium sources by default.** Standard queries should use
   `web`, `academic`, `social`, or `finance` unless the user's question
   specifically calls for premium data.
2. **Before using any premium source**, call `pplx_sources(premium_only=True)`
   to check remaining quota.
3. **Inform the user** of the current quota and ASK for explicit permission
   before including a premium source. Example:
   "Statista has 1/50 queries remaining this month. Shall I use it for
   this query?"
4. **Only proceed** if the user approves.
5. **If quota is exhausted** (0 remaining), do NOT include that source.
   Inform the user and suggest alternatives.
6. **If quota is low** (< 20% remaining), warn the user before asking
   for permission.

### When Premium Sources Make Contextual Sense

- `cbinsights` / `pitchbook`: Private market data, startup funding, investor analysis
- `statista`: Statistics, market size, industry data, survey results
- `wiley`: Academic research, peer-reviewed papers beyond standard academic sources

If the user's question does not clearly need these data types, use standard
sources instead.

## Tool Detection

Check which interface is available before proceeding:

```
has_mcp = check for tools starting with "pplx_"
has_cli = can run "pwm" commands via shell

if has_mcp and has_cli:
    Ask user which they prefer, or use MCP for programmatic access
elif has_mcp:
    Use pplx_* MCP tools directly
else:
    Use pwm CLI via shell
```

## Workflow Decision Tree

```
User wants to...
|
+-- Search the web / ask a question
|   +-- CLI:  pwm ask "query" -m claude_opus --thinking --intent detailed > /tmp/pwm-out.txt
|   +-- MCP:  pplx_claude_opus_think(query)
|
+-- Query multiple models at once (Model Council -- ask user first)
|   +-- CLI:  pwm council "query" > /tmp/pwm-council.txt
|   +-- MCP:  pplx_council(query)
|
+-- Deep research on a topic (ask user first)
|   +-- CLI:  pwm research "query" > /tmp/pwm-research.txt
|   +-- MCP:  pplx_deep_research(query)
|
+-- Second opinion / multi-model critique
|   +-- CLI:  pwm ask "query" -m gpt54 --thinking --intent detailed > /tmp/pwm-gpt.txt
|
+-- Check remaining quotas (only before premium sources, deep research, or council)
|   +-- CLI:  pwm usage
|   +-- MCP:  pplx_usage()
|
+-- Authenticate / re-authenticate
|   +-- Interactive:      pwm login
|   +-- Non-interactive:  pwm login --email EMAIL  then  pwm login --email EMAIL --code CODE
|   +-- MCP (no shell):   pplx_auth_request_code(email)  then  pplx_auth_complete(email, code)
|
+-- Start MCP server
|   +-- pwm-mcp
|
+-- Start API server (for Claude Code / OpenAI SDK)
|   +-- pwm api [--port PORT]
```

## CLI Commands

### Querying (default)

```bash
pwm ask "What is quantum computing?" -m claude_opus --thinking --intent detailed > /tmp/pwm-out.txt
```

Optional source focus with `-s` (omit by default):
```bash
pwm ask "transformer improvements 2025" -m claude_opus --thinking --intent detailed -s academic > /tmp/pwm-out.txt
pwm ask "Apple revenue Q4 2025" -m claude_opus --thinking --intent detailed -s finance > /tmp/pwm-out.txt
```

Second opinion with a different model:
```bash
pwm ask "Compare React and Vue" -m gpt54 --thinking --intent detailed > /tmp/pwm-gpt.txt
```

Add `--json` only when programmatic parsing is needed:
```bash
pwm ask "What is Rust?" -m claude_opus --thinking --intent detailed --json > /tmp/pwm-out.json
```

### Model Council

Query multiple models in parallel and get a synthesized consensus.
Each model in the council costs 1 Pro Search. Default: 3 models = 3 Pro Searches.
Ask the user before using.

```bash
pwm council "What are the best practices for microservices?" > /tmp/pwm-council.txt
pwm council "Compare Rust and Go for backend" -m gpt54,claude_sonnet > /tmp/pwm-council.txt
```

### Deep Research

Uses a separate monthly quota. Produces in-depth reports with extensive sources.

```bash
pwm research "agentic AI trends 2026"
pwm research "climate policy impact" -s academic
pwm research "NVIDIA competitive landscape" -s finance --json
```

### Authentication

```bash
pwm login                                                # Interactive
pwm login --check                                        # Check status
pwm login --email user@example.com                       # Send code
pwm login --email user@example.com --code 123456         # Complete
```

### Usage

```bash
pwm usage                   # Cached limits
pwm usage --refresh         # Force-refresh from server
```

## MCP Tools Summary

| Tool | Cost | Purpose |
|------|------|---------|
| `pplx_claude_opus` / `_think` | 1 Pro | **USE THIS BY DEFAULT** -- Anthropic Claude 4.7 Opus |
| `pplx_smart_query` | Varies by intent | Quota-aware auto routing (fallback) |
| `pplx_sonar` | **FREE** | Perplexity Sonar model (no Pro quota used) |
| `pplx_query` | 1 Pro | Explicit model selection with thinking toggle |
| `pplx_ask` | 1 Pro | Quick Q&A (auto model) |
| `pplx_council` | **N Pro** (1 per model) | Model Council -- **ASK USER which models first!** |
| `pplx_gpt54` / `_thinking` | 1 Pro | OpenAI GPT-5.4 |
| `pplx_claude_sonnet` / `_think` | 1 Pro | Anthropic Claude 4.6 Sonnet |
| `pplx_gemini_pro_think` | 1 Pro | Google Gemini 3.1 Pro (thinking always on) |
| `pplx_nemotron_thinking` | 1 Pro | NVIDIA Nemotron 3 Super (thinking always on) |
| `pplx_deep_research` | 1 Research | In-depth reports (**scarce monthly quota**) |
| `pplx_usage` | FREE | Check remaining quotas |
| `pplx_auth_status` | FREE | Check auth status |
| `pplx_auth_request_code` | FREE | Send verification code |
| `pplx_auth_complete` | FREE | Complete auth with code |
| `pplx_sources(premium_only=False)` | FREE | List available sources and their quotas |

All query tools accept `source_focus`: `"none"`, `"web"`, `"academic"`, `"social"`, `"finance"`, `"all"`.
Use `source_focus="none"` for model-only queries without web search.

For full MCP tool parameters: See [references/mcp-tools.md](references/mcp-tools.md)

## Models

| CLI Name | Provider | Thinking | Notes |
|----------|----------|----------|-------|
| auto | Perplexity | No | Auto-selects best |
| sonar | Perplexity | No | Latest Perplexity model |
| deep_research | Perplexity | No | Monthly quota |
| gpt54 | OpenAI | Toggle | GPT-5.4 |
| claude_sonnet | Anthropic | Toggle | Claude 4.6 Sonnet |
| claude_opus | Anthropic | Toggle | Claude 4.7 Opus (Max tier) |
| gemini_pro | Google | Always | Gemini 3.1 Pro |
| nemotron | NVIDIA | Always | Nemotron 3 Super 120B |

For full model details: See [references/models.md](references/models.md)

## Source Focus Options

| Option | Description | Example Use Case |
|--------|-------------|------------------|
| `none` | No search -- model training data only | Code review, writing, analysis without web |
| `web` | General web search (default) | News, general questions |
| `academic` | Academic papers, journals | Research, citations, scientific topics |
| `social` | Reddit, Twitter, forums | Opinions, recommendations, community |
| `finance` | SEC EDGAR filings | Company financials, regulatory filings |
| `all` | Web + Academic + Social | Broad coverage across all sources |
| `github` | GitHub source code (via connector) | Code search, repository exploration |
| `wiley` | PREMIUM - Wiley Online Library (monthly limit) | Academic research, peer-reviewed papers |
| `cbinsights` | PREMIUM - CB Insights market intelligence (monthly limit) | Startup data, market trends |
| `pitchbook` | PREMIUM - PitchBook financial data (monthly limit) | Private market, funding, investor data |
| `statista` | PREMIUM - Statista statistics (monthly limit) | Statistics, market size, industry data |

Raw source IDs (e.g., `wiley_mcp_cashmere`) and comma-separated lists (e.g., `web,wiley`) are also accepted.
`all` expands to `web + academic + social` only -- it does NOT include premium sources.

## Error Recovery

| Error | Cause | Solution |
|-------|-------|----------|
| 403 Forbidden | Token expired | `pwm login` |
| 429 Rate limit | Quota exhausted | Wait, check `pwm usage` |
| "No token found" | Not authenticated | `pwm login` |
| "LIMIT REACHED" | Quota at zero | Wait for reset or upgrade |

## Common Patterns

### Default query
```bash
pwm ask "What happened in AI today?" -m claude_opus --thinking --intent detailed > /tmp/pwm-ai-news.txt
```

### Parallel queries with 2s stagger
```bash
pwm ask "Compare React and Vue" -m claude_opus --thinking --intent detailed > /tmp/pwm-react-vue.txt &
sleep 2
pwm ask "Compare Next.js and Remix" -m claude_opus --thinking --intent detailed > /tmp/pwm-next-remix.txt &
wait
```

### Academic research
```bash
pwm ask "transformer improvements 2025" -m claude_opus --thinking --intent detailed -s academic > /tmp/pwm-transformers.txt
```

### Financial analysis
```bash
pwm ask "Apple revenue Q4 2025" -m claude_opus --thinking --intent detailed -s finance > /tmp/pwm-apple.txt
```

### Model-only query (no web search)
```bash
pwm ask "Explain the visitor pattern" -m claude_opus --thinking --intent detailed -s none > /tmp/pwm-visitor.txt
```

### Second opinion (GPT 5.4)
```bash
pwm ask "Compare React and Vue" -m gpt54 --thinking --intent detailed > /tmp/pwm-gpt-react.txt
```

### Deep research (ask user first)
```bash
pwm research "quantum computing breakthroughs 2026" > /tmp/pwm-quantum-research.txt
```

### Launch Claude Code seamlessly (Integration)
```bash
pwm hack claude
```

### Re-authenticate (non-interactive, for AI agents)
```bash
pwm login --email user@example.com
# wait for email, then:
pwm login --email user@example.com --code 123456
```

## API Server

For API server setup and model name mapping, see [references/api-endpoints.md](references/api-endpoints.md).
