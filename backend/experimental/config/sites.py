"""
Backward-compatible export of the canonical site registry.

Prefer: from config.site_registry import get_workspace_url, WORKSPACE_SITES
"""

from config.site_registry import WORKSPACE_SITES

SITES = WORKSPACE_SITES
