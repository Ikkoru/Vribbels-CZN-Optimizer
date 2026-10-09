"""
Application version information.

This module provides the single source of truth for the current application version.
"""

__version__ = "v2.4.0 (forked from v1.7.0)"

# The day this version was released (UTC), and the Galactic Disaster
# season live on it. Set by the release step. The Checklist's season
# estimate reads them to judge how far to trust the Chaos figures it
# shipped with: `chaos_estimate.staleness`.
RELEASED_ON = "2026-10-09"
RELEASED_IN = "disaster_s05"
