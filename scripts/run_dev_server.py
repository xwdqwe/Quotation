from __future__ import annotations

import sys
import traceback
from pathlib import Path

import uvicorn


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
LOG_DIR = ROOT / ".codex-run"
LOG_DIR.mkdir(exist_ok=True)
LOG_PATH = LOG_DIR / "uvicorn-wrapper.log"


def main() -> None:
    with LOG_PATH.open("a", encoding="utf-8", buffering=1) as log:
        sys.stdout = log
        sys.stderr = log
        print("starting uvicorn on http://127.0.0.1:8000", flush=True)
        try:
            uvicorn.run("app.main:app", host="127.0.0.1", port=8000, log_level="info")
        except Exception:
            traceback.print_exc()
            raise


if __name__ == "__main__":
    main()
