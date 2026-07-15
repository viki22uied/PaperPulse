"""Paper sources.

Importing this package registers the built-in adapters. Access them by name
through :func:`get_source` / :func:`available`.
"""

from .base import Query, Source, available, get_source, register

# Import for side effects: each module registers its adapter.
from . import arxiv  # noqa: F401,E402
from . import biorxiv  # noqa: F401,E402
from . import pubmed  # noqa: F401,E402
from . import ssrn  # noqa: F401,E402

__all__ = ["Query", "Source", "available", "get_source", "register"]
