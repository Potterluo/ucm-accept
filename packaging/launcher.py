"""PyInstaller / 安装包统一入口。"""

from __future__ import annotations

import multiprocessing
import sys

from ucm_accept.cli import main


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
