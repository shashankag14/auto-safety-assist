# Retriever evaluation

`eval_retriever.py` sends every query in `golden_dataset.json` to the running retriever and scores the ranked results against hand-labeled relevant documents.

```bash
docker-compose up -d postgres retriever
uv run python -m evals.eval_retriever
```

## Golden dataset

Each example is a query plus the NHTSA documents that should come back for it:

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
