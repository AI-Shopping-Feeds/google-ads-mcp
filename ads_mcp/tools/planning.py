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

"""Tools for keyword research and targeting lookups. None of them change an account."""

from typing import Any, Dict, List, Literal
from fastmcp import FastMCP
from mcp.types import ToolAnnotations

import ads_mcp.utils as utils
from google.ads.googleads.errors import GoogleAdsException

planning_mcp = FastMCP("planning")

Network = Literal["GOOGLE_SEARCH", "GOOGLE_SEARCH_AND_PARTNERS"]


def _targeting(
    language_id: str | int, geo_target_ids: List[str | int]
) -> Dict[str, Any]:
    return {
        "language": f"languageConstants/{language_id}",
        "geo_target_constants": [
            f"geoTargetConstants/{g}" for g in geo_target_ids
        ],
    }


@planning_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def generate_keyword_ideas(
    customer_id: str | int,
    keywords: List[str] = [],
    url: str | None = None,
    site: str | None = None,
    language_id: str | int = 1000,
    geo_target_ids: List[str | int] = [2840],
    network: Network = "GOOGLE_SEARCH",
    include_adult_keywords: bool = False,
    limit: int = 100,
    login_customer_id: str | int | None = None,
) -> List[Dict[str, Any]]:
    """Returns keyword ideas with search volume, competition and bid ranges (Keyword Planner).

    Seed with `keywords`, a page `url`, a whole `site` domain, or keywords plus
    a url. Use `suggest_geo_targets` to find geo target IDs.

    Args:
        customer_id: Any customer ID the user can access (used for billing context).
        keywords: Seed keywords.
        url: A page URL to seed ideas from (can be combined with keywords).
        site: A domain such as example.com to seed ideas from (use alone).
        language_id: Language constant ID; 1000 = English, 1001 = German,
            1002 = French, 1003 = Spanish.
        geo_target_ids: Geo target constant IDs; 2840 = United States,
            2826 = United Kingdom, 2036 = Australia, 2124 = Canada.
        network: GOOGLE_SEARCH or GOOGLE_SEARCH_AND_PARTNERS.
        include_adult_keywords: Whether to include adult keywords.
        limit: Maximum number of ideas to return.
        login_customer_id: Optional manager customer ID.
    """
    if not keywords and not url and not site:
        raise utils.ToolError(
            "Provide keywords, a url, or a site to seed ideas."
        )
    if site and (keywords or url):
        raise utils.ToolError(
            "A site seed cannot be combined with keywords or url."
        )

    request: Dict[str, Any] = {
        "customer_id": utils.clean_customer_id(customer_id),
        "keyword_plan_network": network,
        "include_adult_keywords": include_adult_keywords,
        "page_size": min(limit, 10000),
        **_targeting(language_id, geo_target_ids),
    }
    if site:
        request["site_seed"] = {"site": site}
    elif keywords and url:
        request["keyword_and_url_seed"] = {"url": url, "keywords": keywords}
    elif keywords:
        request["keyword_seed"] = {"keywords": keywords}
    else:
        request["url_seed"] = {"url": url}

    service = utils.get_googleads_service(
        "KeywordPlanIdeaService", login_customer_id=login_customer_id
    )
    try:
        ideas = []
        for idea in service.generate_keyword_ideas(request=request):
            ideas.append(utils.format_output_value(idea))
            if len(ideas) >= limit:
                break
        return ideas
    except GoogleAdsException as ex:
        raise utils.google_ads_tool_error(ex)


@planning_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def generate_keyword_historical_metrics(
    customer_id: str | int,
    keywords: List[str],
    language_id: str | int = 1000,
    geo_target_ids: List[str | int] = [2840],
    network: Network = "GOOGLE_SEARCH",
    login_customer_id: str | int | None = None,
) -> List[Dict[str, Any]]:
    """Returns monthly search volume history, competition and bid ranges for specific keywords.

    Args:
        customer_id: Any customer ID the user can access.
        keywords: Up to 10,000 keywords to look up.
        language_id: Language constant ID (1000 = English).
        geo_target_ids: Geo target constant IDs (2840 = United States).
        network: GOOGLE_SEARCH or GOOGLE_SEARCH_AND_PARTNERS.
        login_customer_id: Optional manager customer ID.
    """
    request = {
        "customer_id": utils.clean_customer_id(customer_id),
        "keywords": keywords,
        "keyword_plan_network": network,
        **_targeting(language_id, geo_target_ids),
    }
    service = utils.get_googleads_service(
        "KeywordPlanIdeaService", login_customer_id=login_customer_id
    )
    try:
        response = service.generate_keyword_historical_metrics(request=request)
        return [utils.format_output_value(r) for r in response.results]
    except GoogleAdsException as ex:
        raise utils.google_ads_tool_error(ex)


@planning_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def suggest_geo_targets(
    location_names: List[str],
    locale: str = "en",
    country_code: str | None = None,
    login_customer_id: str | int | None = None,
) -> List[Dict[str, Any]]:
    """Finds geo target constants (IDs for countries, regions, cities) by name.

    Use the returned `geo_target_constant.id` values for keyword planning and
    for location targeting in `mutate` (as `geoTargetConstants/<id>`).

    Args:
        location_names: Place names to look up, e.g. ["London", "Manchester"].
        locale: Language of the returned names, e.g. "en".
        country_code: Optional two-letter country code to narrow results, e.g. "GB".
        login_customer_id: Optional manager customer ID.
    """
    request: Dict[str, Any] = {
        "locale": locale,
        "location_names": {"names": location_names},
    }
    if country_code:
        request["country_code"] = country_code
    service = utils.get_googleads_service(
        "GeoTargetConstantService", login_customer_id=login_customer_id
    )
    try:
        response = service.suggest_geo_target_constants(request=request)
        return [
            utils.format_output_value(s)
            for s in response.geo_target_constant_suggestions
        ]
    except GoogleAdsException as ex:
        raise utils.google_ads_tool_error(ex)
