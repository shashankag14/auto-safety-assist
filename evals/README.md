# Evaluations

The evals in this folder score each pipeline stage against the hand-labeled examples in `golden_dataset.json`.

| Script | Stage | Needs |
|---|---|---|
| `eval_intent_classifier.py` | Intent classifier | `OPENAI_API_KEY` |
| `eval_retriever.py` | Retriever | Postgres and the retriever service running |

## Golden dataset

Every example has the fields all evals use, plus fields for specific stages:

```json
{
  "id": "GD-001",
  "query": "...",
  "intent": "recall_lookup",
  "relevant": [
    { "source": "recall", "key": "18V652000", "grade": 2 }
  ]
}
```

- `intent` is the gold label for the intent classifier: `recall_lookup`, `complaint_search` or `general_question`.
- `relevant` is the gold label for the retriever. See [Retriever](#retriever).

# Intent classifier

`eval_intent_classifier.py` sends every query in `golden_dataset.json` to the classifier and compares the predicted intent with the gold `intent` label.

```bash
uv run python -m evals.eval_intent_classifier
```

The script doesn't need a running service. It calls the classifier's FastAPI app in-process through `TestClient`, so the request goes through the same validation and `/classify` endpoint as in production. It calls the real OpenAI model, so `OPENAI_API_KEY` must be set (it is loaded from `.env`), and each run costs a little money. Set `OPENAI_MODEL` to evaluate a different model.

Unlike the retriever eval, this eval uses every example, including general questions.

## Metrics

| Metric | Question it answers | How it's computed |
|---|---|---|
| Accuracy | How many queries got the right intent? | correct predictions / all queries |
| Precision (per intent) | When we predict this intent, how often are we right? | TP / (TP + FP) |
| Recall (per intent) | Of the queries with this intent, how many did we catch? | TP / (TP + FN) |
| F1 (per intent) | One number that balances precision and recall | 2 · P · R / (P + R) |
| Support | How many gold examples does this intent have? | TP + FN |


### Why per-intent metrics matter

Accuracy alone hides which intents are being confused. The dataset is small and a bit imbalanced (9 recall, 9 complaint, 6 general), so one wrong prediction moves the metrics a lot: about 4 points of accuracy, and more for per-intent recall on `general_question`.

The costs of the errors are also different. In `src/pipeline.py`, a `general_question` prediction skips retrieval and is answered by the response generator's `/answer` endpoint, which uses general knowledge only:

- Predicting `general_question` for a recall or complaint query is the worst mistake: the user gets a generic answer that tells them no records were found, even though the database may have them.
- Predicting `recall_lookup` or `complaint_search` for a general question runs retrieval for nothing. That is wasteful but mostly harmless: if nothing matches, the pipeline falls back to `/answer`, and if something does, the generator is told to say when the context doesn't answer the question.
- Mixing up `recall_lookup` and `complaint_search` doesn't change anything yet, because the retriever doesn't use the intent. It will matter once retrieval is routed by intent.

### Unparsed intents

If the model's output can't be parsed (for example, it refuses or the output is cut off), the classifier returns `"intent": null` instead of guessing. The pipeline then runs RAG anyway, because a wasted retrieval costs less than answering a recall question without data.

The eval reports these as `unparsed`: they get their own count and confusion-matrix column, count as wrong for accuracy, and lower the recall of the gold intent. They don't count as a false positive for any intent, so they can't hide inside another intent's precision.

## Reading the report

```
Accuracy: 22/24 (91.7%)
Unparsed: 0/24

intent               precision    recall        f1   support
recall_lookup             1.00      0.89      0.94         9
complaint_search          0.90      1.00      0.95         9
general_question          0.83      0.83      0.83         6

Confusion matrix (rows = gold, cols = predicted):
                           recall_lookup    complaint_search    general_question            unparsed
recall_lookup                          8                   0                   1                   0
complaint_search                       0                   9                   0                   0
general_question                       0                   1                   5                   0

Mispredictions (2):
  [GD-007] gold=recall_lookup pred=general_question | ...
  [GD-019] gold=general_question pred=complaint_search | ...
```

The numbers above are only an example of the format.

- **Rows are gold, columns are predicted.** Read along a row to see where queries of one intent went. Read down a column to see what was predicted as that intent.
- **Start debugging with the mispredictions list.** Often the query is genuinely ambiguous. If so, change the label or the classifier instructions (`CLASSIFIER_INSTRUCTIONS` in `src/common/config.py`), not the model.
- **Run it more than once before comparing changes.** The model isn't fully deterministic, so a single prediction can flip between runs. With 24 examples, a difference of one or two queries may just be noise.
- An OpenAI error stops the run. The script raises on the first failed request and doesn't skip it.

# Retriever

`eval_retriever.py` sends every query in `golden_dataset.json` to the running retriever and scores the ranked results against hand-labeled relevant documents.

```bash
docker-compose up -d postgres retriever
uv run python -m evals.eval_retriever
```

## Golden labels

Each example lists the NHTSA documents that should come back for its query:

```json
{
  "query": "...",
  "relevant": [
    { "source": "recall", "key": "18V652000", "grade": 2 }
  ]
}
```

- `key` is the NHTSA natural key: the campaign number for recalls, the ODI number for complaints.
- `grade` is how relevant the document is. Recalls are graded 2 and complaints 1. Only NDCG uses the grade.
- Examples with an empty `relevant` list (general questions) are skipped.

The retriever returns Postgres row ids. Before scoring, the script maps them to NHTSA keys so they can be compared with the golden labels.

## Chunks vs. documents

Each recall is stored as three chunks: summary, remedy and consequence. All three have the same campaign number, so one recall can fill up to three of the top-k slots.

The golden labels are per document, not per chunk, so the metrics are computed per document too:

- **Precision** counts each document once. Repeated chunks are dropped, keeping the highest-ranked one.
- **MRR and NDCG** use the original chunk ranks, because that's the order the LLM sees. NDCG gives credit for a document only at its first occurrence.

## Metrics

| Metric | Question it answers | How it's computed |
|---|---|---|
| Precision@k | How much of what we returned is relevant? | relevant docs returned / unique docs returned |
| Recall@k | Did we find everything we needed? | relevant docs returned / relevant docs in golden set |
| MRR | How high is the first relevant result? | 1 / rank of the first relevant chunk, averaged over queries |
| NDCG@k | Is the whole ranking in a good order? | graded gain discounted by log2(rank + 1), divided by the score of a perfect ranking |
| Unique docs@k | How many of the k slots hold distinct documents? | unique docs / chunks returned |

### Precision ceiling

Most queries in the dataset have one relevant document. With k=5, the best possible precision for such a query is about 0.2. Even a perfect retriever would have non-relevant documents in the other four slots.

The report prints the ceiling next to precision:

```
Mean Precision@k: 0.21  (ceiling 0.25)
```

Compare precision with the ceiling, not with 1.0. Until the dataset has more queries with several relevant documents, use Recall, MRR and NDCG to compare retriever changes.

### Unique docs@k

A low value here means repeated chunks of the same recall are crowding other documents out of the top-k. Watch it when changing the chunking strategy or `top_k`.

## Reading the report

```
Evaluated 18 queries (top_k=5)

Mean Precision@k: 0.21
Mean Recall@k:    0.86
MRR:              0.71
Mean NDCG@k:      0.74
Mean unique docs@k: 4.6 / 5.0
```

- **Recall** matters most for RAG: the generator can't cite a document it never received.
- **MRR / NDCG** show whether relevant documents are near the top, which matters if `top_k` is reduced or a reranker is added.
- Queries with recall below 1.0 are listed after the summary with their golden, returned and deduplicated results. Start debugging with those.
