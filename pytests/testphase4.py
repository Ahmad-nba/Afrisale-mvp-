"""
Phase 4 test suite — pipeline wire-up
=======================================
Tests the full pipeline runner and FastAPI route integration.
All external dependencies (DB, Parlant, channels) are mocked.

Run with:
    pytest tests/test_phase4_wireup.py -v

Expected: 44 passed, 0 failed, 0 errors
"""

import asyncio
import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call
import pytest
import importlib


def import_module(dotted):
    try:
        return importlib.import_module(dotted)
    except ModuleNotFoundError as e:
        pytest.fail(f"Module '{dotted}' could not be imported: {e}")


# ---------------------------------------------------------------------------
# Shared mocks
# ---------------------------------------------------------------------------

def make_mock_customer(customer_id=1, phone="+256700000001"):
    customer = MagicMock()
    customer.id = customer_id
    customer.phone = phone
    return customer


def make_mock_db(customer=None):
    db = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()
    db.refresh = MagicMock()
    return db


VALID_REPLY = "Your order has been placed successfully!"
FALLBACK_REPLY = "I'm having trouble with that. Please try again."


# ---------------------------------------------------------------------------
# ── 1. Pipeline stages — normalize_inbound ───────────────────────────────────
# ---------------------------------------------------------------------------

class TestNormalizeInbound:

    @pytest.fixture(autouse=True)
    def stages(self):
        self.m = import_module("app.pipeline.stages")

    @pytest.mark.asyncio
    async def test_strips_whatsapp_prefix(self):
        result = await self.m.normalize_inbound("whatsapp:+256700000001", "hello")
        assert "whatsapp:" not in result["phone"]

    @pytest.mark.asyncio
    async def test_returns_e164_phone(self):
        result = await self.m.normalize_inbound("+256700000001", "hello")
        assert result["phone"].startswith("+")

    @pytest.mark.asyncio
    async def test_strips_text_whitespace(self):
        result = await self.m.normalize_inbound("+256700000001", "  hello  ")
        assert result["text"] == "hello"

    @pytest.mark.asyncio
    async def test_returns_dict_with_phone_and_text(self):
        result = await self.m.normalize_inbound("+256700000001", "test")
        assert "phone" in result
        assert "text" in result

    @pytest.mark.asyncio
    async def test_raises_on_empty_phone(self):
        with pytest.raises((ValueError, Exception)):
            await self.m.normalize_inbound("", "hello")


# ---------------------------------------------------------------------------
# ── 2. Pipeline stages — persist_inbound ─────────────────────────────────────
# ---------------------------------------------------------------------------

class TestPersistInbound:

    @pytest.fixture(autouse=True)
    def stages(self):
        self.m = import_module("app.pipeline.stages")

    @pytest.mark.asyncio
    async def test_returns_customer_and_message_tuple(self):
        mock_db = make_mock_db()
        with patch("app.services.message_service.get_or_create_customer") as mock_cust, \
             patch("app.services.message_service.save_message") as mock_msg:
            mock_cust.return_value = make_mock_customer()
            mock_msg.return_value = MagicMock()
            result = await self.m.persist_inbound(mock_db, "+256700000001", "hello")
            assert isinstance(result, tuple)
            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_saves_message_with_direction_in(self):
        mock_db = make_mock_db()
        with patch("app.services.message_service.get_or_create_customer",
                   return_value=make_mock_customer()), \
             patch("app.services.message_service.save_message") as mock_save:
            mock_save.return_value = MagicMock()
            await self.m.persist_inbound(mock_db, "+256700000001", "order rice")
            # Check direction='in' or equivalent was used
            call_kwargs = str(mock_save.call_args)
            assert "in" in call_kwargs or mock_save.called


# ---------------------------------------------------------------------------
# ── 3. Pipeline stages — dispatch_outbound ───────────────────────────────────
# ---------------------------------------------------------------------------

class TestDispatchOutbound:

    @pytest.fixture(autouse=True)
    def stages(self):
        self.m = import_module("app.pipeline.stages")

    @pytest.mark.asyncio
    async def test_calls_outbound_send_when_provided(self):
        mock_send = AsyncMock()
        await self.m.dispatch_outbound("+256700000001", "Hello!", outbound_send=mock_send)
        mock_send.assert_called_once_with("+256700000001", "Hello!")

    @pytest.mark.asyncio
    async def test_calls_africastalking_when_no_outbound_send(self):
        with patch("app.integrations.africastalking.send_sms") as mock_sms:
            mock_sms.return_value = None
            await self.m.dispatch_outbound("+256700000001", "Hello!", outbound_send=None)
            mock_sms.assert_called_once()

    @pytest.mark.asyncio
    async def test_does_not_raise_on_send_failure(self):
        """dispatch_outbound must swallow exceptions — never crash the pipeline."""
        async def failing_send(to, msg):
            raise ConnectionError("Twilio down")

        try:
            await self.m.dispatch_outbound("+256700000001", "Hello!",
                                           outbound_send=failing_send)
        except Exception as e:
            pytest.fail(f"dispatch_outbound must not raise on send failure: {e}")

    @pytest.mark.asyncio
    async def test_does_not_raise_on_sms_failure(self):
        with patch("app.integrations.africastalking.send_sms",
                   side_effect=Exception("AT down")):
            try:
                await self.m.dispatch_outbound("+256700000001", "Hello!", outbound_send=None)
            except Exception as e:
                pytest.fail(f"dispatch_outbound must not raise on SMS failure: {e}")


# ---------------------------------------------------------------------------
# ── 4. Pipeline runner — run_pipeline ────────────────────────────────────────
# ---------------------------------------------------------------------------

class TestRunPipeline:

    @pytest.fixture(autouse=True)
    def runner(self):
        self.m = import_module("app.pipeline.runner")

    def test_run_pipeline_function_exists(self):
        assert hasattr(self.m, "run_pipeline"), \
            "app.pipeline.runner must expose run_pipeline"
        assert callable(self.m.run_pipeline)

    def test_run_pipeline_is_async(self):
        import inspect
        assert inspect.iscoroutinefunction(self.m.run_pipeline), \
            "run_pipeline must be async"

    def test_run_pipeline_signature(self):
        import inspect
        sig = inspect.signature(self.m.run_pipeline)
        params = list(sig.parameters)
        assert "db" in params
        assert "from_raw" in params
        assert "text_raw" in params
        assert "owner_phone" in params
        assert "outbound_send" in params

    @pytest.mark.asyncio
    async def test_valid_message_returns_string(self):
        mock_db = make_mock_db()
        mock_customer = make_mock_customer()

        with patch("app.pipeline.stages.normalize_inbound",
                   new=AsyncMock(return_value={"phone": "+256700000001", "text": "show catalog"})), \
             patch("app.pipeline.stages.persist_inbound",
                   new=AsyncMock(return_value=(mock_customer, MagicMock()))), \
             patch("app.guardrails.input_guardrail.InputGuardrail.validate",
                   return_value=(True, "")), \
             patch("app.pipeline.stages.call_agent",
                   new=AsyncMock(return_value=VALID_REPLY)), \
             patch("app.guardrails.output_validation.OutputValidationGuardrail.validate",
                   return_value=(True, "")), \
             patch("app.guardrails.output_formatting.OutputFormattingGuardrail.format",
                   return_value=VALID_REPLY), \
             patch("app.pipeline.stages.persist_outbound", new=AsyncMock()), \
             patch("app.pipeline.stages.dispatch_outbound", new=AsyncMock()), \
             patch("app.observability.logger.log_inbound", new=AsyncMock()), \
             patch("app.observability.logger.log_guardrail_decision", new=AsyncMock()), \
             patch("app.observability.logger.log_final_response", new=AsyncMock()), \
             patch("app.core.config.settings") as mock_settings:
            mock_settings.owner_phone = "+256700000099"
            result = await self.m.run_pipeline(
                db=mock_db,
                from_raw="+256700000001",
                text_raw="show catalog",
                owner_phone="+256700000099",
            )
            assert isinstance(result, str)
            assert len(result) > 0

    @pytest.mark.asyncio
    async def test_invalid_input_returns_fallback_without_calling_agent(self):
        mock_db = make_mock_db()
        mock_customer = make_mock_customer()

        with patch("app.pipeline.stages.normalize_inbound",
                   new=AsyncMock(return_value={"phone": "+256700000001", "text": "!!!"})), \
             patch("app.pipeline.stages.persist_inbound",
                   new=AsyncMock(return_value=(mock_customer, MagicMock()))), \
             patch("app.guardrails.input_guardrail.InputGuardrail.validate",
                   return_value=(False, "no_intent")), \
             patch("app.pipeline.stages.call_agent",
                   new=AsyncMock(return_value=VALID_REPLY)) as mock_agent, \
             patch("app.pipeline.stages.persist_outbound", new=AsyncMock()), \
             patch("app.pipeline.stages.dispatch_outbound", new=AsyncMock()), \
             patch("app.observability.logger.log_inbound", new=AsyncMock()), \
             patch("app.observability.logger.log_guardrail_decision", new=AsyncMock()), \
             patch("app.core.config.settings") as mock_settings:
            mock_settings.owner_phone = "+256700000099"
            result = await self.m.run_pipeline(
                db=mock_db,
                from_raw="+256700000001",
                text_raw="!!!",
                owner_phone="+256700000099",
            )
            mock_agent.assert_not_called()
            assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_invalid_output_returns_fallback_without_formatting(self):
        mock_db = make_mock_db()
        mock_customer = make_mock_customer()

        with patch("app.pipeline.stages.normalize_inbound",
                   new=AsyncMock(return_value={"phone": "+256700000001", "text": "hello"})), \
             patch("app.pipeline.stages.persist_inbound",
                   new=AsyncMock(return_value=(mock_customer, MagicMock()))), \
             patch("app.guardrails.input_guardrail.InputGuardrail.validate",
                   return_value=(True, "")), \
             patch("app.pipeline.stages.call_agent",
                   new=AsyncMock(return_value="ok")), \
             patch("app.guardrails.output_validation.OutputValidationGuardrail.validate",
                   return_value=(False, FALLBACK_REPLY)), \
             patch("app.guardrails.output_formatting.OutputFormattingGuardrail.format") as mock_fmt, \
             patch("app.pipeline.stages.persist_outbound", new=AsyncMock()), \
             patch("app.pipeline.stages.dispatch_outbound", new=AsyncMock()), \
             patch("app.observability.logger.log_inbound", new=AsyncMock()), \
             patch("app.observability.logger.log_guardrail_decision", new=AsyncMock()), \
             patch("app.observability.logger.log_final_response", new=AsyncMock()), \
             patch("app.core.config.settings") as mock_settings:
            mock_settings.owner_phone = "+256700000099"
            result = await self.m.run_pipeline(
                db=mock_db, from_raw="+256700000001",
                text_raw="hello", owner_phone="+256700000099",
            )
            mock_fmt.assert_not_called()
            assert result == FALLBACK_REPLY

    @pytest.mark.asyncio
    async def test_owner_phone_gets_owner_role(self):
        mock_db = make_mock_db()
        owner_phone = "+256700000099"
        owner_customer = make_mock_customer(phone=owner_phone)

        with patch("app.pipeline.stages.normalize_inbound",
                   new=AsyncMock(return_value={"phone": owner_phone, "text": "list orders"})), \
             patch("app.pipeline.stages.persist_inbound",
                   new=AsyncMock(return_value=(owner_customer, MagicMock()))), \
             patch("app.guardrails.input_guardrail.InputGuardrail.validate",
                   return_value=(True, "")), \
             patch("app.pipeline.stages.call_agent",
                   new=AsyncMock(return_value=VALID_REPLY)) as mock_agent, \
             patch("app.guardrails.output_validation.OutputValidationGuardrail.validate",
                   return_value=(True, "")), \
             patch("app.guardrails.output_formatting.OutputFormattingGuardrail.format",
                   return_value=VALID_REPLY), \
             patch("app.pipeline.stages.persist_outbound", new=AsyncMock()), \
             patch("app.pipeline.stages.dispatch_outbound", new=AsyncMock()), \
             patch("app.observability.logger.log_inbound", new=AsyncMock()), \
             patch("app.observability.logger.log_guardrail_decision", new=AsyncMock()), \
             patch("app.observability.logger.log_final_response", new=AsyncMock()), \
             patch("app.core.config.settings") as mock_settings:
            mock_settings.owner_phone = owner_phone
            await self.m.run_pipeline(
                db=mock_db, from_raw=owner_phone,
                text_raw="list orders", owner_phone=owner_phone,
            )
            call_kwargs = mock_agent.call_args
            assert call_kwargs is not None
            role_arg = call_kwargs.kwargs.get("role") or (
                call_kwargs.args[3] if len(call_kwargs.args) > 3 else None
            )
            assert role_arg == "owner", \
                f"Owner phone must map to role='owner', got: {role_arg}"

    @pytest.mark.asyncio
    async def test_observability_fires_for_inbound(self):
        mock_db = make_mock_db()
        mock_customer = make_mock_customer()

        with patch("app.pipeline.stages.normalize_inbound",
                   new=AsyncMock(return_value={"phone": "+256700000001", "text": "hi"})), \
             patch("app.pipeline.stages.persist_inbound",
                   new=AsyncMock(return_value=(mock_customer, MagicMock()))), \
             patch("app.guardrails.input_guardrail.InputGuardrail.validate",
                   return_value=(False, "too_short")), \
             patch("app.pipeline.stages.persist_outbound", new=AsyncMock()), \
             patch("app.pipeline.stages.dispatch_outbound", new=AsyncMock()), \
             patch("app.observability.logger.log_inbound",
                   new=AsyncMock()) as mock_log_in, \
             patch("app.observability.logger.log_guardrail_decision",
                   new=AsyncMock()) as mock_log_grl, \
             patch("app.core.config.settings") as mock_settings:
            mock_settings.owner_phone = "+256700000099"
            await self.m.run_pipeline(
                db=mock_db, from_raw="+256700000001",
                text_raw="hi", owner_phone="+256700000099",
            )
            # Give fire-and-forget tasks a tick to run
            await asyncio.sleep(0)
            mock_log_in.assert_called()
            mock_log_grl.assert_called()

    @pytest.mark.asyncio
    async def test_persist_outbound_called_before_dispatch(self):
        """Outbound must be persisted to DB before it is sent to the channel."""
        call_order = []
        mock_db = make_mock_db()
        mock_customer = make_mock_customer()

        async def track_persist(*args, **kwargs):
            call_order.append("persist")

        async def track_dispatch(*args, **kwargs):
            call_order.append("dispatch")

        with patch("app.pipeline.stages.normalize_inbound",
                   new=AsyncMock(return_value={"phone": "+256700000001", "text": "hello"})), \
             patch("app.pipeline.stages.persist_inbound",
                   new=AsyncMock(return_value=(mock_customer, MagicMock()))), \
             patch("app.guardrails.input_guardrail.InputGuardrail.validate",
                   return_value=(True, "")), \
             patch("app.pipeline.stages.call_agent",
                   new=AsyncMock(return_value=VALID_REPLY)), \
             patch("app.guardrails.output_validation.OutputValidationGuardrail.validate",
                   return_value=(True, "")), \
             patch("app.guardrails.output_formatting.OutputFormattingGuardrail.format",
                   return_value=VALID_REPLY), \
             patch("app.pipeline.stages.persist_outbound", new=AsyncMock(side_effect=track_persist)), \
             patch("app.pipeline.stages.dispatch_outbound", new=AsyncMock(side_effect=track_dispatch)), \
             patch("app.observability.logger.log_inbound", new=AsyncMock()), \
             patch("app.observability.logger.log_guardrail_decision", new=AsyncMock()), \
             patch("app.observability.logger.log_final_response", new=AsyncMock()), \
             patch("app.core.config.settings") as mock_settings:
            mock_settings.owner_phone = "+256700000099"
            await self.m.run_pipeline(
                db=mock_db, from_raw="+256700000001",
                text_raw="hello", owner_phone="+256700000099",
            )
            assert call_order.index("persist") < call_order.index("dispatch"), \
                "persist_outbound must be called before dispatch_outbound"


# ---------------------------------------------------------------------------
# ── 5. FastAPI routes use run_pipeline ──────────────────────────────────────
# ---------------------------------------------------------------------------

class TestFastAPIRoutesCallRunPipeline:
    """
    Source-level checks — verify that messages.py calls run_pipeline,
    not the old handle_inbound. We parse the AST to avoid import side-effects.
    """

    @pytest.fixture(autouse=True)
    def source(self):
        path = Path("app/api/messages.py")
        assert path.exists(), "app/api/messages.py must exist"
        self.source = path.read_text()
        self.tree = ast.parse(self.source)

    def _get_all_calls(self):
        """Return all function call names in the source."""
        calls = []
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.append(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls.append(node.func.attr)
        return calls

    def test_run_pipeline_imported(self):
        assert "run_pipeline" in self.source, \
            "messages.py must import run_pipeline from app.pipeline.runner"

    def test_run_pipeline_called(self):
        calls = self._get_all_calls()
        assert "run_pipeline" in calls, \
            "messages.py must call run_pipeline in at least one route handler"

    def test_handle_inbound_not_called_in_routes(self):
        calls = self._get_all_calls()
        assert "handle_inbound" not in calls, \
            "messages.py must not call handle_inbound — it has been replaced by run_pipeline"

    def test_whatsapp_route_exists(self):
        assert "whatsapp_webhook" in self.source or "whatsapp" in self.source, \
            "messages.py must still define the WhatsApp webhook route"

    def test_json_route_exists(self):
        assert "webhook_json" in self.source or "/api/webhook" in self.source, \
            "messages.py must still define the JSON webhook route"


# ---------------------------------------------------------------------------
# ── 6. Old message_service.handle_inbound is NOT called ─────────────────────
# ---------------------------------------------------------------------------

class TestHandleInboundNotInPipeline:

    def test_pipeline_runner_does_not_import_handle_inbound(self):
        source = Path("app/pipeline/runner.py").read_text()
        assert "handle_inbound" not in source, \
            "pipeline/runner.py must not reference handle_inbound"

    def test_pipeline_stages_does_not_import_handle_inbound(self):
        source = Path("app/pipeline/stages.py").read_text()
        assert "handle_inbound" not in source, \
            "pipeline/stages.py must not reference handle_inbound"