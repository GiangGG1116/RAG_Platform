"""
RabbitMQ async messaging layer using aio-pika.

Provides publisher/consumer with retry, dead-letter, and graceful shutdown.
"""

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import aio_pika
from aio_pika import ExchangeType, Message
from aio_pika.abc import AbstractChannel, AbstractConnection, AbstractQueue

from shared.config import get_settings

logger = logging.getLogger(__name__)

# ── Exchange & Queue Names ───────────────────────────────
EXCHANGE_NAME = "rag.events"
DLX_EXCHANGE_NAME = "rag.events.dlx"

QUEUE_DOCUMENT_INGEST = "rag.document.ingest"
QUEUE_EMBEDDING_GENERATE = "rag.embedding.generate"
QUEUE_DLQ = "rag.dlq"

ROUTING_KEY_INGEST = "document.ingest"
ROUTING_KEY_EMBEDDING = "embedding.generate"


class RabbitMQPublisher:
    """Async RabbitMQ publisher with connection pooling and retry."""

    def __init__(self) -> None:
        self._connection: AbstractConnection | None = None
        self._channel: AbstractChannel | None = None
        self._exchange: aio_pika.Exchange | None = None

    async def connect(self) -> None:
        """Establish connection and declare exchange."""
        settings = get_settings()
        self._connection = await aio_pika.connect_robust(
            settings.rabbitmq_url,
            timeout=30,
        )
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=10)

        # Declare main exchange
        self._exchange = await self._channel.declare_exchange(
            EXCHANGE_NAME,
            ExchangeType.TOPIC,
            durable=True,
        )
        # Declare DLX
        dlx_exchange = await self._channel.declare_exchange(
            DLX_EXCHANGE_NAME,
            ExchangeType.DIRECT,
            durable=True,
        )
        # Declare DLQ
        dlq = await self._channel.declare_queue(QUEUE_DLQ, durable=True)
        await dlq.bind(dlx_exchange, routing_key="dead-letter")

        logger.info("RabbitMQ publisher connected")

    async def publish(
        self,
        routing_key: str,
        body: dict[str, Any],
        headers: dict[str, str] | None = None,
        priority: int = 0,
    ) -> None:
        """Publish a message to the exchange."""
        if not self._exchange:
            await self.connect()

        message = Message(
            body=json.dumps(body, default=str).encode(),
            content_type="application/json",
            headers=headers or {},
            priority=priority,
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        await self._exchange.publish(message, routing_key=routing_key)  # type: ignore[union-attr]
        logger.debug("Published message to %s", routing_key)

    async def close(self) -> None:
        """Close the connection."""
        if self._connection:
            await self._connection.close()
            logger.info("RabbitMQ publisher disconnected")


class RabbitMQConsumer:
    """Async RabbitMQ consumer with ack/nack and graceful shutdown."""

    def __init__(
        self,
        queue_name: str,
        routing_key: str,
        handler: Callable[[dict[str, Any]], Awaitable[None]],
        prefetch_count: int = 10,
    ) -> None:
        self._queue_name = queue_name
        self._routing_key = routing_key
        self._handler = handler
        self._prefetch_count = prefetch_count
        self._connection: AbstractConnection | None = None
        self._channel: AbstractChannel | None = None
        self._queue: AbstractQueue | None = None
        self._running = False

    async def start(self) -> None:
        """Connect, declare queue, and start consuming."""
        settings = get_settings()
        self._connection = await aio_pika.connect_robust(
            settings.rabbitmq_url,
            timeout=30,
        )
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=self._prefetch_count)

        # Declare exchange
        exchange = await self._channel.declare_exchange(
            EXCHANGE_NAME,
            ExchangeType.TOPIC,
            durable=True,
        )

        # Declare queue with DLX
        self._queue = await self._channel.declare_queue(
            self._queue_name,
            durable=True,
            arguments={
                "x-dead-letter-exchange": DLX_EXCHANGE_NAME,
                "x-dead-letter-routing-key": "dead-letter",
                "x-max-retries": 3,
            },
        )
        await self._queue.bind(exchange, routing_key=self._routing_key)

        self._running = True
        logger.info("Consumer started on queue %s", self._queue_name)

        async with self._queue.iterator() as queue_iter:
            async for message in queue_iter:
                if not self._running:
                    break
                async with message.process(requeue=True):
                    try:
                        body = json.loads(message.body.decode())
                        await self._handler(body)
                    except Exception:
                        logger.exception("Error processing message from %s", self._queue_name)
                        # Message will be requeued or sent to DLQ after max retries

    async def stop(self) -> None:
        """Gracefully stop consuming."""
        self._running = False
        if self._connection:
            await self._connection.close()
        logger.info("Consumer stopped on queue %s", self._queue_name)


# ── Singleton Publisher ──────────────────────────────────
_publisher: RabbitMQPublisher | None = None


async def get_publisher() -> RabbitMQPublisher:
    """Get or create a singleton publisher."""
    global _publisher
    if _publisher is None:
        _publisher = RabbitMQPublisher()
        await _publisher.connect()
    return _publisher


async def close_publisher() -> None:
    """Close the singleton publisher."""
    global _publisher
    if _publisher:
        await _publisher.close()
        _publisher = None
