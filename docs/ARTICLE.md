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

## The five discovery strategies, in detail

Every method runs the same Master loop — **discover → select → route** — and
differs in the discover and select steps. Here is exactly how each one works
and where each one breaks.

### 1. Static mapping

**Mechanism:** a hardcoded `skill-tag → agent endpoint` dict compiled into the
Master. No network, no cards, no directory.

**Selection:** a plain dict lookup on the task's declared tag; if the tag is
unknown, it degrades to a naive keyword rank over all candidates.

**Cost:** ~0.01 ms, 0 tokens.

**Shines when:** the fleet is tiny, fixed, and known to the developer.
**Breaks when:** anything changes (code change + redeploy), the task has no
declared tag (nothing to look up), or an agent dies (routing just fails).

### 2. Card discovery

**Mechanism:** at startup, the Master fetches every endpoint's Agent Card at
`/.well-known/agent-card.json`, parses its `skills[]`, and builds an in-memory
`tag → agents` index. Discovery is paid once; per-request it is pure memory.

**Selection:** score every candidate by keyword overlap between the task text
and the card's skill tags/descriptions, add a bonus for an exact `skill_tag`
match, sort, take the top agent.

**Cost:** ~0.001 ms per request, 0 tokens.

**Shines when:** small/medium fleets that change occasionally, where you want
minimum latency and no central infrastructure.
**Breaks when:** the task is paraphrased so badly that no keyword overlaps the
card (fuzzy routing), or an agent is down *at fetch time* — it silently never
enters the roster (the "vanished" failure).

### 3. Registry skill search

**Mechanism:** agents register their cards in a central Agent Directory; the
Master queries it per request with `GET /agents/search?skill=<tag>`, falling
back to a full `GET /agents` listing. Mirrors Google Cloud Agent Registry.

**Selection:** the same keyword ranker as card discovery, applied to whatever
subset the directory returns.

**Cost:** ~21 ms per request (a real network round trip), 0 tokens.

**Shines when:** large/dynamic fleets, multi-team setups, governance/auth/audit,
and any place you want to search across agents by skill without contacting each
one.
**Breaks when:** you need per-request speed (four orders of magnitude slower
than memory), or the directory is a single point of failure. The ranker is
still keyword-based, so fuzzy tasks degrade just like card discovery.

### 4. Cached discovery

**Mechanism:** wraps card/registry discovery in a 30-second TTL cache, warmed at
startup; expired entries are re-fetched lazily, everything else is served from
memory.

**Selection:** the same in-memory index query — with a staleness window until
the TTL fires.

**Cost:** ~0.03 ms per request, 0 tokens (36/36 cache hits in our run).

**Shines when:** latency-sensitive production, hot paths, high QPS — especially
on top of a registry, where it buys the registry's governance at memory speed.
**Breaks when:** the TTL window serves a moved/dead endpoint, or (same as every
method) a vanished agent was never cached in the first place.

### 5. LLM-reasoned selection

**Mechanism:** builds the same card index, then hands the LLM a routing prompt —
*"You are a routing dispatcher. Reply with ONLY the agent name…"* — listing every
card's name, description, and skill tags. The reply is parsed and validated; if
no LLM is reachable it falls back to the deterministic scorer.

**Selection:** fully semantic. It understands paraphrase, can weigh descriptions
and examples, and generalizes to phrasing that never appears in any tag.

**Cost:** ~0.37 ms selection plus **≈2,266 tokens** per 12-task run — the only
method that spends tokens.

**Shines when:** tasks are fuzzy, tags are sparse or noisy, agents overlap, or
the domain is open-ended.
**Breaks when:** you have a tight cost/latency budget, need deterministic
behavior (an LLM can hallucinate a name that isn't in the roster), or your fleet
is small and well-tagged (then it is pure overkill).

### 6. BM25 — sparse lexical retrieval (from the research)

Searching the agent-discovery literature surfaced three more methods worth
comparing — all from the tool-retrieval line of work (Tool-to-Agent Retrieval,
Agent-as-a-Graph, semantic MCP tool discovery). We implemented all three.

**Mechanism:** tokenize each Agent Card (name + description + skill names +
tags) into a document; rank tasks with **Okapi BM25** (k1=1.5, b=0.75) — the
classic sparse-retrieval baseline from the papers.
**Cost:** ~0.2 ms selection, 0 tokens. Pure Python, no model.
**Strengths:** the best *lexical* matcher (92% on well-tagged, 75% on noisy in
our tests).
**Weakness:** vocabulary-bound — a paraphrased task shares no words with the
card and it fails (33%).

### 7. Semantic — dense embeddings (from the research)

**Mechanism:** embed every card once at startup (fastembed,
all-MiniLM-L6-v2, offline); per task, embed the request and take the highest
cosine similarity — the vector-retrieval approach of the MCP semantic tool
discovery paper.
**Cost:** ~30–66 ms selection (an embedding per request), 0 tokens.
**Strengths:** understands paraphrase (75% on our paraphrased set vs 33% for
every lexical method) and needs no tag vocabulary.
**Weakness:** the slowest non-LLM method, weakest on keyword-rich and noisy
tasks (75% / 58%) — embeddings ignore the exact-tag signal lexical methods
exploit.

### 8. Hybrid — BM25 + semantic with Reciprocal Rank Fusion (from the research)

**Mechanism:** run BM25 and the dense embedder, fuse the two ranked lists with
**Reciprocal Rank Fusion** (k=60) — the hybrid-retrieval recipe of
Tool-to-Agent Retrieval / Agent-as-a-Graph.
**Cost:** ~40–76 ms selection, 0 tokens.
**Strengths:** the **only method ≥75% accuracy in every regime we tested** —
it combines exact-keyword strength with paraphrase robustness.
**Weakness:** the most expensive non-LLM method (two embeddings + BM25 +
fusion), and two things to tune.

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

## When 100% is not guaranteed — where the methods split

The "perfect score" is **not** a general law of the five methods. It only holds
for our benchmark: 12 hand-written tasks aimed at a deliberately well-tagged
fleet. That is the *best case*, not the general case. Change the use case and
the methods split apart — fast.

| use case | static | card_discovery | registry_skill | cached | llm_reasoned |
|---|---|---|---|---|---|
| well-tagged tasks (our benchmark) | ✅ 100% | ✅ 100% | ✅ 100% | ✅ 100% | ✅ 100% |
| paraphrased task, wording not in any card | ✗ no tag to match | ~ weak keyword overlap | ~ weak keyword overlap | ~ same as card | ✅ reads the description |
| sparse / noisy skills metadata | ✗ often misses | ~ weak signals | ~ weak signals | ~ weak signals | ✅ uses description semantics |
| near-duplicate agents (overlapping skills) | ✗ picks wrong | ~ ranks wrong one first | ~ returns many, must disambiguate | ~ same as card | ✅ weighs nuance |
| new / unseen task types | ✗ unknown tag, cannot route | ~ fuzzy match only | ~ fuzzy match only | ~ fuzzy match only | ✅ generalizes |
| task has no declared skill tag | ✗ nothing to look up | ~ keyword ranking only | ~ keyword ranking only | ~ keyword ranking only | ✅ reasons from description |
| multi-intent / compound task | ✗ | ~ partial | ~ partial | ~ partial | ✅ handles it better |
| large fleet, many similar agents | ✗ does not scale | ~ linear startup, weak ranking | ~ search narrows it, ranking still weak | ~ same as card | ✅ reads every card |

✅ handles it well · ~ degrades gracefully (partial / occasional misses) · ✗ breaks.

So accuracy is only a **tie when your tasks are as clean as your tags**. The
moment the real world shows up — paraphrases, sparse metadata, overlapping
agents, unknown task types — the deterministic methods start missing, with
**static breaking first** (it has nothing to fall back on) and the **LLM
pulling ahead** (it understands intent, not just vocabulary). That is exactly
when `llm_reasoned` earns its tokens.

## The measured verdict: we ran the matrix

We didn't just speculate — we turned the "when" into an experiment. Three task
sets (well-tagged, paraphrased, noisy) × every method = a 15-cell accuracy
matrix, run on the real fleet:

![Accuracy by use case: keyword methods win when tags match the text; semantic and hybrid win when the request is paraphrased; hybrid is the only method that stays >= 75% everywhere.](experiments/accuracy_by_usecase.png)

| task set | static | card_discovery | bm25 | semantic | hybrid |
|---|---|---|---|---|---|
| **well_tagged** (tags match text) | **100%** | **100%** | 92% | 75% | 83% |
| **paraphrased** (no shared vocab, no tag) | 33% | 33% | 33% | **75%** | **83%** |
| **noisy** (wrong-agent keywords) | 58% | 58% | **75%** | 58% | **75%** |

Three things fall out:

1. **When tags match the text, lexical wins.** BM25 and card discovery are the
   cheapest accurate methods on well-tagged tasks — and embeddings are the
   *weakest* (75%) *and* the slowest (+30–66 ms). If your tasks are keyword-y,
   don't pay for semantics.
2. **When the request is paraphrased, semantics win.** All three lexical
   methods drop to 33% (random on 4 agents); semantic hits 75% and hybrid 83%.
   This is exactly where embeddings earn their latency, and where an LLM would
   earn its tokens.
3. **When tasks are noisy, hybrid is king.** Dense-only falls to 58% because a
   wrong-agent keyword pulls the vector toward the wrong card; BM25 and hybrid
   hold 75%. **Hybrid is the only method ≥75% in every regime** — the robust
   default, mirroring the "hybrid retrieval + rank fusion" recommendation in
   the tool-retrieval papers (and LLMRouterBench's finding that no single
   router dominates).

## So which discovery method wins?

On a well-tagged fleet, **accuracy is a tie** — all five original methods hit
100%. The winner is therefore decided on cost and robustness, not on who
"works". (The measured matrix above showed that on *messier* use cases accuracy
stops being a tie: **cost wins when accuracy ties, semantics wins when it
doesn't** — and hybrid is the only method that stays strong in both worlds.)

| method | discovery cost | tokens | needs infra? | verdict |
|---|---|---|---|---|
| static | ~0.01 ms | 0 | no | great floor, zero dynamism |
| **card_discovery** | ~0.001 ms | 0 | no | **runner-up for small fleets** |
| registry_skill | **20.7 ms** | 0 | yes (directory) | right for scale, slow per lookup |
| **cached** | ~0.03 ms | 0 | cache only | **🏆 cost winner on well-tagged fleets** |
| bm25 | ~0.2 ms | 0 | no | best lexical; fails on paraphrase |
| semantic | 30–66 ms | 0 | embedding model | wins on paraphrased tasks |
| **hybrid** | 40–76 ms | 0 | embedding model | **🏆 robust winner (≥75% everywhere)** |
| llm_reasoned | 0.37 ms | **2,266** | yes (LLM) | wins only on deep semantics |

**The two winners, by use case.** On a stable, well-tagged fleet — the case the
original lab measured — **cached card discovery** still wins: 100% accuracy at
~0.03 ms and zero tokens. But the research extensions changed the *general*
answer: across the three measured use cases, **hybrid (BM25 + semantic with
rank fusion)** is the only method that never drops below 75%, which makes it
the robust default for fleets whose workloads you don't fully control. For a
small, stable fleet the runner-up remains plain **card discovery**: equally
accurate and fast, and simpler (no TTL machinery, no embedding model).

But there is no single winner for every deployment. The decision actually maps
to your situation:

| your situation | use this |
|---|---|
| tiny fixed fleet, endpoints known | **static** (or just card discovery) |
| tag-rich / exact-keyword tasks | **bm25 or card_discovery** |
| paraphrased requests, sparse tags | **semantic** |
| noisy / unknown workload | **hybrid** (the safe default) |
| large/dynamic fleet; governance + search | **registry_skill + cache** |
| deeply fuzzy/ambiguous tasks | **llm_reasoned** (pay tokens for understanding) |
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