"""Build step 1: parse the Constitution PDF into data/processed/articles.json.

Run:  .venv\\Scripts\\python scripts\\parse_constitution.py

The code lives in src/ingest/parse_constitution.py; this file only runs it.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ingest.parse_constitution import main  # noqa: E402

if __name__ == "__main__":
    main()
