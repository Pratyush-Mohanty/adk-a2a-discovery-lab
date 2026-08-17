# GUIDE.md — A2A discovery, explained and built

## The problem

A Master (orchestrator) agent must hand work to specialized sub-agents. Before
it can delegate, it must know:

1. **What agents exist** — discovery.
2. **What each one can do** — capability advertisement.
3. **How to reach it** — endpoint + protocol binding.

The Agent-to-Agent (A2A) protocol standardizes 1–3. This guide walks through
the mechanism, then shows how this repo turns "discover an agent" into
something you can *measure*.

---

## How A2A discovery actually works

### 1. Agent Cards (the capability contract)

Every agent advertises an **Agent Card** — a JSON document served over HTTP
at a well-known path. This SDK serves it at `/.well-known/agent-card.json`.

A card contains:

| field | meaning |
|---|---|
| `name`, `description` | identity + human-readable capability summary |
| `version` | semantic version of the agent |
| `supported_interfaces[]` | the actual RPC endpoints: `{url, protocol_binding, protocol_version}` (JSONRPC, gRPC, HTTP+JSON) |
| `capabilities` | streaming, push notifications |
| `default_input/output_modes` | what the agent accepts/returns (`text/plain`, `application/json`) |
| `skills[]` | the searchable part: `{id, name, description, tags, examples}` |

**Skills are the discovery primitive.** An orchestrator doesn't ask "is there an
agent for translation?" — it searches skill tags, exactly like tags on a
StackOverflow question or keywords on a store listing.

```jsonc
// what a sub-agent advertises (from this repo's fleet)
{
  "name": "translator",
  "description": "Translates text between English, Spanish, French and Hindi.",
  "supportedInterfaces": [
    { "url": "http://127.0.0.1:8102/a2a/jsonrpc",
      "protocolBinding": "JSONRPC", "protocolVersion": "1.0" }
  ],
  "skills": [
    { "id": "translate", "name": "Translation",
      "description": "Translates text to a requested language",
      "tags": ["translate", "language"] },
    { "id": "multiling", "name": "Multilingual", "tags": ["multilingual", "i18n"] }
  ]
}
```

### 2. Discovery patterns (the spectrum this lab measures)

| pattern | where the answer lives | cost | risk |
|---|---|---|---|
| **Static** | compile-time map in the master | ~0 | stale, not dynamic |
| **Card discovery** | fetched from each known endpoint at startup | one fetch per agent | needs a seed list of endpoints |
| **Directory / Registry** | central index (like Google Cloud Agent Registry, or this repo's `registry_server`) | network query per lookup | directory becomes a SPOF |
| **Cached discovery** | TTL cache in front of either | ~0 after warm | stale cards |
| **LLM-reasoned** | an LLM reads the cards and decides | tokens + latency | cost, nondeterminism |

Real systems (and Google Cloud Agent Registry) combine them: register agents in
a directory, resolve `list_agents(filter='skills.tags:"..."')` at startup,
cache, and re-resolve on TTL or failure.

### 3. The message flow (once you've picked an agent)

```
Master                        Sub-agent
  |  GET /.well-known/agent-card.json  |
  |----------------------------------->|  (discovery: learn capabilities)
  |  POST /a2a/jsonrpc  message/send   |
  |----------------------------------->|  (JSON-RPC 2.0, typed Message Parts)
  |      task.status: submitted        |
  |      task.status: working          |
  |      artifact_update: result       |
  |      task.status: completed        |
  |<-----------------------------------|
```

All data travels as JSON-RPC 2.0. Requests carry `Message {role, parts[]}`;
lifecycle is a `Task` (submitted → working → completed / failed / canceled).
The client abstracts all of this — `client.send_message()` returns the final
text.

---

## What's in this repo

```
adk-a2a-discovery-lab/
├── discovery_lab/
│   ├── config.py          # ports, fleet catalog, 12-task benchmark set
│   ├── fleet.py           # 4 deterministic skill agents (summarizer, translator,
│   │                      #   extractor, classifier) — handlers are pure Python
│   ├── server.py          # AgentExecutor + FastAPI app → real A2A server + card
│   ├── registry_server.py # Agent Directory: /agents, /agents/search?skill=
│   ├── a2a_client.py      # fetch_card + send_text helpers over a2a-sdk
│   ├── strategies.py      # the 5 discovery strategies (the research surface)
│   ├── llm_client.py      # free-LLM client (Ollama/OpenAI-compatible/mock)
│   ├── master.py          # discover → select → route, with failure fallback
│   ├── metrics.py         # RunResult / ExperimentSummary
│   ├── experiments.py     # the experiment ladder (ex1–ex6)
│   ├── plot.py            # accuracy / latency / token charts
│   ├── launch.py          # runs fleet + registry in-process (real HTTP)
│   ├── run.py             # CLI
│   └── adk_demo.py        # ADK LlmAgent host driven by a free local LLM
├── docs/                  # NOTES.md (findings), GUIDE.md (this file)
└── experiments/           # regenerated JSON + PNG output
```

## Quickstart (Windows, 3.10+)

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# full experiment ladder (all 6 experiments, 8 scenarios)
py -m discovery_lab.run

# single strategy
py -m discovery_lab.run --strategy llm_reasoned
py -m discovery_lab.run --strategy registry_skill --no-plot
```

Output lands in `experiments/` (`summary.json`, `runs.json`, `accuracy.png`,
`latency.png`, `tokens.png`). No API keys, no cloud, no LLM required — ex6
falls back to a mock scorer if Ollama isn't running.

## Want a real LLM driving the master?

1. Install [Ollama](https://ollama.com), then `ollama pull llama3.2`.
2. `pip install -r requirements-llm.txt` (installs `google-adk`).
3. `py -m discovery_lab.run --strategy llm_reasoned` — now routes with a real
   local LLM (tokens measured).
4. `py -m discovery_lab.adk_demo` — an actual ADK `LlmAgent` ("host") with
   `list_remote_agents()` + `delegate()` tools over the same fleet.

Any OpenAI-compatible endpoint works: set `FREE_LLM_BASE_URL`,
`FREE_LLM_MODEL`, `FREE_LLM_API_KEY` (e.g. Groq / OpenRouter / LM Studio).

## How to extend

- **Add a sub-agent:** append an `AgentSpec` (+ handler) to `fleet.py`. It gets
  a port, a card, and auto-registers in the directory.
- **Add a task:** append a `TaskSpec` to `config.TASKS` with the expected
  agent + skill tag.
- **Add a strategy:** subclass `DiscoveryStrategy` in `strategies.py` and
  implement `setup()` + `resolve()`. It'll be compared on the same 12 tasks.
- **Change the cache TTL / timeout:** `config.CARD_CACHE_TTL_S`,
  `config.HTTP_TIMEOUT_S`.

## Useful upstream references

- `a2aproject/A2A` — the protocol spec (Agent Card schema, JSON-RPC methods).
- `a2aproject/a2a-sdk` — Python SDK used here (v1.x, proto-based types).
- `google/adk-python` — ADK; `to_a2a()`, `RemoteA2aAgent`, `A2aAgentExecutor`.
- Google codelab *Multi-Agent Systems with Agent2Agent* — the host-agent
  (`list_remote_agents` + `send_message`) pattern this lab mirrors.
- Google Cloud Agent Registry docs — production discovery with skill filters.
