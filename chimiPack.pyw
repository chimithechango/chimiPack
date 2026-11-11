"""Double-click this file to start chimiPack (needs Python 3.9+, no extra packages)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from chimipack.server import main  # noqa: E402

if __name__ == "__main__":
    main()
