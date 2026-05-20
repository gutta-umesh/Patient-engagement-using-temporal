"""
Reusable Temporal client factory.
All services use this to connect to the Temporal server.
"""

from temporalio.client import Client
from shared.constants import TEMPORAL_HOST


async def get_temporal_client() -> Client:
    """Create and return an async Temporal client."""
    return await Client.connect(TEMPORAL_HOST)
