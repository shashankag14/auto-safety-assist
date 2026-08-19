# Evaluating Retrievers: Precision, Recall, MRR, and NDCG

## 0. The setup

Every one of these metrics answers the same underlying question in a different way:

> "You ran a query through your retriever, pgvector returned a ranked list of chunks (recall notices, complaints). How good was that list?"

To measure "good," you need a **labeled eval set**: a handful of test queries where you (a human) have already decided which documents in your corpus are actually relevant. Without that ground truth, none of these metrics can be computed — this is the unglamorous but necessary first step.

**Example eval query for the Auto Safety Assistant**:

> Query: *"transmission slipping 2018 Honda Accord"*
> Relevant docs (ground truth, you label these by hand):
> - `RECALL-2019-001` (exact recall bulletin) — highly relevant
> - `COMPLAINT-4821` (same symptom, same vehicle) — relevant
> - `COMPLAINT-5103` (same symptom, same vehicle) — relevant
> - Everything else in the corpus — not relevant

Suppose your retriever returns the top 5 results, ranked:

```
Rank 1: COMPLAINT-5103        (relevant)
Rank 2: RECALL-2015-330       (NOT relevant — different vehicle)
Rank 3: RECALL-2019-001       (relevant — the exact bulletin!)
Rank 4: COMPLAINT-4821        (relevant)
Rank 5: COMPLAINT-9902        (NOT relevant — different vehicle)
```

We'll use this exact example for every metric below so you can see how each one scores the *same* ranking differently.

---

## 1. Precision@k

**Question it answers:** *"Of the k documents I retrieved, what fraction were actually relevant?"*

```
Precision@k = (relevant docs in top k) / k
```

**Worked example:**

- Precision@1 = 1/1 = 1.0 (rank 1, COMPLAINT-5103, is relevant)
- Precision@3 = 2/3 = 0.67 (ranks 1 and 3 relevant, rank 2 not)
- Precision@5 = 3/5 = 0.60 (ranks 1, 3, 4 relevant; ranks 2 and 5 not)

**What it's good for:** Telling you how much *noise* the user (or your LLM generator) has to wade through. If Precision@5 is low, your generation layer is being handed a lot of irrelevant context, which risks hallucinated or off-target citations.

**What it misses:** Order. Precision@5 = 0.80 doesn't tell you *whether* the irrelevant doc was at rank 1 (bad — user sees garbage first) or rank 5 (less bad). It also doesn't tell you whether you *missed* other relevant docs sitting further down or outside your corpus retrieval entirely.

---

## 2. Recall@k

**Question it answers:** *"Of all the relevant documents that exist, what fraction did I actually manage to retrieve in my top k?"*

```
Recall@k = (relevant docs in top k) / (total relevant docs in corpus)
```

**Worked example:** We said there are 3 relevant docs total (1 recall + 2 complaints).

- Recall@3 = 2/3 = 0.67 (found 2 of the 3 relevant docs in top 3)
- Recall@5 = 3/3 = 1.00 (found all 3 by rank 5)

**What it's good for:** Catching *missed* relevant documents. This matters a lot for Recall Radar specifically — if there's a genuine recall for someone's exact vehicle and your retriever fails to surface it at all, that's a much worse failure than surfacing it at rank 4 instead of rank 1. Recall tells you about that failure mode; precision doesn't.

**What it misses:** Order, again. Recall@5 = 1.0 whether the 4 relevant docs are at ranks 1-2-3-4 or at ranks 2-3-4-5. It also has a quirk: recall trivially → 1.0 as k → size of corpus, so it's only meaningful relative to a reasonable k (you wouldn't report Recall@1000 for a 10-document context window).

**Precision vs. Recall tension:** These trade off against each other. You can get Recall@20 = 1.0 by just returning more documents, but that tanks precision and floods your LLM context with noise (and cost/latency, since more chunks = more tokens into the generation call). This is the classic tradeoff — which is exactly why people reach for MRR and NDCG to get a single number that accounts for *rank position* rather than picking one k and squinting at both metrics.

---

## 3. MRR (Mean Reciprocal Rank)

**Question it answers:** *"How far down the list did I have to look before I hit the first relevant document?"*

```
RR (single query) = 1 / (rank of first relevant doc)
MRR = average of RR across all your eval queries
```

**Worked example:** First relevant doc is at rank 1 (COMPLAINT-5103).

```
RR = 1/1 = 1.0
```

Contrast: if the ranking had instead been `[RECALL-2015-330, RECALL-2019-001, ...]`, first relevant doc is at rank 2:

```
RR = 1/2 = 0.5
```

Then average RR across, say, 40 test queries to get your MRR.

**What it's good for:** Scenarios where the user just needs *one* good answer, fast, and doesn't care about the rest of the list. "Is there a recall on my car, yes or no, show me the one that matters" is this kind of query.

**What it misses:** Everything after the first hit. MRR = 1.0 for a ranking of `[relevant, garbage, garbage, garbage, garbage]` — identical score to `[relevant, relevant, relevant, relevant, relevant]`. For Recall Radar, that's a real blind spot: your LLM generation step often wants to cite *multiple* supporting complaints alongside the recall bulletin ("12 other owners reported the same issue"), and MRR is blind to whether those extra citations were retrieved well.

---

## 4. NDCG (Normalized Discounted Cumulative Gain)

This one has three ideas stacked on top of each other. Let's build it up piece by piece instead of dropping the formula cold.

### Idea 1: Graded relevance, not binary

Instead of "relevant / not relevant," assign a relevance *grade*, e.g. (a 0-2 scale is enough now that your schema is just recall + complaint):

| Grade | Meaning (Recall Radar) |
|---|---|
| 2 | Exact recall bulletin for this vehicle+issue |
| 1 | Complaint describing the same issue, same vehicle |
| 0 | Irrelevant |

Our ranked list gets graded:

```
Rank 1: COMPLAINT-5103   → grade 1
Rank 2: RECALL-2015-330  → grade 0
Rank 3: RECALL-2019-001  → grade 2
Rank 4: COMPLAINT-4821   → grade 1
Rank 5: COMPLAINT-9902   → grade 0
```

### Idea 2: Discount gains by position (DCG)

A relevant doc at rank 1 is worth more than the same doc at rank 5 — but the penalty shouldn't be as brutal as MRR's "only rank 1 counts." NDCG uses a **logarithmic discount**:

```
DCG@k = Σ (grade_i / log2(i + 1))   for i = 1 to k
```

Computing DCG@5 for our list:

```
Rank 1: 1 / log2(2) = 1 / 1.00  = 1.00
Rank 2: 0 / log2(3) = 0 / 1.58  = 0.00
Rank 3: 2 / log2(4) = 2 / 2.00  = 1.00
Rank 4: 1 / log2(5) = 1 / 2.32  = 0.43
Rank 5: 0 / log2(6) = 0 / 2.58  = 0.00

DCG@5 = 1.00 + 0.00 + 1.00 + 0.43 + 0.00 = 2.43
```

### Idea 3: Normalize against the ideal ranking (this is the "N" in NDCG)

Raw DCG isn't comparable across queries — a query with 5 relevant docs will naturally have higher DCG than one with 1 relevant doc. So you compute the **best possible DCG** (IDCG) by sorting the same graded docs in the *ideal* order (highest grade first) and compute DCG on that:

```
Ideal order: [grade 2, grade 1, grade 1, grade 0, grade 0]

IDCG@5:
Rank 1: 2 / log2(2) = 2.00
Rank 2: 1 / log2(3) = 0.63
Rank 3: 1 / log2(4) = 0.50
Rank 4: 0 / log2(5) = 0.00
Rank 5: 0 / log2(6) = 0.00

IDCG@5 = 2.00 + 0.63 + 0.50 + 0.00 + 0.00 = 3.13
```

Then:

```
NDCG@5 = DCG@5 / IDCG@5 = 2.43 / 3.13 = 0.78
```

**Interpretation:** Your actual ranking captured 78% of the maximum possible ranking quality for this query. Score is bounded [0, 1], comparable across queries with different numbers/grades of relevant docs — this is why it's usable as a single headline metric. Note the "penalty" here: the exact recall bulletin (grade 2) sitting at rank 3 instead of rank 1 costs you meaningfully more than a complaint (grade 1) would, because NDCG weights *how relevant* the misplaced doc was, not just whether it was misplaced.

**What it's good for:** Exactly the failure mode MRR misses — it rewards you for putting *multiple* good documents near the top, and it lets "exact recall bulletin" outweigh "same-issue complaint" instead of treating them as equally relevant.

**What it costs you:** You need graded relevance labels, not just binary yes/no, which is more labeling effort when building your eval set. And log-discount curves and normalization make it less intuitive to eyeball than "3 out of 5 were relevant."

---

## 5. Putting it together for Recall Radar

| Metric | What it tells you | Where it's the right lens |
|---|---|---|
| **Precision@k** | How much noise is in my top k | Sanity-checking retrieval before it hits the LLM context — noisy context risks bad/hallucinated citations |
| **Recall@k** | Did I miss any relevant recall/complaint entirely | Safety-relevant: missing a real recall is a worse failure than ranking it 2nd instead of 1st |
| **MRR** | How fast do I hit the *first* right answer | Debugging "did intent classification + retrieval find the right recall bulletin at all" |
| **NDCG@k** | How good is the *whole* ranked list, weighted by degree of relevance | Headline metric — reflects what your LLM generation layer actually needs: several well-ranked, well-graded supporting docs for citations |

**Practical recommendation for your eval harness:**
1. Build ~30-50 labeled test queries against your NHTSA corpus, with graded relevance (0-2 scale as above: recall bulletin / complaint / irrelevant).
2. Report **NDCG@10** as your primary retrieval-quality number — it's what will move in the direction that actually matters for citation quality.
3. Report **Recall@10** alongside it as a safety-oriented secondary metric — you specifically care about *never* missing the one recall bulletin that matters, even if it's not ranked #1.
4. Keep **MRR** and **Precision@k** as debugging companions when NDCG drops, to figure out *why* (first-hit problem vs. noise problem).
5. Wire this into an offline eval script that runs before you promote a new embedding model, chunking strategy, or reranker — this is a natural fit for whichever MLOps phase covers eval/observability tooling.

---

*Note: the exact formula conventions (e.g., log base 2 in NDCG, whether to use `log2(i+1)` vs `log2(i)+1`) are standard in IR literature but worth double-checking against a reference (e.g., scikit-learn's `ndcg_score` docs or the original Järvelin & Kekäläinen paper) before hardcoding into your eval script — I don't have search enabled in this conversation, so treat specifics as a starting point to verify, not gospel.*