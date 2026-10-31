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

"""Test cases for the conversion upload tools."""

import unittest
from unittest.mock import MagicMock, patch

from fastmcp.exceptions import ToolError
from google.ads.googleads.v26.services.types.conversion_upload_service import (
    UploadClickConversionsRequest,
    UploadClickConversionsResponse,
)

from ads_mcp.tools import conversions


class TestConversionTools(unittest.TestCase):
    """Test cases for the conversions tools module."""

    def setUp(self):
        patcher = patch("ads_mcp.utils.get_googleads_service")
        self.mock_get_service = patcher.start()
        self.addCleanup(patcher.stop)
        self.service = MagicMock()
        self.service.upload_click_conversions.return_value = (
            UploadClickConversionsResponse()
        )
        self.mock_get_service.return_value = self.service

    def test_upload_click_conversions(self):
        result = conversions.upload_click_conversions(
            customer_id="123-456-7890",
            conversion_action_id=55,
            conversions=[
                {
                    "gclid": "abc",
                    "conversion_date_time": "2026-10-30 14:05:00+00:00",
                    "conversion_value": 49.99,
                    "currency_code": "GBP",
                    "order_id": "A1",
                }
            ],
            validate_only=True,
        )

        _, kwargs = self.service.upload_click_conversions.call_args
        request = UploadClickConversionsRequest(kwargs["request"])
        self.assertEqual(request.customer_id, "1234567890")
        self.assertTrue(request.partial_failure)
        self.assertTrue(request.validate_only)
        conv = request.conversions[0]
        self.assertEqual(
            conv.conversion_action, "customers/1234567890/conversionActions/55"
        )
        self.assertEqual(conv.order_id, "A1")
        self.assertTrue(result["validate_only"])

    def test_requires_one_click_id(self):
        with self.assertRaises(ToolError):
            conversions.upload_click_conversions(
                customer_id="1",
                conversion_action_id=1,
                conversions=[
                    {
                        "gclid": "a",
                        "gbraid": "b",
                        "conversion_date_time": "2026-10-30 14:05:00+00:00",
                    }
                ],
            )
        self.service.upload_click_conversions.assert_not_called()

    def test_requires_date_time(self):
        with self.assertRaises(ToolError):
            conversions.upload_click_conversions(
                customer_id="1",
                conversion_action_id=1,
                conversions=[{"gclid": "a"}],
            )


if __name__ == "__main__":
    unittest.main()
