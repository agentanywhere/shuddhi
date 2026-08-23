import os
import sys

# Put the repository root on the path so `pytest` works straight from a
# clone, with nothing installed. An installed copy takes precedence, which
# is what you want when testing a release.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
