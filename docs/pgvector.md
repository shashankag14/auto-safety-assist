# pgvector — Installation & Setup

`pgvector` is a PostgreSQL extension that adds a `vector` data type plus similarity search (L2, cosine, inner product) and approximate-nearest-neighbor indexes (`ivfflat`, `hnsw`). Useful for storing embeddings alongside your regular relational data. See [postgreSQL.md](postgreSQL.md) for general Postgres setup first — pgvector is installed *into* an existing PostgreSQL instance.

> Repo: https://github.com/pgvector/pgvector
> Reference video used to learn pgvector: https://www.youtube.com/watch?v=j1QcPSLj7u0

---

## Table of Contents

1. [Windows — Build from Source](#windows--build-from-source)
2. [macOS](#macos)
3. [Linux (Debian/Ubuntu)](#linux-debianubuntu)
4. [Enabling the Extension](#enabling-the-extension)
5. [Verify](#verify)
6. [Gotchas](#gotchas)

---

## Windows — Build from Source

Windows has no prebuilt installer, so pgvector is compiled from source against your existing PostgreSQL install using MSVC.

### Prerequisites
- PostgreSQL already installed (e.g. `C:\Program Files\PostgreSQL\18`), with `pg_config` on PATH.
- Visual Studio (Community edition is fine) with the **"Desktop development with C++"** workload — this provides `cl.exe`, `nmake.exe`, and `vcvars64.bat`.
- The pgvector source cloned locally, e.g.:
  ```powershell
  git clone https://github.com/pgvector/pgvector.git D:\research\agentic_ai\pgvector
  ```

### Build
Open a regular (non-admin) PowerShell and run:

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\<version>\<edition>\VC\Auxiliary\Build\vcvars64.bat" && set "PGROOT=C:\Program Files\PostgreSQL\<major-version>" && cd /d D:\research\agentic_ai\pgvector && nmake /f Makefile.win'
```

Replace `<version>\<edition>` (e.g. `18\Community`) and `<major-version>` (e.g. `18`) to match your install. This compiles `vector.dll` and the extension SQL files — no elevation needed for this step.

### Install
Copying the built files into `C:\Program Files\PostgreSQL\...` requires an **elevated (Administrator) PowerShell**. Open one and run:

```powershell
cmd /c '"C:\Program Files\Microsoft Visual Studio\<version>\<edition>\VC\Auxiliary\Build\vcvars64.bat" && set "PGROOT=C:\Program Files\PostgreSQL\<major-version>" && cd /d D:\research\agentic_ai\pgvector && nmake /f Makefile.win install'
```

This copies `vector.dll` → `lib`, `vector.control` + SQL files → `share\extension`, and headers → `include\server\extension\vector`.

> ⚠️ **Gotcha:** if you set `PGROOT` inline in a one-liner (`set PGROOT=... && ...`), an unquoted value swallows the trailing space before `&&`, producing a broken path like `...\18 \include`. Always quote it: `set "PGROOT=C:\Program Files\PostgreSQL\18"`.

---

## macOS

```bash
brew install pgvector
```

(Or build from source the same way as Linux below if you need a version not yet on Homebrew.)

---

## Linux (Debian/Ubuntu)

```bash
sudo apt install postgresql-<version>-pgvector
```

Or build from source:

```bash
git clone https://github.com/pgvector/pgvector.git
cd pgvector
make
sudo make install
```

---

## Enabling the Extension

Once installed (any OS), enable it per-database from `psql`:

```sql
CREATE EXTENSION vector;
```

---

## Verify

```sql
\dx
```

You should see `vector` listed alongside `plpgsql` and any other installed extensions, with its version (e.g. `0.8.5`).

---

## Notes

1. **Per-database, not per-cluster.** `CREATE EXTENSION vector;` only enables it in the database you're currently connected to (`\c <dbname>` first if needed) — run it again in every database that needs vector columns.
2. **Windows install needs admin rights.** The build step doesn't, but copying files into `C:\Program Files\PostgreSQL\...` does — use an elevated PowerShell for `nmake ... install` only.
3. **Match PostgreSQL major version.** The extension is built/packaged against a specific PostgreSQL major version — rebuilding or reinstalling is needed after a Postgres major version upgrade.
4. **Vector dimensions are fixed per column** — e.g. `vector(1536)` for OpenAI's `text-embedding-3-small`. Changing embedding models with a different dimension count requires a new column (or table).
5. **`vector` columns work fine inside an upsert.** `INSERT ... ON CONFLICT (...) DO UPDATE SET embedding = EXCLUDED.embedding` needs no special syntax — a vector column is just another column type as far as `ON CONFLICT`/`EXCLUDED` are concerned. See [Upserts](postgreSQL.md#upserts-insert-or-update-in-one-statement) in the Postgres guide.
