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

"""Test cases for the generic service tools."""

import unittest
from unittest.mock import MagicMock, patch

from fastmcp.exceptions import ToolError

from ads_mcp.tools import services


class TestServicesTools(unittest.TestCase):
    """Test cases for the services tools module."""

    def test_list_services_includes_write_services(self):
        result = services.list_services()

        self.assertEqual(result["api_version"], "v26")
        catalog = result["services"]
        self.assertIn(
            "upload_click_conversions", catalog["ConversionUploadService"]
        )
        self.assertIn("mutate", catalog["GoogleAdsService"])
        self.assertIn("create_customer_client", catalog["CustomerService"])
        for methods in catalog.values():
            self.assertNotIn("from_service_account_file", methods)

    def test_list_services_describes_request_fields(self):
        result = services.list_services("ConversionUploadService")

        fields = result["methods"]["upload_click_conversions"]["request_fields"]
        self.assertIn("conversions", fields)
        self.assertIn("validate_only", fields)

    def test_list_services_unknown(self):
        with self.assertRaises(ToolError):
            services.list_services("NotAService")

    @patch("ads_mcp.utils.get_googleads_service")
    def test_call_service_cleans_customer_id(self, mock_get_service):
        mock_client = MagicMock()
        mock_client.upload_click_conversions.return_value = MagicMock(
            _pb=object()
        )
        mock_get_service.return_value = mock_client

        with patch("ads_mcp.utils.format_output_value", return_value={"ok": 1}):
            result = services.call_service(
                "ConversionUploadService",
                "upload_click_conversions",
                {"customer_id": "123-456-7890", "conversions": []},
            )

        self.assertEqual(result, {"ok": 1})
        mock_get_service.assert_called_once_with(
            "ConversionUploadService", login_customer_id=None
        )
        _, kwargs = mock_client.upload_click_conversions.call_args
        self.assertEqual(kwargs["request"]["customer_id"], "1234567890")

    def test_call_service_rejects_unknown_method(self):
        with self.assertRaises(ToolError):
            services.call_service("CampaignService", "drop_tables", {})


if __name__ == "__main__":
    unittest.main()
