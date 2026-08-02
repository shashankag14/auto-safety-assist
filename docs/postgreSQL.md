# PostgreSQL — A Practical Tutorial

A from-scratch guide to installing, setting up, and using PostgreSQL — written for people with **little to no SQL experience**. It walks through installing Postgres, connecting to it, and the core commands you'll use day to day, with runnable examples.

> Reference video used while compiling these notes: https://www.youtube.com/watch?v=zw4s3Ey8ayo

---

## Table of Contents

1. [What is PostgreSQL?](#what-is-postgresql)
2. [Installing PostgreSQL](#installing-postgresql)
3. [VS Code Extensions for a Quick DB View](#vs-code-extensions-for-a-quick-db-view)
4. [Setting Up & Connecting to the Server](#setting-up--connecting-to-the-server)
5. [psql Cheat Sheet (Meta-commands)](#psql-cheat-sheet-meta-commands)
6. [Core Concepts & Datatypes](#core-concepts--datatypes)
7. [Creating Tables](#creating-tables)
8. [CRUD Commands](#crud-commands)
9. [Upserts (Insert or Update in One Statement)](#upserts-insert-or-update-in-one-statement)
10. [System Catalogs (Introspecting Your Own Schema)](#system-catalogs-introspecting-your-own-schema)
11. [Anonymous Code Blocks (DO Blocks)](#anonymous-code-blocks-do-blocks)
12. [Relationships & JOINs](#relationships--joins)
13. [Quick Command Reference](#quick-command-reference)
14. [Gotchas & Tips](#gotchas--tips)

---

## What is PostgreSQL?

PostgreSQL ("Postgres") is a free, open-source **relational database**. Data is stored in **tables** (rows and columns), and tables can be linked to each other using **relationships** (e.g. a user has many posts). You interact with it using **SQL** (Structured Query Language).

---

## Installing PostgreSQL

### Windows
1. Download the installer from the official site: https://www.postgresql.org/download/windows/
2. Run the installer (via EnterpriseDB). It will ask you to:
   - Choose an install directory (defaults are fine).
   - Select components — keep **PostgreSQL Server**, **pgAdmin 4**, **Command Line Tools**, and **Stack Builder** checked.
   - Set a **password for the `postgres` superuser** — remember this, you'll need it every time you connect.
   - Set the **port** (default `5432` — keep it unless it conflicts with something).
3. Finish the install. This also installs `psql` (the command-line client) and adds it to your PATH (a restart of your terminal may be needed).

### macOS
```bash
brew install postgresql@16
brew services start postgresql@16
```

### Linux (Debian/Ubuntu)
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
```

### Verify the install
```bash
psql --version
```

---

## VS Code Extensions for a Quick DB View

You don't need to leave your editor to browse tables, run queries, and inspect data:

| Extension | Publisher | What it's for |
|---|---|---|
| **PostgreSQL** | Chris Kolkman | Lightweight explorer — connect to a server, browse databases/tables/columns in a tree view, run `.sql` files against the connection. |
| **SQLTools** + **SQLTools PostgreSQL/Redshift Driver** | Matheus Teixeira | Full-featured DB client inside VS Code: connection manager, results grid, query history, autocomplete. Most popular combo for this. |
| **vscode-database-client** ("Database Client") | Weijan Chen | GUI-style client with a UI similar to DBeaver — good if you want table editing without SQL. |

**Recommended setup:** install **SQLTools** + the **PostgreSQL driver** for SQLTools. Then:
1. Open the SQLTools sidebar icon.
2. Click **Add New Connection** → choose **PostgreSQL**.
3. Fill in `host: localhost`, `port: 5432`, `database`, `username: postgres`, `password: <what you set at install>`.
4. Test the connection, save it, and you can now open any `.sql` file and run it directly against your DB (select the query → run, or use the "Run on Connection" button).

You can also use **pgAdmin 4** (installed alongside Postgres on Windows) as a standalone GUI if you prefer a full desktop app over the VS Code extension.

---

## Setting Up & Connecting to the Server

Once Postgres is installed and running as a service, connect to it from a terminal:

```bash
psql -U postgres
```
- `-U postgres` → connect as the `postgres` username.
- You'll be prompted for the password you set during install.

Once connected, you're in the `psql` shell (prompt looks like `postgres=#`). From here you can create a database and switch to it:

```sql
CREATE DATABASE demo;
```
```
\c demo
```
- `\c demo` → **c**onnects you to the `demo` database (prompt changes to `demo=#`).

---

## psql Cheat Sheet (Meta-commands)

These start with `\` and are psql-specific (not SQL) — they help you navigate without writing queries:

| Command | What it does |
|---|---|
| `\l` | List all databases |
| `\c <dbname>` | Connect to a database |
| `\dt` | List all tables in the current database |
| `\d <table>` | Describe a table (columns, types, constraints) |
| `\du` | List all users/roles |
| `\q` | Quit psql |
| `\?` | Help — list all meta-commands |
| `\x` | Toggle "expanded display" — useful for wide rows |

---

## Core Concepts & Datatypes

| Concept | Meaning |
|---|---|
| **Database** | A container for tables (e.g. `demo`). |
| **Table** | Rows + columns, e.g. a `user` table. |
| **Row / Record** | A single entry in a table. |
| **Column / Field** | A single attribute of a row (e.g. `name`, `age`). |
| **Primary Key** | A column (or set of columns) that **uniquely identifies** each row. |
| **Foreign Key** | A column that references another table's primary key, forming a relationship. |

Common datatypes you'll reach for:

| Type | Use it for |
|---|---|
| `SERIAL` | Auto-incrementing integer — great for `id` columns; the DB manages the counter for you. |
| `INT` | Whole numbers (e.g. `age`). |
| `VARCHAR(n)` | Text with a max length of `n` characters (e.g. `VARCHAR(255)` for an email). |
| `TEXT` | Text with **no length limit** — better for things like hashed passwords or long content. |
| `BOOLEAN` | `true` / `false`. |
| `DATE` / `TIMESTAMP` | Dates, or dates with time. |

---

## Creating Tables

A `user` table (note: `user` is a **reserved SQL keyword**, so it must be wrapped in double quotes any time you reference it):

```sql
CREATE TABLE "user"(
    id SERIAL PRIMARY KEY,      -- auto-incrementing unique ID, managed by the DB
    name VARCHAR(100),          -- short text, capped at 100 chars
    email VARCHAR(255),
    password TEXT,              -- hashed passwords can be long, so TEXT not VARCHAR
    age INT
);
```

A `social_media_post` table that belongs to a `user` (a **one-to-many** relationship — one user, many posts):

```sql
CREATE TABLE IF NOT EXISTS social_media_post(
    id SERIAL PRIMARY KEY,
    name VARCHAR(255),
    content TEXT,
    user_id INT,
    CONSTRAINT fk_user
        FOREIGN KEY(user_id)
            REFERENCES "user"(id)
);
```
- `IF NOT EXISTS` → skips creation instead of erroring if the table already exists.
- `FOREIGN KEY(user_id) REFERENCES "user"(id)` → every `user_id` in this table must match a real `id` in `"user"`. This is what links the two tables.

---

## CRUD Commands

CRUD = **C**reate, **R**ead, **U**pdate, **D**elete — the four basic operations on data.

### Create — `INSERT`
```sql
-- Column order can be whatever you like, as long as VALUES follows the same order
INSERT INTO "user" (name, email, age, password) VALUES (
    'troy', 'troy@fake.email', 34, 'dwebdubefu'
);
```

### Read — `SELECT`
```sql
SELECT * FROM "user";                          -- all columns, all rows
SELECT * FROM "user" WHERE age < 30;           -- filter rows
SELECT * FROM "user" WHERE name = 'troy';      -- exact match
SELECT age FROM "user" WHERE name != 'troy';   -- only one column, and NOT equal to
```

| Operator | Meaning |
|---|---|
| `=` | equal to |
| `!=` or `<>` | not equal to |
| `<`, `>`, `<=`, `>=` | less/greater than (or equal) |
| `AND`, `OR` | combine conditions |
| `LIKE '%troy%'` | pattern match (case-sensitive) |
| `ILIKE '%troy%'` | pattern match (case-**insensitive**) |

### Update — `UPDATE`
```sql
UPDATE "user" SET age = 30 WHERE name = 'troy';
```
Here `=` plays two different roles in the same line:
- `SET age = 30` → **assign** the value 30 to `age`.
- `WHERE name = 'troy'` → **compare** — only update rows where this is true.

⚠️ Always include a `WHERE` clause with `UPDATE`/`DELETE` — without one, **every row** in the table is affected.

### Delete — `DELETE`
```sql
DELETE FROM "user" WHERE name = 'troy';
```

### Clearing an entire table — `DELETE` vs `TRUNCATE`
```sql
DELETE FROM "user";              -- removes rows one at a time, logged, triggers fire, slower on big tables
TRUNCATE "user";                 -- deallocates all storage at once, much faster
TRUNCATE "user" RESTART IDENTITY; -- also resets any SERIAL/identity column back to its start (this is the default)
TRUNCATE "user" CONTINUE IDENTITY; -- keeps the SERIAL counter where it was
```
⚠️ **`TRUNCATE` only clears data — it does not touch the table's schema.** If you're expecting a table to be "reset to brand new" so a `CREATE TABLE IF NOT EXISTS` will rebuild it with new columns, `TRUNCATE` won't do that — the table still exists (just empty), so `IF NOT EXISTS` still skips it. Use `DROP TABLE` if you actually want the schema rebuilt from scratch.

---

## Upserts (Insert or Update in One Statement)

An **upsert** = insert a row, unless one matching some key already exists, in which case update it instead. Postgres does this with `INSERT ... ON CONFLICT ... DO UPDATE`:

```sql
INSERT INTO "user" (email, name, age)
VALUES ('troy@fake.email', 'troy', 34)
ON CONFLICT (email)
DO UPDATE SET
    name = EXCLUDED.name,
    age = EXCLUDED.age;
```

- `ON CONFLICT (email)` — tells Postgres which columns to treat as "this row already exists." This only works if those columns are covered by a `UNIQUE` (or `PRIMARY KEY`) constraint — `ON CONFLICT` is matching against a real constraint/index, not just any column you name.
- If no existing row conflicts, the `INSERT` proceeds normally.
- If a row *does* conflict, Postgres runs `DO UPDATE SET ...` against the **existing** row instead of raising a duplicate-key error.
- `EXCLUDED` is a special pseudo-table available only inside `ON CONFLICT` — it holds the row you *tried* to insert. `name = EXCLUDED.name` means "overwrite the stored name with the new incoming one."

A composite key (matching on more than one column) works the same way — useful when uniqueness only makes sense as a *pair* of columns:

```sql
-- e.g. one external "campaign" can have several rows (one per chunk_source),
-- so the pair (campaign_number, chunk_source) is what's actually unique, not either column alone
ALTER TABLE recall_chunks
    ADD CONSTRAINT recall_chunks_campaign_source_key
    UNIQUE (campaign_number, chunk_source);

INSERT INTO recall_chunks (campaign_number, chunk_source, chunk_text)
VALUES ('24V123', 'summary', 'Some updated summary text')
ON CONFLICT (campaign_number, chunk_source)
DO UPDATE SET chunk_text = EXCLUDED.chunk_text;
```

---

## System Catalogs (Introspecting Your Own Schema)

Postgres tracks its own structure — every table, column, and constraint you create — in a set of built-in tables called **system catalogs**. You can `SELECT` from them exactly like your own data:

| Catalog | What it lists |
|---|---|
| `pg_class` | Every table (and index, sequence, view) |
| `pg_attribute` | Every column on every table |
| `pg_constraint` | Every constraint (primary key, unique, foreign key, check) on every table |

Example — list every constraint on one table, with a readable definition:

```sql
SELECT conname, contype, pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'recall_chunks'::regclass;
```

- `conname` — the constraint's name (auto-generated like `recall_chunks_pkey`, or whatever you named it explicitly).
- `contype` — a one-letter code: `p` = primary key, `u` = unique, `f` = foreign key, `c` = check, `n` = not-null.
- `conrelid` is stored as a raw internal object ID — casting `::regclass` converts it back to the readable table name.
- `pg_get_constraintdef(oid)` renders the constraint back into SQL text (e.g. `UNIQUE (campaign_number, chunk_source)`), which is much easier to read than decoding the raw column-position arrays these catalogs store internally.

This is the mechanism behind `\d <table>` in psql — it's just running catalog queries like this one for you and formatting the output.

---

## Anonymous Code Blocks (DO Blocks)

Plain SQL statements are declarative — one instruction each, no `if`/`then` logic. To run actual conditional logic as part of a script (e.g. "add this constraint only if it doesn't already exist"), you need Postgres's procedural language, `plpgsql`, wrapped in a `DO` block:

```sql
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'recall_chunks_campaign_source_key'
    ) THEN
        ALTER TABLE recall_chunks
            ADD CONSTRAINT recall_chunks_campaign_source_key
            UNIQUE (campaign_number, chunk_source);
    END IF;
END $$;
```

- `DO` — "run the following as a one-off procedural script" (as opposed to a normal declarative statement).
- `$$ ... $$` — **dollar quoting**. The block's body is really one big string literal handed to the `plpgsql` interpreter; `$$` lets that string contain its own quotes and semicolons without needing to escape anything (the alternative — wrapping it in `'...'` — would require escaping every internal `'`).
- `BEGIN ... END` — `plpgsql` requires procedural code to be grouped inside a `BEGIN`/`END` block, the same way `{ }` groups a block of statements in C-like languages. This is what allows `IF ... THEN ... END IF;` to exist at all — plain SQL has no `IF` statement.
- It's called **anonymous** because, unlike a real `CREATE FUNCTION`, nothing is saved — it runs once immediately and is discarded.

This pattern is the fix for a common gotcha (see [Gotchas & Tips](#gotchas--tips)): `ADD CONSTRAINT` has no built-in `IF NOT EXISTS` shorthand, so wrapping it in a `pg_constraint` existence check is how you make adding a constraint idempotent (safe to re-run).

---

## Relationships & JOINs

Three kinds of relationships between tables:

| Relationship | Example |
|---|---|
| **One-to-Many** | One user → many social media posts |
| **Many-to-One** | Many posts → one user (same relationship, other direction) |
| **Many-to-Many** | Many students ↔ many courses (needs a "join table" in between) |

To pull data from both related tables at once, use `JOIN`:

```sql
SELECT * FROM "user" JOIN social_media_post ON social_media_post.user_id = "user".id;
```

Result — notice the columns from **both** tables appear, and `id` is duplicated (once per table) since both have a column called `id`:

| id | name  | email | password | age | id | name | content | user_id |
|----|-------|-------|----------|-----|----|------|---------|---------|
| 2 | kylie | kylie@fake.email | dsdfwdfw | 25 | 1 | why i love postgres | its easy to learn | 2 |
| 2 | kylie | kylie@fake.email | dsdfwdfw | 25 | 2 | Why i like dogs so much | i just love them | 2 |

Clean this up by picking specific columns and using `AS` to rename (alias) ambiguous ones:

```sql
SELECT "user".*, social_media_post.content, social_media_post.id AS post_id,
       social_media_post.name AS title, social_media_post.user_id
FROM "user"
JOIN social_media_post ON social_media_post.user_id = "user".id;
```

| id | name  | email | password | age | content | post_id | title | user_id |
|----|-------|-------|----------|-----|---------|---------|-------|---------|
| 2 | kylie | kylie@fake.email | dsdfwdfw | 25 | its easy to learn | 1 | why i love postgres | 2 |
| 2 | kylie | kylie@fake.email | dsdfwdfw | 25 | i just love them | 2 | Why i like dogs so much | 2 |

---

## Quick Command Reference

| Task | SQL |
|---|---|
| Create a database | `CREATE DATABASE demo;` |
| Create a table | `CREATE TABLE "user" (id SERIAL PRIMARY KEY, name VARCHAR(100));` |
| Add a row | `INSERT INTO "user" (name) VALUES ('troy');` |
| Read all rows | `SELECT * FROM "user";` |
| Read with a filter | `SELECT * FROM "user" WHERE age < 30;` |
| Update a row | `UPDATE "user" SET age = 30 WHERE name = 'troy';` |
| Delete a row | `DELETE FROM "user" WHERE name = 'troy';` |
| Clear all rows (keep schema) | `TRUNCATE "user" RESTART IDENTITY;` |
| Insert-or-update (upsert) | `INSERT INTO ... VALUES (...) ON CONFLICT (col) DO UPDATE SET x = EXCLUDED.x;` |
| Add a column if missing | `ALTER TABLE t ADD COLUMN IF NOT EXISTS c TEXT;` |
| Join two tables | `SELECT * FROM a JOIN b ON b.a_id = a.id;` |
| Drop a table | `DROP TABLE "user";` |
| Drop a database | `DROP DATABASE demo;` |

---

## Gotchas & Tips

1. **Casing doesn't matter to SQL** — `SELECT`, `select`, and `Select` all work. The convention is `UPPERCASE` for keywords (`SELECT`, `WHERE`, `INSERT`) and `snake_case`/lowercase for your own table and column names.
2. **`=` means different things depending on context.** In `UPDATE ... SET age = 55 WHERE id = 1`, the first `=` **assigns** a value, the second **compares** for equality.
3. **Reserved words need quoting.** `user` is a reserved keyword in Postgres — if you name a table `user`, you must always wrap it in double quotes: `"user"`. Avoiding reserved words as table names (e.g. `app_user`) sidesteps this entirely.
4. **`VARCHAR(n)` vs `TEXT`** — `VARCHAR(n)` caps the string length at `n` characters (max 255 as a soft convention, though Postgres allows more). Use `TEXT` for unbounded content like hashed passwords or post bodies.
5. **`SERIAL` for IDs** — let the database auto-generate primary keys instead of assigning them yourself; this avoids collisions and manual bookkeeping.
6. **Always scope `UPDATE`/`DELETE` with `WHERE`** unless you genuinely mean to touch every row.
7. **`CREATE TABLE IF NOT EXISTS` only guards *creation*, not *evolution*.** If the table already exists, the whole statement is a no-op — adding a new column to that `CREATE TABLE` block later has zero effect on a database where the table was already created. New columns/constraints on an existing table need an explicit `ALTER TABLE`.
8. **`TRUNCATE` doesn't reset a table back to "doesn't exist."** It only empties rows; the schema (columns, constraints) is untouched. If you truncated a table hoping `CREATE TABLE IF NOT EXISTS` would then rebuild it with a new column, it won't — the table still exists, just empty. Use `DROP TABLE` if you want a full rebuild from schema.
9. **`ADD COLUMN` supports `IF NOT EXISTS`, but `ADD CONSTRAINT` does not.** `ALTER TABLE t ADD COLUMN IF NOT EXISTS c TEXT;` is safe to re-run directly. Adding a constraint idempotently needs the `DO $$ ... pg_constraint check ... $$` pattern from [Anonymous Code Blocks](#anonymous-code-blocks-do-blocks) instead.
