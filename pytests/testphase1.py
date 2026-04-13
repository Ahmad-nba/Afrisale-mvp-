"""
Phase 1 test suite — skeleton & contracts
==========================================
Tests ONLY structure, signatures, module layout, and stub contracts.
No DB, no Parlant, no LangChain, no network calls required.

Run with:
    pytest tests/test_phase1_skeleton.py -v

All tests must pass before moving to Phase 2.
Expected: 40 passed, 0 failed, 0 errors
"""

import ast
import asyncio
import inspect
import importlib
import os
import sys
from pathlib import Path
from typing import get_type_hints

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def import_module(dotted: str):
    """Import a module by dotted path, fail with a clear message if missing."""
    try:
        return importlib.import_module(dotted)
    except ModuleNotFoundError as e:
        pytest.fail(f"Module '{dotted}' could not be imported: {e}")


def get_class(module, name: str):
    cls = getattr(module, name, None)
    assert cls is not None, f"Class '{name}' not found in {module.__name__}"
    assert inspect.isclass(cls), f"'{name}' in {module.__name__} is not a class"
    return cls


def get_func(module, name: str):
    fn = getattr(module, name, None)
    assert fn is not None, f"Function '{name}' not found in {module.__name__}"
    assert callable(fn), f"'{name}' in {module.__name__} is not callable"
    return fn


def is_async_func(fn) -> bool:
    return inspect.iscoroutinefunction(fn)


def method_exists(cls, name: str):
    return hasattr(cls, name) and callable(getattr(cls, name))


def has_docstring(obj) -> bool:
    doc = inspect.getdoc(obj)
    return doc is not None and len(doc.strip()) > 10


# ---------------------------------------------------------------------------
# ── 1. FILE STRUCTURE ───────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

EXPECTED_FILES = [
    "app/pipeline/__init__.py",
    "app/pipeline/stages.py",
    "app/guardrails/__init__.py",
    "app/guardrails/input_guardrail.py",
    "app/guardrails/output_validation.py",
    "app/guardrails/output_formatting.py",
    "app/parlant_agent/__init__.py",
    "app/parlant_agent/session.py",
    "app/parlant_agent/engine.py",
    "app/parlant_agent/guidelines.py",
    "app/parlant_agent/tool_registry.py",
    "app/observability/__init__.py",
    "app/observability/logger.py",
]


@pytest.mark.parametrize("filepath", EXPECTED_FILES)
def test_file_exists(filepath):
    """Every skeleton file must exist on disk."""
    assert Path(filepath).exists(), f"Missing file: {filepath}"


@pytest.mark.parametrize("filepath", EXPECTED_FILES)
def test_file_is_valid_python(filepath):
    """Every skeleton file must be parseable Python (no syntax errors)."""
    source = Path(filepath).read_text()
    try:
        ast.parse(source)
    except SyntaxError as e:
        pytest.fail(f"Syntax error in {filepath}: {e}")


# ---------------------------------------------------------------------------
# ── 2. MODULE IMPORTS ────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

MODULES = [
    "app.pipeline.stages",
    "app.guardrails.input_guardrail",
    "app.guardrails.output_validation",
    "app.guardrails.output_formatting",
    "app.parlant_agent.session",
    "app.parlant_agent.engine",
    "app.parlant_agent.guidelines",
    "app.parlant_agent.tool_registry",
    "app.observability.logger",
]


@pytest.mark.parametrize("module_path", MODULES)
def test_module_imports_cleanly(module_path):
    """Every module must import without errors at stub stage."""
    import_module(module_path)


# ---------------------------------------------------------------------------
# ── 3. app/pipeline/stages.py ───────────────────────────────────────────────
# ---------------------------------------------------------------------------

class TestPipelineStages:

    @pytest.fixture(autouse=True)
    def mod(self):
        self.m = import_module("app.pipeline.stages")

    def test_normalize_inbound_exists(self):
        get_func(self.m, "normalize_inbound")

    def test_normalize_inbound_is_async(self):
        fn = get_func(self.m, "normalize_inbound")
        assert is_async_func(fn), "normalize_inbound must be async"

    def test_normalize_inbound_signature(self):
        fn = get_func(self.m, "normalize_inbound")
        sig = inspect.signature(fn)
        params = list(sig.parameters)
        assert "from_raw" in params, "normalize_inbound must have 'from_raw' param"
        assert "text_raw" in params, "normalize_inbound must have 'text_raw' param"

    def test_persist_inbound_exists_and_async(self):
        fn = get_func(self.m, "persist_inbound")
        assert is_async_func(fn), "persist_inbound must be async"

    def test_persist_inbound_signature(self):
        fn = get_func(self.m, "persist_inbound")
        params = list(inspect.signature(fn).parameters)
        assert "db" in params
        assert "phone" in params
        assert "text" in params

    def test_call_agent_exists_and_async(self):
        fn = get_func(self.m, "call_agent")
        assert is_async_func(fn), "call_agent must be async"

    def test_call_agent_signature(self):
        fn = get_func(self.m, "call_agent")
        params = list(inspect.signature(fn).parameters)
        assert "db" in params
        assert "customer" in params
        assert "text" in params
        assert "role" in params
        assert "outbound_send" in params

    def test_call_agent_outbound_send_defaults_none(self):
        fn = get_func(self.m, "call_agent")
        sig = inspect.signature(fn)
        default = sig.parameters["outbound_send"].default
        assert default is None, "outbound_send must default to None"

    def test_persist_outbound_exists_and_async(self):
        fn = get_func(self.m, "persist_outbound")
        assert is_async_func(fn), "persist_outbound must be async"

    def test_dispatch_outbound_exists_and_async(self):
        fn = get_func(self.m, "dispatch_outbound")
        assert is_async_func(fn), "dispatch_outbound must be async"

    def test_dispatch_outbound_outbound_send_defaults_none(self):
        fn = get_func(self.m, "dispatch_outbound")
        sig = inspect.signature(fn)
        default = sig.parameters["outbound_send"].default
        assert default is None, "dispatch_outbound.outbound_send must default to None"

    def test_all_stages_have_docstrings(self):
        for name in ["normalize_inbound", "persist_inbound", "call_agent",
                     "persist_outbound", "dispatch_outbound"]:
            fn = get_func(self.m, name)
            assert has_docstring(fn), f"{name} must have a descriptive docstring"

    def test_stub_normalize_returns_none_or_dict(self):
        """Stub must not raise — returning None or {} is fine at phase 1."""
        fn = get_func(self.m, "normalize_inbound")
        try:
            result = asyncio.get_event_loop().run_until_complete(
                fn("whatsapp:+256700000000", "hello")
            )
            # stub can return None (pass) or a dict — both acceptable
            assert result is None or isinstance(result, dict), \
                "normalize_inbound stub must return None or dict"
        except NotImplementedError:
            pass  # explicit NotImplementedError is also acceptable at stub stage
        except Exception as e:
            pytest.fail(f"normalize_inbound raised unexpected error: {e}")


# ---------------------------------------------------------------------------
# ── 4. app/guardrails/input_guardrail.py ────────────────────────────────────
# ---------------------------------------------------------------------------

class TestInputGuardrail:

    @pytest.fixture(autouse=True)
    def mod(self):
        self.m = import_module("app.guardrails.input_guardrail")

    def test_class_exists(self):
        get_class(self.m, "InputGuardrail")

    def test_validate_method_exists(self):
        cls = get_class(self.m, "InputGuardrail")
        assert method_exists(cls, "validate"), \
            "InputGuardrail must have a 'validate' method"

    def test_validate_is_not_async(self):
        """Input guardrail validate must be synchronous — it's a fast gate."""
        cls = get_class(self.m, "InputGuardrail")
        fn = cls.validate
        assert not is_async_func(fn), \
            "InputGuardrail.validate must be synchronous (not async)"

    def test_validate_signature(self):
        cls = get_class(self.m, "InputGuardrail")
        sig = inspect.signature(cls.validate)
        params = list(sig.parameters)
        assert "text" in params, "validate must accept 'text' parameter"

    def test_class_has_docstring(self):
        cls = get_class(self.m, "InputGuardrail")
        assert has_docstring(cls), "InputGuardrail class must have a docstring"

    def test_validate_has_docstring(self):
        cls = get_class(self.m, "InputGuardrail")
        assert has_docstring(cls.validate), \
            "InputGuardrail.validate must have a docstring"

    def test_instantiation_does_not_raise(self):
        cls = get_class(self.m, "InputGuardrail")
        try:
            cls()
        except Exception as e:
            pytest.fail(f"InputGuardrail() raised on instantiation: {e}")


# ---------------------------------------------------------------------------
# ── 5. app/guardrails/output_validation.py ──────────────────────────────────
# ---------------------------------------------------------------------------

class TestOutputValidationGuardrail:

    @pytest.fixture(autouse=True)
    def mod(self):
        self.m = import_module("app.guardrails.output_validation")

    def test_class_exists(self):
        get_class(self.m, "OutputValidationGuardrail")

    def test_validate_method_exists(self):
        cls = get_class(self.m, "OutputValidationGuardrail")
        assert method_exists(cls, "validate")

    def test_validate_signature(self):
        cls = get_class(self.m, "OutputValidationGuardrail")
        sig = inspect.signature(cls.validate)
        params = list(sig.parameters)
        assert "db" in params,    "validate must accept 'db' param"
        assert "reply" in params, "validate must accept 'reply' param"

    def test_class_has_docstring(self):
        cls = get_class(self.m, "OutputValidationGuardrail")
        assert has_docstring(cls)

    def test_validate_docstring_mentions_strict(self):
        cls = get_class(self.m, "OutputValidationGuardrail")
        doc = inspect.getdoc(cls) or ""
        assert "STRICT" in doc or "strict" in doc, \
            "OutputValidationGuardrail docstring must mention STRICT intent"

    def test_instantiation_does_not_raise(self):
        cls = get_class(self.m, "OutputValidationGuardrail")
        try:
            cls()
        except Exception as e:
            pytest.fail(f"OutputValidationGuardrail() raised on instantiation: {e}")


# ---------------------------------------------------------------------------
# ── 6. app/guardrails/output_formatting.py ──────────────────────────────────
# ---------------------------------------------------------------------------

class TestOutputFormattingGuardrail:

    @pytest.fixture(autouse=True)
    def mod(self):
        self.m = import_module("app.guardrails.output_formatting")

    def test_class_exists(self):
        get_class(self.m, "OutputFormattingGuardrail")

    def test_format_method_exists(self):
        cls = get_class(self.m, "OutputFormattingGuardrail")
        assert method_exists(cls, "format"), \
            "OutputFormattingGuardrail must have a 'format' method"

    def test_format_signature(self):
        cls = get_class(self.m, "OutputFormattingGuardrail")
        sig = inspect.signature(cls.format)
        params = list(sig.parameters)
        assert "reply" in params,   "format must accept 'reply' param"
        assert "channel" in params, "format must accept 'channel' param"

    def test_format_channel_defaults_to_whatsapp(self):
        cls = get_class(self.m, "OutputFormattingGuardrail")
        sig = inspect.signature(cls.format)
        default = sig.parameters["channel"].default
        assert default == "whatsapp", \
            "format channel param must default to 'whatsapp'"

    def test_format_is_not_async(self):
        cls = get_class(self.m, "OutputFormattingGuardrail")
        assert not is_async_func(cls.format), \
            "OutputFormattingGuardrail.format must be synchronous"

    def test_instantiation_does_not_raise(self):
        cls = get_class(self.m, "OutputFormattingGuardrail")
        try:
            cls()
        except Exception as e:
            pytest.fail(f"OutputFormattingGuardrail() raised on instantiation: {e}")


# ---------------------------------------------------------------------------
# ── 7. app/parlant_agent/session.py ─────────────────────────────────────────
# ---------------------------------------------------------------------------

class TestAfrisaleSession:

    @pytest.fixture(autouse=True)
    def mod(self):
        self.m = import_module("app.parlant_agent.session")

    def test_class_exists(self):
        get_class(self.m, "AfrisaleSession")

    def test_init_signature(self):
        cls = get_class(self.m, "AfrisaleSession")
        sig = inspect.signature(cls.__init__)
        params = list(sig.parameters)
        assert "customer_id" in params, "__init__ must have 'customer_id'"
        assert "role" in params,        "__init__ must have 'role'"

    def test_run_turn_exists_and_async(self):
        cls = get_class(self.m, "AfrisaleSession")
        assert method_exists(cls, "run_turn"), "AfrisaleSession must have run_turn"
        assert is_async_func(cls.run_turn), "run_turn must be async"

    def test_run_turn_signature(self):
        cls = get_class(self.m, "AfrisaleSession")
        sig = inspect.signature(cls.run_turn)
        params = list(sig.parameters)
        assert "db" in params,        "run_turn must accept 'db'"
        assert "user_text" in params, "run_turn must accept 'user_text'"

    def test_class_docstring_mentions_state_boundary(self):
        cls = get_class(self.m, "AfrisaleSession")
        doc = inspect.getdoc(cls) or ""
        keywords = ["conversation", "turn", "business state", "DB", "SQLite", "tool"]
        matched = [k for k in keywords if k.lower() in doc.lower()]
        assert len(matched) >= 2, \
            "AfrisaleSession docstring must clarify the state boundary " \
            f"(conversation only, DB owns business state). Found keywords: {matched}"

    def test_instantiation_with_valid_args_does_not_raise(self):
        cls = get_class(self.m, "AfrisaleSession")
        try:
            cls(customer_id=1, role="customer")
        except Exception as e:
            pytest.fail(f"AfrisaleSession(customer_id=1, role='customer') raised: {e}")


# ---------------------------------------------------------------------------
# ── 8. app/parlant_agent/engine.py ──────────────────────────────────────────
# ---------------------------------------------------------------------------

class TestBuildEngine:

    @pytest.fixture(autouse=True)
    def mod(self):
        self.m = import_module("app.parlant_agent.engine")

    def test_build_engine_exists(self):
        get_func(self.m, "build_engine")

    def test_build_engine_signature(self):
        fn = get_func(self.m, "build_engine")
        sig = inspect.signature(fn)
        params = list(sig.parameters)
        assert "role" in params, "build_engine must accept 'role'"

    def test_build_engine_has_docstring(self):
        fn = get_func(self.m, "build_engine")
        assert has_docstring(fn)

    def test_build_engine_docstring_mentions_gemini(self):
        fn = get_func(self.m, "build_engine")
        doc = inspect.getdoc(fn) or ""
        assert "gemini" in doc.lower() or "google_api_key" in doc.lower(), \
            "build_engine docstring must reference Gemini / google_api_key"


# ---------------------------------------------------------------------------
# ── 9. app/parlant_agent/guidelines.py ──────────────────────────────────────
# ---------------------------------------------------------------------------

class TestGuidelines:

    @pytest.fixture(autouse=True)
    def mod(self):
        self.m = import_module("app.parlant_agent.guidelines")

    def test_customer_guidelines_exists(self):
        get_func(self.m, "customer_guidelines")

    def test_owner_guidelines_exists(self):
        get_func(self.m, "owner_guidelines")

    def test_customer_guidelines_returns_list(self):
        fn = get_func(self.m, "customer_guidelines")
        result = fn()
        assert result is None or isinstance(result, list), \
            "customer_guidelines must return a list (or None at stub stage)"

    def test_owner_guidelines_returns_list(self):
        fn = get_func(self.m, "owner_guidelines")
        result = fn()
        assert result is None or isinstance(result, list), \
            "owner_guidelines must return a list (or None at stub stage)"

    def test_customer_guidelines_docstring_mentions_delivery(self):
        fn = get_func(self.m, "customer_guidelines")
        doc = inspect.getdoc(fn) or ""
        assert "delivery" in doc.lower(), \
            "customer_guidelines docstring must mention delivery location requirement"

    def test_owner_guidelines_docstring_mentions_catalog(self):
        fn = get_func(self.m, "owner_guidelines")
        doc = inspect.getdoc(fn) or ""
        assert any(k in doc.lower() for k in ["product", "catalog", "stock", "order"]), \
            "owner_guidelines docstring must mention catalog/product/stock/order"


# ---------------------------------------------------------------------------
# ── 10. app/parlant_agent/tool_registry.py ──────────────────────────────────
# ---------------------------------------------------------------------------

class TestToolRegistry:

    @pytest.fixture(autouse=True)
    def mod(self):
        self.m = import_module("app.parlant_agent.tool_registry")

    def test_build_customer_tools_exists(self):
        get_func(self.m, "build_customer_tools")

    def test_build_owner_tools_exists(self):
        get_func(self.m, "build_owner_tools")

    def test_build_customer_tools_signature(self):
        fn = get_func(self.m, "build_customer_tools")
        params = list(inspect.signature(fn).parameters)
        assert "db" in params,          "build_customer_tools must accept 'db'"
        assert "customer_id" in params, "build_customer_tools must accept 'customer_id'"

    def test_build_owner_tools_signature(self):
        fn = get_func(self.m, "build_owner_tools")
        params = list(inspect.signature(fn).parameters)
        assert "db" in params, "build_owner_tools must accept 'db'"

    def test_customer_tools_docstring_mentions_search_products(self):
        """search_products was missing in the original — must be explicit here."""
        fn = get_func(self.m, "build_customer_tools")
        doc = inspect.getdoc(fn) or ""
        assert "search_products" in doc, \
            "build_customer_tools docstring MUST list search_products — " \
            "it was missing in the original and is a required fix"

    def test_customer_tools_docstring_mentions_create_order(self):
        fn = get_func(self.m, "build_customer_tools")
        doc = inspect.getdoc(fn) or ""
        assert "create_order" in doc

    def test_owner_tools_docstring_mentions_add_product(self):
        fn = get_func(self.m, "build_owner_tools")
        doc = inspect.getdoc(fn) or ""
        assert "add_product" in doc or "update_stock" in doc


# ---------------------------------------------------------------------------
# ── 11. app/observability/logger.py ─────────────────────────────────────────
# ---------------------------------------------------------------------------

class TestObservabilityLogger:

    @pytest.fixture(autouse=True)
    def mod(self):
        self.m = import_module("app.observability.logger")

    def test_log_inbound_exists_and_async(self):
        fn = get_func(self.m, "log_inbound")
        assert is_async_func(fn), "log_inbound must be async"

    def test_log_inbound_signature(self):
        fn = get_func(self.m, "log_inbound")
        params = list(inspect.signature(fn).parameters)
        assert "customer_id" in params
        assert "text" in params
        assert "phone" in params

    def test_log_tool_call_exists_and_async(self):
        fn = get_func(self.m, "log_tool_call")
        assert is_async_func(fn), "log_tool_call must be async"

    def test_log_tool_call_signature(self):
        fn = get_func(self.m, "log_tool_call")
        params = list(inspect.signature(fn).parameters)
        assert "customer_id" in params
        assert "tool_name" in params
        assert "args" in params
        assert "result" in params

    def test_log_guardrail_decision_exists_and_async(self):
        fn = get_func(self.m, "log_guardrail_decision")
        assert is_async_func(fn), "log_guardrail_decision must be async"

    def test_log_guardrail_decision_signature(self):
        fn = get_func(self.m, "log_guardrail_decision")
        params = list(inspect.signature(fn).parameters)
        assert "stage" in params
        assert "passed" in params
        assert "reason" in params
        assert "customer_id" in params

    def test_log_final_response_exists_and_async(self):
        fn = get_func(self.m, "log_final_response")
        assert is_async_func(fn), "log_final_response must be async"

    def test_log_final_response_signature(self):
        fn = get_func(self.m, "log_final_response")
        params = list(inspect.signature(fn).parameters)
        assert "customer_id" in params
        assert "reply" in params
        assert "channel" in params

    def test_all_logger_functions_do_not_raise_when_called(self):
        """Stubs must be callable without raising — they're fire-and-forget."""
        loop = asyncio.get_event_loop()
        try:
            loop.run_until_complete(
                self.m.log_inbound(customer_id=1, text="test", phone="+256700000001")
            )
            loop.run_until_complete(
                self.m.log_tool_call(
                    customer_id=1, tool_name="get_catalog", args={}, result=None
                )
            )
            loop.run_until_complete(
                self.m.log_guardrail_decision(
                    stage="input", passed=True, reason="", customer_id=1
                )
            )
            loop.run_until_complete(
                self.m.log_final_response(
                    customer_id=1, reply="Hello", channel="whatsapp"
                )
            )
        except NotImplementedError:
            pass  # acceptable at stub stage
        except Exception as e:
            pytest.fail(f"Logger stub raised unexpectedly: {e}")


# ---------------------------------------------------------------------------
# ── 12. NO LANGCHAIN IMPORTS IN NEW FILES ───────────────────────────────────
# ---------------------------------------------------------------------------

NEW_MODULE_FILES = [
    "app/pipeline/stages.py",
    "app/guardrails/input_guardrail.py",
    "app/guardrails/output_validation.py",
    "app/guardrails/output_formatting.py",
    "app/parlant_agent/session.py",
    "app/parlant_agent/engine.py",
    "app/parlant_agent/guidelines.py",
    "app/parlant_agent/tool_registry.py",
    "app/observability/logger.py",
]


@pytest.mark.parametrize("filepath", NEW_MODULE_FILES)
def test_no_langchain_in_new_files(filepath):
    """New skeleton files must not import LangChain."""
    source = Path(filepath).read_text()
    assert "langchain" not in source.lower(), \
        f"{filepath} must not import LangChain — " \
        "new files use Parlant only. LangChain removal is Phase 5."


@pytest.mark.parametrize("filepath", NEW_MODULE_FILES)
def test_no_run_turn_in_new_files(filepath):
    """New files must not reference the old run_turn function."""
    source = Path(filepath).read_text()
    assert "run_turn" not in source, \
        f"{filepath} references run_turn — use AfrisaleSession.run_turn instead"


@pytest.mark.parametrize("filepath", NEW_MODULE_FILES)
def test_no_handle_inbound_in_new_files(filepath):
    """New files must not call handle_inbound — pipeline runner owns the flow."""
    source = Path(filepath).read_text()
    assert "handle_inbound" not in source, \
        f"{filepath} references handle_inbound — this is being decomposed"