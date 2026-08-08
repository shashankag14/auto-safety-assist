# Why Split a Pipeline Into Multiple Services?

**Short answer:** a single script that does everything works fine. Splitting only pays off once you care about things a laptop script doesn't: uptime, cost, and shipping changes safely.

## It's not about correctness

A single Python script could do ingestion → embedding → intent classification → retrieval → LLM call, all in one process and it would work correctly. So "why split it up" isn't about fixing something broken, it's about what you're optimizing for once real users and real infrastructure are involved.

A **service** is just one piece of that pipeline pulled out to run on its own, in its own process, talking to the other pieces over the network instead of through a direct function call.

## The four real reasons to split

### 1. Different pieces run on different schedules

**TLDR:** don't force a once-a-day job and an always-on job to share a lifecycle.

Ingestion (pulling new NHTSA data) might run once a day or once a week. Answering a user's question needs to happen in real time, in under a second. Bundled into one script, you can't run one without the other  (e.g., kick off ingestion and you've disturbed the thing answering live queries). Split apart, ingestion runs as a scheduled batch job, and the query-answering service stays up and responsive 24/7, untouched by ingestion runs.

### 2. Different pieces have wildly different resource needs

**TLDR:** don't pay for a GPU everywhere just because one part needs one.

Embedding text and calling an LLM are compute-hungry. Fetching data from an API and inserting rows into Postgres is mostly just waiting on the network. Bundle them together and you're stuck giving lightweight ingestion code the same beefy resources as the heavy embedding/LLM code, or the other way round — you overpay or you bottleneck. Split apart, you scale each piece independently. In Kubernetes terms (Phase 2 of the roadmap): 1 replica of the ingestion job, 5 replicas of the query-answering service, because that's where the real-time load actually is.

### 3. Failure isolation

**TLDR:** one bug shouldn't be able to take down everything.

In a monolith, if the embedding step throws an unhandled exception, it can take intent classification, retrieval, and the LLM call down with it — one bug kills everything. As separate services, if ingestion crashes at 3am, users can still ask questions and get answers from whatever data was already loaded. The blast radius of a bug stays contained to the one service that broke.

### 4. Independent deployability

**TLDR:** change one piece without having to redeploy (and risk breaking) everything else.

Improve the intent classifier next month, and in a monolith, redeploying means redeploying everything — ingestion, retrieval, the LLM layer — even though only one small piece changed. As a separate service, you redeploy just that piece. Less risk, faster iteration, a smaller blast radius if the deploy goes wrong.

## Why this project splits this way

Mapping the four reasons above onto what's actually in this repo:

### Ingestion is a different animal than the query path

[ingestion.py](../src/ingestion/ingestion.py) pulls recalls/complaints from the NHTSA API and writes them to `data/` — it's a batch job you run occasionally (cron, manual trigger), not something a user is ever waiting on. [classifier.py](../src/services/intent_classifier/classifier.py), [retriever.py](../src/services/retriever/retriever.py), and [generator.py](../src/services/response_generator/generator.py) are the opposite: they exist to answer a live user question in under a second. Bundled into one process, a slow/failing NHTSA pull would sit in the same lifecycle as the thing answering questions — this is reason #1 (different schedules), concretely.

### The retriever is the odd one out on resources

`retriever.py` is the only one of the three query services holding real local state: an embedding model loaded into memory ([retriever.py:26](../src/services/retriever/retriever.py#L26)) and a Postgres/pgvector connection ([retriever.py:85](../src/services/retriever/retriever.py#L85)). `classifier.py` and `generator.py` hold neither — they're thin wrappers around an OpenAI client call. That's reason #2: if this were one process, you'd be sizing the whole thing for the retriever's memory/DB footprint even though two-thirds of the code is just making an outbound API call.

### A downed dependency stays contained to one service

Because they're split, an outage in one dependency doesn't take down the others: if Postgres is unreachable, `/retrieve` fails but `/classify` and `/generate` keep responding; if OpenAI is rate-limited or down, `/classify` and `/generate` fail but `/retrieve` still works. This is exactly why each service got its own `/healthz` — the health check is what lets you *see* that isolation (which specific service lost its dependency) instead of just seeing "the assistant is broken."

### Each piece changes for a different reason, at a different pace

The classifier's prompt/instructions, the retriever's SQL/embedding logic, and the generator's context-building are each going to get iterated on independently as the project matures (e.g. tuning `CLASSIFIER_INSTRUCTIONS` vs. tuning `VECTOR_SEARCH_QUERY`). Reason #4 means shipping a better classifier prompt doesn't require redeploying the retriever's DB-facing code, and vice versa.

### The cost is real here too

The classify → retrieve → generate flow (as wired up for the eventual orchestrator) is a **chain** of three network calls per user question, not one function call. That's the concrete version of "every call is now a network call" below — and part of why each service having its own health check matters: a chain is only as reliable as its weakest link, so you need visibility into each link separately, not just the chain as a whole.

## What it costs you

- **Every call is now a network call.** A function call that used to take microseconds now involves serialization + a network round trip. It's slower, and it can fail in new ways a function call never could (the other service is down, slow, or unreachable).
- **More moving parts to run and watch.** Instead of one process to start and one log to read, you now have several and each needs its own health check, its own logs, its own deploy.
- **Debugging spans machines instead of a stack trace.** Tracing a bug across three services is harder than stepping through one script (this is exactly what Phase 5's tracing work is for).

