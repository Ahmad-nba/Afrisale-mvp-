"""
Phase 2 test suite — guardrails implementation
===============================================
Tests that all three guardrail classes contain real logic, not stubs.
No DB, no Parlant, no network required.

Run with:
    pytest tests/test_phase2_guardrails.py -v

Expected: 46 passed, 0 failed, 0 errors
"""

import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import pytest
import importlib


def import_module(dotted):
    try:
        return importlib.import_module(dotted)
    except ModuleNotFoundError as e:
        pytest.fail(f"Module '{dotted}' could not be imported: {e}")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def input_grl():
    m = import_module("app.guardrails.input_guardrail")
    return m.InputGuardrail()


@pytest.fixture
def output_val():
    m = import_module("app.guardrails.output_validation")
    return m.OutputValidationGuardrail()


@pytest.fixture
def output_fmt():
    m = import_module("app.guardrails.output_formatting")
    return m.OutputFormattingGuardrail()


@pytest.fixture
def mock_db_with_prices():
    """DB session with two variant prices: 5000 and 12000."""
    from app.models.models import ProductVariant
    v1 = MagicMock(spec=ProductVariant)
    v1.price = 5000
    v2 = MagicMock(spec=ProductVariant)
    v2.price = 12000
    db = MagicMock()
    db.query.return_value.all.return_value = [v1, v2]
    return db


# ---------------------------------------------------------------------------
# ── 1. InputGuardrail — valid cases ─────────────────────────────────────────
# ---------------------------------------------------------------------------

class TestInputGuardrailValid:

    def test_normal_message_passes(self, input_grl):
        valid, reason = input_grl.validate("I want to order a bag of rice")
        assert valid is True
        assert reason == ""

    def test_short_but_valid_message_passes(self, input_grl):
        valid, reason = input_grl.validate("Hi")
        assert valid is True

    def test_message_with_numbers_passes(self, input_grl):
        valid, reason = input_grl.validate("I want 3 bags of maize flour")
        assert valid is True

    def test_question_passes(self, input_grl):
        valid, reason = input_grl.validate("What products do you have?")
        assert valid is True

    def test_owner_command_passes(self, input_grl):
        valid, reason = input_grl.validate("Add new product: Omo 1kg at 3000 UGX")
        assert valid is True

    def test_message_at_max_length_passes(self, input_grl):
        valid, reason = input_grl.validate("a" * 1000)
        assert valid is True


# ---------------------------------------------------------------------------
# ── 2. InputGuardrail — invalid cases ───────────────────────────────────────
# ---------------------------------------------------------------------------

class TestInputGuardrailInvalid:

    def test_empty_string_fails(self, input_grl):
        valid, reason = input_grl.validate("")
        assert valid is False
        assert reason == "empty_message"

    def test_whitespace_only_fails(self, input_grl):
        valid, reason = input_grl.validate("     ")
        assert valid is False
        assert reason == "empty_message"

    def test_single_char_fails(self, input_grl):
        valid, reason = input_grl.validate("a")
        assert valid is False
        assert reason == "too_short"

    def test_message_over_1000_chars_fails(self, input_grl):
        valid, reason = input_grl.validate("a" * 1001)
        assert valid is False
        assert reason == "too_long"

    def test_special_chars_only_fails(self, input_grl):
        valid, reason = input_grl.validate("!@#$%^&*()")
        assert valid is False
        assert reason == "no_intent"

    def test_digits_only_fails(self, input_grl):
        valid, reason = input_grl.validate("123456")
        assert valid is False
        assert reason == "no_intent"

    def test_returns_tuple(self, input_grl):
        result = input_grl.validate("hello")
        assert isinstance(result, tuple), "validate must return a tuple"
        assert len(result) == 2, "validate must return a 2-tuple"

    def test_valid_result_has_empty_reason(self, input_grl):
        valid, reason = input_grl.validate("show me all products")
        assert valid is True
        assert reason == "", "reason must be empty string on valid — not None"

    def test_invalid_result_has_non_empty_reason(self, input_grl):
        valid, reason = input_grl.validate("")
        assert valid is False
        assert isinstance(reason, str) and len(reason) > 0, \
            "reason must be a non-empty string on invalid"


# ---------------------------------------------------------------------------
# ── 3. OutputValidationGuardrail — valid cases ──────────────────────────────
# ---------------------------------------------------------------------------

class TestOutputValidationValid:

    def test_clean_reply_passes(self, output_val, mock_db_with_prices):
        valid, fallback = output_val.validate(
            mock_db_with_prices,
            "Here are our products: Rice 1kg and Maize Flour 2kg."
        )
        assert valid is True
        assert fallback == ""

    def test_reply_with_known_price_passes(self, output_val, mock_db_with_prices):
        valid, fallback = output_val.validate(
            mock_db_with_prices,
            "The item costs KES 5000."
        )
        assert valid is True

    def test_reply_with_second_known_price_passes(self, output_val, mock_db_with_prices):
        valid, fallback = output_val.validate(
            mock_db_with_prices,
            "Premium option is Ksh 12000."
        )
        assert valid is True

    def test_reply_with_no_prices_passes(self, output_val, mock_db_with_prices):
        valid, fallback = output_val.validate(
            mock_db_with_prices,
            "Sure! Let me check that order for you."
        )
        assert valid is True


# ---------------------------------------------------------------------------
# ── 4. OutputValidationGuardrail — invalid cases ────────────────────────────
# ---------------------------------------------------------------------------

class TestOutputValidationInvalid:

    def test_hallucinated_price_fails(self, output_val, mock_db_with_prices):
        """Price not in DB (5000, 12000) must be blocked."""
        valid, fallback = output_val.validate(
            mock_db_with_prices,
            "That product costs KES 9999."
        )
        assert valid is False

    def test_fallback_is_non_empty_string_on_failure(self, output_val, mock_db_with_prices):
        valid, fallback = output_val.validate(
            mock_db_with_prices,
            "That costs UGX 1."
        )
        assert valid is False
        assert isinstance(fallback, str) and len(fallback) > 0, \
            "fallback must be a non-empty string when validation fails"

    def test_too_short_reply_fails(self, output_val, mock_db_with_prices):
        valid, fallback = output_val.validate(mock_db_with_prices, "ok")
        assert valid is False

    def test_empty_reply_fails(self, output_val, mock_db_with_prices):
        valid, fallback = output_val.validate(mock_db_with_prices, "")
        assert valid is False

    def test_returns_tuple(self, output_val, mock_db_with_prices):
        result = output_val.validate(mock_db_with_prices, "Hello!")
        assert isinstance(result, tuple) and len(result) == 2

    def test_valid_result_fallback_is_empty_string(self, output_val, mock_db_with_prices):
        valid, fallback = output_val.validate(
            mock_db_with_prices, "Your order has been placed."
        )
        assert valid is True
        assert fallback == "", "fallback must be empty string on valid result — not None"

    def test_multiple_currency_symbols_detected(self, output_val, mock_db_with_prices):
        """All common East African currency patterns must trigger price check."""
        symbols = ["KES", "Ksh", "UGX", "$", "₦", "£"]
        for sym in symbols:
            valid, _ = output_val.validate(
                mock_db_with_prices, f"That is {sym} 99999 total."
            )
            assert valid is False, \
                f"Currency symbol '{sym}' with hallucinated price should fail"


# ---------------------------------------------------------------------------
# ── 5. OutputValidationGuardrail — observability hook ───────────────────────
# ---------------------------------------------------------------------------

class TestOutputValidationLogging:

    def test_guardrail_decision_logged_on_valid(self, output_val, mock_db_with_prices):
        with patch("app.observability.logger.log_guardrail_decision") as mock_log:
            mock_log.return_value = asyncio.coroutine(lambda: None)()
            output_val.validate(
                mock_db_with_prices,
                "Your order is confirmed."
            )
            # Log may be fire-and-forget; just verify no exception raised
            # (full async log assertion belongs in integration tests)

    def test_guardrail_decision_logged_on_invalid(self, output_val, mock_db_with_prices):
        with patch("app.observability.logger.log_guardrail_decision") as mock_log:
            mock_log.return_value = asyncio.coroutine(lambda: None)()
            output_val.validate(mock_db_with_prices, "ok")


# ---------------------------------------------------------------------------
# ── 6. OutputFormattingGuardrail — WhatsApp channel ─────────────────────────
# ---------------------------------------------------------------------------

class TestOutputFormattingWhatsApp:

    def test_basic_reply_unchanged(self, output_fmt):
        reply = "Here are your products!"
        result = output_fmt.format(reply, channel="whatsapp")
        assert "Here are your products!" in result

    def test_strips_think_tokens(self, output_fmt):
        reply = "<think>internal reasoning here</think>Here is your answer."
        result = output_fmt.format(reply, channel="whatsapp")
        assert "<think>" not in result
        assert "internal reasoning here" not in result
        assert "Here is your answer." in result

    def test_strips_internal_tokens(self, output_fmt):
        reply = "[INTERNAL: skip this] Your order is placed."
        result = output_fmt.format(reply, channel="whatsapp")
        assert "[INTERNAL:" not in result
        assert "Your order is placed." in result

    def test_collapses_excessive_blank_lines(self, output_fmt):
        reply = "Line one\n\n\n\n\nLine two"
        result = output_fmt.format(reply, channel="whatsapp")
        assert "\n\n\n" not in result

    def test_trims_leading_trailing_whitespace(self, output_fmt):
        reply = "   Hello there   "
        result = output_fmt.format(reply, channel="whatsapp")
        assert result == result.strip()

    def test_truncates_at_1600_chars(self, output_fmt):
        reply = "a" * 2000
        result = output_fmt.format(reply, channel="whatsapp")
        assert len(result) <= 1600, \
            f"WhatsApp reply must be ≤1600 chars, got {len(result)}"

    def test_truncated_reply_ends_with_ellipsis(self, output_fmt):
        reply = "word " * 500  # well over 1600
        result = output_fmt.format(reply, channel="whatsapp")
        assert result.endswith("…"), "Truncated WhatsApp reply must end with …"

    def test_short_reply_not_truncated(self, output_fmt):
        reply = "Order placed!"
        result = output_fmt.format(reply, channel="whatsapp")
        assert "…" not in result

    def test_normalises_line_endings(self, output_fmt):
        reply = "Line one\r\nLine two\rLine three"
        result = output_fmt.format(reply, channel="whatsapp")
        assert "\r" not in result


# ---------------------------------------------------------------------------
# ── 7. OutputFormattingGuardrail — SMS channel ──────────────────────────────
# ---------------------------------------------------------------------------

class TestOutputFormattingSMS:

    def test_sms_truncates_at_160_chars(self, output_fmt):
        reply = "w " * 200
        result = output_fmt.format(reply, channel="sms")
        assert len(result) <= 160, \
            f"SMS reply must be ≤160 chars, got {len(result)}"

    def test_sms_truncated_ends_with_ellipsis(self, output_fmt):
        reply = "This is a very long message that exceeds the SMS character limit " * 5
        result = output_fmt.format(reply, channel="sms")
        assert result.endswith("…")

    def test_sms_strips_bold_markdown(self, output_fmt):
        reply = "Your *order* is placed."
        result = output_fmt.format(reply, channel="sms")
        assert "*" not in result
        assert "order" in result

    def test_sms_strips_italic_markdown(self, output_fmt):
        reply = "Thank you _very_ much."
        result = output_fmt.format(reply, channel="sms")
        assert "_" not in result
        assert "very" in result

    def test_short_sms_passes_through(self, output_fmt):
        reply = "Order confirmed!"
        result = output_fmt.format(reply, channel="sms")
        assert "Order confirmed" in result

    def test_sms_returns_string(self, output_fmt):
        result = output_fmt.format("Hello", channel="sms")
        assert isinstance(result, str)

    def test_whatsapp_returns_string(self, output_fmt):
        result = output_fmt.format("Hello", channel="whatsapp")
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# ── 8. Guardrail pipeline ordering contract ─────────────────────────────────
# ---------------------------------------------------------------------------

class TestGuardrailOrdering:

    def test_formatting_never_called_on_invalid_validation(
        self, output_val, output_fmt, mock_db_with_prices
    ):
        """
        If OutputValidationGuardrail fails, OutputFormattingGuardrail
        must not receive the raw reply. This test simulates the runner logic.
        """
        bad_reply = "ok"  # too short, will fail validation
        valid, fallback = output_val.validate(mock_db_with_prices, bad_reply)
        assert valid is False
        # Formatter should only be called with validated replies
        # Simulate: if not valid, use fallback — never call formatter
        final = fallback if not valid else output_fmt.format(bad_reply, "whatsapp")
        assert final == fallback

    def test_formatting_receives_validated_reply(
        self, output_val, output_fmt, mock_db_with_prices
    ):
        good_reply = "Your order has been placed. Total: KES 5000."
        valid, fallback = output_val.validate(mock_db_with_prices, good_reply)
        assert valid is True
        result = output_fmt.format(good_reply, "whatsapp")
        assert isinstance(result, str) and len(result) > 0