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

"""Test cases for the planning tools."""

import unittest
from unittest.mock import MagicMock, patch

from fastmcp.exceptions import ToolError
from google.ads.googleads.v26.services.types.keyword_plan_idea_service import (
    GenerateKeywordIdeaResult,
    GenerateKeywordIdeasRequest,
)

from ads_mcp.tools import planning


class TestPlanningTools(unittest.TestCase):
    """Test cases for the planning tools module."""

    def setUp(self):
        patcher = patch("ads_mcp.utils.get_googleads_service")
        self.mock_get_service = patcher.start()
        self.addCleanup(patcher.stop)
        self.mock_service = MagicMock()
        self.mock_get_service.return_value = self.mock_service

    def test_generate_keyword_ideas_keyword_seed(self):
        self.mock_service.generate_keyword_ideas.return_value = [
            GenerateKeywordIdeaResult(text="a"),
            GenerateKeywordIdeaResult(text="b"),
            GenerateKeywordIdeaResult(text="c"),
        ]

        result = planning.generate_keyword_ideas(
            customer_id="123-456-7890",
            keywords=["shoes"],
            geo_target_ids=[2826],
            limit=2,
        )

        self.assertEqual([r["text"] for r in result], ["a", "b"])
        _, kwargs = self.mock_service.generate_keyword_ideas.call_args
        request = GenerateKeywordIdeasRequest(kwargs["request"])
        self.assertEqual(request.customer_id, "1234567890")
        self.assertEqual(list(request.keyword_seed.keywords), ["shoes"])
        self.assertEqual(request.language, "languageConstants/1000")
        self.assertEqual(
            list(request.geo_target_constants), ["geoTargetConstants/2826"]
        )

    def test_generate_keyword_ideas_keyword_and_url_seed(self):
        self.mock_service.generate_keyword_ideas.return_value = []

        planning.generate_keyword_ideas(
            customer_id="1", keywords=["shoes"], url="https://example.com"
        )

        _, kwargs = self.mock_service.generate_keyword_ideas.call_args
        self.assertIn("keyword_and_url_seed", kwargs["request"])

    def test_generate_keyword_ideas_requires_seed(self):
        with self.assertRaises(ToolError):
            planning.generate_keyword_ideas(customer_id="1")

    def test_generate_keyword_ideas_site_is_exclusive(self):
        with self.assertRaises(ToolError):
            planning.generate_keyword_ideas(
                customer_id="1", site="example.com", keywords=["x"]
            )

    def test_suggest_geo_targets(self):
        self.mock_service.suggest_geo_target_constants.return_value = MagicMock(
            geo_target_constant_suggestions=[]
        )

        planning.suggest_geo_targets(
            location_names=["London"], country_code="GB"
        )

        _, kwargs = self.mock_service.suggest_geo_target_constants.call_args
        self.assertEqual(
            kwargs["request"]["location_names"], {"names": ["London"]}
        )
        self.assertEqual(kwargs["request"]["country_code"], "GB")


if __name__ == "__main__":
    unittest.main()
