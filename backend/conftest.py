import sys
import os
import tempfile
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

if "PYTEST_CURRENT_TEST" in os.environ or any("pytest" in arg for arg in sys.argv):
    os.environ.setdefault(
        "FRIDAY_QDRANT_PATH",
        os.path.join(tempfile.gettempdir(), f"friday_qdrant_pytest_{os.getpid()}"),
    )
    os.environ.setdefault("FRIDAY_FORCE_HASH_EMBEDDINGS", "1")
