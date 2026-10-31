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

"""Tools for linking Google Ads accounts to Google Merchant Center accounts."""

from typing import Any, Dict, Literal
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

import ads_mcp.utils as utils
from ads_mcp.tools.search import search as run_search
from google.ads.googleads.errors import GoogleAdsException

merchant_center_mcp = FastMCP("merchant_center")


@merchant_center_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def list_links(
    customer_id: str | int,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Lists Merchant Center accounts linked to a Google Ads account, and pending invitations.

    Shopping and Performance Max campaigns need a linked Merchant Center
    account. Invitations sent from either side show their status (for example
    PENDING_APPROVAL or REQUESTED) until accepted or rejected.

    Args:
        customer_id: The ID of the Google Ads customer.
        login_customer_id: Optional manager customer ID.
    """
    result: Dict[str, Any] = {}
    errors: Dict[str, str] = {}
    try:
        result["links"] = run_search(
            customer_id=customer_id,
            fields=[
                "product_link.resource_name",
                "product_link.product_link_id",
                "product_link.type",
                "product_link.merchant_center.merchant_center_id",
            ],
            resource="product_link",
            conditions=["product_link.type = 'MERCHANT_CENTER'"],
            login_customer_id=login_customer_id,
        )
    except ToolError as ex:
        errors["links"] = str(ex)
    try:
        result["invitations"] = run_search(
            customer_id=customer_id,
            fields=[
                "product_link_invitation.resource_name",
                "product_link_invitation.product_link_invitation_id",
                "product_link_invitation.status",
                "product_link_invitation.type",
                "product_link_invitation.merchant_center.merchant_center_id",
            ],
            resource="product_link_invitation",
            conditions=["product_link_invitation.type = 'MERCHANT_CENTER'"],
            login_customer_id=login_customer_id,
        )
    except ToolError as ex:
        errors["invitations"] = str(ex)
    if errors:
        result["errors"] = errors
    return result


def _call(service_name: str, method: str, request: Dict[str, Any], login):
    service = utils.get_googleads_service(service_name, login_customer_id=login)
    try:
        return utils.format_output_value(
            getattr(service, method)(request=request)
        )
    except GoogleAdsException as ex:
        raise utils.google_ads_tool_error(ex)


@merchant_center_mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False)
)
def invite_link(
    customer_id: str | int,
    merchant_center_id: str | int,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Sends a link invitation from a Google Ads account to a Merchant Center account.

    An admin of the Merchant Center account must then accept it, in Merchant
    Center or with the Merchant Center MCP.

    Args:
        customer_id: The ID of the Google Ads customer.
        merchant_center_id: The Merchant Center account ID.
        login_customer_id: Optional manager customer ID.
    """
    return _call(
        "ProductLinkInvitationService",
        "create_product_link_invitation",
        {
            "customer_id": utils.clean_customer_id(customer_id),
            "product_link_invitation": {
                "merchant_center": {
                    "merchant_center_id": int(
                        utils.clean_customer_id(merchant_center_id)
                    )
                }
            },
        },
        login_customer_id,
    )


@merchant_center_mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False)
)
def respond_to_invitation(
    customer_id: str | int,
    invitation_resource_name: str,
    response: Literal["ACCEPTED", "REJECTED"],
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Accepts or rejects a link invitation that a Merchant Center account sent to this Google Ads account.

    Find invitations with `merchant_center_list_links`; only those with
    status PENDING_APPROVAL can be answered from the Google Ads side.

    Args:
        customer_id: The ID of the Google Ads customer.
        invitation_resource_name: e.g. customers/123/productLinkInvitations/456.
        response: ACCEPTED or REJECTED.
        login_customer_id: Optional manager customer ID.
    """
    return _call(
        "ProductLinkInvitationService",
        "update_product_link_invitation",
        {
            "customer_id": utils.clean_customer_id(customer_id),
            "resource_name": invitation_resource_name,
            "product_link_invitation_status": response,
        },
        login_customer_id,
    )


@merchant_center_mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True)
)
def remove_link(
    customer_id: str | int,
    product_link_resource_name: str,
    validate_only: bool = False,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Unlinks a Merchant Center account from a Google Ads account.

    Shopping and Performance Max campaigns that use the account's products
    stop serving those products.

    Args:
        customer_id: The ID of the Google Ads customer.
        product_link_resource_name: e.g. customers/123/productLinks/456.
        validate_only: If True, validate the request but do not apply it.
        login_customer_id: Optional manager customer ID.
    """
    return _call(
        "ProductLinkService",
        "remove_product_link",
        {
            "customer_id": utils.clean_customer_id(customer_id),
            "resource_name": product_link_resource_name,
            "validate_only": validate_only,
        },
        login_customer_id,
    )
