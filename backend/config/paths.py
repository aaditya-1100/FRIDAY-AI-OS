"""
config/paths.py — Centralised data-directory resolution for FRIDAY.

All persistent data (SQLite DBs, Qdrant store, screenshots, project files)
is rooted under a single DATA_DIR.  Set the FRIDAY_DATA_DIR environment
variable to override the default (backend/data/).

Per-user isolation: point each user's .env at a different FRIDAY_DATA_DIR
(e.g. backend/data/alice, backend/data/bob).  No auth required; the
separation is purely filesystem-level.
"""
import os

# ── Root data directory ───────────────────────────────────────────────────────
# Reads FRIDAY_DATA_DIR from env.  Default: <backend>/data/
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_data_dir() -> str:
    """Return the absolute root data directory, creating it if absent."""
    configured = os.environ.get("FRIDAY_DATA_DIR", "")
    if configured:
        path = os.path.abspath(configured)
    else:
        path = os.path.join(_BACKEND_DIR, "data")
    os.makedirs(path, exist_ok=True)
    return path


def get_data_path(*parts: str) -> str:
    """Return an absolute path rooted inside the data directory.

    Examples
    --------
    get_data_path("episodic.db")
        → <DATA_DIR>/episodic.db
    get_data_path("projects", "project_registry.json")
        → <DATA_DIR>/projects/project_registry.json
    """
    return os.path.join(get_data_dir(), *parts)


def ensure_data_dirs() -> None:
    """Create the standard subdirectory layout on first run.

    Called by the server lifespan so no manual mkdir is required after
    a fresh clone.
    """
    data_dir = get_data_dir()
    subdirs = ["qdrant", "screenshots", "projects"]
    first_run = False
    for sub in subdirs:
        full = os.path.join(data_dir, sub)
        if not os.path.exists(full):
            os.makedirs(full, exist_ok=True)
            first_run = True
    if first_run:
        print(f"[STARTUP] First run: data directory initialised at {data_dir}")
    else:
        print(f"[STARTUP] Data directory confirmed at {data_dir}")
