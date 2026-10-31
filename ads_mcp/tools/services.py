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

"""Generic access to every Google Ads API service method.

These tools cover RPCs that have no dedicated tool, such as conversion
uploads, Customer Match jobs, reach planning, audience insights, batch jobs
and account creation. The available services are discovered from the
installed client library, so a library upgrade exposes new methods without
code changes.
"""

import importlib
import inspect
import pkgutil
from functools import lru_cache
from typing import Any, Dict, List
from fastmcp import FastMCP
from mcp.types import ToolAnnotations

import ads_mcp.utils as utils
from google.ads.googleads.errors import GoogleAdsException

services_mcp = FastMCP("services")

# Methods every generated client exposes that are not API calls.
_NON_RPC_METHODS = {"from_service_account_file", "from_service_account_info"}


@lru_cache(maxsize=1)
def _service_clients() -> Dict[str, type]:
    """Maps service names (e.g. CampaignService) to their client classes."""
    package = importlib.import_module(
        f"google.ads.googleads.{utils.API_VERSION}.services.services"
    )
    clients: Dict[str, type] = {}
    for module_info in pkgutil.iter_modules(package.__path__):
        module = importlib.import_module(
            f"{package.__name__}.{module_info.name}"
        )
        for attr in dir(module):
            if attr.endswith("ServiceClient"):
                clients[attr.removesuffix("Client")] = getattr(module, attr)
    return clients


def _rpc_methods(client_cls: type) -> List[str]:
    return sorted(
        name
        for name, fn in inspect.getmembers(client_cls, inspect.isfunction)
        if not name.startswith("_")
        and name not in _NON_RPC_METHODS
        and "request" in inspect.signature(fn).parameters
    )


def _service_catalog() -> Dict[str, List[str]]:
    """Maps service names to their snake_case RPC methods."""
    return {name: _rpc_methods(cls) for name, cls in _service_clients().items()}


def _request_fields(service: str, method: str) -> List[str]:
    """Returns the top-level field names of a method's request message."""
    fn = getattr(_service_clients()[service], method)
    annotation = inspect.signature(fn).parameters["request"].annotation
    for arg in getattr(annotation, "__args__", ()):
        if hasattr(arg, "meta"):
            return list(arg.meta.fields)
    return []


@services_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def list_services(service: str | None = None) -> Dict[str, Any]:
    """Lists the Google Ads API services and methods available to `call_service`.

    Without arguments returns every service and its methods. With `service`
    (e.g. "ConversionUploadService") also returns the request fields of each
    method, so you can build a request for `call_service`. Full request
    documentation is at
    https://developers.google.com/google-ads/api/reference/rpc/latest/overview

    Args:
        service: Optional service name to describe in detail.
    """
    catalog = _service_catalog()
    if service is None:
        return {"api_version": utils.API_VERSION, "services": catalog}
    if service not in catalog:
        raise utils.ToolError(
            f"Unknown service '{service}'. Call list_services() to see all."
        )
    return {
        "api_version": utils.API_VERSION,
        "service": service,
        "methods": {
            m: {"request_fields": _request_fields(service, m)}
            for m in catalog[service]
        },
    }


@services_mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True)
)
def call_service(
    service: str,
    method: str,
    request: Dict[str, Any],
    login_customer_id: str | int | None = None,
) -> Any:
    """Calls any Google Ads API service method with a raw request.

    Use this only when no dedicated tool fits, for example:
    ConversionUploadService.upload_click_conversions,
    ConversionAdjustmentUploadService.upload_conversion_adjustments,
    OfflineUserDataJobService (Customer Match), UserDataService,
    ReachPlanService.generate_reach_forecast,
    AudienceInsightsService.generate_insights_finder_report,
    CustomerService.create_customer_client, BatchJobService,
    ExperimentService, ShareablePreviewService or
    KeywordPlanIdeaService.generate_keyword_forecast_metrics.

    Many methods change the account. Methods that support it accept
    `validate_only: true` in the request to check it without applying it.

    Args:
        service: Service name from `list_services`, e.g. "ConversionUploadService".
        method: snake_case method name, e.g. "upload_click_conversions".
        request: The request message as a dict with snake_case field names
            and enum values as strings. Include `customer_id` where the
            request has one (digits only).
        login_customer_id: Optional manager customer ID.
    """
    catalog = _service_catalog()
    if service not in catalog:
        raise utils.ToolError(
            f"Unknown service '{service}'. Call list_services() to see all."
        )
    if method not in catalog[service]:
        raise utils.ToolError(
            f"{service} has no method '{method}'. Available: "
            + ", ".join(catalog[service])
        )
    if "customer_id" in request:
        request = {
            **request,
            "customer_id": utils.clean_customer_id(request["customer_id"]),
        }

    client = utils.get_googleads_service(
        service, login_customer_id=login_customer_id
    )
    utils.logger.info("ads_mcp.call_service %s.%s", service, method)
    try:
        response = getattr(client, method)(request=request)
    except GoogleAdsException as ex:
        raise utils.google_ads_tool_error(ex)
    except (TypeError, ValueError, KeyError) as ex:
        raise utils.ToolError(f"Invalid request for {service}.{method}: {ex}")

    # Streaming and paged methods return iterables of messages.
    if hasattr(response, "__iter__") and not hasattr(response, "_pb"):
        return [utils.format_output_value(item) for item in response]
    return utils.format_output_value(response)
