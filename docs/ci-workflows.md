# CI workflows

The repo has two GitHub Actions workflows with different jobs and costs:

| Workflow | Runs when | Cost | Purpose |
|---|---|---|---|
| [`ci.yml`](../.github/workflows/ci.yml) | Every push and pull request | Free | Lint, test, and build the service images |
| [`eval.yml`](../.github/workflows/eval.yml) | PRs into `main` that touch answer-affecting code, manual runs, monthly | Paid (OpenAI) | Block changes that make answers worse |

## Overview

```mermaid
%%{init: {"theme":"base","themeVariables":{"fontFamily":"Inter, Segoe UI, Helvetica, Arial, sans-serif","fontSize":"15px","lineColor":"#64748b","primaryTextColor":"#0f172a","edgeLabelBackground":"#ffffff","clusterBkg":"#f8fafc","clusterBorder":"#cbd5e1"},"flowchart":{"curve":"basis","nodeSpacing":40,"rankSpacing":60,"padding":16}}}%%
flowchart LR
    subgraph triggers["Triggers"]
        push(["Push<br/>any branch"]):::trigger
        pr(["Pull request<br/>any branch"]):::trigger
        prmain(["PR into main<br/>answer-affecting paths"]):::trigger
        manual(["Manual run"]):::trigger
        cron(["Monthly<br/>1st, 06:00 UTC"]):::trigger
    end

    subgraph ci["ci.yml · free, every change"]
        lint["Lint + test<br/>ruff & pytest"]:::job
        build["Build images ×4<br/>classifier · retriever · generator · ingestion"]:::job
    end

    subgraph eval["eval.yml · paid, selective"]
        gate["RAGAS regression gate"]:::job
    end

    ecr[("AWS ECR<br/>image registry")]:::store
    verdict{"Pass / Fail<br/>on the PR"}:::decision
    report[/"Job summary<br/>+ artifacts"/]:::output

    push --> lint
    pr --> lint
    lint -- "only if green" --> build
    build -- "push on main only<br/>(OIDC → IAM role)" --> ecr

    prmain --> gate
    manual --> gate
    cron --> gate
    gate --> verdict
    gate --> report

    classDef trigger fill:#ede9fe,stroke:#7c3aed,stroke-width:1.5px,color:#4c1d95
    classDef job fill:#dbeafe,stroke:#2563eb,stroke-width:1.5px,color:#1e3a8a
    classDef store fill:#dcfce7,stroke:#16a34a,stroke-width:1.5px,color:#14532d
    classDef decision fill:#fef3c7,stroke:#d97706,stroke-width:1.5px,color:#78350f
    classDef output fill:#f1f5f9,stroke:#64748b,stroke-width:1.5px,color:#334155
```

- **`ci.yml`** runs on every change because it's fast and free. Images are built on every run (to catch broken Dockerfiles) but only pushed to ECR from `main`, tagged with the commit SHA. CI logs in to AWS with GitHub OIDC, using a role that only `main` can assume and that can push images but not delete them.
- **`eval.yml`** calls OpenAI, so it only runs when answer quality can change: PRs into `main` that touch the retriever, generator, shared config, ingestion, evals or dependencies. The monthly run catches model drift, where a model changes behind an unchanged name.

## Eval regression gate

```mermaid
%%{init: {"theme":"base","themeVariables":{"fontFamily":"Inter, Segoe UI, Helvetica, Arial, sans-serif","fontSize":"15px","lineColor":"#64748b","primaryTextColor":"#0f172a","edgeLabelBackground":"#ffffff","clusterBkg":"#f8fafc","clusterBorder":"#cbd5e1"},"flowchart":{"curve":"basis","nodeSpacing":40,"rankSpacing":55,"padding":16}}}%%
flowchart LR
    fixture[/"Pinned data snapshot<br/>S3 · ID pinned in manifest.json"/]:::input

    subgraph prepare["Prepare · no API cost"]
        direction TB
        setup["① Checkout + install<br/>uv sync --frozen"]:::step
        stage["② Stage data<br/>AWS login via OIDC · download from S3<br/>verify snapshot ID"]:::step
        index["③ Build index<br/>embed → pgvector service"]:::step
        retr["④ Start retriever<br/>wait for /healthz"]:::step
        setup --> stage --> index --> retr
    end

    subgraph evaluate["Evaluate · OpenAI calls"]
        direction TB
        gen["⑤ Generate samples<br/>18 questions → retrieve → answer"]:::paid
        score["⑥ Score samples<br/>5 RAGAS metrics · no cache"]:::paid
        gen --> score
    end

    baseline[/"Baseline<br/>evals/baseline.json"/]:::input
    check{"⑦ Within tolerance<br/>of baseline?"}:::decision
    pass(["Gate passes"]):::pass
    fail(["Gate fails the PR"]):::fail
    report[/"Job summary + artifacts<br/>always uploaded"/]:::output

    fixture -.-> prepare
    prepare --> evaluate
    evaluate --> check
    baseline -.-> check
    check -- yes --> pass
    check -- no --> fail
    check -.-> report

    classDef step fill:#dbeafe,stroke:#2563eb,stroke-width:1.5px,color:#1e3a8a
    classDef paid fill:#fef3c7,stroke:#d97706,stroke-width:1.5px,color:#78350f
    classDef input fill:#ede9fe,stroke:#7c3aed,stroke-width:1.5px,color:#4c1d95
    classDef decision fill:#fff7ed,stroke:#ea580c,stroke-width:1.5px,color:#7c2d12
    classDef output fill:#f1f5f9,stroke:#64748b,stroke-width:1.5px,color:#334155
    classDef pass fill:#dcfce7,stroke:#16a34a,stroke-width:2px,color:#14532d
    classDef fail fill:#fee2e2,stroke:#dc2626,stroke-width:2px,color:#7f1d1d
```

**Prepare** builds a throwaway copy of the system inside the runner. Postgres runs as a service container that only lives for this job. The data comes from the pinned snapshot, never the live NHTSA API, and the job stops if its ID doesn't match the manifest.

The snapshot files live in S3, one folder per snapshot ID. The job logs in to AWS with GitHub OIDC: GitHub issues a short-lived token, and AWS swaps it for temporary credentials for a role that only this repo can assume and that can only read the snapshot folder. No AWS keys are stored in GitHub. The role ARN and bucket name are repository variables (`AWS_EVAL_ROLE_ARN`, `EVAL_SNAPSHOT_BUCKET`). The IAM policies are in [`infra/aws/iam/`](../infra/aws/iam/), and the steps for publishing a new snapshot are in [evals/README.md](../evals/README.md#refreshing-the-snapshot).

**Evaluate** generates fresh answers for the 18 retrieval questions in the golden dataset and scores them with RAGAS. The judge cache is off, because the baseline's tolerances were measured without it.

**The gate** (`compare_ragas check`) fails the job when:

| Check | Why |
|---|---|
| A gated metric drops more than its tolerance below the baseline | A real quality regression |
| Any judge call failed | The mean is computed on fewer samples and can't be trusted |
| The judge model, embedding model, metric mode or RAGAS version differs from the baseline | Scores from a different measuring setup aren't comparable |
| The data snapshot differs from the baseline | The golden labels may no longer match the data; rebuild the baseline instead |

Faithfulness, factual correctness, context precision and context recall are gated. Answer relevancy is reported but never fails the gate, because it moves with answer style rather than quality.

The job summary and the samples/scores artifacts are uploaded even when the gate fails, since that's when they're needed.
