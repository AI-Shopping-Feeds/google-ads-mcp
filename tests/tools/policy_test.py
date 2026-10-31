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

"""Test cases for the policy tools."""

import unittest
from unittest.mock import patch

from fastmcp.exceptions import ToolError
from google.ads.googleads.v26.common.types.policy import PolicyTopicEntry

from ads_mcp import utils
from ads_mcp.tools import policy


def _entries():
    """Policy topic entries formatted the way the search tool returns them."""
    return utils.format_output_value(
        [
            PolicyTopicEntry(
                topic="DESTINATION_NOT_WORKING",
                type_="PROHIBITED",
                evidences=[{"destination_not_working": {"device": "DESKTOP"}}],
            ),
            PolicyTopicEntry(
                topic="TRADEMARKS_IN_AD_TEXT",
                type_="LIMITED",
                evidences=[{"text_list": {"texts": ["Acme"]}}],
            ),
        ]
    )


class TestPolicyTools(unittest.TestCase):
    """Test cases for the policy tools module."""

    @patch("ads_mcp.tools.policy.run_search")
    def test_list_policy_issues(self, mock_search):
        def fake_search(resource, conditions, **kwargs):
            if resource == "ad_group_ad":
                self.assertIn(
                    "ad_group_ad.policy_summary.approval_status IN "
                    "('DISAPPROVED', 'APPROVED_LIMITED')",
                    conditions,
                )
                return [
                    {
                        "campaign.id": 1,
                        "campaign.name": "Brand",
                        "ad_group.id": 2,
                        "ad_group.name": "Shoes",
                        "ad_group_ad.ad.id": 3,
                        "ad_group_ad.ad.type": "RESPONSIVE_SEARCH_AD",
                        "ad_group_ad.policy_summary.approval_status": "DISAPPROVED",
                        "ad_group_ad.policy_summary.review_status": "REVIEWED",
                        "ad_group_ad.policy_summary.policy_topic_entries": _entries(),
                    }
                ]
            if resource == "ad_group_criterion":
                return [
                    {
                        "ad_group_criterion.criterion_id": 9,
                        "ad_group_criterion.keyword.text": "cheap pills",
                        "ad_group_criterion.disapproval_reasons": [
                            "DESTINATION_NOT_WORKING"
                        ],
                    }
                ]
            raise ToolError("asset view not available")

        mock_search.side_effect = fake_search

        result = policy.list_policy_issues(customer_id="1")

        ad = result["ads"][0]
        self.assertEqual(ad["approval_status"], "DISAPPROVED")
        self.assertEqual(
            ad["policy_topics"],
            [
                {
                    "topic": "DESTINATION_NOT_WORKING",
                    "type": "PROHIBITED",
                    "evidence": ["destination not working"],
                },
                {
                    "topic": "TRADEMARKS_IN_AD_TEXT",
                    "type": "LIMITED",
                    "evidence": ["Acme"],
                },
            ],
        )
        self.assertEqual(result["keywords"][0]["keyword"], "cheap pills")
        # A failing section is reported without failing the whole call.
        self.assertEqual(result["assets"], [])
        self.assertIn("assets", result["errors"])
        self.assertEqual(
            result["summary"]["counts"], {"ads": 1, "keywords": 1, "assets": 0}
        )
        self.assertEqual(
            result["summary"]["top_policy_topics"][0],
            {"topic": "DESTINATION_NOT_WORKING", "items": 2},
        )
        self.assertIn("Policy manager", result["how_to_resolve"])

    @patch("ads_mcp.tools.policy.run_search", return_value=[])
    def test_list_policy_issues_include_filter(self, mock_search):
        result = policy.list_policy_issues(customer_id="1", include=["ads"])

        self.assertEqual(mock_search.call_count, 1)
        self.assertNotIn("keywords", result)
        self.assertNotIn("errors", result)


if __name__ == "__main__":
    unittest.main()
