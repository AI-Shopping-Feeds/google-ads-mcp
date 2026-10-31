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

"""Tools for uploading offline conversions."""

from typing import Any, Dict, List
from fastmcp import FastMCP
from mcp.types import ToolAnnotations

import ads_mcp.utils as utils
from google.ads.googleads.errors import GoogleAdsException

conversions_mcp = FastMCP("conversions")

_CLICK_IDS = ("gclid", "gbraid", "wbraid")


@conversions_mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False)
)
def upload_click_conversions(
    customer_id: str | int,
    conversion_action_id: str | int,
    conversions: List[Dict[str, Any]],
    validate_only: bool = False,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Uploads offline click conversions (e.g. sales from a CRM) to a conversion action.

    Find the conversion action with `search` on `conversion_action`
    (type UPLOAD_CLICKS). Each conversion needs exactly one click ID and a
    timestamp. Uploads run with partial failure, so valid rows are kept and
    errors are reported per row in `partial_failure_error`.

    Args:
        customer_id: The ID of the customer.
        conversion_action_id: The ID of the conversion action to credit.
        conversions: Items such as {"gclid": "...",
            "conversion_date_time": "2026-10-30 14:05:00+00:00",
            "conversion_value": 49.99, "currency_code": "GBP",
            "order_id": "A123"}. Use "gbraid" or "wbraid" instead of "gclid"
            for iOS traffic. Other ClickConversion fields such as
            "user_identifiers" (enhanced conversions for leads) or
            "consent" are passed through.
        validate_only: If True, validate the rows but do not record them.
        login_customer_id: Optional manager customer ID.
    """
    cid = utils.clean_customer_id(customer_id)
    action = f"customers/{cid}/conversionActions/{conversion_action_id}"
    rows = []
    for i, conv in enumerate(conversions):
        click_ids = [k for k in _CLICK_IDS if conv.get(k)]
        if len(click_ids) != 1 and not conv.get("user_identifiers"):
            raise utils.ToolError(
                f"Conversion {i} needs exactly one of gclid, gbraid or wbraid."
            )
        if not conv.get("conversion_date_time"):
            raise utils.ToolError(f"Conversion {i} needs conversion_date_time.")
        rows.append({**conv, "conversion_action": action})

    service = utils.get_googleads_service(
        "ConversionUploadService", login_customer_id=login_customer_id
    )
    try:
        response = service.upload_click_conversions(
            request={
                "customer_id": cid,
                "conversions": rows,
                "partial_failure": True,
                "validate_only": validate_only,
            }
        )
    except GoogleAdsException as ex:
        raise utils.google_ads_tool_error(ex)
    except (TypeError, ValueError, KeyError) as ex:
        raise utils.ToolError(f"Invalid conversion: {ex}")
    result = utils.format_output_value(response)
    result["validate_only"] = validate_only
    return result
