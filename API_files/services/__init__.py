from __future__ import annotations

# Expose router_client submodule so consumers can `from api.services import router_client`
from . import router_client

# Search service (safe/lightweight)
from .search import (
    SearchService,
)
from .search import directory_settings as get_directory_settings
from .search import (
    get_search_service,
)
from .search import hybrid as hybrid_search
from .search import index_stats as get_index_stats
from .search import keyword as keyword_search
from .search import vector as vector_search

# NOTE:
# Keep this package lightweight at import time.
# Importing heavy/optional modules (e.g., pseudocode_translator) here breaks route imports
# because `from api.services.router_client import get_router` first executes this __init__.
# Export search-only re-exports and provide access to router_client without importing translator.

# Do NOT import translator module here to avoid optional dependency import at package import time.
# Callers should import api.services.translator directly if needed.

__all__ = [
    # Search
    "SearchService",
    "get_search_service",
    "keyword_search",
    "vector_search",
    "hybrid_search",
    "get_index_stats",
    "get_directory_settings",
    # Submodules
    "router_client",
]
