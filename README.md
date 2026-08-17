# ADK / A2A Discovery Lab

**How does a Master agent *efficiently discover* sub-agents over the
Agent-to-Agent (A2A) protocol?** — measured, not just demoed.

This project is an end-to-end experiment platform. It spins up a small fleet of
real A2A sub-agents (each with an Agent Card and a JSON-RPC endpoint), a central
Agent Directory, and a Master agent with *pluggable discovery strategies*. It
then benchmarks six discovery strategies across 12 routing tasks, recording
**selection accuracy, discovery latency, routing latency, token cost, and
failure recovery** — and writes charts + notes.

Everything runs locally: no cloud account, no API keys, no paid LLM. The
LLM-reasoned experiment uses a **free local LLM (Ollama)** when available and
falls back to a deterministic scorer otherwise.

---

## The theory in 60 seconds

A2A separates **communication** from **discovery**:

- **Discovery** = an agent advertises what it can do via an **Agent Card**
  (name, description, endpoint, and — crucially — **skills with tags**),
  served at `/.well-known/agent-card.json`.
- **Orchestration** = a Master reads cards (directly, via a **directory/registry**,
  or from a **cache**), *picks* the best sub-agent, then delegates over
  JSON-RPC 2.0 (`message/send`, task lifecycle `submitted → completed`).

The research question is: **what's the cheapest reliable way to find the right
sub-agent?** The answer is a trade-off spectrum — static (zero cost, zero
flexibility) → card discovery (one fetch per agent) → registry search (network
per query) → cached (fast but stale) → LLM-reasoned (semantic but costs tokens).

See **[docs/GUIDE.md](docs/GUIDE.md)** for the full mechanism walkthrough and
**[docs/NOTES.md](docs/NOTES.md)** for the lab notebook.

## Experiment ladder

| # | Strategy | Question it answers |
|---|---|---|
| ex1 | `static` | Baseline: compile-time knowledge (zero discovery cost) |
| ex2 | `card_discovery` | Fetch Agent Cards at startup → skill index |
| ex3 | `registry_skill` | Per-request skill-tag search against a directory |
| ex4 | `cached` | TTL cache: hit vs miss latency, staleness tradeoff |
| ex5 | `card_discovery` (+faults) | Agent down → fallback; agent vanished → silent misroute; recovery |
| ex6 | `llm_reasoned` | Free LLM picks the agent (tokens + latency vs. tag scoring) |

## Quickstart

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
py -m discovery_lab.run            # full ladder -> experiments/*.json + *.png
```

### Optional: real LLM routing (free)

```powershell
# 1. install Ollama and pull a model
ollama pull llama3.2

# 2. install ADK for the LLM + demo paths
pip install -r requirements-llm.txt

# 3. route with a real local LLM (tokens tracked)
py -m discovery_lab.run --strategy llm_reasoned

# 4. run the ADK LlmAgent "host" over the same fleet
py -m discovery_lab.adk_demo
```

Any OpenAI-compatible endpoint works too — set `FREE_LLM_BASE_URL`,
`FREE_LLM_MODEL`, `FREE_LLM_API_KEY` (Groq / OpenRouter / LM Studio).

## Reference results (localhost, a2a-sdk 1.1.2)

| experiment | accuracy | discovery (ms) | total (ms) | tokens | notes |
|---|---|---|---|---|---|
| static | 100% | 0.01 | 52.9 | 0 | floor: zero discovery cost |
| card_discovery | 100% | ~0 | 31.4 | 0 | discovery paid once at startup |
| registry_skill | 100% | 15.5 | 42.9 | 0 | network round trip per lookup |
| cached (pass1/2) | 100% | 0.03 | ~61 | 0 | 36/36 cache hits |
| **agent down** | **0%** | – | 2151 | 0 | fallback engaged, wrong agent chosen |
| **agent vanished** | **0%** | – | 108 | 0 | **silent misroute — no error, no fallback** |
| recovery | 100% | – | 98 | 0 | re-discovery self-heals |
| llm_reasoned (mock) | 100% | 0.84 | 93.3 | 2266 | semantic routing costs tokens |

### Headline findings

1. **Discovery ≠ routing** — "find candidates" and "pick one" have very
   different costs; optimize them separately.
2. **A directory costs a network round trip (~15 ms here)**; cache it and you
   get in-memory speed, at the price of staleness.
3. **The a2a client re-resolves the Agent Card on every `send_message`** —
   visible in routing latency (~30–60 ms on localhost). Production masters
   should reuse clients / cache cards.
4. **The most dangerous failure is silent misrouting:** an agent that's down
   when *discovery* runs simply never enters the roster — the master routes to
   the wrong agent with **no error**. Monitor roster completeness, not just
   call success.
5. **LLM routing buys semantics, not speed** — worth it for fuzzy tasks, not
   for well-tagged fleets.

Full tables and analysis: **[docs/NOTES.md](docs/NOTES.md)**.

## Repo layout

```
discovery_lab/
├── fleet.py           # 4 deterministic skill agents + handlers
├── server.py          # AgentExecutor + FastAPI app -> real A2A server + card
├── registry_server.py # Agent Directory (skills search)
├── strategies.py      # 5 discovery strategies (the research surface)
├── llm_client.py      # free-LLM client (Ollama / OpenAI-compatible / mock)
├── master.py          # discover -> select -> route + failure fallback
├── experiments.py     # the ladder (ex1–ex6)
├── launch.py          # fleet + registry in-process (real HTTP)
├── run.py             # CLI
└── adk_demo.py        # ADK LlmAgent host + free LLM
docs/GUIDE.md          # how A2A discovery works + how to extend
docs/NOTES.md          # lab notebook + findings
```

## Stack

- `a2a-sdk` 1.x (proto-based Agent Cards + JSON-RPC server/client)
- `google-adk` 2.x (optional: `to_a2a`, `LlmAgent` host, `RemoteA2aAgent`)
- FastAPI + uvicorn (local servers), httpx (A2A client), matplotlib (charts)
- Free LLM: Ollama (or any OpenAI-compatible endpoint), mock fallback

## References

- [a2aproject/A2A](https://github.com/a2aproject/A2A) — protocol spec
- [a2aproject/a2a-sdk](https://github.com/a2aproject/a2a-sdk) — Python SDK
- [google/adk-python](https://github.com/google/adk-python) — Agent Development Kit
- Google codelab *Multi-Agent Systems with Agent2Agent* — host-agent pattern
- Google Cloud Agent Registry — production skill-tag discovery
