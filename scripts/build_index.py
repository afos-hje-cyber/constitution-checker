"""Build step 2: chunk the articles and embed them (one index per strategy).

Run:  .venv\\Scripts\\python scripts\\build_index.py                 (all strategies)
      .venv\\Scripts\\python scripts\\build_index.py --strategy hybrid

The code lives in src/ingest/build_index.py; this file only runs it.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ingest.build_index import main  # noqa: E402

if __name__ == "__main__":
    main()
