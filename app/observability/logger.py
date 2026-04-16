import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

logger = logging.getLogger("afrisale")


def fire_and_forget(task: Coroutine[Any, Any, Any]) -> None:
    """Schedule a coroutine without blocking caller execution."""
    try:
        asyncio.ensure_future(task)
    except RuntimeError:
        logger.exception("log_schedule_failed")


async def log_inbound(customer_id: int, text: str, phone: str) -> None:
    """Logs inbound message event. Called in parallel with persist_inbound."""
    logger.info(
        "event=inbound customer_id=%s phone=%s text=%r",
        customer_id,
        phone,
        text,
    )


async def log_tool_call(customer_id: int, tool_name: str, args: dict, result: Any) -> None:
    """Logs each Parlant tool invocation. Hooked into Parlant engine callback."""
    logger.info(
        "event=tool_call customer_id=%s tool_name=%s args=%r result=%r",
        customer_id,
        tool_name,
        args,
        result,
    )


async def log_guardrail_decision(
    stage: str,
    passed: bool,
    reason: str,
    customer_id: int,
) -> None:
    """
    stage: 'input' | 'output_validation' | 'output_formatting'
    Logs every guardrail pass/fail with reason for diagnosability.
    """
    logger.info(
        "event=guardrail_decision stage=%s passed=%s reason=%s customer_id=%s",
        stage,
        passed,
        reason,
        customer_id,
    )


async def log_final_response(customer_id: int, reply: str, channel: str) -> None:
    """Logs the final outbound message after persist and before dispatch."""
    logger.info(
        "event=final_response customer_id=%s channel=%s reply=%r",
        customer_id,
        channel,
        reply,
    )


async def log_provider_event(
    stage: str,
    provider: str,
    action: str,
    detail: str = "",
) -> None:
    """Logs provider selection/retry/failover lifecycle events."""
    logger.info(
        "event=provider stage=%s provider=%s action=%s detail=%s",
        stage,
        provider,
        action,
        detail,
    )
