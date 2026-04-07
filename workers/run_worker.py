"""Run worker: picks tasks from Redis queue and executes them.

Each task is processed through the full run lifecycle via RunEngine.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import redis.asyncio as aioredis

from foundry.contracts.task_types import TaskRequest
from foundry.orchestration.run_engine import RunEngine

logger = logging.getLogger(__name__)

QUEUE_KEY = "foundry:runs"


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
        self._redis: aioredis.Redis | None = None

    async def start(self) -> None:
        """Connect to Redis and enter the consume loop.

        Blocks until :meth:`shutdown` is called. Each message is
        passed to :meth:`process_task` for execution.
        """
        self._redis = aioredis.from_url(self.redis_url, decode_responses=True)
        self._running = True
        logger.info("RunWorker started, listening on queue: %s", QUEUE_KEY)

        try:
            while self._running:
                result = await self._redis.brpop(QUEUE_KEY, timeout=5)
                if result is None:
                    continue

                _key, raw_payload = result
                try:
                    task_data = json.loads(raw_payload)
                    await self.process_task(task_data)
                except Exception:
                    logger.exception("Failed to process task payload")
        finally:
            if self._redis:
                await self._redis.aclose()
            logger.info("RunWorker stopped")

    async def process_task(self, task_data: dict[str, Any]) -> None:
        """Deserialise a task payload and execute the run.

        Args:
            task_data: Raw dict from the Redis queue, representing
                a serialised TaskRequest.
        """
        # Extract internal metadata before validation
        run_id = task_data.pop("_run_id", None)

        task_request = TaskRequest.model_validate(task_data)
        logger.info(
            "Processing task: %s — %s (run_id=%s)",
            task_request.task_type,
            task_request.title,
            run_id,
        )

        try:
            response = await self.engine.execute_run(task_request)
            logger.info(
                "Run completed: %s — state=%s",
                response.id,
                response.state,
            )
        except Exception:
            logger.exception("Run execution failed for task: %s", task_request.title)

    async def shutdown(self) -> None:
        """Signal the worker to stop consuming and exit gracefully."""
        logger.info("RunWorker shutting down")
        self._running = False
