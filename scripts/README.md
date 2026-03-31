# Scripts

## Feature tests

- **`seed_test_products.py`** — Adds two sample rows (Black T-Shirt, Denim Jeans) to the DB from `.env`; skips names that already exist.
- **`read_local_db_catalog.py`** — Prints the live catalog for your configured `DATABASE_URL`.
- **`database_read_write_test.py`** — Verifies SQLAlchemy models, `add_product`, and `memory_service` last-five ordering using a temporary SQLite file.
- **`agentTest.py`** — Interactive REPL: you type what you want; the customer agent uses tools (e.g. `get_products`) against your `.env` database; messages are saved for multi-turn memory. Needs `GOOGLE_API_KEY`.
- **`agent_test.py`** — Calls `run_turn` once against Gemini; requires `GOOGLE_API_KEY`. Exits with skip message if the key is missing.

Run from the **repository root**:

`python scripts/<script_name>.py`

## `_w.py` … `_w10.py` (scaffold generators)

These files were used to materialize the initial codebase. Each script writes specific paths under `app/` and `main.py`. They now resolve the repo root with `Path(__file__).resolve().parents[1]`, so they can be run from any cwd:

`python scripts/_w.py` (and so on).

**Warning:** Running them again **overwrites** the embedded file contents with the snapshot inside each script. Prefer editing the real modules under `app/` directly unless you intentionally want to reset those files to the generator version.
