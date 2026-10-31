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

"""Test cases for the Merchant Center link tools."""

import unittest
from unittest.mock import MagicMock, patch

from google.ads.googleads.v26.services.types.product_link_invitation_service import (
    CreateProductLinkInvitationRequest,
    CreateProductLinkInvitationResponse,
    UpdateProductLinkInvitationRequest,
    UpdateProductLinkInvitationResponse,
)
from google.ads.googleads.v26.services.types.product_link_service import (
    RemoveProductLinkRequest,
    RemoveProductLinkResponse,
)

from ads_mcp.tools import merchant_center


class TestMerchantCenterTools(unittest.TestCase):
    """Test cases for the merchant_center tools module."""

    def setUp(self):
        patcher = patch("ads_mcp.utils.get_googleads_service")
        self.mock_get_service = patcher.start()
        self.addCleanup(patcher.stop)
        self.service = MagicMock()
        self.mock_get_service.return_value = self.service

    @patch("ads_mcp.tools.merchant_center.run_search")
    def test_list_links(self, mock_search):
        mock_search.side_effect = [[{"product_link.product_link_id": 1}], []]

        result = merchant_center.list_links(customer_id="1")

        self.assertEqual(result["links"], [{"product_link.product_link_id": 1}])
        self.assertEqual(result["invitations"], [])
        resources = [c.kwargs["resource"] for c in mock_search.call_args_list]
        self.assertEqual(resources, ["product_link", "product_link_invitation"])

    def test_invite_link(self):
        self.service.create_product_link_invitation.return_value = (
            CreateProductLinkInvitationResponse(resource_name="x")
        )

        merchant_center.invite_link(
            customer_id="123-456-7890", merchant_center_id="987654321"
        )

        _, kwargs = self.service.create_product_link_invitation.call_args
        request = CreateProductLinkInvitationRequest(kwargs["request"])
        self.assertEqual(request.customer_id, "1234567890")
        self.assertEqual(
            request.product_link_invitation.merchant_center.merchant_center_id,
            987654321,
        )

    def test_respond_to_invitation(self):
        self.service.update_product_link_invitation.return_value = (
            UpdateProductLinkInvitationResponse()
        )

        merchant_center.respond_to_invitation(
            customer_id="1",
            invitation_resource_name="customers/1/productLinkInvitations/2",
            response="ACCEPTED",
        )

        _, kwargs = self.service.update_product_link_invitation.call_args
        request = UpdateProductLinkInvitationRequest(kwargs["request"])
        self.assertEqual(
            request.product_link_invitation_status.name, "ACCEPTED"
        )

    def test_remove_link(self):
        self.service.remove_product_link.return_value = (
            RemoveProductLinkResponse()
        )

        merchant_center.remove_link(
            customer_id="1",
            product_link_resource_name="customers/1/productLinks/3",
            validate_only=True,
        )

        _, kwargs = self.service.remove_product_link.call_args
        request = RemoveProductLinkRequest(kwargs["request"])
        self.assertEqual(request.resource_name, "customers/1/productLinks/3")
        self.assertTrue(request.validate_only)


if __name__ == "__main__":
    unittest.main()
