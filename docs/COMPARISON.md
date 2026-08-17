# Agent Discovery Methods — When to Use Which + Pros & Cons

A quick-reference decision guide built from the measured results of the ADK/A2A
Discovery Lab (`docs/REPORT.md` for the full analysis). All numbers below are
real measurements from the reference run (localhost, a2a-sdk 1.1.2).

---

## 1. The five methods at a glance

| method | how it finds agents | measured discovery cost | tokens | best for |
|---|---|---|---|---|
| **static** | compile-time map in the Master | ~0.01 ms | 0 | tiny, fixed fleets |
| **card_discovery** | fetch each endpoint's Agent Card at startup, index skills | ~0.001 ms/request (paid once at setup) | 0 | small/medium fleets that change |
| **registry_skill** | query a central Agent Directory by skill tag | **~20.7 ms/request** (network round trip) | 0 | large/dynamic fleets, governance |
| **cached** | card/registry answers behind a TTL cache | ~0.03 ms/request | 0 | latency-sensitive production |
| **llm_reasoned** | an LLM reads the cards and decides | ~0.37 ms + **2,266 tokens**/run | yes | fuzzy/ambiguous tasks |

---

## 2. Decision guide — which case → which method

| # | your situation | method to use | why |
|---|---|---|---|
| 1 | Tiny fixed fleet, endpoints known forever, want zero machinery | **static** | nothing to run, nothing to go stale by accident, 0.01 ms |
| 2 | Small/medium fleet that changes occasionally; want minimum latency + simplicity | **card_discovery** | cards are the source of truth, one fetch per agent at startup, ~0 ms per request |
| 3 | Large / multi-team fleet; agents join & leave; need governance, auth, search | **registry_skill** | central catalog you can filter by skill tags; Masters only know one URL |
| 4 | Same as #3 but you care about per-request latency / load on the directory | **cached** (registry-backed) | keeps the registry as source of truth, adds in-memory speed |
| 5 | Tasks are fuzzy, tags are sparse/noisy, need semantic understanding | **llm_reasoned** | an LLM can understand paraphrases and weigh descriptions, not just tags |
| 6 | Everything reliability-critical | any + **failure fallback + liveness monitoring** | no method detects a "vanished" agent (see §4) |

**If you remember one line:** small + simple → **card_discovery**;
big + governed → **registry + cache**; fuzzy → **LLM**; and never ship any of
them without a failure fallback.

---

## 3. Each method in detail — advantages & disadvantages

### 3.1 static

**How it works:** the Master ships with a hardcoded map `skill-tag → agent endpoint`.

**Advantages**
- Fastest possible: ~0.01 ms, zero network, zero tokens.
- Trivially simple and deterministic — nothing to operate.
- No registry, no cache, no model, no failure modes of its own.

**Disadvantages**
- **Stale by construction**: adding/removing an agent or moving a port = code change + redeploy.
- No discovery at runtime — the Master only knows what it compiled in.
- Cannot be shared across teams; no central governance or search.
- No resilience: if the endpoint dies, routing just fails.

**Use when:** tiny fixed fleets, demos, pinned internal endpoints.
**Avoid when:** anything that changes, scales, or involves more than one team.

---

### 3.2 card_discovery

**How it works:** at startup the Master fetches `/.well-known/agent-card.json`
from every known endpoint, builds an in-memory `tag → agents` index, then ranks
candidates per task (keyword overlap + exact-tag bonus).

**Advantages**
- **Data-driven**: the Agent Card (authored by the agent itself) is the source of truth — no manual syncing.
- Near-zero per-request cost (~0.001 ms): all network paid once at setup.
- Self-healing: re-fetching cards after a restart picks up changes.
- No central infrastructure; works offline and locally (as in this lab).

**Disadvantages**
- **Bootstrap problem**: you still need a seed list of endpoint URLs.
- Startup cost grows linearly with fleet size (N card fetches).
- No central search or governance — every Master re-discovers everything.
- If an endpoint is down *when you fetch*, that agent silently never enters the
  roster (the "vanished" failure — the most dangerous one we found).
- The a2a client re-resolves the card on every `send_message` (~30–75 ms, 2 s
  when the endpoint is dead).

**Use when:** small/medium, changing fleets; simplicity + latency matter more than scale.
**Avoid when:** very large fleets, or you need governed/shared discovery.

---

### 3.3 registry_skill (Agent Directory)

**How it works:** agents register their cards in a central directory; the Master
queries it per request (`GET /agents/search?skill=<tag>`), mirroring Google
Cloud Agent Registry's skill filters.

**Advantages**
- **Central source of truth** with dynamic register/unregister.
- Governance, authentication, and validation in one place.
- **Scalable search**: filter by skill tags instead of broadcasting to every endpoint.
- Masters only need the directory URL — agents can change without touching them.
- Realistic production pattern (GCP Agent Registry does exactly this).

**Disadvantages**
- **Network latency per lookup** (~20.7 ms here — four orders of magnitude over an in-memory hit).
- The directory is a **single point of failure** (must be HA).
- Needs a registration pipeline; stale entries if agents don't unregister.
- Extra infrastructure to build and operate.

**Use when:** large/dynamic fleets, multi-team, governance/audit requirements.
**Avoid when:** tiny fleets or ultra-low-latency hot paths — you're paying a
network round trip to answer a question the Master could answer in memory.

---

### 3.4 cached (TTL-cached discovery)

**How it works:** wraps card/registry discovery with a TTL cache (30 s here);
expired entries are re-fetched lazily, everything else is served from memory.

**Advantages**
- **Registry/card benefits at in-memory speed**: ~0.03 ms vs ~21 ms — the whole
  point of caching.
- Reduces load on the directory / endpoints (fewer fetches).
- Simple TTL knob to trade freshness for speed.
- In our run: 36/36 cache hits, 100% accuracy.

**Disadvantages**
- **Staleness window**: the cache serves an old endpoint until the TTL fires —
  routing to a moved/dead agent in between.
- Cache invalidation adds complexity (TTLs, expiries, poison entries).
- Still cannot detect a "vanished" agent — a dead agent is simply never cached.
- Consistency questions: who clears the cache when a card changes?

**Use when:** latency-sensitive production, high request volume, hot paths —
especially on top of a registry.
**Avoid when:** lookups are rare and every answer must be perfectly fresh
(correctness-critical, low QPS).

---

### 3.5 llm_reasoned (LLM selection)

**How it works:** gathers the same discovered cards, then asks a free LLM
(Ollama / any OpenAI-compatible endpoint) to pick the best agent for the task;
token usage is recorded. Falls back to a deterministic scorer when no LLM is
reachable.

**Advantages**
- **Semantic understanding**: handles paraphrase, fuzzy or sparse tags, and can
  weigh a card's description/examples — not just keywords.
- No manual tag maintenance or scoring-tuning.
- Generalizes to new/unseen task phrasing without reindexing.

**Disadvantages**
- **Token cost**: ≈2,266 tokens for the 12-task run (and latency ~0.37 ms selection on top).
- **Nondeterministic**: quality depends on the model + prompt; can return a name
  that isn't in the roster.
- Needs a model endpoint (or a mock fallback, which defeats the purpose).
- Overkill when the fleet is small and well-tagged (deterministic scoring wins).

**Use when:** tasks are fuzzy, tags are sparse/noisy, or you want to handle
open-ended routing without maintaining a tag vocabulary.
**Avoid when:** tight cost/latency budgets, deterministic guarantees required,
or a clean, well-tagged fleet.

---

## 4. The failure caveat that applies to ALL methods

Our experiments found the most dangerous failure mode is **not** a slow lookup —
it is a **silent misroute**:

- **agent down (card known):** route fails → visible error → fallback engages
  (but may pick the wrong agent). `fallbacks=3`, accuracy 0%, latency 2.1 s.
- **agent vanished (card never fetched):** the agent is simply missing from the
  roster → the Master routes to a wrong agent with **no error, no fallback, no
  log**. `errors=0`, accuracy 0%.

None of the five methods detects a vanished agent on its own. Whatever method
you choose, add **liveness / roster-completeness monitoring** and a
**skill-aware fallback** (fall back to the next agent that actually fits the
task, not just "next in the list").

---

## 5. Rule-of-thumb summary

```
small fixed fleet          -> static
small/medium dynamic fleet -> card_discovery          (simplest real discovery)
large / governed fleet     -> registry_skill           (source of truth + search)
fast + governed            -> registry_skill + cached  (both worlds)
fuzzy / sparse tags        -> llm_reasoned             (semantics, pay tokens)
production                 -> any of the above + fallback + liveness monitoring
```

Full measurements, methodology, and experiment ladder:
[`docs/REPORT.md`](REPORT.md) · notebook: [`docs/NOTES.md`](NOTES.md) ·
mechanism walkthrough: [`docs/GUIDE.md`](GUIDE.md).
