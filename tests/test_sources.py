"""Tests for source alias resolution and live source discovery helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from perplexity_web_mcp.enums import SearchFocus
from perplexity_web_mcp.sources import (
    AvailableSource,
    aliases_for_source_id,
    fetch_available_sources,
    filter_premium_sources,
    resolve_source_focus,
)


class TestResolveSourceFocus:
    """Verify source alias expansion and validation."""

    def test_builtin_aliases(self) -> None:
        sources, search_focus = resolve_source_focus("academic")
        assert sources == ["scholar"]
        assert search_focus is SearchFocus.WEB

    def test_comma_separated_sources(self) -> None:
        sources, search_focus = resolve_source_focus("web,github")
        assert sources == ["web", "github_mcp_direct"]
        assert search_focus is SearchFocus.WEB

    def test_none_is_exclusive(self) -> None:
        with pytest.raises(ValueError, match="cannot be combined"):
            resolve_source_focus("none,web")

    def test_raw_source_id_passthrough(self) -> None:
        sources, search_focus = resolve_source_focus("github_mcp_direct")
        assert sources == ["github_mcp_direct"]
        assert search_focus is SearchFocus.WEB

    @patch("perplexity_web_mcp.sources.fetch_available_sources")
    @patch("perplexity_web_mcp.sources.load_token", return_value="token")
    def test_dynamic_alias_uses_live_sources(self, mock_token: MagicMock, mock_fetch: MagicMock) -> None:
        from perplexity_web_mcp.sources import AvailableSource

        mock_fetch.return_value = [
            AvailableSource(source_id="linear_alt", aliases=("linear",), auth_type="oauth", connected=False),
        ]

        sources, _ = resolve_source_focus("linear")
        assert sources == ["linear_alt"]


class TestAliasesForSourceId:
    """Verify raw source IDs produce useful aliases."""

    def test_builtin_aliases(self) -> None:
        assert aliases_for_source_id("scholar") == ["academic", "scholar"]

    def test_cashmere_source_alias(self) -> None:
        assert aliases_for_source_id("wiley_mcp_cashmere") == ["wiley"]

    def test_direct_source_alias(self) -> None:
        assert aliases_for_source_id("github_mcp_direct") == ["github"]


class TestFetchAvailableSources:
    """Verify live source discovery merges settings and limit data safely."""

    @patch("perplexity_web_mcp.sources.fetch_rate_limits")
    @patch("perplexity_web_mcp.sources._create_session")
    def test_fetch_available_sources_merges_connectors_and_limits(
        self, mock_session_factory: MagicMock, mock_fetch_limits: MagicMock
    ) -> None:
        session = MagicMock()
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "sources": {
                "source_to_limit": {
                    "wiley_mcp_cashmere": {"monthly_limit": 50, "remaining": 23},
                    "web": {"monthly_limit": None, "remaining": None},
                }
            },
            "connectors": {
                "connectors": [
                    {
                        "source_id": "github_mcp_direct",
                        "auth_type": "oauth",
                        "connected": True,
                        "has_required_scopes": False,
                        "capabilities": {"direct_api_search": True},
                    }
                ]
            },
        }
        session.get.return_value = response
        mock_session_factory.return_value.__enter__.return_value = session
        mock_fetch_limits.return_value = None

        available = fetch_available_sources("token")
        assert available is not None

        github = next(source for source in available if source.source_id == "github_mcp_direct")
        assert github.aliases == ("github",)
        assert github.status == "missing scopes"

        wiley = next(source for source in available if source.source_id == "wiley_mcp_cashmere")
        assert wiley.remaining == 23
        assert wiley.remaining_label == "23/50"


class TestFilterPremiumSources:
    """Verify premium source filtering and is_premium property."""

    def test_is_premium_true_for_metered(self) -> None:
        src = AvailableSource(source_id="wiley_mcp_cashmere", monthly_limit=50, remaining=23)
        assert src.is_premium is True

    def test_is_premium_false_for_unlimited(self) -> None:
        src = AvailableSource(source_id="web", monthly_limit=None, remaining=None)
        assert src.is_premium is False

    def test_is_premium_false_for_zero_limit(self) -> None:
        src = AvailableSource(source_id="box", monthly_limit=0, remaining=0)
        assert src.is_premium is False

    def test_filters_to_only_metered_sources(self) -> None:
        sources = [
            AvailableSource(source_id="web", monthly_limit=None, remaining=None),
            AvailableSource(source_id="wiley_mcp_cashmere", monthly_limit=50, remaining=23),
            AvailableSource(source_id="box", monthly_limit=0, remaining=0),
            AvailableSource(source_id="statista_mcp_cashmere", monthly_limit=50, remaining=1),
        ]
        result = filter_premium_sources(sources)
        assert len(result) == 2
        assert result[0].source_id == "wiley_mcp_cashmere"
        assert result[1].source_id == "statista_mcp_cashmere"

    def test_empty_list_returns_empty(self) -> None:
        assert filter_premium_sources([]) == []

    def test_no_premium_returns_empty(self) -> None:
        sources = [
            AvailableSource(source_id="web", monthly_limit=None, remaining=None),
            AvailableSource(source_id="scholar", monthly_limit=None, remaining=None),
        ]
        assert filter_premium_sources(sources) == []
