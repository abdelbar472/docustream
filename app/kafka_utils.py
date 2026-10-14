"""Shared Kafka plumbing: connect-with-retry, JSON producer, and a worker loop that
gives every stage the same delivery semantics:

  * manual offset commits, AFTER processing  -> at-least-once delivery
  * N retries with exponential backoff       -> survives transient failures
  * dead-letter topic after the last retry   -> poison messages never block a partition
"""
import asyncio
import json
import logging
from typing import Awaitable, Callable

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.structs import TopicPartition

from . import config

log = logging.getLogger("kafka")


async def start_with_retry(factory, name: str, attempts: int = 30, delay: float = 2.0):
    """Start a Kafka client, retrying while the broker is still coming up."""
    for attempt in range(1, attempts + 1):
        client = factory()
        try:
            await client.start()
            return client
        except Exception as e:
            try:
                await client.stop()
            except Exception:
                pass
            if attempt == attempts:
                raise
            log.warning("%s: Kafka not ready (%s), retry %d/%d", name, e, attempt, attempts)
            await asyncio.sleep(delay)


async def make_producer(name: str) -> AIOKafkaProducer:
    return await start_with_retry(
        lambda: AIOKafkaProducer(
            bootstrap_servers=config.BOOTSTRAP,
            value_serializer=lambda v: json.dumps(v).encode(),
            acks="all",
            # batch a few ms of records into one request and compress them
            linger_ms=config.PRODUCER_LINGER_MS,
            compression_type=config.PRODUCER_COMPRESSION or None,
        ),
        name,
    )


async def send_to_dlq(producer: AIOKafkaProducer, msg, stage: str, error: Exception):
    await producer.send_and_wait(
        config.TOPIC_DLQ,
        {
            "stage": stage,
            "error": f"{type(error).__name__}: {error}",
            "source_topic": msg.topic,
            "partition": msg.partition,
            "offset": msg.offset,
            "original": msg.value.decode("utf-8", errors="replace"),
        },
        key=msg.key,
    )


async def run_worker(
    *,
    name: str,
    topic: str,
    group: str,
    producer: AIOKafkaProducer,
    handler: Callable[[dict], Awaitable[None]] | None = None,
    on_dead: Callable[[dict | None, Exception], Awaitable[None]] | None = None,
    batch_handler: Callable[[list[dict]], Awaitable[None]] | None = None,
    max_batch: int = 1,
    batch_wait_ms: int = 100,
):
    """Consume `topic` in consumer group `group`.

    With `batch_handler`, messages are pulled in batches (up to `max_batch`, waiting at
    most `batch_wait_ms`) and handed over together so a stage can vectorize work such as
    embedding and upserts. A batch that fails falls back to per-message retries and the
    dead-letter path, so delivery semantics are identical to the single-message mode.
    """
    consumer = await start_with_retry(
        lambda: AIOKafkaConsumer(
            topic,
            bootstrap_servers=config.BOOTSTRAP,
            group_id=group,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
        ),
        name,
    )
    log.info("%s: consuming %s as group %s", name, topic, group)
    use_batch = batch_handler is not None and max_batch > 1
    try:
        if use_batch:
            await _batch_loop(consumer, producer, name, batch_handler, handler, on_dead,
                              max_batch, batch_wait_ms)
        else:
            await _single_loop(consumer, producer, name, handler, on_dead)
    finally:
        await consumer.stop()
        await producer.stop()


async def _commit(consumer, messages) -> None:
    """Commit each partition at the highest offset seen + 1, after it was handled."""
    offsets: dict[TopicPartition, int] = {}
    for msg in messages:
        offsets[TopicPartition(msg.topic, msg.partition)] = msg.offset + 1
    if offsets:
        await consumer.commit(offsets)


async def _single_loop(consumer, producer, name, handler, on_dead) -> None:
    async for msg in consumer:
        payload = None
        try:
            payload = json.loads(msg.value)
            await _with_retries(name, handler, payload)
        except Exception as e:
            log.error("%s: giving up on %s[%d]@%d: %s", name, msg.topic, msg.partition, msg.offset, e)
            await send_to_dlq(producer, msg, name, e)
            if on_dead:
                await on_dead(payload, e)
        # commit only after the message was handled or dead-lettered
        await _commit(consumer, [msg])


async def _batch_loop(consumer, producer, name, batch_handler, handler, on_dead,
                      max_batch: int, batch_wait_ms: int) -> None:
    while True:
        batches = await consumer.getmany(timeout_ms=batch_wait_ms, max_records=max_batch)
        messages = [msg for records in batches.values() for msg in records]
        if not messages:
            continue

        ready: list = []      # (msg, payload) pairs that parsed fine
        for msg in messages:
            try:
                ready.append((msg, json.loads(msg.value)))
            except Exception as e:
                log.error("%s: bad message %s[%d]@%d: %s",
                          name, msg.topic, msg.partition, msg.offset, e)
                await send_to_dlq(producer, msg, name, e)

        if ready:
            try:
                await batch_handler([payload for _, payload in ready])
            except Exception as e:
                # isolate the failure: retry each message, dead-lettering the poison one
                log.warning("%s: batch of %d failed (%s); falling back to per-message",
                            name, len(ready), e)
                for msg, payload in ready:
                    try:
                        await _with_retries(name, handler, payload)
                    except Exception as e2:
                        log.error("%s: giving up on %s[%d]@%d: %s",
                                  name, msg.topic, msg.partition, msg.offset, e2)
                        await send_to_dlq(producer, msg, name, e2)
                        if on_dead:
                            await on_dead(payload, e2)

        # commit once, at the highest offset seen per partition, after handling everything
        await _commit(consumer, messages)


async def _with_retries(name: str, handler, payload: dict):
    delay = config.RETRY_BACKOFF
    for attempt in range(1, config.MAX_ATTEMPTS + 1):
        try:
            await handler(payload)
            return
        except Exception as e:
            if attempt == config.MAX_ATTEMPTS:
                raise
            log.warning("%s: attempt %d/%d failed (%s); retrying in %.1fs",
                        name, attempt, config.MAX_ATTEMPTS, e, delay)
            await asyncio.sleep(delay)
            delay *= 2
