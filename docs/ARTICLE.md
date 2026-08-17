# Agent discovery in A2A: we tested 5 ways to find the right agent — and found the winner

**An end-to-end benchmark of agent discovery on a real (tiny) multi-agent fleet built with Google's ADK and the A2A protocol.**

---

If you have ever built a multi-agent system, you know the quiet crisis that hits
once you have more than two or three agents: *which agent should handle this
task, and how do I find out?*

Agent discovery — the "find the right agent for the task" step — is where
distributed systems meet search engines. Do it badly and your system is slow,
brittle, or silently routes work to the wrong agent. Do it well and you get
speed, resilience, and clean governance for free.

We built a small but real A2A fleet — four deterministic worker agents behind a
Master agent — and benchmarked **five discovery strategies** against it:
static mapping, A2A card discovery, registry-based skill search, TTL-cached
discovery, and LLM-reasoned routing. We measured accuracy, latency, token cost,
and behavior under failure.

The headline: **on a well-tagged fleet, accuracy is a tie (100% for every
method), so the winner is decided by cost — and cached card discovery wins.**

![Architecture of the lab: a Master agent with five discovery strategies routing to four skill workers via their Agent Cards or a directory.](experiments/architecture.png)

---

## Why agent discovery is the real problem

An agent is only useful if the system knows it exists, knows what it can do, and
can reach it. A2A (Agent2Agent) gives you a standard for the *reach it* part —
real JSON-RPC over HTTP with a well-known endpoint — but the *knows it exists*
and *knows what it can do* parts are left to you.

That's where discovery comes in. And every discovery decision is a trade-off:

- **Where does the catalog live?** In the Master's code (static), in the
  agents themselves (Agent Cards), or in a central directory?
- **When do you look it up?** Once at startup, per request, or through a cache?
- **Who does the deciding?** A deterministic scorer, or a language model?

Five obvious strategies fall out of those choices. We built all five.

## What we tested it on: a real (tiny) A2A fleet

Four worker agents, each a genuine A2A server (FastAPI + the official `a2a-sdk`)
serving its **Agent Card** at `/.well-known/agent-card.json` and a JSON-RPC
endpoint. Their "brains" are deterministic Python handlers, so every result is
reproducible and needs no API keys or cloud.

| agent | port | configured for | skills (id → tags) | tasks |
|---|---|---|---|---|
| summarizer | 8101 | concise summaries & tl;dr | `summarize` → [summarize, summary]; `tldr` → [tl;dr, concise] | t01–t03 |
| translator | 8102 | EN ↔ ES / FR / HI | `translate` → [translate, language]; `multiling` → [multilingual, i18n] | t04–t06 |
| extractor | 8103 | structured data & PII extraction | `extract` → [extract, structured, json]; `pii` → [pii, entities] | t07–t09 |
| classifier | 8104 | sentiment / urgency / labeling | `classify` → [sentiment, classify]; `label` → [label, urgency, ops] | t10–t12 |

The fleet is deliberately **ambiguous at the edges**: extractor and classifier
both touch "entities"; summarizer and classifier both do text analysis. That
makes routing a real decision rather than a trivial exact-tag lookup.

Each of the **12 benchmark tasks** (3 per agent) declares its expected agent, so
routing correctness is scored objectively. Every strategy plugs into the same
Master, runs the same tasks, and reports the same metrics.

## The five discovery strategies, briefly

1. **Static** — a hardcoded `skill-tag → agent` map compiled into the Master.
   No network. ~0.01 ms. The floor everything else must beat.
2. **Card discovery** — at startup, fetch every endpoint's Agent Card, index
   its skills in memory, then rank candidates per task (keyword overlap +
   exact-tag bonus). ~0.001 ms per request; discovery cost paid once.
3. **Registry skill search** — a central Agent Directory; per request, ask it
   `GET /agents/search?skill=<tag>` (mirroring Google Cloud Agent Registry).
   Real network round trip: ~21 ms.
4. **Cached** — card/registry discovery behind a 30-second TTL cache. ~0.03 ms
   per request, 36/36 hits in the run.
5. **LLM-reasoned** — hand every card's name + description + skill tags to a
   free LLM and let it pick. ~0.37 ms selection plus **2,266 tokens** per run.

## What we did, run by run

We ran eight scenarios: the five strategies plus three failure drills.

- **ex1 static** → 100% accuracy, discovery 0.01 ms
- **ex2 card_discovery** → 100%, discovery ~0 ms
- **ex3 registry_skill** → 100%, but discovery costs **20.7 ms** — four orders
  of magnitude over an in-memory hit
- **ex4 cached** → 100%, ~0.03 ms, 36/36 cache hits
- **ex5a agent down** → the Master routes to a dead endpoint, the fallback
  engages but picks the wrong agent: **accuracy 0%**, routing 2.1 s, 3 fallbacks
- **ex5b agent vanished** → the dead agent was never discovered, so routing is
  silently wrong: **accuracy 0%, zero errors, zero fallbacks** — the scariest
  result in the whole lab
- **ex5c agent recovered** → back to 100%
- **ex6 llm_reasoned** → 100%, 2,266 tokens

![Routing accuracy per experiment: 100% everywhere except the two failure scenarios.](experiments/accuracy.png)

![End-to-end latency per experiment, dominated by the registry's per-request lookup and the 2.1 s dead-agent route.](experiments/latency.png)

![Token usage: only the LLM strategy spends any.](experiments/tokens.png)

## So which discovery method wins?

On a well-tagged fleet, **accuracy is a tie** — all five methods hit 100%. The
winner is therefore decided on cost and robustness, not on who "works".

| method | discovery cost | tokens | needs infra? | verdict |
|---|---|---|---|---|
| static | ~0.01 ms | 0 | no | great floor, zero dynamism |
| **card_discovery** | ~0.001 ms | 0 | no | **runner-up for small fleets** |
| registry_skill | **20.7 ms** | 0 | yes (directory) | right for scale, slow per lookup |
| **cached** | ~0.03 ms | 0 | cache only | **🏆 overall winner** |
| llm_reasoned | 0.37 ms | **2,266** | yes (LLM) | wins only on semantics |

**The winner: cached card discovery.** It matches static and card discovery's
near-zero per-request latency, spends zero tokens, and — unlike static — keeps
working when the roster changes, because it re-fetches cards on TTL expiry.
For a small, stable fleet the runner-up is plain **card discovery**: equally
accurate and fast, and simpler (no TTL machinery).

But there is no single winner for every deployment. The decision actually maps
to your situation:

| your situation | use this |
|---|---|
| tiny fixed fleet, endpoints known | **static** (or just card discovery) |
| small/medium fleet that changes; want latency + simplicity | **card_discovery** |
| large/dynamic fleet; governance + search without touching Masters | **registry_skill + cache** |
| fuzzy/ambiguous tasks, sparse/noisy tags | **llm_reasoned** (pay tokens for understanding) |
| production | any + **failure fallback + liveness monitoring** |

## The one finding that beats every method

The lab's most valuable result has nothing to do with which method is faster. It
is that **none of the five detects a vanished agent**:

- **Agent down, card known** → visible error, fallback engages (but may pick
  the wrong agent). Accuracy 0%, latency 2.1 s.
- **Agent vanished, card never fetched** → the agent silently never enters the
  roster; the Master routes to the wrong agent with **no error, no fallback, no
  log**. Accuracy 0%, errors 0%.

Whatever method you pick, add **liveness / roster-completeness monitoring** and
a **skill-aware fallback** — fall back to the next agent that actually fits the
task, not "next in the list". That single lesson (ex5b) is worth more than any
latency difference between the five methods.

## If you want to try it

The whole lab is open source and runs offline on a laptop — no cloud, no API
keys. Clone, `pip install -e .[a2a,extensions]`, run `python discovery_lab/run.py`,
and you get the full experiment ladder plus the charts in seconds.

```
adk-a2a-discovery-lab/
├── discovery_lab/          # the lab: fleet, strategies, experiments
├── docs/                   # this article + full report, guide, notebook
├── scripts/                # chart + doc/HTML generators
└── experiments/            # results + charts (regenerated every run)
```

If you're building a multi-agent system, spend an afternoon on your discovery
layer. It is the cheapest place to buy speed, resilience, and governance — and,
as our vanished-agent scenario shows, the most dangerous place to ignore.

---

*Built with Google ADK + the A2A protocol (a2a-sdk 1.1.2). Full methodology,
measurements, and the experiment ladder live in the companion report
[docs/REPORT.md](REPORT.md); mechanism walkthrough in
[docs/GUIDE.md](GUIDE.md); decision guide in [docs/COMPARISON.md](COMPARISON.md).*