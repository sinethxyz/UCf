"""Run worker: picks tasks from Redis queue and executes them.

Each task is processed through the full run lifecycle via RunEngine.
"""

from __future__ import annotations

import logging
from typing import Any

from foundry.contracts.task_types import TaskRequest
from foundry.orchestration.run_engine import RunEngine

logger = logging.getLogger(__name__)


class RunWorker:
    """Consumes run tasks from Redis queue and executes them via RunEngine.

    The worker connects to the configured Redis instance, listens on the
    run task queue, deserialises incoming payloads into TaskRequest objects,
    and delegates execution to RunEngine.execute_run().
    """

    def __init__(self, redis_url: str, engine: RunEngine) -> None:
        self.redis_url = redis_url
        self.engine = engine
        self._running = False

    async def start(self) -> None:
        """Connect to Redis and enter the consume loop.

        Blocks until :meth:`shutdown` is called. Each message is
        passed to :meth:`process_task` for execution.
        """
        raise NotImplementedError("Run worker not yet implemented")

    async def process_task(self, task_data: dict[str, Any]) -> None:
        """Deserialise a task payload and execute the run.

        Args:
            task_data: Raw dict from the Redis queue, representing
                a serialised TaskRequest.
        """
        task_request = TaskRequest.model_validate(task_data)
        logger.info("Processing task: %s — %s", task_request.task_type, task_request.title)
        raise NotImplementedError("Task processing not yet implemented")

    async def shutdown(self) -> None:
        """Signal the worker to stop consuming and exit gracefully."""
        logger.info("RunWorker shutting down")
        self._running = False
