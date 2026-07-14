"""Delivery channels for a rendered digest.

Every channel takes the digest markdown (and the ranked papers, for richer
formats like RSS) and ships it somewhere: a file, an inbox, a feed, or a chat
webhook. Network channels are configured by environment/argument and fail with a
clear message rather than silently.
"""

from .email import send_email
from .rss import render_rss
from .webhook import send_slack, send_discord

__all__ = ["send_email", "render_rss", "send_slack", "send_discord"]
