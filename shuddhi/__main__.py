"""Entry point for `python -m shuddhi`.

Kept alongside the console script so the tool runs straight from a clone
with nothing installed — the first thing anyone does with a new repository
is run it, and `pip install` first is a step that loses people.
"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
