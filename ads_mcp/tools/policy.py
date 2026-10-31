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

"""Tools for finding disapproved and limited ads, keywords and assets."""

from collections import Counter
from typing import Any, Dict, List, Literal
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

import ads_mcp.utils as utils
from ads_mcp.tools.search import search as run_search

policy_mcp = FastMCP("policy")

ApprovalStatus = Literal[
    "DISAPPROVED", "APPROVED_LIMITED", "AREA_OF_INTEREST_ONLY"
]

_APPEAL_GUIDANCE = (
    "The Google Ads API cannot file policy appeals. Fix the ad, keyword or "
    "asset (editing it sends it for review again), or appeal in Google Ads "
    "under Tools > Policy manager. For exemptible policies, an ad can be "
    "resubmitted with an exemption request using `mutate` with "
    "`policy_validation_parameter` on the ad_group_ad_operation."
)


# PolicyTopicEvidence list fields and the repeated field inside each.
_EVIDENCE_LISTS = (
    ("text_list", "texts"),
    ("website_list", "websites"),
    ("destination_text_list", "destination_texts"),
)


def _topics(entries: Any) -> List[Dict[str, Any]]:
    """Simplifies policy topic entries to topic, type and short evidence."""
    out = []
    for entry in entries or []:
        evidence = []
        for ev in entry.get("evidences", []) or []:
            for key, inner in _EVIDENCE_LISTS:
                evidence.extend((ev.get(key) or {}).get(inner, []))
            if ev.get("destination_not_working"):
                evidence.append("destination not working")
            if ev.get("destination_mismatch"):
                evidence.append("destination mismatch")
        item = {"topic": entry.get("topic"), "type": entry.get("type_")}
        if evidence:
            item["evidence"] = evidence[:5]
        out.append(item)
    return out


def _in_list(values: List[str]) -> str:
    return "(" + ", ".join(f"'{v}'" for v in values) + ")"


def _section(
    rows_fn, errors: Dict[str, str], name: str
) -> List[Dict[str, Any]]:
    """Runs one query; records its error instead of failing the whole report."""
    try:
        return rows_fn()
    except ToolError as ex:
        errors[name] = str(ex)
        return []


@policy_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def list_policy_issues(
    customer_id: str | int,
    approval_statuses: List[ApprovalStatus] = [
        "DISAPPROVED",
        "APPROVED_LIMITED",
    ],
    include: List[Literal["ads", "keywords", "assets"]] = [
        "ads",
        "keywords",
        "assets",
    ],
    limit: int = 200,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Lists disapproved or limited ads, keywords and ad assets with their policy reasons.

    Covers non-removed items in non-removed campaigns. Each item has IDs,
    names, approval and review status, and the policy topics with short
    evidence. `summary` counts items by policy topic so the biggest problems
    stand out.

    The API cannot submit appeals; see `how_to_resolve` in the result.

    Args:
        customer_id: The ID of the customer.
        approval_statuses: Which approval statuses to include.
        include: Which entity types to check.
        limit: Maximum rows per entity type.
        login_customer_id: Optional manager customer ID.
    """
    statuses = _in_list(approval_statuses)
    live = [
        "campaign.status != 'REMOVED'",
        "ad_group.status != 'REMOVED'",
    ]
    errors: Dict[str, str] = {}
    result: Dict[str, Any] = {}
    topic_counts: Counter = Counter()

    def query(resource, fields, conditions):
        return run_search(
            customer_id=customer_id,
            fields=fields,
            resource=resource,
            conditions=conditions,
            limit=limit,
            login_customer_id=login_customer_id,
        )

    if "ads" in include:

        def ads():
            rows = query(
                "ad_group_ad",
                [
                    "campaign.id",
                    "campaign.name",
                    "ad_group.id",
                    "ad_group.name",
                    "ad_group_ad.ad.id",
                    "ad_group_ad.ad.type",
                    "ad_group_ad.ad.final_urls",
                    "ad_group_ad.status",
                    "ad_group_ad.policy_summary.approval_status",
                    "ad_group_ad.policy_summary.review_status",
                    "ad_group_ad.policy_summary.policy_topic_entries",
                ],
                live
                + [
                    "ad_group_ad.status != 'REMOVED'",
                    f"ad_group_ad.policy_summary.approval_status IN {statuses}",
                ],
            )
            return [
                {
                    "campaign": {
                        "id": r.get("campaign.id"),
                        "name": r.get("campaign.name"),
                    },
                    "ad_group": {
                        "id": r.get("ad_group.id"),
                        "name": r.get("ad_group.name"),
                    },
                    "ad_id": r.get("ad_group_ad.ad.id"),
                    "ad_type": r.get("ad_group_ad.ad.type"),
                    "final_urls": r.get("ad_group_ad.ad.final_urls"),
                    "status": r.get("ad_group_ad.status"),
                    "approval_status": r.get(
                        "ad_group_ad.policy_summary.approval_status"
                    ),
                    "review_status": r.get(
                        "ad_group_ad.policy_summary.review_status"
                    ),
                    "policy_topics": _topics(
                        r.get("ad_group_ad.policy_summary.policy_topic_entries")
                    ),
                }
                for r in rows
            ]

        result["ads"] = _section(ads, errors, "ads")

    if "keywords" in include:

        def keywords():
            rows = query(
                "ad_group_criterion",
                [
                    "campaign.id",
                    "campaign.name",
                    "ad_group.id",
                    "ad_group.name",
                    "ad_group_criterion.criterion_id",
                    "ad_group_criterion.keyword.text",
                    "ad_group_criterion.keyword.match_type",
                    "ad_group_criterion.approval_status",
                    "ad_group_criterion.disapproval_reasons",
                ],
                live
                + [
                    "ad_group_criterion.type = 'KEYWORD'",
                    "ad_group_criterion.status != 'REMOVED'",
                    "ad_group_criterion.approval_status = 'DISAPPROVED'",
                ],
            )
            return [
                {
                    "campaign": {
                        "id": r.get("campaign.id"),
                        "name": r.get("campaign.name"),
                    },
                    "ad_group": {
                        "id": r.get("ad_group.id"),
                        "name": r.get("ad_group.name"),
                    },
                    "criterion_id": r.get("ad_group_criterion.criterion_id"),
                    "keyword": r.get("ad_group_criterion.keyword.text"),
                    "match_type": r.get(
                        "ad_group_criterion.keyword.match_type"
                    ),
                    "approval_status": r.get(
                        "ad_group_criterion.approval_status"
                    ),
                    "policy_topics": [
                        {"topic": reason}
                        for reason in r.get(
                            "ad_group_criterion.disapproval_reasons"
                        )
                        or []
                    ],
                }
                for r in rows
            ]

        result["keywords"] = _section(keywords, errors, "keywords")

    if "assets" in include:

        def assets():
            rows = query(
                "ad_group_ad_asset_view",
                [
                    "campaign.id",
                    "campaign.name",
                    "ad_group.id",
                    "ad_group_ad.ad.id",
                    "asset.id",
                    "asset.name",
                    "asset.type",
                    "ad_group_ad_asset_view.field_type",
                    "ad_group_ad_asset_view.policy_summary.approval_status",
                    "ad_group_ad_asset_view.policy_summary.review_status",
                    "ad_group_ad_asset_view.policy_summary.policy_topic_entries",
                ],
                live
                + [
                    "ad_group_ad_asset_view.enabled = TRUE",
                    "ad_group_ad_asset_view.policy_summary.approval_status IN "
                    + statuses,
                ],
            )
            return [
                {
                    "campaign": {
                        "id": r.get("campaign.id"),
                        "name": r.get("campaign.name"),
                    },
                    "ad_group_id": r.get("ad_group.id"),
                    "ad_id": r.get("ad_group_ad.ad.id"),
                    "asset": {
                        "id": r.get("asset.id"),
                        "name": r.get("asset.name"),
                        "type": r.get("asset.type"),
                    },
                    "field_type": r.get("ad_group_ad_asset_view.field_type"),
                    "approval_status": r.get(
                        "ad_group_ad_asset_view.policy_summary.approval_status"
                    ),
                    "review_status": r.get(
                        "ad_group_ad_asset_view.policy_summary.review_status"
                    ),
                    "policy_topics": _topics(
                        r.get(
                            "ad_group_ad_asset_view.policy_summary.policy_topic_entries"
                        )
                    ),
                }
                for r in rows
            ]

        result["assets"] = _section(assets, errors, "assets")

    for items in result.values():
        for item in items:
            for topic in item.get("policy_topics", []):
                topic_counts[topic.get("topic")] += 1

    result["summary"] = {
        "counts": {k: len(v) for k, v in result.items() if isinstance(v, list)},
        "top_policy_topics": [
            {"topic": t, "items": n} for t, n in topic_counts.most_common(10)
        ],
    }
    result["how_to_resolve"] = _APPEAL_GUIDANCE
    if errors:
        result["errors"] = errors
    return result
