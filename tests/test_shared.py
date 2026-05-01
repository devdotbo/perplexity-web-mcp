"""Tests for the shared module (model mappings, resolve_model, ask)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from perplexity_web_mcp.exceptions import AuthenticationError, RateLimitError
from perplexity_web_mcp.models import Model, Models
from perplexity_web_mcp.rate_limits import RateLimits
from perplexity_web_mcp.router import SmartResponse
from perplexity_web_mcp.shared import (
    MODEL_MAP,
    MODEL_NAMES,
    SOURCE_FOCUS_MAP,
    SOURCE_FOCUS_NAMES,
    ask,
    check_limits_before_query,
    resolve_model,
    smart_ask,
)


# ============================================================================
# 1. MODEL_MAP and SOURCE_FOCUS_MAP constants
# ============================================================================


class TestMappings:
    """Verify the shared mapping dictionaries are well-formed."""

    def test_model_map_has_all_expected_keys(self) -> None:
        expected = {"auto", "sonar", "deep_research", "gpt54", "gpt55", "claude_sonnet",
                    "claude_opus", "gemini_pro", "nemotron", "kimi_k26"}
        assert set(MODEL_MAP.keys()) == expected

    def test_model_names_matches_map_keys(self) -> None:
        assert MODEL_NAMES == list(MODEL_MAP.keys())

    def test_source_focus_map_has_all_expected_keys(self) -> None:
        expected = {
            "none",
            "web",
            "academic",
            "social",
            "finance",
            "all",
            "github",
            "wiley",
            "cbinsights",
            "pitchbook",
            "statista",
        }
        assert set(SOURCE_FOCUS_MAP.keys()) == expected

    def test_source_focus_names_matches_map_keys(self) -> None:
        assert SOURCE_FOCUS_NAMES == list(SOURCE_FOCUS_MAP.keys())

    def test_every_model_tuple_has_model_instances(self) -> None:
        for name, (base, thinking) in MODEL_MAP.items():
            assert isinstance(base, Model), f"{name} base is not a Model"
            assert thinking is None or isinstance(thinking, Model), f"{name} thinking is not Model|None"

    def test_source_focus_values_are_lists(self) -> None:
        for name, sources in SOURCE_FOCUS_MAP.items():
            assert isinstance(sources, list), f"{name} value is not a list"
            if name != "none":
                assert len(sources) >= 1, f"{name} has empty source list"

    def test_none_source_focus_has_empty_list(self) -> None:
        assert SOURCE_FOCUS_MAP["none"] == []


# ============================================================================
# 2. resolve_model
# ============================================================================


class TestResolveModel:
    """Test resolve_model with various inputs."""

    def test_auto_returns_best(self) -> None:
        assert resolve_model("auto") is Models.BEST

    def test_auto_thinking_still_returns_best(self) -> None:
        # auto has no thinking variant (None)
        assert resolve_model("auto", thinking=True) is Models.BEST

    def test_nemotron_base(self) -> None:
        assert resolve_model("nemotron") is Models.NEMOTRON_3_SUPER

    def test_nemotron_thinking(self) -> None:
        assert resolve_model("nemotron", thinking=True) is Models.NEMOTRON_3_SUPER

    def test_claude_sonnet_base(self) -> None:
        assert resolve_model("claude_sonnet") is Models.CLAUDE_46_SONNET

    def test_claude_sonnet_thinking(self) -> None:
        assert resolve_model("claude_sonnet", thinking=True) is Models.CLAUDE_46_SONNET_THINKING

    def test_gemini_pro_always_thinking(self) -> None:
        # gemini_pro has no non-thinking variant
        assert resolve_model("gemini_pro") is Models.GEMINI_31_PRO_THINKING
        assert resolve_model("gemini_pro", thinking=True) is Models.GEMINI_31_PRO_THINKING

    def test_nemotron_always_thinking(self) -> None:
        # nemotron is reasoning-only, always thinking
        assert resolve_model("nemotron") is Models.NEMOTRON_3_SUPER
        assert resolve_model("nemotron", thinking=True) is Models.NEMOTRON_3_SUPER

    def test_unknown_model_falls_back_to_best(self) -> None:
        assert resolve_model("nonexistent") is Models.BEST

    def test_unknown_model_thinking_still_falls_back(self) -> None:
        assert resolve_model("nonexistent", thinking=True) is Models.BEST

    def test_deep_research(self) -> None:
        assert resolve_model("deep_research") is Models.DEEP_RESEARCH

    def test_all_models_resolve_without_error(self) -> None:
        for name in MODEL_NAMES:
            model = resolve_model(name)
            assert isinstance(model, Model)
            model_t = resolve_model(name, thinking=True)
            assert isinstance(model_t, Model)


# ============================================================================
# 3. ask function (mocked)
# ============================================================================


class TestAsk:
    """Test the shared ask() function with mocked Perplexity client."""

    @patch("perplexity_web_mcp.shared.check_limits_before_query", return_value=None)
    @patch("perplexity_web_mcp.shared.get_limit_cache", return_value=None)
    @patch("perplexity_web_mcp.shared.get_client")
    def test_successful_query_returns_answer(
        self, mock_client_fn: MagicMock, mock_cache: MagicMock, mock_limits: MagicMock
    ) -> None:
        mock_conv = MagicMock()
        mock_conv.answer = "The answer is 42"
        mock_conv.search_results = []
        mock_client = MagicMock()
        mock_client.create_conversation.return_value = mock_conv
        mock_client_fn.return_value = mock_client

        result = ask("question", Models.BEST)
        assert result == "The answer is 42"

    @patch("perplexity_web_mcp.shared.check_limits_before_query", return_value=None)
    @patch("perplexity_web_mcp.shared.get_limit_cache", return_value=None)
    @patch("perplexity_web_mcp.shared.get_client")
    def test_successful_query_includes_citations(
        self, mock_client_fn: MagicMock, mock_cache: MagicMock, mock_limits: MagicMock
    ) -> None:
        from perplexity_web_mcp.types import SearchResultItem

        mock_conv = MagicMock()
        mock_conv.answer = "Answer text"
        mock_conv.search_results = [
            SearchResultItem(title="S1", url="https://a.com"),
            SearchResultItem(title="S2", url="https://b.com"),
        ]
        mock_client = MagicMock()
        mock_client.create_conversation.return_value = mock_conv
        mock_client_fn.return_value = mock_client

        result = ask("question", Models.BEST)
        assert "Answer text" in result
        assert "Citations:" in result
        assert "[1]: https://a.com" in result
        assert "[2]: https://b.com" in result

    @patch("perplexity_web_mcp.shared.check_limits_before_query", return_value=None)
    @patch("perplexity_web_mcp.shared.get_limit_cache", return_value=None)
    @patch("perplexity_web_mcp.shared.get_client")
    def test_no_answer_returns_no_answer_received(
        self, mock_client_fn: MagicMock, mock_cache: MagicMock, mock_limits: MagicMock
    ) -> None:
        mock_conv = MagicMock()
        mock_conv.answer = None
        mock_conv.search_results = []
        mock_client = MagicMock()
        mock_client.create_conversation.return_value = mock_conv
        mock_client_fn.return_value = mock_client

        result = ask("question", Models.BEST)
        assert result == "No answer received"

    @patch("perplexity_web_mcp.shared.check_limits_before_query", return_value=None)
    @patch("perplexity_web_mcp.shared.get_limit_cache", return_value=None)
    @patch("perplexity_web_mcp.shared.get_client")
    def test_exception_returns_error_string(
        self, mock_client_fn: MagicMock, mock_cache: MagicMock, mock_limits: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_client.create_conversation.side_effect = RuntimeError("Network failure")
        mock_client_fn.return_value = mock_client

        result = ask("question", Models.BEST)
        assert "Error" in result
        assert "Network failure" in result

    @patch("perplexity_web_mcp.shared.check_limits_before_query", return_value=None)
    @patch("perplexity_web_mcp.shared.get_limit_cache", return_value=None)
    @patch("perplexity_web_mcp.shared.get_client")
    def test_none_source_uses_writing_mode(
        self, mock_client_fn: MagicMock, mock_cache: MagicMock, mock_limits: MagicMock
    ) -> None:
        from perplexity_web_mcp.enums import SearchFocus

        mock_conv = MagicMock()
        mock_conv.answer = "Model-only answer"
        mock_conv.search_results = []
        mock_client = MagicMock()
        mock_client.create_conversation.return_value = mock_conv
        mock_client_fn.return_value = mock_client

        result = ask("question", Models.BEST, "none")
        assert result == "Model-only answer"

        config = mock_client.create_conversation.call_args[0][0]
        assert config.search_focus == SearchFocus.WRITING
        assert config.source_focus == []

    @patch("perplexity_web_mcp.shared.check_limits_before_query", return_value=None)
    @patch("perplexity_web_mcp.shared.get_limit_cache", return_value=None)
    @patch("perplexity_web_mcp.shared.get_client")
    def test_web_source_uses_web_mode(
        self, mock_client_fn: MagicMock, mock_cache: MagicMock, mock_limits: MagicMock
    ) -> None:
        from perplexity_web_mcp.enums import SearchFocus

        mock_conv = MagicMock()
        mock_conv.answer = "Web answer"
        mock_conv.search_results = []
        mock_client = MagicMock()
        mock_client.create_conversation.return_value = mock_conv
        mock_client_fn.return_value = mock_client

        result = ask("question", Models.BEST, "web")
        assert result == "Web answer"

        config = mock_client.create_conversation.call_args[0][0]
        assert config.search_focus == SearchFocus.WEB

    @patch("perplexity_web_mcp.shared.check_limits_before_query", return_value=None)
    @patch("perplexity_web_mcp.shared.get_limit_cache", return_value=None)
    @patch("perplexity_web_mcp.shared.get_client")
    def test_github_alias_resolves_to_raw_source_id(
        self, mock_client_fn: MagicMock, mock_cache: MagicMock, mock_limits: MagicMock
    ) -> None:
        mock_conv = MagicMock()
        mock_conv.answer = "GitHub answer"
        mock_conv.search_results = []
        mock_client = MagicMock()
        mock_client.create_conversation.return_value = mock_conv
        mock_client_fn.return_value = mock_client

        result = ask("question", Models.BEST, "github")
        assert result == "GitHub answer"

        config = mock_client.create_conversation.call_args[0][0]
        assert config.source_focus == ["github_mcp_direct"]

    @patch("perplexity_web_mcp.shared.check_limits_before_query", return_value=None)
    @patch("perplexity_web_mcp.shared.get_limit_cache", return_value=None)
    @patch("perplexity_web_mcp.shared.get_client")
    def test_comma_separated_sources_resolve(
        self, mock_client_fn: MagicMock, mock_cache: MagicMock, mock_limits: MagicMock
    ) -> None:
        mock_conv = MagicMock()
        mock_conv.answer = "Combined answer"
        mock_conv.search_results = []
        mock_client = MagicMock()
        mock_client.create_conversation.return_value = mock_conv
        mock_client_fn.return_value = mock_client

        result = ask("question", Models.BEST, "web,github")
        assert result == "Combined answer"

        config = mock_client.create_conversation.call_args[0][0]
        assert config.source_focus == ["web", "github_mcp_direct"]


# ============================================================================
# 4. smart_ask function (mocked)
# ============================================================================


class TestSmartAsk:
    """Test the shared smart_ask() function with mocked Perplexity client."""

    @patch("perplexity_web_mcp.shared.get_limit_cache", return_value=None)
    @patch("perplexity_web_mcp.shared.get_client")
    def test_returns_smart_response(self, mock_client_fn: MagicMock, mock_cache: MagicMock) -> None:
        mock_conv = MagicMock()
        mock_conv.answer = "Smart answer"
        mock_conv.search_results = []
        mock_client = MagicMock()
        mock_client.create_conversation.return_value = mock_conv
        mock_client_fn.return_value = mock_client

        result = smart_ask("question")
        assert isinstance(result, SmartResponse)
        assert result.answer == "Smart answer"

    @patch("perplexity_web_mcp.shared.get_limit_cache", return_value=None)
    @patch("perplexity_web_mcp.shared.get_client")
    def test_quick_intent_uses_sonar(self, mock_client_fn: MagicMock, mock_cache: MagicMock) -> None:
        mock_conv = MagicMock()
        mock_conv.answer = "Quick answer"
        mock_conv.search_results = []
        mock_client = MagicMock()
        mock_client.create_conversation.return_value = mock_conv
        mock_client_fn.return_value = mock_client

        result = smart_ask("question", intent="quick")
        assert result.routing.model_name == "sonar"

    @patch("perplexity_web_mcp.shared.get_limit_cache")
    @patch("perplexity_web_mcp.shared.get_client")
    def test_downgrades_when_exhausted(self, mock_client_fn: MagicMock, mock_cache_fn: MagicMock) -> None:
        limits = RateLimits(remaining_pro=0, remaining_research=0)
        mock_cache = MagicMock()
        mock_cache.get_rate_limits.return_value = limits
        mock_cache_fn.return_value = mock_cache

        mock_conv = MagicMock()
        mock_conv.answer = "Downgraded answer"
        mock_conv.search_results = []
        mock_client = MagicMock()
        mock_client.create_conversation.return_value = mock_conv
        mock_client_fn.return_value = mock_client

        result = smart_ask("question", intent="detailed")
        assert result.routing.model_name == "sonar"
        assert result.routing.was_downgraded is True

    @patch("perplexity_web_mcp.shared.get_limit_cache", return_value=None)
    @patch("perplexity_web_mcp.shared.get_client")
    def test_error_returns_smart_response_with_error(self, mock_client_fn: MagicMock, mock_cache: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.create_conversation.side_effect = RuntimeError("Boom")
        mock_client_fn.return_value = mock_client

        result = smart_ask("question")
        assert isinstance(result, SmartResponse)
        assert "Error" in result.answer
        assert "Boom" in result.answer
        assert result.citations == []

    @patch("perplexity_web_mcp.shared.get_limit_cache", return_value=None)
    @patch("perplexity_web_mcp.shared.get_client")
    def test_invalid_intent_defaults_to_standard(self, mock_client_fn: MagicMock, mock_cache: MagicMock) -> None:
        mock_conv = MagicMock()
        mock_conv.answer = "Fallback answer"
        mock_conv.search_results = []
        mock_client = MagicMock()
        mock_client.create_conversation.return_value = mock_conv
        mock_client_fn.return_value = mock_client

        result = smart_ask("question", intent="bogus")
        assert result.routing.intent.value == "standard"

    @patch("perplexity_web_mcp.shared.get_limit_cache", return_value=None)
    @patch("perplexity_web_mcp.shared.get_client")
    def test_none_source_uses_writing_mode(self, mock_client_fn: MagicMock, mock_cache: MagicMock) -> None:
        from perplexity_web_mcp.enums import SearchFocus

        mock_conv = MagicMock()
        mock_conv.answer = "Model-only smart answer"
        mock_conv.search_results = []
        mock_client = MagicMock()
        mock_client.create_conversation.return_value = mock_conv
        mock_client_fn.return_value = mock_client

        result = smart_ask("question", source_focus="none")
        assert isinstance(result, SmartResponse)
        assert result.answer == "Model-only smart answer"

        config = mock_client.create_conversation.call_args[0][0]
        assert config.search_focus == SearchFocus.WRITING
        assert config.source_focus == []

    def test_invalid_source_returns_error(self) -> None:
        result = smart_ask("question", source_focus="none,web")
        assert "Error" in result.answer


# ============================================================================
# 5. isError propagation — AuthenticationError and RateLimitError raise
# ============================================================================


class TestAskErrorPropagation:
    """Verify AuthenticationError and RateLimitError propagate from ask()
    instead of being swallowed into return strings (MCP isError fix)."""

    @patch("perplexity_web_mcp.shared.check_limits_before_query", return_value=None)
    @patch("perplexity_web_mcp.shared.load_token", return_value=None)
    @patch("perplexity_web_mcp.shared.reset_client")
    @patch("perplexity_web_mcp.shared.get_client")
    def test_auth_error_raises(
        self,
        mock_client_fn: MagicMock,
        mock_reset: MagicMock,
        mock_load: MagicMock,
        mock_limits: MagicMock,
    ) -> None:
        mock_client = MagicMock()
        mock_client.create_conversation.return_value.ask.side_effect = AuthenticationError()
        mock_client_fn.return_value = mock_client

        with pytest.raises(AuthenticationError):
            ask("question", Models.BEST)

    @patch("perplexity_web_mcp.shared.check_limits_before_query", return_value=None)
    @patch("perplexity_web_mcp.shared.get_client")
    def test_rate_limit_error_raises(
        self,
        mock_client_fn: MagicMock,
        mock_limits: MagicMock,
    ) -> None:
        mock_client = MagicMock()
        mock_client.create_conversation.return_value.ask.side_effect = RateLimitError()
        mock_client_fn.return_value = mock_client

        with pytest.raises(RateLimitError):
            ask("question", Models.BEST)

    @patch("perplexity_web_mcp.shared.check_limits_before_query", return_value=None)
    @patch("perplexity_web_mcp.shared.get_limit_cache", return_value=None)
    @patch("perplexity_web_mcp.shared.get_client")
    def test_generic_error_still_returns_string(
        self,
        mock_client_fn: MagicMock,
        mock_cache: MagicMock,
        mock_limits: MagicMock,
    ) -> None:
        mock_client = MagicMock()
        mock_client.create_conversation.side_effect = RuntimeError("Network failure")
        mock_client_fn.return_value = mock_client

        result = ask("question", Models.BEST)
        assert isinstance(result, str)
        assert "Network failure" in result


class TestSmartAskErrorPropagation:
    """Verify AuthenticationError and RateLimitError propagate from smart_ask()."""

    @patch("perplexity_web_mcp.shared.get_limit_cache", return_value=None)
    @patch("perplexity_web_mcp.shared.load_token", return_value=None)
    @patch("perplexity_web_mcp.shared.reset_client")
    @patch("perplexity_web_mcp.shared.get_client")
    def test_auth_error_raises(
        self,
        mock_client_fn: MagicMock,
        mock_reset: MagicMock,
        mock_load: MagicMock,
        mock_cache: MagicMock,
    ) -> None:
        mock_client = MagicMock()
        mock_client.create_conversation.return_value.ask.side_effect = AuthenticationError()
        mock_client_fn.return_value = mock_client

        with pytest.raises(AuthenticationError):
            smart_ask("question")

    @patch("perplexity_web_mcp.shared.get_limit_cache", return_value=None)
    @patch("perplexity_web_mcp.shared.get_client")
    def test_rate_limit_error_raises(
        self,
        mock_client_fn: MagicMock,
        mock_cache: MagicMock,
    ) -> None:
        mock_client = MagicMock()
        mock_client.create_conversation.return_value.ask.side_effect = RateLimitError()
        mock_client_fn.return_value = mock_client

        with pytest.raises(RateLimitError):
            smart_ask("question")

    @patch("perplexity_web_mcp.shared.get_limit_cache", return_value=None)
    @patch("perplexity_web_mcp.shared.get_client")
    def test_generic_error_returns_smart_response(
        self,
        mock_client_fn: MagicMock,
        mock_cache: MagicMock,
    ) -> None:
        mock_client = MagicMock()
        mock_client.create_conversation.side_effect = RuntimeError("Boom")
        mock_client_fn.return_value = mock_client

        result = smart_ask("question")
        assert isinstance(result, SmartResponse)
        assert "Boom" in result.answer


# ============================================================================
# 6. Token-from-disk retry on AuthenticationError
# ============================================================================


class TestTokenRetryOnAuthError:
    """Verify that ask() retries with a fresh token when the token file changed."""

    @patch("perplexity_web_mcp.shared.check_limits_before_query", return_value=None)
    @patch("perplexity_web_mcp.shared.get_limit_cache", return_value=None)
    @patch("perplexity_web_mcp.shared.load_token", return_value="new-token-from-disk")
    @patch("perplexity_web_mcp.shared.reset_client")
    @patch("perplexity_web_mcp.shared.get_client")
    def test_ask_retries_when_token_changed(
        self,
        mock_client_fn: MagicMock,
        mock_reset: MagicMock,
        mock_load: MagicMock,
        mock_cache: MagicMock,
        mock_limits: MagicMock,
    ) -> None:
        import perplexity_web_mcp.shared as shared

        shared._client_token = "old-stale-token"

        mock_conv_fail = MagicMock()
        mock_conv_fail.ask.side_effect = AuthenticationError()
        mock_conv_ok = MagicMock()
        mock_conv_ok.ask.return_value = None
        mock_conv_ok.answer = "Retried answer"
        mock_conv_ok.search_results = []

        mock_client = MagicMock()
        mock_client.create_conversation.side_effect = [mock_conv_fail, mock_conv_ok]
        mock_client_fn.return_value = mock_client

        result = ask("question", Models.BEST)
        assert result == "Retried answer"
        mock_reset.assert_called_once()

    @patch("perplexity_web_mcp.shared.check_limits_before_query", return_value=None)
    @patch("perplexity_web_mcp.shared.load_token", return_value="same-token")
    @patch("perplexity_web_mcp.shared.reset_client")
    @patch("perplexity_web_mcp.shared.get_client")
    def test_ask_does_not_retry_when_token_unchanged(
        self,
        mock_client_fn: MagicMock,
        mock_reset: MagicMock,
        mock_load: MagicMock,
        mock_limits: MagicMock,
    ) -> None:
        import perplexity_web_mcp.shared as shared

        shared._client_token = "same-token"

        mock_client = MagicMock()
        mock_client.create_conversation.return_value.ask.side_effect = AuthenticationError()
        mock_client_fn.return_value = mock_client

        with pytest.raises(AuthenticationError):
            ask("question", Models.BEST)

    @patch("perplexity_web_mcp.shared.get_limit_cache", return_value=None)
    @patch("perplexity_web_mcp.shared.load_token", return_value="new-token-from-disk")
    @patch("perplexity_web_mcp.shared.reset_client")
    @patch("perplexity_web_mcp.shared.get_client")
    def test_smart_ask_retries_when_token_changed(
        self,
        mock_client_fn: MagicMock,
        mock_reset: MagicMock,
        mock_load: MagicMock,
        mock_cache: MagicMock,
    ) -> None:
        import perplexity_web_mcp.shared as shared

        shared._client_token = "old-stale-token"

        mock_conv_fail = MagicMock()
        mock_conv_fail.ask.side_effect = AuthenticationError()
        mock_conv_ok = MagicMock()
        mock_conv_ok.ask.return_value = None
        mock_conv_ok.answer = "Retried smart answer"
        mock_conv_ok.search_results = []

        mock_client = MagicMock()
        mock_client.create_conversation.side_effect = [mock_conv_fail, mock_conv_ok]
        mock_client_fn.return_value = mock_client

        result = smart_ask("question")
        assert isinstance(result, SmartResponse)
        assert result.answer == "Retried smart answer"
        mock_reset.assert_called_once()


# ============================================================================
# 8. Pre-query source guard
# ============================================================================


class TestCheckLimitsSourceGuard:
    """Verify check_limits_before_query blocks on exhausted premium sources."""

    @patch("perplexity_web_mcp.shared.get_limit_cache")
    def test_exhausted_source_returns_error(self, mock_cache_fn: MagicMock) -> None:
        from perplexity_web_mcp.rate_limits import SourceLimit

        mock_cache = MagicMock()
        mock_cache.get_rate_limits.return_value = RateLimits(
            remaining_pro=100,
            remaining_research=5,
            source_limits=[
                SourceLimit(source_id="statista_mcp_cashmere", monthly_limit=50, remaining=0),
            ],
        )
        mock_cache_fn.return_value = mock_cache

        result = check_limits_before_query(Models.BEST, resolved_sources=["statista_mcp_cashmere"])
        assert result is not None
        assert "LIMIT REACHED" in result
        assert "statista_mcp_cashmere" in result

    @patch("perplexity_web_mcp.shared.get_limit_cache")
    def test_healthy_source_returns_none(self, mock_cache_fn: MagicMock) -> None:
        from perplexity_web_mcp.rate_limits import SourceLimit

        mock_cache = MagicMock()
        mock_cache.get_rate_limits.return_value = RateLimits(
            remaining_pro=100,
            remaining_research=5,
            source_limits=[
                SourceLimit(source_id="wiley_mcp_cashmere", monthly_limit=50, remaining=23),
            ],
        )
        mock_cache_fn.return_value = mock_cache

        result = check_limits_before_query(Models.BEST, resolved_sources=["wiley_mcp_cashmere"])
        assert result is None

    @patch("perplexity_web_mcp.shared.get_limit_cache")
    def test_no_sources_skips_check(self, mock_cache_fn: MagicMock) -> None:
        mock_cache = MagicMock()
        mock_cache.get_rate_limits.return_value = RateLimits(remaining_pro=100, remaining_research=5)
        mock_cache_fn.return_value = mock_cache

        result = check_limits_before_query(Models.BEST, resolved_sources=None)
        assert result is None

    @patch("perplexity_web_mcp.shared.get_limit_cache")
    def test_unlimited_source_never_blocks(self, mock_cache_fn: MagicMock) -> None:
        from perplexity_web_mcp.rate_limits import SourceLimit

        mock_cache = MagicMock()
        mock_cache.get_rate_limits.return_value = RateLimits(
            remaining_pro=100,
            remaining_research=5,
            source_limits=[
                SourceLimit(source_id="web", monthly_limit=None, remaining=None),
            ],
        )
        mock_cache_fn.return_value = mock_cache

        result = check_limits_before_query(Models.BEST, resolved_sources=["web"])
        assert result is None

    @patch("perplexity_web_mcp.shared.get_limit_cache")
    def test_source_not_in_query_not_blocked(self, mock_cache_fn: MagicMock) -> None:
        from perplexity_web_mcp.rate_limits import SourceLimit

        mock_cache = MagicMock()
        mock_cache.get_rate_limits.return_value = RateLimits(
            remaining_pro=100,
            remaining_research=5,
            source_limits=[
                SourceLimit(source_id="statista_mcp_cashmere", monthly_limit=50, remaining=0),
            ],
        )
        mock_cache_fn.return_value = mock_cache

        # Query uses web, not statista -- should not block
        result = check_limits_before_query(Models.BEST, resolved_sources=["web"])
        assert result is None
