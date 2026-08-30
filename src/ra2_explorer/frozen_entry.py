from __future__ import annotations

import sys
from pathlib import Path

from ra2_explorer.cli import main as cli_main
from ra2_explorer.launcher import main as launcher_main


def main() -> int:
    executable_name = Path(sys.executable).stem.casefold()
    if executable_name == "ra2exp" or len(sys.argv) > 1:
        return cli_main()
    return launcher_main()


if __name__ == "__main__":
    raise SystemExit(main())
