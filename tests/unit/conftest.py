"""Put src/shared/ and src/inbound/ on sys.path so tests can `import` layer modules."""

import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
for sub in ("src/shared", "src/inbound"):
    path = os.path.join(_REPO, sub)
    if path not in sys.path:
        sys.path.insert(0, path)
