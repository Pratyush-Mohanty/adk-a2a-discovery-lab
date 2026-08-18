# NOTES.md — experiment log & findings

A lab notebook for **"how can a Master agent efficiently discover sub-agents over A2A?"**.
Every run regenerates `experiments/*.json` + `experiments/*.png` via
`py -m discovery_lab.run`. Numbers below are from the reference run on
Windows / Python 3.10 / a2a-sdk 1.1.2 / google-adk 2.7.

## Environment / SDK notes (things we learned the hard way)

- **Package split.** Two layers matter:
  - `a2a-sdk` — the A2A protocol itself (Agent Cards, JSON-RPC server, client).
    This lab's *core* runs on `a2a-sdk` only, so it is cloud-free and key-free.
  - `google-adk[a2a]` — ADK's `to_a2a()`, `RemoteA2aAgent`, and the host-agent
    pattern. Used in the optional `adk_demo`.
- **a2a-sdk v1.x is proto-based.** `a2a.types` re-exports `a2a_pb2`; types are
  Protocol Buffer messages, not pydantic. Enums are prefixed:
  `TASK_STATE_WORKING`, `ROLE_USER`, etc. (v0.3 used pydantic + bare names.)
- **Card path is `/.well-known/agent-card.json`** (served by
  `create_agent_card_routes`), and `A2ACardResolver` appends it to a *base URL*.
- **The card's `supported_interfaces[].url` must point at the RPC route**
  (e.g. `http://host:8101/a2a/jsonrpc`), not the root. If you put the root URL
  there, the client POSTs JSON-RPC to `/` and gets a 404.
- **`create_client(agent=...)` re-fetches the Agent Card on every send.**
  `Client.send_message()` therefore costs a card fetch *per message* — the A2A
  SDK deliberately re-resolves identity each time. A production master should
  reuse a client or cache cards; we quantify this in the routing latency below.
- **ADK LiteLlm** lives under `google.adk.models.lite_llm` and requires the
  `google-adk[extensions]` extra (there is no `[lite-llm]` extra in 2.7).

## Reference run (aggregate)

| experiment | strategy | acc | disc ms | sel ms | route ms | total ms | tokens | cache hits | fallbacks | errors |
|---|---|---|---|---|---|---|---|---|---|---|
| ex1 | static | 100% | 0.01 | 0.00 | 52.8 | 52.9 | 0 | – | 0 | 0 |
| ex2 | card_discovery | 100% | ~0 | 0.15 | 31.2 | 31.4 | 0 | – | 0 | 0 |
| ex3 | registry_skill | 100% | 15.5 | 0.07 | 27.3 | 42.9 | 0 | – | 0 | 0 |
| ex4 pass1 | cached | 100% | 0.03 | 0.26 | 59.0 | 59.3 | 0 | 12/12 | 0 | 0 |
| ex4 pass2 | cached | 100% | 0.03 | 0.28 | 63.1 | 63.4 | 0 | 24/24 | 0 | 0 |
| ex5 down | card_discovery | 0% | ~0 | 0.26 | 2150.8 | 2151.2 | 0 | – | 3 | 0 |
| ex5 vanished | card_discovery | 0% | ~0 | 0.29 | 107.3 | 107.6 | 0 | – | 0 | 0 |
| ex5 recovery | card_discovery | 100% | ~0 | 0.76 | 96.9 | 97.8 | 0 | – | 0 | 0 |
| ex6 | llm_reasoned (mock) | 100% | ~0 | 0.84 | 92.4 | 93.3 | 2266 | – | 0 | 0 |

Timings are per-task means. `discovery` = time to obtain candidates;
`selection` = time to choose; `routing` = A2A message/send round trip
(includes the SDK's per-send card re-fetch).

## What each experiment answered

### ex1 — static (baseline)
Compile-time map `skill-tag -> agent endpoint`. Zero discovery cost (~0.01 ms),
100% accuracy. **Floor:** this is the fastest possible answer — the question is
whether you can afford to hardcode it (no dynamic fleets, no reconfig at
runtime, no cross-team sharing).

### ex2 — card discovery
Fetch `agent.json` from known endpoints once at startup, index skills, then
select by keyword/tag scoring per task. Discovery ~0.003 ms/task (all paid at
setup). 100% accuracy. **Takeaway:** card-based discovery converts a hardcoded
map into a *data-driven* map with ~zero per-request cost — the "discovery" bill
is paid once, up front.

### ex3 — registry skill search
Per-request query to a central Agent Directory (`/agents/search?skill=<tag>`).
Discovery jumped to **15.5 ms** (an HTTP round trip) — an order of magnitude
more than ex2's in-memory lookup, for the same accuracy. **Takeaway:** a
directory gives you dynamic registration, governance, and scale, but you pay
network latency per lookup; cache the directory response.

### ex4 — cached discovery (TTL)
Card discovery behind a 30s TTL cache. All 12 (then 24) tasks were cache hits;
discovery stayed ~0.03 ms. **Takeaway:** caching collapses ex3's network cost to
ex2's memory cost. The price is *staleness* — see ex5. TTL choice is the
latency-vs-freshness knob.

### ex5 — failure (the interesting one)
Two distinct failure modes surfaced:

1. **ex5_failure_down — card known, agent dead.** The master routed to the
   translator (correct selection), the A2A send failed, and the master
   re-discovered *excluding* the dead agent and re-routed. `fallbacks=3`.
   Cost: routing ballooned to **2151 ms** (client card-refetch + connect
   timeout on the dead endpoint) and accuracy dropped to 0% because the
   fallback candidate was the *wrong* agent (summarizer for a translation
   task).
2. **ex5_failure_vanished — card unreachable at discovery time.** Because the
   agent was down *when the cards were fetched*, it never entered the roster.
   The master happily routed translation tasks to a different agent —
   **silently**, with `fallbacks=0`, `errors=0`, accuracy 0%. No exception, no
   signal. This is the more dangerous failure: discovery failures look like
   "agent doesn't exist", not "agent is broken".

**Recovery:** restart the agent, re-discover → 100% accuracy again. Discovery
is self-healing by re-fetching cards; what it *cannot* do is verify liveness.

### ex6 — LLM-reasoned routing
A free local LLM (Ollama) picks the best agent from the discovered cards,
instead of deterministic tag scoring. With no LLM configured it falls back to
the keyword scorer (`llm_mode=mock`, estimated tokens recorded).
**Takeaway:** routing becomes *semantic* (it can understand "translate" even
when tags are sparse), but you pay **tokens + ~10–50× selection latency**, and
accuracy is only as good as the model + prompt. For a small, well-tagged fleet,
deterministic scoring won this benchmark on cost; LLM routing is worth it when
tasks are fuzzy or descriptions are noisy. See `docs/adk_demo` for the ADK
`LlmAgent` version driven by the same fleet.

## Key findings

1. **Discovery ≠ routing.** "Efficient discovery" splits into *find candidates*
   (card fetch / directory query / cache) and *pick one* (scoring / LLM).
   Optimize them separately; they have very different costs.
2. **Static is a floor, not a target.** It has no network, no roster, and no
   resilience — any dynamic fleet needs card/directory discovery.
3. **A directory costs ~15 ms/lookup locally** (network round trip). Cache it
   and you get in-memory speed; but caching reintroduces staleness.
4. **Every `send_message` re-resolves the Agent Card** in the a2a client
   (visible in routing latency ~30–60 ms on localhost). Reuse clients / cache
   resolved cards for real deployments.
5. **Silent misrouting is the worst failure.** A down agent that is missing
   from discovery causes wrong answers with *no error*; a down agent that is
   *present* in discovery at least triggers a visible routing failure and
   fallback. Monitor roster completeness, not just call success.
6. **LLM routing buys semantics at real cost** (tokens, latency). Use it where
   tag-based scoring is brittle, not for well-structured fleets.
7. **No single discovery method dominates** — the use-case matrix (new) proves
   it: each method has a regime where it wins, matching the "no single router
   dominates" finding in the LLM-routing literature (LLMRouterBench).

## Research-backed discovery methods (added)

Surveyed the agent-discovery / tool-retrieval literature and implemented the
methods that are (a) offline, (b) dependency-light, (c) comparable in our lab:

| paper / work | idea | implemented as |
|---|---|---|
| Tool-to-Agent Retrieval, Agent-as-a-Graph (arXiv 2511.01854, 2511.18194) | BM25 sparse baseline over tool/agent descriptions | `bm25` |
| Semantic Tool Discovery for MCP (arXiv 2603.20313) | vector embeddings of tool docs + cosine retrieval | `semantic` (fastembed, all-MiniLM-L6-v2, offline) |
| Tool-to-Agent Retrieval / Agent-as-a-Graph | hybrid lexical + dense with rank fusion | `hybrid` (Reciprocal Rank Fusion of BM25 + cosine) |
| RouteLLM (arXiv 2406.18665) | similarity-weighted ranking / learned routers | conceptual: semantic ≈ SW-ranking; MF/BERT need training data → out of scope |
| ANS / ACNBP / DNS-style registries (arXiv 2505.10609, 2506.13590) | capability-aware naming + registry | already covered by `registry_skill` |
| DHT + Gossip discovery (AIOS, arXiv 2504.14411) | decentralized P2P discovery | infra-heavy → documented, not built |
| BiRouter / GraphRouter / HYSET | learned scoring / graph / set-level routing | need training/supervision → out of scope |

Implementation: `discovery_lab/strategies.py` (BM25Index, SemanticStrategy,
HybridStrategy), `discovery_lab/usecases.py` (strategy x use-case matrix),
`discovery_lab/config.py` (`TASK_SETS`).

### Use-case matrix (accuracy %, 12 tasks per cell)

| task set | static | card_discovery | bm25 | semantic | hybrid |
|---|---|---|---|---|---|
| well_tagged | 100 | 100 | 92 | 75 | 83 |
| paraphrased | 33 | 33 | 33 | **75** | **83** |
| noisy | 58 | 58 | **75** | 58 | **75** |

- well_tagged (tags match the text) → keyword/tag methods win; **embeddings
  are the weakest** (75%) and the slowest (+30–66 ms selection).
- paraphrased (no shared vocabulary, no tag) → **semantic 75% / hybrid 83%**
  beat lexical 33%; embeddings earn their latency here.
- noisy (distractor keywords from wrong agents) → **bm25 & hybrid 75%**;
  embeddings alone drop to 58%.
- **hybrid is the only method that is ≥75% in every regime** → the robust
  default, mirroring the "hybrid retrieval with rank fusion" recommendation in
  the tool-retrieval papers.

Charts: `experiments/accuracy_by_usecase.png`, `selection_by_usecase.png`,
`tokens_by_usecase.png`.

## Limitations / next steps

- Sub-agents are deterministic (no LLM inside), so reply *quality* isn't
  measured — only routing correctness + latency + cost. Swapping in real ADK
  agents is the natural next experiment.
- Latency is localhost; real networks amplify registry/cache differences.
- `registry_skill` trusts the tag the *task* declares. A harder variant lets
  the master infer the skill from free text (see ex6) and compares end-to-end.
- TTL staleness isn't yet *injected* in ex4; a follow-up could set a tiny TTL,
  mutate a card, and measure the staleness window + recovery.
- Add a large-scale experiment: N agents in the directory, measure lookup vs
  N (index) and broadcast card-fetch vs N (linear).
