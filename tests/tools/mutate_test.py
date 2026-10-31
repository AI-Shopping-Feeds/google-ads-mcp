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

"""Test cases for the mutate tools."""

import unittest
from unittest.mock import MagicMock, patch

from fastmcp.exceptions import ToolError
from google.ads.googleads.v26.services.types.google_ads_service import (
    MutateGoogleAdsRequest,
    MutateGoogleAdsResponse,
)

from ads_mcp.tools import mutate


class TestMutateTools(unittest.TestCase):
    """Test cases for the mutate tools module."""

    def setUp(self):
        patcher = patch("ads_mcp.utils.get_googleads_service")
        self.mock_get_service = patcher.start()
        self.addCleanup(patcher.stop)
        self.mock_service = MagicMock()
        self.mock_service.mutate.return_value = MutateGoogleAdsResponse()
        self.mock_get_service.return_value = self.mock_service

    def _sent_request(self) -> MutateGoogleAdsRequest:
        """Returns the request sent to the API, parsed as the real proto type."""
        _, kwargs = self.mock_service.mutate.call_args
        return MutateGoogleAdsRequest(kwargs["request"])

    def test_mutate_passes_operations_and_flags(self):
        result = mutate.mutate(
            customer_id="123-456-7890",
            operations=[
                {
                    "campaign_operation": {
                        "remove": "customers/1234567890/campaigns/1"
                    }
                }
            ],
            validate_only=True,
            partial_failure=True,
        )

        request = self._sent_request()
        self.assertEqual(request.customer_id, "1234567890")
        self.assertTrue(request.validate_only)
        self.assertTrue(request.partial_failure)
        self.assertEqual(
            request.mutate_operations[0].campaign_operation.remove,
            "customers/1234567890/campaigns/1",
        )
        self.assertTrue(result["validate_only"])
        self.mock_get_service.assert_called_once_with(
            "GoogleAdsService", login_customer_id=None
        )

    def test_mutate_requires_operations(self):
        with self.assertRaises(ToolError):
            mutate.mutate(customer_id="1", operations=[])

    def test_update_campaign_status_builds_update_mask(self):
        mutate.update_campaign_status(
            customer_id="1", campaign_ids=[10, 11], status="PAUSED"
        )

        ops = self._sent_request().mutate_operations
        self.assertEqual(len(ops), 2)
        op = ops[1].campaign_operation
        self.assertEqual(op.update.resource_name, "customers/1/campaigns/11")
        self.assertEqual(op.update.status.name, "PAUSED")
        self.assertEqual(list(op.update_mask.paths), ["status"])

    def test_update_ad_status_uses_composite_resource_name(self):
        mutate.update_ad_status(
            customer_id="1", ad_group_id=5, ad_ids=[9], status="ENABLED"
        )

        op = self._sent_request().mutate_operations[0].ad_group_ad_operation
        self.assertEqual(op.update.resource_name, "customers/1/adGroupAds/5~9")

    def test_update_campaign_budget_rejects_non_positive(self):
        with self.assertRaises(ToolError):
            mutate.update_campaign_budget(
                customer_id="1", budget_id=2, amount_micros=0
            )

    def test_update_campaign_budget(self):
        mutate.update_campaign_budget(
            customer_id="1", budget_id=2, amount_micros=25_000_000
        )

        op = self._sent_request().mutate_operations[0].campaign_budget_operation
        self.assertEqual(op.update.amount_micros, 25_000_000)
        self.assertEqual(list(op.update_mask.paths), ["amount_micros"])

    def test_add_keywords(self):
        mutate.add_keywords(
            customer_id="1",
            ad_group_id=7,
            keywords=[
                {
                    "text": "red shoes",
                    "match_type": "EXACT",
                    "cpc_bid_micros": 1500000,
                },
                {"text": "shoes", "match_type": "PHRASE", "status": "PAUSED"},
            ],
        )

        ops = self._sent_request().mutate_operations
        first = ops[0].ad_group_criterion_operation.create
        self.assertEqual(first.ad_group, "customers/1/adGroups/7")
        self.assertEqual(first.keyword.text, "red shoes")
        self.assertEqual(first.keyword.match_type.name, "EXACT")
        self.assertEqual(first.cpc_bid_micros, 1500000)
        second = ops[1].ad_group_criterion_operation.create
        self.assertEqual(second.status.name, "PAUSED")

    def test_add_keywords_requires_match_type(self):
        with self.assertRaises(ToolError):
            mutate.add_keywords(
                customer_id="1", ad_group_id=7, keywords=[{"text": "shoes"}]
            )

    def test_add_negative_keywords_campaign(self):
        mutate.add_negative_keywords(
            customer_id="1",
            campaign_id=3,
            keywords=[{"text": "free", "match_type": "BROAD"}],
        )

        create = (
            self._sent_request()
            .mutate_operations[0]
            .campaign_criterion_operation.create
        )
        self.assertTrue(create.negative)
        self.assertEqual(create.campaign, "customers/1/campaigns/3")

    def test_add_negative_keywords_needs_exactly_one_target(self):
        with self.assertRaises(ToolError):
            mutate.add_negative_keywords(
                customer_id="1",
                keywords=[{"text": "free", "match_type": "BROAD"}],
            )
        with self.assertRaises(ToolError):
            mutate.add_negative_keywords(
                customer_id="1",
                campaign_id=1,
                ad_group_id=2,
                keywords=[{"text": "free", "match_type": "BROAD"}],
            )

    def test_update_keyword(self):
        mutate.update_keyword(
            customer_id="1",
            ad_group_id=2,
            criterion_id=3,
            status="PAUSED",
            cpc_bid_micros=900000,
        )

        op = (
            self._sent_request()
            .mutate_operations[0]
            .ad_group_criterion_operation
        )
        self.assertEqual(
            op.update.resource_name, "customers/1/adGroupCriteria/2~3"
        )
        self.assertEqual(
            list(op.update_mask.paths), ["status", "cpc_bid_micros"]
        )

    def test_update_keyword_requires_a_change(self):
        with self.assertRaises(ToolError):
            mutate.update_keyword(
                customer_id="1", ad_group_id=2, criterion_id=3
            )

    def test_remove_resources_maps_operation_types(self):
        mutate.remove_resources(
            customer_id="1",
            resource_names=[
                "customers/1/campaigns/2",
                "customers/1/adGroupCriteria/3~4",
                "customers/1/adGroupAds/3~5",
                "customers/1/campaignBudgets/6",
            ],
        )

        ops = self._sent_request().mutate_operations
        self.assertEqual(
            ops[0].campaign_operation.remove, "customers/1/campaigns/2"
        )
        self.assertEqual(
            ops[1].ad_group_criterion_operation.remove,
            "customers/1/adGroupCriteria/3~4",
        )
        self.assertEqual(
            ops[2].ad_group_ad_operation.remove, "customers/1/adGroupAds/3~5"
        )
        self.assertEqual(
            ops[3].campaign_budget_operation.remove,
            "customers/1/campaignBudgets/6",
        )

    def test_remove_resources_rejects_other_customer(self):
        with self.assertRaises(ToolError):
            mutate.remove_resources(
                customer_id="1", resource_names=["customers/2/campaigns/3"]
            )
        self.mock_service.mutate.assert_not_called()

    def test_apply_recommendations(self):
        self.mock_service.apply_recommendation.return_value = MagicMock()
        with patch("ads_mcp.utils.format_output_value", return_value={}):
            mutate.apply_recommendations(
                customer_id="1",
                recommendation_resource_names=["customers/1/recommendations/a"],
            )

        self.mock_get_service.assert_called_once_with(
            "RecommendationService", login_customer_id=None
        )
        _, kwargs = self.mock_service.apply_recommendation.call_args
        self.assertEqual(
            kwargs["request"]["operations"],
            [{"resource_name": "customers/1/recommendations/a"}],
        )


if __name__ == "__main__":
    unittest.main()
