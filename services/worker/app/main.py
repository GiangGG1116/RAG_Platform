"""
Worker Service - Async RabbitMQ Consumer.

Consumes messages from RabbitMQ queues and processes them:
- Embedding generation for document chunks
- Other async tasks
"""
import asyncio
import logging
import signal
import sys

from shared.cache import close_cache, get_cache
from shared.database import dispose_engine
from shared.messaging import RabbitMQConsumer, QUEUE_EMBEDDING_GENERATE, ROUTING_KEY_EMBEDDING
from shared.observability import setup_observability

from app.consumers.embedding_consumer import handle_embedding_message

logger = logging.getLogger(__name__)

# Graceful shutdown flag
_shutdown_event = asyncio.Event()


def _signal_handler() -> None:
    """Handle shutdown signals."""
    logger.info("Received shutdown signal")
    _shutdown_event.set()


async def _heartbeat_loop() -> None:
    """Touch a heartbeat file periodically to indicate the worker is alive."""
    import os
    heartbeat_path = "/tmp/worker_heartbeat"
    while not _shutdown_event.is_set():
        try:
            with open(heartbeat_path, "w") as f:
                f.write(str(asyncio.get_running_loop().time()))
        except Exception:
            logger.exception("Failed to write worker heartbeat")
        await asyncio.sleep(15)


async def main() -> None:
    """Start the worker service."""
    setup_observability("worker-service")
    logger.info("Worker service starting up...")

    # Initialize connections
    await get_cache()
    logger.info("Redis cache connected")

    # Create consumers
    embedding_consumer = RabbitMQConsumer(
        queue_name=QUEUE_EMBEDDING_GENERATE,
        routing_key=ROUTING_KEY_EMBEDDING,
        handler=handle_embedding_message,
        prefetch_count=5,
    )

    # Register signal handlers
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal_handler)

    # Start heartbeat task
    heartbeat_task = asyncio.create_task(_heartbeat_loop())

    # Start consumers
    logger.info("Starting embedding consumer...")
    consumer_task = asyncio.create_task(embedding_consumer.start())

    # Wait for shutdown signal
    await _shutdown_event.wait()

    # Graceful shutdown
    logger.info("Shutting down worker service...")
    heartbeat_task.cancel()
    await embedding_consumer.stop()
    consumer_task.cancel()

    await close_cache()
    await dispose_engine()
    logger.info("Worker service shut down.")


if __name__ == "__main__":
    asyncio.run(main())
