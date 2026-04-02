**English** | [한국어](README.ko.md)

# NVM (Non-Volatile Memory)

> Your engineering thinking, preserved.

NVM is a [Claude Code](https://docs.anthropic.com/en/docs/claude-code) plugin that automatically generates **thought-trajectory documents** from your Claude conversations and git history.

Code survives. The reasoning behind it doesn't. NVM captures *why you solved it this way* before it evaporates.

## What It Does

Run `/nvm` after a coding session, and it will:

1. **Analyze** your Claude conversation logs + git commits for the period
2. **Extract** the human's problem-definition process and Claude's problem-solving approach
3. **Generate** a narrative document in `.nvm/{date}.md`

The output is not a summary or a log — it's a **narrative reconstruction of your thinking process**.

## Example

```markdown
## event-hub: Amplitude API stabilization — shared session + circuit breaker + fire-and-forget

**Problem**
Airflow pod kept throwing aiohttp `CancelledError`, causing all Amplitude event
sends to fail. Root cause: creating a new `ClientSession` per request, exhausting
the connection pool.

**Trajectory**
1. Per-request session creation → replaced with app-level singleton (lifespan open/close)
2. Removed tenacity retry → retries were making pool exhaustion worse; switched to fire-and-forget
3. Circuit breaker design debate:

> **Me:** "Still, not sending events to Amplitude is pretty critical"
> **Claude:** "Since all events go to PubSub, the Amplitude side can be recovered later"

Agreed on: circuit open = still attempt with shortened 5s timeout (not skip entirely).

**Resolution**
Registered an exception handler to catch uncaught exceptions.
Then switched to fire-and-forget to remove main-thread blocking.
```

## Installation

### From GitHub (standalone marketplace)

```
/plugin marketplace add https://github.com/kgw7401/nvm.git

/plugin install nvm
```

### Manual Installation

Copy the plugin files into your Claude Code setup:

```bash
git clone https://github.com/kgw7401/nvm.git
cp -r nvm/skills/nvm ~/.claude/commands/
cp -r nvm/scripts ~/your-project/scripts/
```

## Usage

```
/nvm              # Today's thought trajectory
/nvm week         # Last 7 days
/nvm 2026-03-25   # From specific date to now
```

Output is saved to `.nvm/{date}.md` in your project directory.

## How It Works

```
/nvm [period]
  │
  ├─ 1. Parse period (today / week / YYYY-MM-DD)
  │
  ├─ 2. Preprocess session JSONL via extract_session.py
  │     (530KB raw → ~25K tokens — full user messages + Claude responses truncated to 200 chars)
  │
  ├─ 3. Collect git log + commit details
  │
  ├─ 4. Generate narrative document
  │     • Human axis: problem definition, direction, decisions
  │     • Claude axis: approach, alternatives, implementation
  │
  └─ 5. Save to .nvm/{date}.md
```

### Generation Principles

- **Free narrative** — not fixed fields. Content adapts to type (decision, debugging, learning, etc.)
- **3 required elements** per card: one-line summary, core content, reference links
- **Card depth varies** — deep for decisions with elimination process, shallow for simple fixes
- **Conversation excerpts** — captures turning points where the user pivoted direction
- **Language auto-detection** — generates in the same language used in your conversations

## Project Structure

```
nvm/
├── .claude-plugin/
│   └── plugin.json          # Plugin metadata
├── skills/
│   └── nvm/
│       └── SKILL.md         # /nvm command definition
├── scripts/
│   └── extract_session.py   # JSONL preprocessor
├── prd.md                   # Product requirements
├── LICENSE
└── README.md
```

## Requirements

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
- Python 3.10+
- git

No external Python dependencies — uses only the standard library.

## Why NVM?

| Existing tools | NVM |
|---------------|-----|
| Save logs | Restores thinking process |
| Provide summaries | Generates narratives |
| Fixed format | Adapts to content type |
| Record what happened | Captures **why it happened that way** |

The name "Non-Volatile Memory" reflects the core idea: making your engineering thinking persistent, just like NVM in hardware preserves data when power is lost.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## License

[MIT](LICENSE)
