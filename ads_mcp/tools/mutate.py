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

"""Tools for creating, updating and removing Google Ads resources.

Every tool in this module can change a live account. They all accept
`validate_only`: when True the API checks the request and returns errors
without applying anything, so agents should preview with it before writing.
"""

import re
from typing import Any, Dict, List, Literal
from fastmcp import FastMCP
from mcp.types import ToolAnnotations

import ads_mcp.utils as utils
from google.ads.googleads.errors import GoogleAdsException

mutate_mcp = FastMCP("mutate")

_WRITE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=False
)
_DESTRUCTIVE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=True, idempotentHint=True
)

EntityStatus = Literal["ENABLED", "PAUSED", "REMOVED"]
MatchType = Literal["EXACT", "PHRASE", "BROAD"]


def _mutate_operations(
    customer_id: str | int,
    operations: List[Dict[str, Any]],
    validate_only: bool,
    partial_failure: bool,
    login_customer_id: str | int | None,
    response_content_type: str = "RESOURCE_NAME_ONLY",
) -> Dict[str, Any]:
    """Sends operations through GoogleAdsService.Mutate and formats the reply."""
    customer_id = utils.clean_customer_id(customer_id)
    ga_service = utils.get_googleads_service(
        "GoogleAdsService", login_customer_id=login_customer_id
    )
    request = {
        "customer_id": customer_id,
        "mutate_operations": operations,
        "validate_only": validate_only,
        "partial_failure": partial_failure,
        "response_content_type": response_content_type,
    }
    utils.logger.info(
        "ads_mcp.mutate customer=%s operations=%d validate_only=%s",
        customer_id,
        len(operations),
        validate_only,
    )
    try:
        response = ga_service.mutate(request=request)
    except GoogleAdsException as ex:
        raise utils.google_ads_tool_error(ex)
    except (TypeError, ValueError, KeyError) as ex:
        raise utils.ToolError(f"Invalid mutate operation: {ex}")

    result = utils.format_output_value(response)
    result["validate_only"] = validate_only
    return result


def mutate(
    customer_id: str | int,
    operations: List[Dict[str, Any]],
    validate_only: bool = False,
    partial_failure: bool = False,
    response_content_type: Literal[
        "RESOURCE_NAME_ONLY", "MUTABLE_RESOURCE"
    ] = "RESOURCE_NAME_ONLY",
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Creates, updates or removes any Google Ads resources in one atomic request.

    Wraps GoogleAdsService.Mutate, which supports every mutable resource
    (campaigns, budgets, ad groups, ads, keywords, criteria, assets, asset
    groups, labels, conversion actions, bidding strategies, shared sets,
    experiments, user lists and more).

    Each item in `operations` is a MutateOperation with exactly one key named
    `<resource>_operation` (snake_case), holding one of `create`, `update` or
    `remove`. Field names are snake_case and enums are their string names.
    Updates must include `update_mask` listing the changed field paths.

    Examples:
        Pause a campaign:
            {"campaign_operation": {
                "update": {"resource_name": "customers/123/campaigns/456",
                           "status": "PAUSED"},
                "update_mask": {"paths": ["status"]}}}
        Create a budget and a campaign together using a temporary ID (-1):
            {"campaign_budget_operation": {"create": {
                "resource_name": "customers/123/campaignBudgets/-1",
                "name": "Budget A", "amount_micros": 20000000,
                "delivery_method": "STANDARD"}}},
            {"campaign_operation": {"create": {
                "name": "Campaign A", "status": "PAUSED",
                "advertising_channel_type": "SEARCH",
                "campaign_budget": "customers/123/campaignBudgets/-1",
                "manual_cpc": {},
                "contains_eu_political_advertising":
                    "DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING"}}}
        Remove an ad group:
            {"ad_group_operation": {"remove": "customers/123/adGroups/789"}}

    Money values are in micros (1 unit of currency = 1,000,000 micros).
    Run with validate_only=True first to check the request without changing
    the account. Without partial_failure the whole request fails if any
    operation fails.

    Args:
        customer_id: The ID of the customer to change (digits only).
        operations: The MutateOperation objects to apply, in order.
        validate_only: If True, validate the request but do not apply it.
        partial_failure: If True, apply the valid operations and report errors
            for the rest instead of failing the whole request.
        response_content_type: RESOURCE_NAME_ONLY (default) or
            MUTABLE_RESOURCE to return the full resources after the change.
        login_customer_id: Optional manager customer ID to use as the
            login-customer-id header.
    """
    if not operations:
        raise utils.ToolError("At least one operation is required.")
    return _mutate_operations(
        customer_id,
        operations,
        validate_only,
        partial_failure,
        login_customer_id,
        response_content_type,
    )


mutate_mcp.tool(mutate, annotations=_WRITE)


def _status_operation(
    operation: str, resource_name: str, status: str
) -> Dict[str, Any]:
    return {
        operation: {
            "update": {"resource_name": resource_name, "status": status},
            "update_mask": {"paths": ["status"]},
        }
    }


@mutate_mcp.tool(annotations=_WRITE)
def update_campaign_status(
    customer_id: str | int,
    campaign_ids: List[str | int],
    status: Literal["ENABLED", "PAUSED"],
    validate_only: bool = False,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Enables or pauses one or more campaigns.

    To delete a campaign use `remove_resources` instead.

    Args:
        customer_id: The ID of the customer that owns the campaigns.
        campaign_ids: The IDs of the campaigns to change.
        status: ENABLED or PAUSED.
        validate_only: If True, validate the request but do not apply it.
        login_customer_id: Optional manager customer ID.
    """
    cid = utils.clean_customer_id(customer_id)
    ops = [
        _status_operation(
            "campaign_operation", f"customers/{cid}/campaigns/{c}", status
        )
        for c in campaign_ids
    ]
    return _mutate_operations(cid, ops, validate_only, False, login_customer_id)


@mutate_mcp.tool(annotations=_WRITE)
def update_ad_group_status(
    customer_id: str | int,
    ad_group_ids: List[str | int],
    status: Literal["ENABLED", "PAUSED"],
    validate_only: bool = False,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Enables or pauses one or more ad groups.

    Args:
        customer_id: The ID of the customer that owns the ad groups.
        ad_group_ids: The IDs of the ad groups to change.
        status: ENABLED or PAUSED.
        validate_only: If True, validate the request but do not apply it.
        login_customer_id: Optional manager customer ID.
    """
    cid = utils.clean_customer_id(customer_id)
    ops = [
        _status_operation(
            "ad_group_operation", f"customers/{cid}/adGroups/{a}", status
        )
        for a in ad_group_ids
    ]
    return _mutate_operations(cid, ops, validate_only, False, login_customer_id)


@mutate_mcp.tool(annotations=_WRITE)
def update_ad_status(
    customer_id: str | int,
    ad_group_id: str | int,
    ad_ids: List[str | int],
    status: Literal["ENABLED", "PAUSED"],
    validate_only: bool = False,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Enables or pauses ads within an ad group.

    Args:
        customer_id: The ID of the customer that owns the ads.
        ad_group_id: The ID of the ad group containing the ads.
        ad_ids: The IDs of the ads to change.
        status: ENABLED or PAUSED.
        validate_only: If True, validate the request but do not apply it.
        login_customer_id: Optional manager customer ID.
    """
    cid = utils.clean_customer_id(customer_id)
    ops = [
        _status_operation(
            "ad_group_ad_operation",
            f"customers/{cid}/adGroupAds/{ad_group_id}~{ad}",
            status,
        )
        for ad in ad_ids
    ]
    return _mutate_operations(cid, ops, validate_only, False, login_customer_id)


@mutate_mcp.tool(annotations=_WRITE)
def update_campaign_budget(
    customer_id: str | int,
    budget_id: str | int,
    amount_micros: int,
    validate_only: bool = False,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Sets the daily amount of a campaign budget.

    Find a campaign's budget with the `search` tool by selecting
    `campaign.campaign_budget` from `campaign`. A shared budget changes for
    every campaign that uses it.

    Args:
        customer_id: The ID of the customer that owns the budget.
        budget_id: The ID of the campaign budget.
        amount_micros: The new daily amount in micros (e.g. 25000000 = 25.00).
        validate_only: If True, validate the request but do not apply it.
        login_customer_id: Optional manager customer ID.
    """
    if amount_micros <= 0:
        raise utils.ToolError("amount_micros must be greater than zero.")
    cid = utils.clean_customer_id(customer_id)
    ops = [
        {
            "campaign_budget_operation": {
                "update": {
                    "resource_name": f"customers/{cid}/campaignBudgets/{budget_id}",
                    "amount_micros": amount_micros,
                },
                "update_mask": {"paths": ["amount_micros"]},
            }
        }
    ]
    return _mutate_operations(cid, ops, validate_only, False, login_customer_id)


@mutate_mcp.tool(annotations=_WRITE)
def add_keywords(
    customer_id: str | int,
    ad_group_id: str | int,
    keywords: List[Dict[str, Any]],
    validate_only: bool = False,
    partial_failure: bool = False,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Adds positive keywords to an ad group.

    Args:
        customer_id: The ID of the customer that owns the ad group.
        ad_group_id: The ID of the ad group to add keywords to.
        keywords: Items of the form {"text": "running shoes",
            "match_type": "EXACT" | "PHRASE" | "BROAD",
            "cpc_bid_micros": 1500000 (optional),
            "status": "ENABLED" | "PAUSED" (optional, default ENABLED),
            "final_urls": ["https://..."] (optional)}.
        validate_only: If True, validate the request but do not apply it.
        partial_failure: If True, add the valid keywords and report the rest.
        login_customer_id: Optional manager customer ID.
    """
    cid = utils.clean_customer_id(customer_id)
    ops = []
    for kw in keywords:
        if not kw.get("text") or not kw.get("match_type"):
            raise utils.ToolError(
                "Every keyword needs 'text' and 'match_type'."
            )
        criterion: Dict[str, Any] = {
            "ad_group": f"customers/{cid}/adGroups/{ad_group_id}",
            "status": kw.get("status", "ENABLED"),
            "keyword": {"text": kw["text"], "match_type": kw["match_type"]},
        }
        if kw.get("cpc_bid_micros") is not None:
            criterion["cpc_bid_micros"] = int(kw["cpc_bid_micros"])
        if kw.get("final_urls"):
            criterion["final_urls"] = list(kw["final_urls"])
        ops.append({"ad_group_criterion_operation": {"create": criterion}})
    return _mutate_operations(
        cid, ops, validate_only, partial_failure, login_customer_id
    )


@mutate_mcp.tool(annotations=_WRITE)
def add_negative_keywords(
    customer_id: str | int,
    keywords: List[Dict[str, str]],
    campaign_id: str | int | None = None,
    ad_group_id: str | int | None = None,
    validate_only: bool = False,
    partial_failure: bool = False,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Adds negative keywords to a campaign or an ad group.

    Give exactly one of `campaign_id` or `ad_group_id`. For account-level or
    shared negative keyword lists, use `mutate` with
    `shared_criterion_operation`.

    Args:
        customer_id: The ID of the customer.
        keywords: Items of the form {"text": "free",
            "match_type": "EXACT" | "PHRASE" | "BROAD"}.
        campaign_id: The campaign to add negatives to.
        ad_group_id: The ad group to add negatives to.
        validate_only: If True, validate the request but do not apply it.
        partial_failure: If True, add the valid keywords and report the rest.
        login_customer_id: Optional manager customer ID.
    """
    if (campaign_id is None) == (ad_group_id is None):
        raise utils.ToolError(
            "Provide exactly one of campaign_id or ad_group_id."
        )
    cid = utils.clean_customer_id(customer_id)
    ops = []
    for kw in keywords:
        if not kw.get("text") or not kw.get("match_type"):
            raise utils.ToolError(
                "Every keyword needs 'text' and 'match_type'."
            )
        keyword = {"text": kw["text"], "match_type": kw["match_type"]}
        if campaign_id is not None:
            ops.append(
                {
                    "campaign_criterion_operation": {
                        "create": {
                            "campaign": f"customers/{cid}/campaigns/{campaign_id}",
                            "negative": True,
                            "keyword": keyword,
                        }
                    }
                }
            )
        else:
            ops.append(
                {
                    "ad_group_criterion_operation": {
                        "create": {
                            "ad_group": f"customers/{cid}/adGroups/{ad_group_id}",
                            "negative": True,
                            "keyword": keyword,
                        }
                    }
                }
            )
    return _mutate_operations(
        cid, ops, validate_only, partial_failure, login_customer_id
    )


@mutate_mcp.tool(annotations=_WRITE)
def update_keyword(
    customer_id: str | int,
    ad_group_id: str | int,
    criterion_id: str | int,
    status: Literal["ENABLED", "PAUSED"] | None = None,
    cpc_bid_micros: int | None = None,
    validate_only: bool = False,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Changes the status and/or max CPC bid of an existing keyword.

    Args:
        customer_id: The ID of the customer.
        ad_group_id: The ID of the ad group containing the keyword.
        criterion_id: The criterion ID of the keyword.
        status: ENABLED or PAUSED.
        cpc_bid_micros: The new max CPC bid in micros.
        validate_only: If True, validate the request but do not apply it.
        login_customer_id: Optional manager customer ID.
    """
    if status is None and cpc_bid_micros is None:
        raise utils.ToolError("Provide status and/or cpc_bid_micros.")
    cid = utils.clean_customer_id(customer_id)
    update: Dict[str, Any] = {
        "resource_name": f"customers/{cid}/adGroupCriteria/{ad_group_id}~{criterion_id}"
    }
    paths = []
    if status is not None:
        update["status"] = status
        paths.append("status")
    if cpc_bid_micros is not None:
        update["cpc_bid_micros"] = cpc_bid_micros
        paths.append("cpc_bid_micros")
    ops = [
        {
            "ad_group_criterion_operation": {
                "update": update,
                "update_mask": {"paths": paths},
            }
        }
    ]
    return _mutate_operations(cid, ops, validate_only, False, login_customer_id)


_RESOURCE_NAME = re.compile(r"^customers/\d+/([A-Za-z]+)/[^/]+$")


def _operation_for_resource_name(resource_name: str) -> str:
    """Maps e.g. customers/1/adGroupCriteria/2~3 to ad_group_criterion_operation."""
    match = _RESOURCE_NAME.match(resource_name)
    if not match:
        raise utils.ToolError(
            f"'{resource_name}' is not a removable resource name."
        )
    collection = re.sub(r"(?<!^)(?=[A-Z])", "_", match.group(1)).lower()
    if collection.endswith("criteria"):
        singular = collection[: -len("criteria")] + "criterion"
    elif collection.endswith("ies"):
        singular = collection[:-3] + "y"
    elif collection.endswith("s"):
        singular = collection[:-1]
    else:
        singular = collection
    return f"{singular}_operation"


@mutate_mcp.tool(annotations=_DESTRUCTIVE)
def remove_resources(
    customer_id: str | int,
    resource_names: List[str],
    validate_only: bool = False,
    partial_failure: bool = False,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Permanently removes resources by resource name.

    Works for any removable resource, e.g. `customers/123/campaigns/456`,
    `customers/123/adGroups/789`, `customers/123/adGroupAds/789~111`,
    `customers/123/adGroupCriteria/789~222`, `customers/123/campaignCriteria/456~333`,
    `customers/123/labels/444`. Removed campaigns, ad groups and ads cannot be
    re-enabled. To stop serving temporarily, pause instead.

    Args:
        customer_id: The ID of the customer that owns the resources.
        resource_names: Full resource names to remove.
        validate_only: If True, validate the request but do not apply it.
        partial_failure: If True, remove what can be removed and report the rest.
        login_customer_id: Optional manager customer ID.
    """
    cid = utils.clean_customer_id(customer_id)
    ops = []
    for name in resource_names:
        if not name.startswith(f"customers/{cid}/"):
            raise utils.ToolError(
                f"'{name}' does not belong to customer {cid}."
            )
        ops.append({_operation_for_resource_name(name): {"remove": name}})
    return _mutate_operations(
        cid, ops, validate_only, partial_failure, login_customer_id
    )


@mutate_mcp.tool(annotations=_WRITE)
def apply_recommendations(
    customer_id: str | int,
    recommendation_resource_names: List[str],
    partial_failure: bool = False,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Applies Google Ads recommendations with their default parameters.

    List recommendations first with `search` on the `recommendation` resource
    (select `recommendation.resource_name`, `recommendation.type` and the
    type-specific detail fields). For custom parameters use `call_service`
    with RecommendationService.ApplyRecommendation.

    Args:
        customer_id: The ID of the customer.
        recommendation_resource_names: Recommendation resource names to apply.
        partial_failure: If True, apply what can be applied and report the rest.
        login_customer_id: Optional manager customer ID.
    """
    cid = utils.clean_customer_id(customer_id)
    service = utils.get_googleads_service(
        "RecommendationService", login_customer_id=login_customer_id
    )
    request = {
        "customer_id": cid,
        "operations": [
            {"resource_name": rn} for rn in recommendation_resource_names
        ],
        "partial_failure": partial_failure,
    }
    try:
        return utils.format_output_value(
            service.apply_recommendation(request=request)
        )
    except GoogleAdsException as ex:
        raise utils.google_ads_tool_error(ex)


@mutate_mcp.tool(annotations=_WRITE)
def dismiss_recommendations(
    customer_id: str | int,
    recommendation_resource_names: List[str],
    partial_failure: bool = False,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Dismisses Google Ads recommendations so they stop being suggested.

    Args:
        customer_id: The ID of the customer.
        recommendation_resource_names: Recommendation resource names to dismiss.
        partial_failure: If True, dismiss what can be dismissed and report the rest.
        login_customer_id: Optional manager customer ID.
    """
    cid = utils.clean_customer_id(customer_id)
    service = utils.get_googleads_service(
        "RecommendationService", login_customer_id=login_customer_id
    )
    request = {
        "customer_id": cid,
        "operations": [
            {"resource_name": rn} for rn in recommendation_resource_names
        ],
        "partial_failure": partial_failure,
    }
    try:
        return utils.format_output_value(
            service.dismiss_recommendation(request=request)
        )
    except GoogleAdsException as ex:
        raise utils.google_ads_tool_error(ex)
