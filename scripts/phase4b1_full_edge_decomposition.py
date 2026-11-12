from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from options_structure_trader.phase4b1 import Phase4B1EdgeDecomposer  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build Phase 4B.1 research-only edge decomposition artifacts."
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    result = Phase4B1EdgeDecomposer(args.root).run()
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
