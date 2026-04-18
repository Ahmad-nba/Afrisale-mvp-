import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.parlant_agent.engine import LocalParlantEngine


class _QueueProvider:
    def __init__(self, responses):
        self._responses = list(responses)

    async def generate(self, prompt: str) -> str:
        if not self._responses:
            return ""
        return self._responses.pop(0)


def _engine(*, provider, tools, memory_state=None, save_state=None):
    return LocalParlantEngine(
        role="customer",
        tools=tools,
        guidelines=["Use tools for catalog operations."],
        model_backend="gemini",
        provider=provider,
        retry_attempts=1,
        retry_backoff_seconds=0.0,
        recent_messages=[],
        memory_state=memory_state or {},
        save_state=save_state,
    )


@pytest.mark.asyncio
async def test_followup_reference_uses_previous_candidates():
    calls = []

    def search_products(**kwargs):
        calls.append(kwargs)
        return []

    provider = _QueueProvider(
        responses=[
            json.dumps({"tool": "search_products", "args": {"query": "black one"}}),
            "Done",
        ]
    )
    state = {
        "lastProductCandidates": [
            {"title": "Leather Belt (M, Brown)", "price": 40000, "variant_id": 1, "product_id": 1},
            {"title": "Leather Belt (L, Black)", "price": 42000, "variant_id": 2, "product_id": 1},
        ]
    }
    engine = _engine(
        provider=provider,
        tools=[{"name": "search_products", "handler": search_products}],
        memory_state=state,
    )

    await engine.run("The black one for 42,000, place for me an order to Gayaza")

    assert calls, "search_products should be called"
    assert calls[0]["query"] == "Leather Belt (L, Black)"


@pytest.mark.asyncio
async def test_search_tool_updates_memory_slots():
    persisted = {}

    def save_state(state):
        persisted.update(state)
        return state

    def search_products(**kwargs):
        return [
            {"title": "Leather Belt (L, Black)", "price": 42000, "variant_id": 22, "product_id": 5},
            {"title": "Leather Belt (M, Brown)", "price": 40000, "variant_id": 21, "product_id": 5},
        ]

    provider = _QueueProvider(
        responses=[
            json.dumps({"tool": "search_products", "args": {"query": "leather belt"}}),
            "Here are options.",
        ]
    )
    engine = _engine(
        provider=provider,
        tools=[{"name": "search_products", "handler": search_products}],
        save_state=save_state,
    )

    await engine.run("I need a leather belt")

    assert persisted.get("lastProductCandidates"), "lastProductCandidates should be persisted"
    assert persisted.get("selectedVariantId") == 22
    assert persisted.get("selectedProductId") == 5
    assert persisted.get("lastMentionedPrice") == 42000


@pytest.mark.asyncio
async def test_create_order_reuses_saved_delivery_and_variant():
    order_calls = []

    def create_order(**kwargs):
        order_calls.append(kwargs)
        return {"ok": True}

    provider = _QueueProvider(
        responses=[
            json.dumps({"tool": "create_order", "args": {"items": []}}),
            "Order placed.",
        ]
    )
    engine = _engine(
        provider=provider,
        tools=[{"name": "create_order", "handler": create_order}],
        memory_state={
            "selectedVariantId": 9,
            "deliveryLocation": "Gayaza",
        },
    )

    await engine.run("place the order now")

    assert order_calls, "create_order should be called"
    assert order_calls[0].get("delivery_location") == "Gayaza"
    assert order_calls[0].get("items") == [{"variant_id": 9, "quantity": 1}]


@pytest.mark.asyncio
async def test_session_wires_history_and_state_into_engine():
    from app.parlant_agent.session import AfrisaleSession

    session = AfrisaleSession(customer_id=1, role="customer")
    mock_engine = MagicMock()
    mock_engine.set_memory_context = MagicMock()
    mock_engine.run = AsyncMock(return_value="ok")
    mock_db = MagicMock()

    with (
        pytest.MonkeyPatch.context() as mpatch,
    ):
        mpatch.setattr(
            "app.services.message_service.get_recent_messages",
            lambda db, customer_id, limit=6: [
                MagicMock(direction="in", message="hello"),
                MagicMock(direction="out", message="hi there"),
            ],
        )
        mpatch.setattr(
            "app.services.conversation_state_service.get_state",
            lambda db, customer_id: {"deliveryLocation": "Gayaza"},
        )
        mpatch.setattr(
            "app.parlant_agent.engine.build_engine",
            lambda role, tools, guidelines: mock_engine,
        )
        mpatch.setattr(
            "app.parlant_agent.tool_registry.build_customer_tools",
            lambda db, customer_id: [],
        )

        await session.run_turn(db=mock_db, user_text="hello again")

    assert mock_engine.set_memory_context.called
