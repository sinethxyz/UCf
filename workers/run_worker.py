"""Run worker: picks tasks from Redis queue and executes them.

Each task is processed through the full run lifecycle via RunEngine.
"""


async def process_run_queue() -> None:
    """Main worker loop: consume tasks from Redis and execute runs."""
    raise NotImplementedError
