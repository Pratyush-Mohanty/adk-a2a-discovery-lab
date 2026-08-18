# How I Learned to Stop Guessing and Start Routing Agents

**A practical field guide to agent → sub-agent discovery, built by actually measuring 8 routing methods on a real A2A fleet.**

---

While building multi-agent systems, I kept running into the same itch: **how do
you efficiently route a task to the right sub-agent?**

Not "how do you call an API." That's easy. The hard part happens *before* the
call: the orchestrator has a request, and there are N agents that *could*
handle it. Which one should it go to — and how did you even find out it
exists, and what it can do?

Agent discovery is the forgotten middle layer of every "AI team of agents"
demo. And as I found out, it is a **real engineering trade-off**, not a
one-liner. This article is the result of a small experiment lab I built (real
A2A servers, real agent cards, real measurements) to answer it properly.

---

## The problem in one paragraph

An agent is only useful if the system knows three things: that it exists, what
it can do, and how to reach it. The A2A protocol (Google's standard for
inter-agent communication) solves the "reach it" part — real JSON-RPC over
HTTP with a well-known endpoint. The "knows it exists" and "knows what it can
do" parts are **left to you**, and that's where all the interesting choices
are:

- **Where does the catalog live?** In code (static), in the agents themselves
  (Agent Cards), or in a central directory?
- **When do you look it up?** Once at startup, per request, or through a cache?
- **Who does the deciding?** A dictionary, a keyword scorer, a BM25 index, an
  embedding model, or an LLM?

Pick wrong and your system is slow, brittle, or — the worst outcome — silently
routes work to the wrong agent. I built a lab that measures all of this.

## What I built: a real (tiny) A2A fleet

Four worker agents, each a genuine A2A server (FastAPI + the official `a2a-sdk`)
serving its **Agent Card** at `/.well-known/agent-card.json`. Their "brains"
are deterministic Python handlers, so every result is reproducible and needs
no API keys or cloud.

![The lab: a Master agent with multiple discovery strategies routing to four skill workers via their Agent Cards or a directory.](experiments/architecture.png)

| agent | port | what it's configured for | skills | benchmark tasks |
|---|---|---|---|---|
| summarizer | 8101 | concise summaries & tl;dr | summarize, tldr | t01–t03 |
| translator | 8102 | EN ↔ ES / FR / HI translation | translate, multiling | t04–t06 |
| extractor | 8103 | structured data & PII extraction | extract, pii | t07–t09 |
| classifier | 8104 | sentiment / urgency / labeling | classify, label | t10–t12 |

The fleet is deliberately **ambiguous at the edges** (extractor vs classifier
both touch "entities"; summarizer vs classifier both analyze text), so routing
is a real decision, not a trivial tag lookup. **12 benchmark tasks** drive an
objective accuracy metric: did the Master route to the agent it *should* have?

Every discovery strategy plugs into the same Master, runs the same tasks, and
reports the same metrics — so they're comparable by construction.

---

## The methods: every way I found to route, with pros and cons

I ended up comparing **8 discovery/selection methods**. Here is each one, what
it does, its advantages, and its disadvantages. (Yes, all eight — that's the
only honest way to answer "which should I use?")

### 1. Static mapping

**What it is:** a hardcoded `skill-tag → agent endpoint` map compiled into the
Master. Zero discovery at runtime.

**Advantages:**
- Fastest possible (~0.01 ms), zero network, zero tokens.
- Trivially simple and deterministic — nothing to operate.

**Disadvantages:**
- **Stale by construction** — adding/moving an agent = code change + redeploy.
- No runtime roster, no resilience, can't be shared across teams.
- If a task has no declared tag, it can't route at all.

**Use when:** tiny fixed fleets, demos, pinned endpoints.

### 2. Card discovery

**What it is:** fetch every endpoint's Agent Card once at startup, parse its
skills, build an in-memory `tag → agents` index, then rank candidates per task
by keyword overlap + exact-tag bonus.

**Advantages:**
- **Data-driven** — the Agent Card (authored by the agent itself) is the source
  of truth; no manual syncing.
- Near-zero per-request cost (~0.001 ms); all network paid once at setup.
- Self-healing: re-fetching after a restart picks up changes. No central infra.

**Disadvantages:**
- **Bootstrap problem** — you still need the seed list of endpoint URLs.
- If an endpoint is down *at fetch time*, that agent silently never enters the
  roster (the most dangerous failure we found).
- Keyword-only: paraphrased requests with no vocabulary overlap rank poorly.

**Use when:** small/medium fleets that change, minimum latency + simplicity.

### 3. Registry / directory skill search

**What it is:** agents register their cards in a central Agent Directory; the
Master queries it per request (`GET /agents/search?skill=<tag>`) — mirroring
Google Cloud Agent Registry.

**Advantages:**
- **Central source of truth** with dynamic register/unregister, governance,
  auth, and audit in one place.
- **Scalable search** by skill tag instead of broadcasting to every endpoint.
- Masters only know one URL; agents can change without touching them.

**Disadvantages:**
- **Network latency per lookup** (~21 ms locally — four orders of magnitude
  over an in-memory hit).
- The directory is a **single point of failure** (must be HA).
- Needs a registration pipeline; stale entries if agents don't unregister.

**Use when:** large/dynamic multi-team fleets that need governance.

### 4. Cached discovery

**What it is:** card/registry discovery behind a TTL cache (30 s here); expired
entries re-fetched lazily, everything else served from memory.

**Advantages:**
- **Registry/card benefits at in-memory speed** (~0.03 ms vs ~21 ms) — the
  whole point of caching. Reduces load on the directory.
- 36/36 cache hits in our run, 100% accuracy.

**Disadvantages:**
- **Staleness window** — the cache keeps serving an old endpoint until the TTL
  fires, even if the agent moved or died.
- Cache invalidation adds complexity; still can't detect a "vanished" agent.

**Use when:** latency-sensitive production, hot paths, high QPS.

### 5. BM25 (sparse lexical retrieval — from the research)

**What it is:** tokenize every card (name + description + skills) into a
document and rank tasks with **Okapi BM25** (k1=1.5, b=0.75) — the classic
sparse-retrieval baseline from the tool-retrieval literature.

**Advantages:**
- Best-in-class *lexical* accuracy: 92% well-tagged, 75% noisy in our tests.
- Pure Python, no model, ~0.2 ms selection, deterministic and explainable.

**Disadvantages:**
- **Vocabulary-bound** — a paraphrased request that shares no words with the
  card collapses (33% on our paraphrased set).

**Use when:** tag-rich / keyword-heavy tasks, or as one leg of a hybrid.

### 6. Semantic (dense embeddings — from the research)

**What it is:** embed every card once at startup (fastembed, all-MiniLM-L6-v2,
offline); per task, embed the request and pick the highest cosine similarity —
the vector-retrieval approach of the MCP semantic-tool-discovery paper.

**Advantages:**
- **Understands paraphrase** — 75% on our paraphrased set vs 33% for every
  lexical method. No tag vocabulary to maintain; generalizes to unseen wording.

**Disadvantages:**
- **Slowest selection** (~30–66 ms local, an embedding per request).
- Weakest on keyword-rich and noisy tasks (75% / 58%) — it ignores the
  exact-tag signal lexical methods exploit.
- Adds an embedding-model dependency.

**Use when:** paraphrased requests, sparse metadata, semantic generalization.

### 7. Hybrid (BM25 + semantic with Reciprocal Rank Fusion — from the research)

**What it is:** runs BM25 *and* the dense embedder, then fuses both ranked
lists with **Reciprocal Rank Fusion** (k=60) — the hybrid-retrieval recipe from
Tool-to-Agent Retrieval / Agent-as-a-Graph.

**Advantages:**
- **The only method ≥75% accuracy in every regime we tested** — the robust
  default. Combines exact-keyword strength with paraphrase robustness.
- Deterministic; no training, no LLM, no tokens.

**Disadvantages:**
- Most expensive of the non-LLM methods (~40–76 ms per selection).
- Two moving parts to tune (BM25 params, fusion k, weights).

**Use when:** you don't fully control the workload — i.e., most real systems.

### 8. LLM-reasoned routing

**What it is:** hand every card's name + description + skill tags to a free LLM
(Ollama / any OpenAI-compatible endpoint) and let it pick. Falls back to a
deterministic scorer when no LLM is reachable.

**Advantages:**
- **Deep semantic understanding** — handles paraphrase, ambiguity, and
  multi-intent tasks that tag-based scoring simply can't.
- No tag vocabulary or scoring to maintain.

**Disadvantages:**
- **Token cost** (~2,266 tokens per 12-task run) plus selection latency.
- **Nondeterministic** — can hallucinate an agent name that isn't in the
  roster.
- Overkill on a small, well-tagged fleet.

**Use when:** deeply fuzzy tasks, sparse/noisy tags, open-ended routing.

---

## What I did: the experiments

I ran **two layers of experiments**. First, the classic ladder — one question
per experiment. Then the thing that changed my mind: a **use-case matrix** that
scores every method against three different kinds of workload.

### The experiment ladder (ex1 → ex6)

| experiment | what it tested | what we measured |
|---|---|---|
| ex1 static | compile-time map | 100% accuracy, ~0.01 ms discovery |
| ex2 card_discovery | fetch cards at startup | 100%, ~0 ms per request |
| ex3 registry_skill | per-request directory lookup | 100%, but **~21 ms discovery** |
| ex4 cached | TTL cache, 2 passes | 100%, ~0.03 ms, 36/36 hits |
| ex5a agent down | route to a dead agent | 0% accuracy, 2.1 s, 3 fallbacks |
| ex5b agent vanished | dead agent never discovered | **0% accuracy, 0 errors** — silent misroute |
| ex5c agent recovered | restart self-heals | back to 100% |
| ex6 llm_reasoned | free LLM picks | 100%, **2,266 tokens** |

![Routing accuracy per experiment: 100% everywhere except the two failure scenarios.](experiments/accuracy.png)

![Latency per experiment: dominated by the registry's per-request lookup and the 2.1 s dead-agent route.](experiments/latency.png)

![Token usage: only the LLM strategy spends any.](experiments/tokens.png)

Two results stopped me in my tracks:

1. **A directory costs ~21 ms per lookup locally** — for a question the Master
   could answer in memory. That's why *caching* the directory is the single
   highest-impact optimization.
2. **The scariest failure is silent.** If an agent is down *when you
   discover*, it simply never enters the roster — and the Master routes to the
   wrong agent with **no error, no fallback, no log**. None of the 8 methods
   detects this on its own. You need liveness/roster-completeness monitoring on
   top of whichever method you pick.

### The use-case matrix (the experiment that changed my mind)

"All methods hit 100% accuracy" is a property of the benchmark, not the
methods. So I built three **task sets** — `well_tagged` (tags match the text),
`paraphrased` (same intent, reworded with no shared vocabulary and no usable
tag), and `noisy` (compound requests with wrong-agent keywords as distractors)
— and ran every method on all three.

![Accuracy by use case: keyword methods win when tags match the text; semantic and hybrid win when the request is paraphrased; hybrid is the only method that stays at or above 75% everywhere.](experiments/accuracy_by_usecase.png)

| task set | static | card | bm25 | semantic | hybrid |
|---|---|---|---|---|---|
| **well_tagged** | **100%** | **100%** | 92% | 75% | 83% |
| **paraphrased** | 33% | 33% | 33% | **75%** | **83%** |
| **noisy** | 58% | 58% | **75%** | 58% | **75%** |

The three takeaways:

1. **When tags match the text, lexical wins.** BM25 and card discovery are the
   cheapest accurate methods on well-tagged tasks — and embeddings are the
   *weakest* (75%) *and* the slowest (+30–66 ms). Don't pay for semantics when
   your tasks are keyword-y.
2. **When requests are paraphrased, semantics win.** All three lexical methods
   collapse to 33% (random, with 4 agents); semantic hits 75%, hybrid 83%. This
   is exactly where embedding latency — and, on harder problems, LLM tokens —
   is justified.
3. **When tasks are noisy, hybrid is king.** Dense-only drops to 58% because a
   wrong-agent keyword pulls the vector toward the wrong card; BM25 and hybrid
   hold 75%. **Hybrid is the only method ≥75% in every regime.**

This mirrors what the research literature reports: hybrid lexical+dense
retrieval with rank fusion beats either alone, and — in the LLM-routing world —
**no single router dominates**. The best method depends on your workload.

---

## The cheat sheet: which scenario → which method

Here's the practical answer to the original question — "how do I route
efficiently?" — as a decision table:

| your situation | use this method | because |
|---|---|---|
| tiny fixed fleet, endpoints known forever | **static** (or card discovery) | zero machinery, 0.01 ms |
| small/medium fleet that changes; want latency + simplicity | **card_discovery** | one fetch per agent at startup, ~0 ms per request |
| tag-rich / exact-keyword tasks | **bm25 or card_discovery** | cheapest accurate when tags match text |
| paraphrased requests, sparse/noisy tags | **semantic** | understands intent, not just vocabulary |
| noisy / unknown workload | **hybrid** (BM25 + semantic) | the only method ≥75% everywhere |
| large/dynamic fleet; governance + search | **registry_skill** | central source of truth, scalable skill search |
| fast + governed (production scale) | **registry_skill + cache** | registry's governance at in-memory speed |
| deeply fuzzy/ambiguous tasks | **llm_reasoned** | deep semantics — but pay tokens |
| production, always | any + **failure fallback + liveness monitoring** | no method detects a vanished agent |

**The two-minute version:**

- Small fleet, clean tags → **card discovery** (add a cache if hot).
- Real-world, messy requests → **hybrid (BM25 + semantic)** — the robust
  default.
- Big, governed fleet → **registry + cache**.
- Deeply fuzzy routing → **LLM**, and only then.

And whatever you choose: add a **skill-aware fallback** (fall back to the next
agent that actually fits the task, not "next in the list") and **monitor roster
completeness** — the silent-misroute finding is worth more than any latency
difference between methods.

---

## If you want to try it

The whole lab is open source and runs offline on a laptop — no cloud, no API
keys:

```
git clone https://github.com/Pratyush-Mohanty/adk-a2a-discovery-lab
pip install -r requirements.txt
py -m discovery_lab.run        # full ladder + use-case matrix + charts
```

You get all the numbers above regenerated in seconds, plus the charts. If
you're building a multi-agent system, spend an afternoon on your discovery
layer — it is the cheapest place to buy speed, resilience, and governance, and
(as the vanished-agent scenario shows) the most dangerous place to ignore.

---

*Built with Google ADK + the A2A protocol (a2a-sdk 1.1.2). Full methodology,
measurements, and the experiment ladder live in the repo docs — the report,
the decision guide, and the notebook.*