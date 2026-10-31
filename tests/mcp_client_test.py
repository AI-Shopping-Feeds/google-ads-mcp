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

"""End-to-end tests through an in-memory MCP client."""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from fastmcp import Client

from ads_mcp.coordinator import SERVER_VERSION, mcp
import ads_mcp.server  # noqa: F401  (registers resources)


class TestMCPClient(unittest.IsolatedAsyncioTestCase):
    """Exercises the server the way an MCP client sees it."""

    async def test_server_metadata(self):
        async with Client(mcp) as client:
            info = client.server_info
            self.assertEqual(info.name, "Google Ads Server")
            self.assertEqual(info.version, SERVER_VERSION)
            self.assertNotEqual(info.version, "0.0.0")
            self.assertIn("validate_only", client.instructions)
            self.assertEqual(client.protocol_version, "2026-07-28")

    async def test_every_tool_has_title_and_annotations(self):
        async with Client(mcp) as client:
            first = [t.name for t in await client.list_tools()]
            tools = await client.list_tools()
        self.assertEqual(first, [t.name for t in tools])  # deterministic order
        for tool in tools:
            with self.subTest(tool=tool.name):
                self.assertTrue(tool.title or tool.annotations.title)
                self.assertIsNotNone(tool.annotations.read_only_hint)
        read_only = {t.name for t in tools if t.annotations.read_only_hint}
        self.assertIn("search_search", read_only)
        self.assertNotIn("mutate_mutate", read_only)

    @patch("ads_mcp.utils.get_googleads_service")
    async def test_expected_errors_keep_their_message(self, mock_service):
        import google.auth.exceptions

        mock_service.side_effect = (
            google.auth.exceptions.DefaultCredentialsError(
                "Your default credentials were not found."
            )
        )
        async with Client(mcp) as client:
            result = await client.call_tool(
                "search_search",
                {
                    "customer_id": "1",
                    "fields": ["campaign.id"],
                    "resource": "campaign",
                },
                raise_on_error=False,
            )
        self.assertTrue(result.is_error)
        self.assertIn(
            "default credentials were not found", result.content[0].text
        )

    @patch("ads_mcp.utils.get_googleads_service")
    async def test_unexpected_errors_are_masked(self, mock_service):
        mock_service.side_effect = KeyError("internal detail")
        async with Client(mcp) as client:
            result = await client.call_tool(
                "search_search",
                {
                    "customer_id": "1",
                    "fields": ["campaign.id"],
                    "resource": "campaign",
                },
                raise_on_error=False,
            )
        self.assertTrue(result.is_error)
        self.assertNotIn("internal detail", result.content[0].text)

    @patch("ads_mcp.utils.get_googleads_service")
    async def test_video_upload_reports_progress(self, mock_service):
        session = MagicMock()
        session.upload.return_value = MagicMock(
            resource_name="customers/1/youTubeVideoUploads/9"
        )
        mock_service.return_value.create_you_tube_video_upload.return_value = (
            session
        )
        folder = tempfile.mkdtemp()
        for name in ("a.mp4", "b.mp4"):
            with open(os.path.join(folder, name), "wb") as f:
                f.write(b"video")
        progress = []

        async def on_progress(value, total, message):
            progress.append((value, total))

        with patch.dict(os.environ, {"GOOGLE_ADS_MCP_UPLOAD_DIR": folder}):
            async with Client(mcp, progress_handler=on_progress) as client:
                result = await client.call_tool(
                    "youtube_upload_videos",
                    {
                        "customer_id": "1",
                        "videos": [
                            {
                                "path": os.path.join(folder, "a.mp4"),
                                "title": "A",
                            },
                            {
                                "path": os.path.join(folder, "b.mp4"),
                                "title": "B",
                            },
                        ],
                    },
                )
        self.assertEqual(result.structured_content["uploaded"], 2)
        self.assertEqual(progress, [(0, 2), (1, 2), (2, 2)])


if __name__ == "__main__":
    unittest.main()
