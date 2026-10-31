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

"""Tools for exposing simple, core API methods to the MCP server."""

from typing import Any, Dict, List
from fastmcp import FastMCP
from mcp.types import ToolAnnotations

import ads_mcp.utils as utils

from google.ads.googleads.v26.services.types.customer_service import (
    ListAccessibleCustomersResponse,
)

customers_mcp = FastMCP("customers")


@customers_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def list_accessible_customers() -> List[str]:
    """Returns ids of customers directly accessible by the user authenticating the call.

    Use this tool first to discover available customer IDs if the user hasn't
    provided one. Most other tools require a valid customer ID as input.

    Returns:
        List[str]: A list of customer IDs.
    """
    ga_service = utils.get_googleads_service("CustomerService")
    accessible_customers: ListAccessibleCustomersResponse = (
        ga_service.list_accessible_customers()
    )
    # remove customer/ from the start of each resource
    return [
        cust_rn.removeprefix("customers/")
        for cust_rn in accessible_customers.resource_names
    ]


@customers_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_account_hierarchy(
    manager_customer_id: str | int,
    include_hidden: bool = False,
    login_customer_id: str | int | None = None,
) -> List[Dict[str, Any]]:
    """Lists every account under a manager (MCC) account, at all levels.

    Each row has the client's ID, name, level (1 = direct child), whether it
    is a manager, its status, currency, time zone and whether it is a test
    account. Pass the manager ID as `login_customer_id` for the other tools
    when working on these accounts.

    Args:
        manager_customer_id: The manager account to start from.
        include_hidden: Whether to include hidden accounts.
        login_customer_id: Optional manager customer ID, if the starting
            manager is itself reached through another manager.
    """
    from ads_mcp.tools.search import search

    conditions = ["customer_client.level >= 1"]
    if not include_hidden:
        conditions.append("customer_client.hidden = FALSE")
    rows = search(
        customer_id=manager_customer_id,
        fields=[
            "customer_client.id",
            "customer_client.descriptive_name",
            "customer_client.level",
            "customer_client.manager",
            "customer_client.status",
            "customer_client.currency_code",
            "customer_client.time_zone",
            "customer_client.test_account",
        ],
        resource="customer_client",
        conditions=conditions,
        orderings=["customer_client.level ASC"],
        login_customer_id=login_customer_id or manager_customer_id,
    )
    return [
        {k.removeprefix("customer_client."): v for k, v in row.items()}
        for row in rows
    ]
