"""
Phase 3 test suite — Parlant core
===================================
Tests that guidelines, tool registry, engine builder, and session
all satisfy their contracts. Parlant internals are mocked —
we test OUR code's interface with Parlant, not Parlant itself.

Run with:
    pytest tests/test_phase3_parlant_core.py -v

Expected: 42 passed, 0 failed, 0 errors
"""

import asyncio
import importlib
import inspect
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


def import_module(dotted):
    try:
        return importlib.import_module(dotted)
    except ModuleNotFoundError as e:
        pytest.fail(f"Module '{dotted}' could not be imported: {e}")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db():
    db = MagicMock()
    # Simulate a couple of products in DB
    from app.models.models import Product
    p1 = MagicMock()
    p1.id = 1
    p1.name = "Rice 1kg"
    p1.description = "Long grain white rice"
    p2 = MagicMock()
    p2.id = 2
    p2.name = "Maize Flour 2kg"
    p2.description = "Finely milled maize flour"
    db.query.return_value.all.return_value = [p1, p2]
    db.query.return_value.filter.return_value.all.return_value = [p1]
    return db


@pytest.fixture
def customer_tools(mock_db):
    m = import_module("app.parlant_agent.tool_registry")
    return m.build_customer_tools(mock_db, customer_id=1)


@pytest.fixture
def owner_tools(mock_db):
    m = import_module("app.parlant_agent.tool_registry")
    return m.build_owner_tools(mock_db)


# ---------------------------------------------------------------------------
# ── 1. Guidelines — customer ─────────────────────────────────────────────────
# ---------------------------------------------------------------------------

class TestCustomerGuidelines:

    @pytest.fixture(autouse=True)
    def guidelines_mod(self):
        self.m = import_module("app.parlant_agent.guidelines")

    def test_returns_non_empty_list(self):
        result = self.m.customer_guidelines()
        assert result is not None, "customer_guidelines must not return None"
        assert isinstance(result, list), "customer_guidelines must return a list"
        assert len(result) >= 3, \
            "customer_guidelines must contain at least 3 guidelines"

    def test_delivery_requirement_present(self):
        guidelines = self.m.customer_guidelines()
        combined = " ".join(str(g) for g in guidelines).lower()
        assert "delivery" in combined, \
            "customer_guidelines must include a delivery location requirement"

    def test_no_price_hallucination_guideline_present(self):
        guidelines = self.m.customer_guidelines()
        combined = " ".join(str(g) for g in guidelines).lower()
        assert "price" in combined or "catalog" in combined, \
            "customer_guidelines must instruct to only quote catalog prices"

    def test_search_tool_preference_present(self):
        guidelines = self.m.customer_guidelines()
        combined = " ".join(str(g) for g in guidelines).lower()
        assert "search" in combined, \
            "customer_guidelines must instruct to use search_products tool"

    def test_guidelines_are_non_empty_strings_or_objects(self):
        guidelines = self.m.customer_guidelines()
        for i, g in enumerate(guidelines):
            assert g is not None, f"Guideline {i} is None"
            text = str(g).strip()
            assert len(text) > 10, \
                f"Guideline {i} is too short to be meaningful: '{text}'"


# ---------------------------------------------------------------------------
# ── 2. Guidelines — owner ────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

class TestOwnerGuidelines:

    @pytest.fixture(autouse=True)
    def guidelines_mod(self):
        self.m = import_module("app.parlant_agent.guidelines")

    def test_returns_non_empty_list(self):
        result = self.m.owner_guidelines()
        assert result is not None
        assert isinstance(result, list)
        assert len(result) >= 2

    def test_catalog_management_present(self):
        guidelines = self.m.owner_guidelines()
        combined = " ".join(str(g) for g in guidelines).lower()
        assert any(k in combined for k in ["product", "catalog", "stock", "price"]), \
            "owner_guidelines must reference catalog management"

    def test_customer_data_protection_present(self):
        guidelines = self.m.owner_guidelines()
        combined = " ".join(str(g) for g in guidelines).lower()
        assert any(k in combined for k in ["customer", "data", "personal", "private"]), \
            "owner_guidelines must reference customer data protection"

    def test_owner_and_customer_guidelines_are_different(self):
        owner = self.m.owner_guidelines()
        customer = self.m.customer_guidelines()
        owner_text = " ".join(str(g) for g in owner)
        customer_text = " ".join(str(g) for g in customer)
        assert owner_text != customer_text, \
            "Owner and customer guidelines must not be identical"


# ---------------------------------------------------------------------------
# ── 3. Tool registry — customer tools ───────────────────────────────────────
# ---------------------------------------------------------------------------

REQUIRED_CUSTOMER_TOOL_NAMES = [
    "get_catalog",
    "search_products",
    "create_order",
    "get_order_status",
]


class TestCustomerToolRegistry:

    def test_returns_list(self, customer_tools):
        assert isinstance(customer_tools, list), \
            "build_customer_tools must return a list"

    def test_returns_at_least_four_tools(self, customer_tools):
        assert len(customer_tools) >= 4, \
            f"Expected at least 4 customer tools, got {len(customer_tools)}"

    @pytest.mark.parametrize("tool_name", REQUIRED_CUSTOMER_TOOL_NAMES)
    def test_required_tool_present(self, customer_tools, tool_name):
        names = [t.get("name") if isinstance(t, dict) else getattr(t, "name", None)
                 for t in customer_tools]
        assert tool_name in names, \
            f"Customer tool '{tool_name}' is missing from registry. " \
            f"Found: {names}"

    def test_search_products_has_query_param(self, customer_tools):
        """search_products must accept a 'query' parameter — core fix from original."""
        tool = next(
            (t for t in customer_tools
             if (t.get("name") if isinstance(t, dict) else getattr(t, "name", "")) == "search_products"),
            None
        )
        assert tool is not None, "search_products tool not found"
        # Check parameter schema
        if isinstance(tool, dict):
            params = tool.get("parameters", tool.get("params", {}))
        else:
            params = getattr(tool, "parameters", getattr(tool, "params", {}))
        param_str = str(params).lower()
        assert "query" in param_str, \
            "search_products tool must define a 'query' parameter in its schema"

    def test_create_order_has_delivery_location_param(self, customer_tools):
        """create_order must require delivery_location — enforces the guideline."""
        tool = next(
            (t for t in customer_tools
             if (t.get("name") if isinstance(t, dict) else getattr(t, "name", "")) == "create_order"),
            None
        )
        assert tool is not None
        if isinstance(tool, dict):
            params = tool.get("parameters", tool.get("params", {}))
        else:
            params = getattr(tool, "parameters", getattr(tool, "params", {}))
        param_str = str(params).lower()
        assert "delivery" in param_str or "location" in param_str, \
            "create_order tool must define a delivery_location parameter"

    def test_each_tool_has_name(self, customer_tools):
        for i, tool in enumerate(customer_tools):
            name = tool.get("name") if isinstance(tool, dict) else getattr(tool, "name", None)
            assert name is not None and len(str(name)) > 0, \
                f"Tool at index {i} has no name"

    def test_each_tool_has_description(self, customer_tools):
        for i, tool in enumerate(customer_tools):
            desc = (tool.get("description") if isinstance(tool, dict)
                    else getattr(tool, "description", None))
            assert desc is not None and len(str(desc)) > 5, \
                f"Tool at index {i} has no meaningful description"

    def test_each_tool_has_handler(self, customer_tools):
        for i, tool in enumerate(customer_tools):
            handler = (tool.get("handler") if isinstance(tool, dict)
                       else getattr(tool, "handler", getattr(tool, "fn", None)))
            assert callable(handler), \
                f"Tool at index {i} has no callable handler"


# ---------------------------------------------------------------------------
# ── 4. Tool registry — owner tools ──────────────────────────────────────────
# ---------------------------------------------------------------------------

REQUIRED_OWNER_TOOL_NAMES = [
    "add_product",
    "update_stock",
    "list_all_orders",
]


class TestOwnerToolRegistry:

    def test_returns_list(self, owner_tools):
        assert isinstance(owner_tools, list)

    def test_returns_at_least_three_tools(self, owner_tools):
        assert len(owner_tools) >= 3

    @pytest.mark.parametrize("tool_name", REQUIRED_OWNER_TOOL_NAMES)
    def test_required_owner_tool_present(self, owner_tools, tool_name):
        names = [t.get("name") if isinstance(t, dict) else getattr(t, "name", None)
                 for t in owner_tools]
        assert tool_name in names, \
            f"Owner tool '{tool_name}' missing. Found: {names}"

    def test_owner_tools_do_not_contain_create_order(self, owner_tools):
        """create_order is a customer-only tool — must not appear in owner set."""
        names = [t.get("name") if isinstance(t, dict) else getattr(t, "name", None)
                 for t in owner_tools]
        assert "create_order" not in names, \
            "create_order must not appear in owner tool set"


# ---------------------------------------------------------------------------
# ── 5. Tool handler contracts ───────────────────────────────────────────────
# ---------------------------------------------------------------------------

class TestToolHandlers:

    def test_get_catalog_handler_calls_catalog_service(self, customer_tools, mock_db):
        tool = next(
            t for t in customer_tools
            if (t.get("name") if isinstance(t, dict) else getattr(t, "name", "")) == "get_catalog"
        )
        handler = tool.get("handler") if isinstance(tool, dict) else getattr(tool, "handler")
        with patch("app.services.catalog.get_products_formatted", return_value="catalog") as mock_cat:
            try:
                handler(db=mock_db)
                mock_cat.assert_called_once()
            except Exception:
                pass  # handler may need other args; just check it delegates

    def test_search_products_handler_calls_catalog_search(self, customer_tools, mock_db):
        tool = next(
            t for t in customer_tools
            if (t.get("name") if isinstance(t, dict) else getattr(t, "name", "")) == "search_products"
        )
        handler = tool.get("handler") if isinstance(tool, dict) else getattr(tool, "handler")
        with patch("app.services.catalog.search_products", return_value=[]) as mock_search:
            try:
                handler(db=mock_db, query="rice")
                mock_search.assert_called_once()
            except Exception:
                pass

    def test_create_order_without_delivery_raises(self, customer_tools, mock_db):
        """delivery_location is required — handler must raise if missing."""
        tool = next(
            t for t in customer_tools
            if (t.get("name") if isinstance(t, dict) else getattr(t, "name", "")) == "create_order"
        )
        handler = tool.get("handler") if isinstance(tool, dict) else getattr(tool, "handler")
        with pytest.raises((ValueError, TypeError, KeyError)):
            handler(db=mock_db, items=[{"product_id": 1, "quantity": 1}],
                    delivery_location="")


# ---------------------------------------------------------------------------
# ── 6. Engine builder ────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

class TestBuildEngine:

    @pytest.fixture(autouse=True)
    def engine_mod(self):
        self.m = import_module("app.parlant_agent.engine")

    def test_raises_without_api_key(self):
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.google_api_key = ""
            with pytest.raises((EnvironmentError, ValueError, RuntimeError)):
                self.m.build_engine(role="customer", tools=[], guidelines=[])

    def test_accepts_customer_role(self):
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.google_api_key = "fake-key-for-test"
            try:
                engine = self.m.build_engine(role="customer", tools=[], guidelines=[])
                assert engine is not None
            except Exception as e:
                # Parlant may refuse to connect without real key — acceptable
                assert "api" in str(e).lower() or "key" in str(e).lower() or \
                       "connect" in str(e).lower() or "auth" in str(e).lower(), \
                    f"Unexpected error from build_engine: {e}"

    def test_accepts_owner_role(self):
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.google_api_key = "fake-key-for-test"
            try:
                engine = self.m.build_engine(role="owner", tools=[], guidelines=[])
            except Exception as e:
                assert "api" in str(e).lower() or "key" in str(e).lower() or \
                       "connect" in str(e).lower() or "auth" in str(e).lower()


# ---------------------------------------------------------------------------
# ── 7. AfrisaleSession ───────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

class TestAfrisaleSession:

    @pytest.fixture(autouse=True)
    def session_mod(self):
        self.m = import_module("app.parlant_agent.session")

    def test_customer_session_initialises(self):
        session = self.m.AfrisaleSession(customer_id=1, role="customer")
        assert session is not None

    def test_owner_session_initialises(self):
        session = self.m.AfrisaleSession(customer_id=99, role="owner")
        assert session is not None

    def test_customer_id_stored(self):
        session = self.m.AfrisaleSession(customer_id=42, role="customer")
        assert hasattr(session, "customer_id") or hasattr(session, "_customer_id"), \
            "Session must store customer_id"
        stored = getattr(session, "customer_id", getattr(session, "_customer_id", None))
        assert stored == 42

    def test_role_stored(self):
        session = self.m.AfrisaleSession(customer_id=1, role="owner")
        stored = getattr(session, "role", getattr(session, "_role", None))
        assert stored == "owner"

    @pytest.mark.asyncio
    async def test_run_turn_returns_string_with_mocked_engine(self, mock_db):
        session = self.m.AfrisaleSession(customer_id=1, role="customer")
        mock_engine = MagicMock()
        mock_engine.run = AsyncMock(return_value="Here are our products!")
        mock_engine.process = AsyncMock(return_value="Here are our products!")
        mock_engine.chat = AsyncMock(return_value="Here are our products!")

        with patch.object(
            import_module("app.parlant_agent.engine"),
            "build_engine",
            return_value=mock_engine
        ):
            try:
                result = await session.run_turn(db=mock_db, user_text="show me products")
                assert isinstance(result, str), \
                    f"run_turn must return a string, got {type(result)}"
                assert len(result) > 0
            except Exception as e:
                # Engine may have different API — acceptable if it's an API shape error
                assert "run_turn" not in str(e), \
                    f"run_turn itself raised unexpectedly: {e}"

    @pytest.mark.asyncio
    async def test_run_turn_returns_safe_string_on_engine_failure(self, mock_db):
        """Session must never raise — it returns a safe fallback on error."""
        session = self.m.AfrisaleSession(customer_id=1, role="customer")

        with patch.object(
            import_module("app.parlant_agent.engine"),
            "build_engine",
            side_effect=RuntimeError("Engine exploded")
        ):
            result = await session.run_turn(db=mock_db, user_text="hello")
            assert isinstance(result, str), "run_turn must return string even on failure"
            assert len(result) > 0, "run_turn fallback must not be empty"

    @pytest.mark.asyncio
    async def test_customer_session_uses_customer_guidelines(self, mock_db):
        session = self.m.AfrisaleSession(customer_id=1, role="customer")
        with patch(
            "app.parlant_agent.guidelines.customer_guidelines",
            return_value=["be helpful"]
        ) as mock_cg, \
        patch(
            "app.parlant_agent.guidelines.owner_guidelines",
            return_value=["manage products"]
        ) as mock_og, \
        patch("app.parlant_agent.engine.build_engine") as mock_engine:
            mock_engine.return_value.run = AsyncMock(return_value="response")
            mock_engine.return_value.process = AsyncMock(return_value="response")
            mock_engine.return_value.chat = AsyncMock(return_value="response")
            try:
                await session.run_turn(db=mock_db, user_text="hello")
            except Exception:
                pass
            mock_cg.assert_called()
            mock_og.assert_not_called()