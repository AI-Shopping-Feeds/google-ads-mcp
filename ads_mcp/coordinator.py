# Copyright 2026 Google LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Module declaring the singleton MCP instance.

The singleton allows other modules to register their tools with the same MCP
server using `@mcp.tool` annotations, thereby 'coordinating' the bootstrapping
of the server.
"""

import os
from importlib import metadata
from typing import Any
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.auth.providers.google import GoogleProvider
from mcp import types as mcp_types
from mcp.server.subscriptions import InMemorySubscriptionBus, ListenHandler
from ads_mcp.auth_storage import create_client_storage

_CLIENT_ID = os.environ.get("GOOGLE_ADS_MCP_OAUTH_CLIENT_ID")
_CLIENT_SECRET = os.environ.get("GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET")
_BASE_URL = os.environ.get("GOOGLE_ADS_MCP_BASE_URL", "http://localhost:8080")
_JWT_SIGNING_KEY = os.environ.get("GOOGLE_ADS_MCP_JWT_SIGNING_KEY")

try:
    SERVER_VERSION = metadata.version("google-ads-mcp")
except metadata.PackageNotFoundError:
    SERVER_VERSION = "0.0.0"

INSTRUCTIONS = """\
Google Ads MCP: read and change Google Ads accounts through the Google Ads API v26.
- Find accounts with customers_list_accessible_customers (or customers_get_account_hierarchy for a manager account); pass login_customer_id when working through a manager.
- Before writing GAQL for search_search, look up field names with metadata_get_resource_metadata.
- Write tools change live accounts and spend money: call them with validate_only=true first, show the person what will change, and only then apply it.
- policy_list_policy_issues explains disapprovals; mutate_mutate covers any create/update/remove; services_call_service reaches every other API method.
- Money values are in micros (1.00 = 1,000,000). GOOGLE_ADS_MCP_READ_ONLY=true removes all write tools.
"""

_SERVER_KWARGS: dict[str, Any] = {
    "version": SERVER_VERSION,
    "instructions": INSTRUCTIONS,
    "website_url": "https://github.com/AI-Shopping-Feeds/google-ads-mcp",
    # Hide the text of unexpected exceptions; ExpectedErrorsMiddleware below
    # keeps the messages that help the agent fix its call.
    "mask_error_details": True,
}

if _CLIENT_ID and _CLIENT_SECRET:
    client_storage = create_client_storage()
    provider_kwargs: dict[str, Any] = {
        "client_id": _CLIENT_ID,
        "client_secret": _CLIENT_SECRET,
        "base_url": _BASE_URL,
        "required_scopes": [
            "openid",
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/userinfo.profile",
            "https://www.googleapis.com/auth/adwords",
        ],
    }
    if _JWT_SIGNING_KEY:
        provider_kwargs["jwt_signing_key"] = _JWT_SIGNING_KEY
    if client_storage is not None:
        provider_kwargs["client_storage"] = client_storage

    auth = GoogleProvider(**provider_kwargs)
    mcp = FastMCP("Google Ads Server", auth=auth, **_SERVER_KWARGS)
else:
    mcp = FastMCP("Google Ads Server", **_SERVER_KWARGS)


def _expected_errors() -> tuple[type[BaseException], ...]:
    """Errors whose message helps the agent fix the call."""
    import google.auth.exceptions
    from google.ads.googleads.errors import GoogleAdsException
    from google.api_core.exceptions import GoogleAPICallError

    return (
        ValueError,
        RuntimeError,
        PermissionError,
        FileNotFoundError,
        google.auth.exceptions.GoogleAuthError,
        GoogleAdsException,
        GoogleAPICallError,
    )


class ExpectedErrorsMiddleware(Middleware):
    """Re-raises expected errors as ToolError so their message reaches the client.

    With mask_error_details=True, FastMCP replaces the text of any other
    exception with a generic message.
    """

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        expected = _expected_errors()
        try:
            return await call_next(context)
        except ToolError as exc:
            # FastMCP masks the tool's exception into a generic ToolError and
            # keeps the original as its cause.
            cause = exc.__cause__
            if isinstance(cause, expected) and not isinstance(cause, ToolError):
                raise ToolError(str(cause)) from cause
            raise
        except expected as exc:
            raise ToolError(str(exc)) from exc


mcp.add_middleware(ExpectedErrorsMiddleware())


def ensure_subscriptions_listen(server: FastMCP) -> bool:
    """Register the MCP 2026 subscription stream when FastMCP omits it.

    FastMCP 4 (including 4.0.3) builds its low-level ``Server`` without the SDK's
    ``on_subscriptions_listen`` handler. Some modern clients open that stream
    while loading tools; without it, the SDK returns HTTP 404 / method not
    found, which mcp-go reports misleadingly as a missing session.

    The guard preserves a native FastMCP implementation once one is shipped.

    Returns:
        True when the compatibility handler was installed, otherwise False.
    """
    low_level_server = server._mcp_server
    if "subscriptions/listen" in low_level_server._request_handlers:
        return False

    subscription_bus = InMemorySubscriptionBus()
    low_level_server.add_request_handler(
        "subscriptions/listen",
        mcp_types.SubscriptionsListenRequestParams,
        ListenHandler(subscription_bus),
    )
    return True


ensure_subscriptions_listen(mcp)


def _is_read_only_tool(sub_mcp: FastMCP, name: str) -> bool:
    """Returns True if the tool declares readOnlyHint=True."""
    tool = next(
        v
        for k, v in sub_mcp.local_provider._components.items()
        if k.startswith("tool:") and v.name == name
    )
    annotations = getattr(tool, "annotations", None)
    return bool(annotations and annotations.read_only_hint)


def initialize_and_mount_tools(parent_mcp: FastMCP) -> None:
    """Loads the tools configuration and dynamically mounts the tools sub-servers."""
    from ads_mcp.config import ToolsConfig
    from ads_mcp.utils import is_read_only
    import importlib
    import pkgutil
    import ads_mcp.tools as tools_pkg

    # Map of category name -> FastMCP sub-server
    sub_servers = {}

    # Discover and dynamically load all tool modules
    for _, module_name, _ in pkgutil.iter_modules(tools_pkg.__path__):
        full_module_name = f"ads_mcp.tools.{module_name}"
        module = importlib.import_module(full_module_name)

        # Find any FastMCP instances defined in the module
        for attr_name in dir(module):
            attr_val = getattr(module, attr_name)
            if isinstance(attr_val, FastMCP):
                category = attr_val.name
                sub_servers[category] = attr_val

    config = ToolsConfig.load()

    for category, sub_mcp in sub_servers.items():
        if not config.is_namespace_enabled(category):
            continue

        # Filter disabled tools inside the sub-server before mounting
        tool_names = []
        for key, val in sub_mcp.local_provider._components.items():
            if key.startswith("tool:"):
                tool_names.append(val.name)

        read_only = is_read_only()
        for name in tool_names:
            if not config.is_tool_enabled(category, name) or (
                read_only and not _is_read_only_tool(sub_mcp, name)
            ):
                sub_mcp.local_provider.remove_tool(name)

        # Mounted servers must mask unexpected errors too, or their details
        # reach the client even though the parent masks them.
        sub_mcp._mask_error_details = parent_mcp._mask_error_details
        if not any(
            isinstance(m, ExpectedErrorsMiddleware) for m in sub_mcp.middleware
        ):
            sub_mcp.add_middleware(ExpectedErrorsMiddleware())

        # Determine prefix/namespace
        namespace_prefix = config.get_namespace_prefix(category)

        # Mount the sub-server
        parent_mcp.mount(sub_mcp, namespace=namespace_prefix or None)


# Automatically initialize and mount tools upon import
initialize_and_mount_tools(mcp)
