from typing import Any


async def log_inbound(customer_id: int, text: str, phone: str) -> None:
    """Logs inbound message event. Called in parallel with persist_inbound."""
    pass


async def log_tool_call(customer_id: int, tool_name: str, args: dict, result: Any) -> None:
    """Logs each Parlant tool invocation. Hooked into Parlant engine callback."""
    pass


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
    pass


async def log_final_response(customer_id: int, reply: str, channel: str) -> None:
    """Logs the final outbound message after persist and before dispatch."""
    pass
