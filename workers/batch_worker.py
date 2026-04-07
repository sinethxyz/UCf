"""Batch worker: manages batch API job polling and result collection."""

from __future__ import annotations

import logging
from uuid import UUID

logger = logging.getLogger(__name__)


class BatchWorker:
    """Polls Anthropic Batch API for completion and processes results.

    Periodically checks all in-progress batch jobs. When a batch completes,
    validates the results against canon schemas and stores artifacts.
    """

    def __init__(self, redis_url: str, anthropic_api_key: str) -> None:
        self.redis_url = redis_url
        self.anthropic_api_key = anthropic_api_key
        self._running = False

    async def start(self) -> None:
        """Begin the polling loop for pending batch jobs.

        Blocks until :meth:`shutdown` is called.
        """
        raise NotImplementedError("Batch worker not yet implemented")

    async def poll_pending_batches(self) -> None:
        """Check all in-progress batches for completion.

        Queries the database for batch jobs in 'processing' state and
        checks their status via the Anthropic Batch API.
        """
        raise NotImplementedError("Batch polling not yet implemented")

    async def process_completed_batch(self, batch_id: UUID) -> None:
        """Process a completed batch: validate results and store artifacts.

        Args:
            batch_id: ID of the completed batch job.
        """
        raise NotImplementedError("Batch result processing not yet implemented")

    async def shutdown(self) -> None:
        """Signal the worker to stop polling and exit gracefully."""
        logger.info("BatchWorker shutting down")
        self._running = False
