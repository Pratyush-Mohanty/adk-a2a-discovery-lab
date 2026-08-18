# ADK / A2A Master-Agent Discovery — End-to-End Project Report

**Research question: How can a Master (orchestrator) agent *efficiently discover*
the right sub-agent over the Agent-to-Agent (A2A) protocol?**

This report documents, end to end: what we set out to answer, what we built,
how we measured it, what the experiments showed, and the learning points that
fall out of the data. Companion files: `docs/GUIDE.md` (how A2A discovery
works + how to use the repo), `docs/NOTES.md` (lab notebook), `experiments/`
(regenerated JSON + charts).

---

## 1. Executive summary

We built a self-contained experiment lab on top of Google's **Agent
Development Kit (ADK)** and the **A2A protocol SDK** (`a2a-sdk`) that answers
one question with numbers: *which discovery strategy should a Master use, and
what does each one cost?*

We stood up four real A2A sub-agents (each advertising an Agent Card), a
central Agent Directory, and a Master agent with five pluggable discovery
strategies. We then ran 6 experiments / 8 scenarios across a 12-task benchmark,
recording **selection accuracy, discovery latency, routing latency, LLM token
cost, and failure recovery**. Everything runs locally with no cloud account and
no paid API key (the LLM experiment uses a free local Ollama model, with a
deterministic mock fallback).

**Top-line results:** all non-faulty strategies route with 100% accuracy; the
differences are in *cost* (0.01 ms static vs ~21 ms registry lookup vs token
spend for LLM routing) and in *failure behavior* — where we found that the most
dangerous failure mode is a **silent misroute** (an agent that is down when
discovery runs simply never appears in the roster, so the Master routes to the
wrong agent with no error at all).

---

## 2. The problem and research question

A Master agent is useless if it cannot find the specialized agent that can
actually do the work. "Discovery" in the A2A world means:

1. **What agents exist?** — roster / catalog.
2. **What can each one do?** — capability advertisement (skills, tags).
3. **How do we reach it?** — endpoint + protocol binding.

The textbook answer — "fetch the Agent Card, pick the best match" — hides a
bunch of engineering trade-offs. Fetch from where (each endpoint, or a central
directory)? Cache or not (fresh vs fast)? Rank with a deterministic scorer or
with an LLM (cost vs semantics)? And what happens when an agent is down?

There was no easy, measured answer to "what should I do?", so we built the
lab to make the trade-offs **visible and quantified**.

---

## 3. Background — how A2A discovery works (theory)

### 3.1 Agent Cards
Every A2A agent publishes an **Agent Card** at a well-known HTTP path
(`/.well-known/agent-card.json` in this SDK). The card is the discovery
contract:

| field | what it tells the Master |
|---|---|
| `name`, `description` | who it is, what it does |
| `version` | how the capability contract changed over time |
| `supported_interfaces[]` | the real RPC endpoints (`{url, protocol_binding, protocol_version}`) |
| `capabilities` | streaming, push notifications |
| `default_input/output_modes` | what it accepts / returns |
| `skills[]` | **the searchable part**: `{id, name, description, tags, examples}` |

Skills are the discovery primitive — like tags on a store listing, they are
what an orchestrator searches on.

### 3.2 Discovery strategies (the spectrum we benchmarked)

| strategy | where the answer lives | cost profile | risk |
|---|---|---|---|
| **Static** | compile-time map inside the Master | ~0 | stale; no dynamic fleets |
| **Card discovery** | fetched from each endpoint at startup | one fetch per agent, paid up front | needs a seed list of endpoints |
| **Directory / Registry** | central index (Google Cloud Agent Registry, or our `registry_server`) | network round trip per lookup | directory is a single point of failure |
| **Cached discovery** | TTL cache in front of cards | ~0 after warm-up | staleness |
| **LLM-reasoned** | an LLM reads the cards and decides | tokens + latency | cost; nondeterminism |

### 3.3 The message flow
Once the Master picks an agent: fetch the card, then `POST message/send`
(JSON-RPC 2.0) with a typed `Message`; the agent runs a `Task` through a
lifecycle (`submitted → working → completed | failed | canceled`) and streams
status + artifact updates back. The `a2a-sdk` client hides all of this behind
`client.send_message()`.

---

## 4. What we built

```
adk-a2a-discovery-lab/
├── discovery_lab/
│   ├── config.py          # ports, fleet catalog, 12-task benchmark
│   ├── fleet.py           # 4 deterministic skill agents + pure-Python handlers
│   ├── server.py          # A2A AgentExecutor + FastAPI app + Agent Card
│   ├── registry_server.py # Agent Directory: /agents, /agents/search?skill=
│   ├── a2a_client.py      # fetch_card + send_text (over a2a-sdk)
│   ├── strategies.py      # the 5 discovery strategies (research surface)
│   ├── llm_client.py      # free LLM client (Ollama / OpenAI-compatible / mock)
│   ├── master.py          # discover → select → route + failure fallback
│   ├── metrics.py         # RunResult / ExperimentSummary
│   ├── experiments.py     # the ladder (ex1–ex6)
│   ├── plot.py            # accuracy / latency / token charts
│   ├── launch.py          # fleet + registry in-process (real HTTP)
│   ├── run.py             # CLI
│   └── adk_demo.py        # ADK LlmAgent "host" driven by a free local LLM
├── docs/                  # GUIDE.md, NOTES.md, REPORT.md (this file)
└── experiments/           # summary.json, runs.json, *.png
```

Key design choices:

- **Real protocol, zero cloud.** Sub-agents are real A2A servers on localhost
  (FastAPI + `a2a-sdk`); the Master talks real JSON-RPC over HTTP. But the
  sub-agents' brains are deterministic Python functions, so results are
  reproducible and require no API keys.
- **The experiment harness is the product.** Every strategy plugs into the
  same `MasterAgent`, runs the same 12 tasks, and reports the same metrics —
  so strategies are comparable by construction.
- **Failure is a first-class experiment**, not an afterthought (ex5).

### 4.1 The sub-agent fleet (what we tested with)

Four deterministic "skill workers". Each is a **real A2A server** (FastAPI +
`a2a-sdk`) with its own Agent Card at `/.well-known/agent-card.json`, a
JSON-RPC 1.0 endpoint at `/a2a/jsonrpc`, an HTTP+JSON endpoint at `/a2a/rest`,
streaming capability, and input/output modes `text/plain` + `application/json`.
They are **deterministic** — the "brains" are pure-Python handlers with no LLM —
so every run is reproducible offline. Each simulates **8 ms of work** per task
so routing timings stay measurable.

| agent | port | configured for (role) | skills (`id` → tags) | handler behaviour | tasks |
|---|---|---|---|---|---|
| **summarizer** | 8101 | concise summaries & tl;dr | `summarize` → [summarize, summary]; `tldr` → [tl;dr, concise] | splits text into sentences, keeps the first 2 as "key points", reports word count → `[summary] Word count: N. Key points: …` | t01–t03 |
| **translator** | 8102 | EN ↔ ES / FR / HI translation | `translate` → [translate, language]; `multiling` → [multilingual, i18n] | detects the target language from the text (spanish/french/hindi), maps words through a small bilingual dictionary → `[translated -> <lang>] …` | t04–t06 |
| **extractor** | 8103 | structured data extraction (PII) | `extract` → [extract, structured, json]; `pii` → [pii, entities] | regex extraction of emails, phone numbers, dates, money amounts → JSON | t07–t09 |
| **classifier** | 8104 | sentiment / urgency / topic labeling | `classify` → [sentiment, classify]; `label` → [label, urgency, ops] | keyword lexicons for positive/negative sentiment, urgency, ops topic → JSON | t10–t12 |

**Why these four?** They are deliberately ambiguous at the edges — extractor and
classifier both touch "entities", summarizer and classifier both do text
analysis — so routing is a *real decision*, not a trivial exact-tag lookup. The
task's declared skill tag gives the deterministic scorer a fair chance; the
fuzzier phrasing of the task text is what separates good routing from guessing.

---

## 5. What we did — methodology

### 5.1 The benchmark task set
12 tasks, 3 per sub-agent. Each task declares the **expected agent** (ground
truth) and a **skill tag**, so we can score *routing correctness* objectively:

| id | task text (abridged) | expected agent | skill tag | note |
|---|---|---|---|---|
| t01 | the cat sat on the mat and the dog barked loudly while the neighbors watched | summarizer | summarize | long sentence → summarize |
| t02 | quantum computing uses qubits that can be in superposition states… | summarizer | tl;dr | dense → tl;dr |
| t03 | distributed systems sacrifice consistency for availability under the cap theorem… | summarizer | concise | dense → concise |
| t04 | translate this greeting to spanish: hello good morning | translator | translate | EN → ES |
| t05 | please translate the following to french: thank you very much | translator | language | EN → FR |
| t06 | convert to hindi: where is the nearest railway station | translator | multilingual | EN → HI |
| t07 | extract emails dates and money from: contact jane.doe@example.com by 2026-12-31 and pay $1,299.50 | extractor | extract | entities |
| t08 | find phone numbers and emails in: call +91-98765-43210 or write info@acme.io today | extractor | structured | PII |
| t09 | pull out all named entities and dates: Dr. Reyes reviewed the MRI on April 3rd… | extractor | json | NER |
| t10 | classify the sentiment of this review: the service was awful and the food arrived cold | classifier | sentiment | negative |
| t11 | classify urgency: the production database is down and customers are blocked from paying | classifier | urgency | high urgency |
| t12 | tag this ticket: server keeps crashing after the new deploy at midnight | classifier | label | ops ticket |

### 5.2 The metrics
For every task we record:

- **discovery ms** — time to obtain the candidate list (in-memory index hit,
  directory round trip, or cache hit)
- **selection ms** — time to choose one candidate (scoring or LLM)
- **routing ms** — A2A `message/send` round trip (including the SDK's
  per-send card re-resolution)
- **accuracy** — chosen agent == expected agent
- **tokens** — LLM spend (real `usage` when available, else estimated)
- **fallback / error flags** — how the Master reacted to failures

### 5.3 The experiment ladder

| # | scenario | what it isolates |
|---|---|---|
| ex1 | `static` | the baseline floor: compile-time knowledge |
| ex2 | `card_discovery` | runtime Agent Card fetches → skill index |
| ex3 | `registry_skill` | per-request skill-tag search against the directory |
| ex4 | `cached` (2 passes) | TTL cache: hit vs miss, amortized cost |
| ex5a | `card_discovery` + agent **down** | route fails → fallback + recovery |
| ex5b | `card_discovery` + agent **vanished** | agent missing at discovery time |
| ex5c | recovery (agent restarted) | does re-discovery self-heal? |
| ex6 | `llm_reasoned` | free LLM picks the agent (tokens + latency) |

### 5.4 How each method worked (what we did, step by step)

Every method runs the same Master loop — **discover → select → route** — and
differs only in the first two steps.

**static**
1. At setup, build a compile-time map `skill-tag → agent` straight from the
   fleet spec (no network).
2. Per task: look up the task's declared tag → pick that agent. If the tag is
   missing or the agent is excluded, rank all candidates by keyword overlap.
3. Cost: a dict lookup (~0.01 ms). This is the floor every other method must
   justify itself against.

**card_discovery**
1. At setup, for each of the 4 known endpoints, `HTTP GET
   /.well-known/agent-card.json` via the a2a-sdk `A2ACardResolver`, parse each
   card's skills, and build a `tag → [cards]` index in memory.
2. Per task: score every candidate = keyword overlap between the task text and
   the card's skill tags/descriptions, plus a bonus for an exact `skill_tag`
   match; sort; take the top agent.
3. Cost: all network paid once at setup; per-request discovery is an in-memory
   index query (~0.001 ms).

**registry_skill**
1. Per task: `HTTP GET <directory>/agents/search?skill=<tag>` against the Agent
   Directory. If the search fails, fall back to `GET /agents` (full listing).
2. Same ranking + pick as card_discovery.
3. Cost: a network round trip per request (~21 ms here) — this is the
   measurement that makes the "directory is slow per lookup" trade-off visible.

**cached**
1. Same card fetch as card_discovery, but behind a **30 s TTL cache**, warmed
   at setup.
2. Per task: check whether any cached card has expired; re-fetch only the
   expired ones; then run the same index query. Record whether the request was
   a cache hit.
3. Cost: ~0.03 ms on a hit (all 36 tasks in the run were hits). The hidden
   price is staleness — the cache keeps serving an old endpoint until the TTL
   fires, even if the agent moved or died.

**llm_reasoned**
1. Build the same in-memory card index as card_discovery.
2. Per task: render a prompt — *"You are a routing dispatcher. Reply with ONLY
   the agent name…"* — listing every card as `name: description (skills: tags)`,
   and ask the free LLM (Ollama by default, any OpenAI-compatible endpoint
   otherwise) to pick one; parse the returned name; record token usage.
3. If no LLM is reachable, fall back transparently to the deterministic keyword
   scorer (`llm_mode=mock`, tokens still estimated) so the experiment runs
   offline.
4. Cost: ~0.37 ms selection + **≈2,266 tokens per 12-task run** — the only
   method that spends tokens.

**Failure handling (used by all):** if routing to the chosen agent throws (dead
endpoint), the Master re-runs discovery **excluding** that agent and tries the
next-best candidate once. That fallback is what ex5a exercises; ex5b shows what
happens when the dead agent was never discovered in the first place.

---

## 6. What we achieved — results

Reference run (localhost, Windows, Python 3.10, a2a-sdk 1.1.2, ADK 2.7).
Regenerate anytime with `py -m discovery_lab.run`.

| scenario | accuracy | discovery ms | selection ms | routing ms | total ms | tokens | cache hits | fallbacks | errors |
|---|---|---|---|---|---|---|---|---|---|
| ex1 static | 100% | 0.012 | 0.002 | 74.5 | 74.5 | 0 | – | 0 | 0 |
| ex2 card_discovery | 100% | 0.001 | 0.21 | 45.2 | 45.4 | 0 | – | 0 | 0 |
| ex3 registry_skill | 100% | **20.7** | 0.06 | 28.3 | 49.0 | 0 | – | 0 | 0 |
| ex4 cached (pass 1) | 100% | 0.025 | 0.23 | 37.2 | 37.5 | 0 | 12/12 | 0 | 0 |
| ex4 cached (pass 2) | 100% | 0.039 | 0.27 | 52.8 | 53.1 | 0 | 24/24 | 0 | 0 |
| **ex5a agent down** | **0%** | 0.009 | 0.36 | **2105** | **2105** | 0 | – | **3** | 0 |
| **ex5b agent vanished** | **0%** | 0.001 | 0.11 | 29.5 | 29.6 | 0 | – | **0** | **0** |
| ex5c recovery | 100% | 0.002 | 0.20 | 57.0 | 57.2 | 0 | – | 0 | 0 |
| ex6 llm_reasoned | 100% | 0.003 | 0.37 | 64.6 | 65.0 | **2266** | – | 0 | 0 |

### 6.1 Per-experiment analysis

**ex1 — static.** Perfect accuracy, ~0 ms discovery. It is the *floor*: the
Master "knows" the answer. Cost of that knowledge is zero flexibility — adding
an agent, moving a port, or sharing across teams means editing code. This is
why real systems need some form of dynamic discovery.

**ex2 — card discovery.** Fetch cards once at startup, index skills, score per
task. Discovery is essentially free per request (~0.001 ms) because the network
cost is paid once at setup. Same accuracy. **Lesson: when the roster is small
and stable, fetch-and-index beats query-per-request.**

**ex3 — registry skill search.** Per-request HTTP round trip to the directory.
Discovery jumped to **~21 ms** — four orders of magnitude more than ex2's
in-memory hit — for identical accuracy. The directory buys *dynamic
registration, governance, and scale* (agents can join/leave without touching
the Master), but you pay network latency on every lookup. **Lesson: a directory
is a scalability/governance feature, not a speed feature — cache its answers.**

**ex4 — cached discovery.** A TTL cache turns ex3's network cost into ex2's
memory cost (0.03 ms, all 36 tasks cache hits). The price is **staleness**:
the cache will happily point at an old endpoint until the TTL expires. TTL is
the latency-vs-freshness knob.

**ex5 — failure (the important one).** Two distinct failure modes emerged:

- **5a "agent down" (card known):** the Master selected the correct agent
  (translator), the A2A send failed, and the Master re-discovered *excluding*
  the dead agent and re-routed. Fallback engaged (`fallbacks=3`) but accuracy
  was 0% — the fallback candidate was the *wrong* agent (summarizer for a
  translation task). Routing latency exploded to **2.1 s** due to the SDK's
  per-send card re-fetch + connect timeout on the dead endpoint.
- **5b "agent vanished" (card unreachable at discovery time):** because the
  agent was down *when cards were fetched*, it never entered the roster. The
  Master **silently** routed translation tasks to a wrong agent —
  `fallbacks=0, errors=0, accuracy=0%`. No exception, no signal, no log.
  **This is the scarier failure**: a discovery failure looks like "this agent
  does not exist", not "this agent is broken".
- **5c recovery:** restart the agent, re-discover → 100% accuracy again.
  Discovery self-heals by re-fetching cards; what it *cannot* do is verify
  liveness between refreshes.

**ex6 — LLM-reasoned routing.** A free local LLM reads the discovered cards and
picks the agent. With no LLM present it falls back to the deterministic scorer
(`llm_mode=mock`, tokens are still estimated). The LLM path buys *semantic*
routing — it can understand "translate" even when tags are sparse — but costs
**tokens (≈2,266 estimated for 12 tasks) and extra selection latency**, and its
accuracy is only as good as the model + prompt. On this small, well-tagged
fleet the deterministic scorer won on cost.

### 6.2 What the charts show

- `accuracy.png` — every strategy hits 100% except the two fault scenarios (0%).
- `latency.png` — the registry's ~21 ms discovery spike vs near-zero for
  static/card/cached; the 2.1 s spike for the "agent down" route.
- `tokens.png` — only the LLM strategy spends tokens.

### 6.3 The verdict: which discovery method wins?

We score each method on five axes (higher = better; cost = lower is better):

| method | accuracy | discovery cost | tokens | resilience | simplicity | overall |
|---|---|---|---|---|---|---|
| static | 100% | ~0.01 ms ⭐ | 0 ⭐ | weak (no roster) | ⭐⭐⭐⭐⭐ | great floor, no dynamism |
| **card_discovery** | 100% | ~0.001 ms ⭐ | 0 ⭐ | needs fallback | ⭐⭐⭐⭐ | **runner-up for small fleets** |
| registry_skill | 100% | **20.7 ms** | 0 ⭐ | SPOF, needs fallback | ⭐⭐⭐ | right for scale, slow per lookup |
| **cached** | 100% | ~0.03 ms ⭐ | 0 ⭐ | stale cards, needs fallback | ⭐⭐⭐ | **🏆 overall winner** |
| llm_reasoned | 100% | 0.37 ms + tokens | **2266** | needs fallback | ⭐⭐ | wins only on semantics |

**Overall winner: Cached card discovery.**

On a well-tagged fleet, all five are equally accurate (100%), so the decision
falls on cost and robustness. Cached discovery matches static/card discovery's
near-zero per-request latency (0.03 ms vs 21 ms for a registry lookup), spends
zero tokens, and — unlike static — keeps working when the roster changes,
because it re-fetches cards on TTL expiry. For a small, stable fleet the
**runner-up is plain card_discovery**: same accuracy and speed, simpler (no TTL
machinery), discovery paid once at startup.

The **podium, by situation** (there is no single winner for every deployment):

| your situation | use this method |
|---|---|
| tiny fixed fleet, endpoints known, want zero machinery | **static** (or just card_discovery) |
| small/medium fleet that changes; want minimum latency + simplicity | **card_discovery** |
| large/dynamic fleet; need governance + discovery without touching Masters | **registry_skill + cache** (directory is source of truth, cache for speed) |
| fuzzy/ambiguous tasks, sparse or noisy tags, need semantic matching | **llm_reasoned** (pay tokens for understanding) |
| anything production | always pair the winner with a **failure fallback** and **roster-completeness monitoring** (ex5b) |

**The one caveat that beats every method:** none of them detects a "vanished"
agent — if a sub-agent is down when discovery runs, the Master silently routes
to the wrong agent with zero error. Whichever method you pick, add liveness /
roster monitoring on top; that single finding (ex5b) is worth more than any
latency difference between the methods.

---

### 6.4 Research-backed methods & the use-case matrix

We then surveyed the agent-discovery / tool-retrieval literature and
implemented three more methods in the same harness (offline, dependency-light,
directly comparable):

| source | method implemented |
|---|---|
| Tool-to-Agent Retrieval, Agent-as-a-Graph (arXiv 2511.01854, 2511.18194) | **bm25** — Okapi BM25 over card documents (sparse lexical baseline) |
| Semantic Tool Discovery for MCP (arXiv 2603.20313) | **semantic** — dense embeddings (fastembed, all-MiniLM-L6-v2) + cosine |
| Tool-to-Agent Retrieval / Agent-as-a-Graph | **hybrid** — BM25 + semantic fused with Reciprocal Rank Fusion (k=60) |
| RouteLLM (arXiv 2406.18665) | conceptual only (SW-ranking ≈ semantic; MF/BERT need training data) |
| ANS / ACNBP (arXiv 2505.10609, 2506.13590) | already covered by `registry_skill` (capability-aware registry) |
| AIOS DHT+Gossip (arXiv 2504.14411) | documented, not built (P2P infra-heavy) |
| BiRouter / GraphRouter / HYSET | out of scope (learned scoring / supervision) |

To stress-test the "accuracy is a tie" claim we built three **task sets** in
`discovery_lab/config.py` (`TASK_SETS`) — `well_tagged` (the original 12
tasks), `paraphrased` (same intents, reworded with **no shared vocabulary and
no usable tag** — the "user requests rarely align with the tag vocabulary"
point from ToolDreamer), and `noisy` (compound tasks whose text contains
distractor keywords from the wrong agents). Every strategy ran all 36 tasks.

**Measured matrix (accuracy %, 12 tasks per cell):**

| task set | static | card_discovery | bm25 | semantic | hybrid |
|---|---|---|---|---|---|
| well_tagged | **100** | **100** | 92 | 75 | 83 |
| paraphrased | 33 | 33 | 33 | **75** | **83** |
| noisy | 58 | 58 | **75** | 58 | **75** |

Readings:

1. **Tags that match the text → lexical wins.** On well-tagged tasks BM25 and
   card discovery are the cheapest accurate methods; embeddings are the
   *weakest* (75%) and the slowest (+30–66 ms selection). Don't pay for
   semantics when your tasks are keyword-y.
2. **Paraphrased requests → semantics win.** All three lexical methods collapse
   to 33% (random with 4 agents); semantic reaches 75%, hybrid 83%. This is
   where embedding latency and LLM tokens are actually justified.
3. **Noisy tasks → hybrid is king.** Dense-only drops to 58% (a distractor
   keyword pulls the vector toward the wrong agent); BM25 and hybrid hold 75%.
   **Hybrid is the only method ≥75% in every regime** — the robust default.
4. This mirrors the literature: Tool-to-Agent Retrieval / Agent-as-a-Graph
   report hybrid lexical+dense with rank fusion beating either alone, and
   LLMRouterBench finds **no single router dominates** — the best method
   depends on the workload.

Charts: `../experiments/accuracy_by_usecase.png`,
`../experiments/selection_by_usecase.png`, `../experiments/tokens_by_usecase.png`.

## 7. Learning points

### 7.1 Design lessons (the answers)

1. **Discovery ≠ routing.** "Find candidates" and "pick one" are separate,
   differently-priced operations. Optimize them separately: index once and
   cache the index; spend the expensive selector (LLM) only when the cheap
   scorer is uncertain.
2. **A directory is for governance, not speed.** It gives dynamic registration
   and a governed catalog, but each lookup is a network round trip. Cache
   directory responses (TTL) to get in-memory speed.
3. **Static is a floor, not a target.** ~0 cost, but zero dynamism and zero
   resilience — any evolving fleet needs card/directory discovery.
4. **Caching trades freshness for speed, and freshness is a correctness
   concern.** A stale card can send the Master to a dead endpoint. Combine a
   cache with a liveness/fallback path, or bounded retries.
5. **Plan for failure from day one — and monitor the roster, not just call
   success.** Silent misrouting (5b) had no error at all; only monitoring
   *roster completeness* catches it. The fallback path (5a) at least makes
   failure visible, but can still pick the wrong agent — fallback should be
   *aware* of task-skill fit, not just "next in the list".
6. **LLM routing buys semantics at a real price.** Worth it for fuzzy,
   noisy, or open-ended task routing; overkill for a small, well-tagged fleet.

### 7.2 Engineering lessons (A2A / SDK specifics we hit)

7. **a2a-sdk v1 is proto-based, not pydantic.** `a2a.types` re-exports
   `a2a_pb2`; enums are prefixed (`TASK_STATE_WORKING`, `ROLE_USER`). Code
   written for the 0.3.x (pydantic) API will not port directly.
8. **The card's `supported_interfaces[].url` must be the RPC route**, not the
   server root — otherwise the client POSTs JSON-RPC to `/` and gets a 404.
9. **`create_client(agent=...)` re-resolves the Agent Card on every send.**
   That per-send card fetch is visible in our routing numbers (~30–75 ms on
   localhost) and becomes a 2-second timeout when the agent is down. Production
   Masters should reuse clients / cache resolved cards.
10. **ADK specifics:** `LiteLlm` lives under `google.adk.models.lite_llm` and
    requires the `google-adk[extensions]` extra (there is no `[lite-llm]`
    extra in 2.7); the v2 `Content`/`Part` types come from
    `google.adk.utils.content_utils`.
11. **Keep the LLM optional.** A pluggable client with a deterministic fallback
    (our `llm_client`) means the whole lab runs with zero API keys and zero
    external services, and the real-LLM path is a one-line env change.

### 7.3 Process lessons

12. **Measure before you optimize.** The registry "looked" fine until we
    measured discovery at 21 ms vs 0.03 ms cached; the silent-misroute failure
    was invisible until we deliberately killed an agent mid-run.
13. **Make failure an experiment.** Injecting faults (stop an agent, restart an
    agent) surfaced behavior that happy-path testing never would.

---

## 8. Limitations

- Sub-agents are deterministic (no LLM inside), so we measured *routing*
  correctness, not *reply* quality.
- Latency is on localhost; real networks amplify registry/cache differences.
- `registry_skill` trusts the tag each task declares; a harder variant would
  have the Master *infer* the skill from free text (that is ex6).
- TTL staleness is not yet *injected* in ex4 — we could set a tiny TTL, mutate
  a card, and measure the staleness window explicitly.
- Fleet size is small (4 agents); scaling to N agents (index vs linear lookup,
  directory broadcast) is an obvious next benchmark.

---

## 9. Next steps

1. Swap deterministic sub-agents for real ADK `LlmAgent` workers (via
   `to_a2a`) and re-run the same ladder.
2. Add a **large-scale experiment**: register 10–100 agents, compare index
   lookup vs directory broadcast vs LLM selection as N grows.
3. Implement **skill-inference routing**: Master infers the skill from task
   free text, then compares deterministic scoring vs LLM end-to-end.
4. **Hardening experiment**: inject stale cards + dead endpoints, and measure
   fallback *fitness* (does the fallback pick the next-best *fitting* agent?).
5. Wire observability (tracing of card fetch → selection → task) on top of the
   metrics already collected.

## 10. References

- `a2aproject/A2A` — protocol spec (Agent Card schema, JSON-RPC methods).
- `a2aproject/a2a-sdk` — Python SDK (v1.x, proto-based types).
- `google/adk-python` — ADK: `to_a2a()`, `RemoteA2aAgent`, `LlmAgent`.
- Google codelab *Multi-Agent Systems with Agent2Agent* — host-agent pattern.
- Google Cloud Agent Registry — production skill-tag discovery.
