#!/usr/bin/env python3
"""CLI 兼容 wrapper：直接运行 `python build_knowledge_base.py` 相当于 `biokb`。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from biokb.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
