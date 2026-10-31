"""Offline evaluation: `python services/ai/evaluate.py --redteam --n 200 --seed 42`.

A thin entry point; everything lives in `campuspulse_ai.frameworks.cli.evaluate`.
"""

from campuspulse_ai.frameworks.cli.evaluate import main

if __name__ == "__main__":
    raise SystemExit(main())
