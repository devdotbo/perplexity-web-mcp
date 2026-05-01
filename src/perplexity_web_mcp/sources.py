"""Source alias resolution and live source discovery."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Sequence

from .constants import API_BASE_URL, ENDPOINT_USER_SETTINGS
from .enums import SearchFocus, SourceFocus
from .logging import get_logger
from .rate_limits import _create_session, fetch_rate_limits
from .token_store import load_token


logger = get_logger(__name__)


COMMON_SOURCE_FOCUS_ALIASES: dict[str, list[str]] = {
    "none": [],
    "web": [SourceFocus.WEB.value],
    "academic": [SourceFocus.ACADEMIC.value],
    "scholar": [SourceFocus.ACADEMIC.value],
    "social": [SourceFocus.SOCIAL.value],
    "finance": [SourceFocus.FINANCE.value],
    "edgar": [SourceFocus.FINANCE.value],
    "all": [SourceFocus.WEB.value, SourceFocus.ACADEMIC.value, SourceFocus.SOCIAL.value],
    "github": ["github_mcp_direct"],
    "wiley": ["wiley_mcp_cashmere"],
    "cbinsights": ["cbinsights_mcp_cashmere"],
    "pitchbook": ["pitchbook_mcp_cashmere"],
    "statista": ["statista_mcp_cashmere"],
}

COMMON_SOURCE_FOCUS_NAMES: list[str] = [
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
]

_CANONICAL_SEPARATORS = re.compile(r"[\s_-]+")
_VALID_SOURCE_TOKEN = re.compile(r"^[A-Za-z0-9_-]+$")
_SOURCE_SUFFIXES = ("_mcp_cashmere", "_mcp_direct", "_mcp_merge", "_alt")
_COMMON_ALIAS_MAP_CANONICAL = {
    re.sub(r"[\s_-]+", "", alias).lower(): values for alias, values in COMMON_SOURCE_FOCUS_ALIASES.items()
}


def canonicalize_source_token(token: str) -> str:
    """Normalize a user-facing source token for alias lookup."""
    return _CANONICAL_SEPARATORS.sub("", token).lower()


def source_focus_help_text() -> str:
    """Human-readable source help for CLI/MCP docs."""
    aliases = ", ".join(COMMON_SOURCE_FOCUS_NAMES)
    return f"Source focus aliases ({aliases}); raw source IDs and comma-separated lists are also accepted."


def aliases_for_source_id(source_id: str) -> list[str]:
    """Return parseable user-facing aliases for a raw Perplexity source ID."""
    aliases: list[str] = []

    if source_id == SourceFocus.WEB.value:
        aliases.append("web")
    elif source_id == SourceFocus.ACADEMIC.value:
        aliases.extend(["academic", "scholar"])
    elif source_id == SourceFocus.SOCIAL.value:
        aliases.append("social")
    elif source_id == SourceFocus.FINANCE.value:
        aliases.extend(["finance", "edgar"])

    for suffix in _SOURCE_SUFFIXES:
        if source_id.endswith(suffix):
            base = source_id[: -len(suffix)]
            if base:
                aliases.append(base)
            break

    if not aliases and source_id in COMMON_SOURCE_FOCUS_ALIASES:
        aliases.append(source_id)

    seen: set[str] = set()
    ordered: list[str] = []
    for alias in aliases:
        alias = alias.strip()
        if alias and alias not in seen:
            seen.add(alias)
            ordered.append(alias)
    return ordered


@dataclass(frozen=True, slots=True)
class AvailableSource:
    """A discoverable Perplexity source or connector."""

    source_id: str
    aliases: tuple[str, ...] = ()
    auth_type: str = "none"
    connected: bool | None = None
    has_required_scopes: bool | None = None
    monthly_limit: int | None = None
    remaining: int | None = None
    capabilities: tuple[str, ...] = ()

    @property
    def status(self) -> str:
        if self.auth_type == "oauth":
            if self.connected is False:
                return "not connected"
            if self.has_required_scopes is False:
                return "missing scopes"
            if self.connected is True:
                return "connected"
        return "available"

    @property
    def is_premium(self) -> bool:
        """Whether this source has a metered monthly limit (premium/paid connector)."""
        return self.monthly_limit is not None and self.monthly_limit > 0

    @property
    def remaining_label(self) -> str:
        if self.monthly_limit is None:
            return "unlimited"
        if self.remaining is None:
            return f"?/{self.monthly_limit}"
        return f"{self.remaining}/{self.monthly_limit}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "aliases": list(self.aliases),
            "auth_type": self.auth_type,
            "connected": self.connected,
            "has_required_scopes": self.has_required_scopes,
            "monthly_limit": self.monthly_limit,
            "remaining": self.remaining,
            "capabilities": list(self.capabilities),
            "status": self.status,
        }


def filter_premium_sources(sources: list[AvailableSource]) -> list[AvailableSource]:
    """Return only sources that have a monthly limit (premium/metered sources).

    Excludes unlimited sources and sources with monthly_limit == 0
    (disabled connectors like box, crunchbase).
    """
    return [s for s in sources if s.is_premium]


def fetch_available_sources(token: str) -> list[AvailableSource] | None:
    """Fetch live source/connector metadata for the authenticated account."""
    try:
        with _create_session(token) as session:
            response = session.get(f"{API_BASE_URL}{ENDPOINT_USER_SETTINGS}")
            if response.status_code != 200:
                logger.warning(f"Available sources fetch failed: HTTP {response.status_code}")
                return None
            settings_data = response.json()
    except Exception as exc:
        logger.warning(f"Available sources fetch error: {exc}")
        return None

    limit_map: dict[str, tuple[int | None, int | None]] = {}
    for source_id, limit_data in settings_data.get("sources", {}).get("source_to_limit", {}).items():
        limit_map[source_id] = (
            limit_data.get("monthly_limit"),
            limit_data.get("remaining"),
        )

    limits = fetch_rate_limits(token)
    if limits is not None:
        for limit in limits.source_limits:
            limit_map[limit.source_id] = (limit.monthly_limit, limit.remaining)

    connector_map: dict[str, dict[str, Any]] = {}
    raw_connectors = settings_data.get("connectors", {}).get("connectors", [])
    for connector in raw_connectors:
        if not isinstance(connector, dict):
            continue
        source_id = connector.get("source_id") or connector.get("name")
        if isinstance(source_id, str) and source_id:
            connector_map[source_id] = connector

    source_ids = {
        SourceFocus.WEB.value,
        SourceFocus.ACADEMIC.value,
        SourceFocus.SOCIAL.value,
        SourceFocus.FINANCE.value,
        *limit_map.keys(),
        *connector_map.keys(),
    }

    available: list[AvailableSource] = []
    for source_id in sorted(source_ids):
        connector = connector_map.get(source_id, {})
        monthly_limit, remaining = limit_map.get(source_id, (None, None))
        capabilities = connector.get("capabilities", {})
        capability_names = (
            tuple(sorted(name for name, enabled in capabilities.items() if enabled))
            if isinstance(capabilities, dict)
            else ()
        )

        available.append(
            AvailableSource(
                source_id=source_id,
                aliases=tuple(aliases_for_source_id(source_id)),
                auth_type=str(connector.get("auth_type", "none")),
                connected=connector.get("connected"),
                has_required_scopes=connector.get("has_required_scopes"),
                monthly_limit=monthly_limit,
                remaining=remaining,
                capabilities=capability_names,
            )
        )

    return available


def _dynamic_source_alias_map(token: str | None) -> dict[str, list[str]]:
    """Build alias -> raw source mapping from live account metadata."""
    if not token:
        return {}

    available = fetch_available_sources(token)
    if not available:
        return {}

    alias_map: dict[str, list[str]] = {}
    for source in available:
        alias_map[canonicalize_source_token(source.source_id)] = [source.source_id]
        for alias in source.aliases:
            alias_map[canonicalize_source_token(alias)] = [source.source_id]
    return alias_map


def _split_source_tokens(source_focus: str | Sequence[str]) -> list[str]:
    raw_items = [source_focus] if isinstance(source_focus, str) else list(source_focus)
    tokens: list[str] = []
    for item in raw_items:
        tokens.extend(part.strip() for part in str(item).split(",") if part.strip())
    return tokens


def resolve_source_focus(source_focus: str | Sequence[str]) -> tuple[list[str], SearchFocus]:
    """Resolve user-facing source aliases into raw Perplexity source IDs."""
    tokens = _split_source_tokens(source_focus)
    if not tokens:
        tokens = ["web"]

    canonical_tokens = [canonicalize_source_token(token) for token in tokens]
    if "none" in canonical_tokens:
        if len(canonical_tokens) != 1:
            raise ValueError("Source 'none' cannot be combined with other sources.")
        return [], SearchFocus.WRITING

    dynamic_aliases: dict[str, list[str]] | None = None
    resolved: list[str] = []
    for token, canonical in zip(tokens, canonical_tokens):
        mapped = _COMMON_ALIAS_MAP_CANONICAL.get(canonical)
        raw_source = token.strip().lower().replace("-", "_")
        if mapped is None and _VALID_SOURCE_TOKEN.fullmatch(raw_source) and "_" in raw_source:
            resolved.append(raw_source)
            continue
        if mapped is None:
            if dynamic_aliases is None:
                dynamic_aliases = _dynamic_source_alias_map(load_token())
            mapped = dynamic_aliases.get(canonical) if dynamic_aliases else None

        if mapped is not None:
            resolved.extend(mapped)
            continue

        if not _VALID_SOURCE_TOKEN.fullmatch(raw_source):
            raise ValueError(f"Invalid source '{token}'. Use a common alias or raw source ID.")
        resolved.append(raw_source)

    seen: set[str] = set()
    unique_sources: list[str] = []
    for source_id in resolved:
        if source_id not in seen:
            seen.add(source_id)
            unique_sources.append(source_id)

    return unique_sources, SearchFocus.WEB
