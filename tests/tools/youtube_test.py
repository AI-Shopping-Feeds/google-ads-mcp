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

"""Test cases for the YouTube upload tools."""

import asyncio
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from fastmcp.exceptions import ToolError
from google.ads.googleads.v26.services.types.google_ads_service import (
    MutateGoogleAdsRequest,
    MutateGoogleAdsResponse,
)
from google.ads.googleads.v26.services.types.youtube_video_upload_service import (
    CreateYouTubeVideoUploadRequest,
    CreateYouTubeVideoUploadResponse,
)

from ads_mcp.tools import youtube


class FakeContext:
    """Records progress reported by a tool."""

    def __init__(self):
        self.progress = []

    async def report_progress(self, progress, total=None, message=None):
        self.progress.append((progress, total, message))


def _upload(ctx=None, **kwargs):
    """Runs the async upload tool with a fake Context."""
    return asyncio.run(
        youtube.upload_videos(ctx=ctx or FakeContext(), **kwargs)
    )


class FakeSession:
    """Stands in for google.api_core's ResumableUploadSession."""

    def __init__(self):
        self.uploaded = None

    def upload(self, stream, size=None, content_type=None):
        self.uploaded = (stream.read(), size, content_type)
        return CreateYouTubeVideoUploadResponse(
            resource_name="customers/1/youTubeVideoUploads/9"
        )


class TestYouTubeTools(unittest.TestCase):
    """Test cases for the youtube tools module."""

    def setUp(self):
        patcher = patch("ads_mcp.utils.get_googleads_service")
        self.mock_get_service = patcher.start()
        self.addCleanup(patcher.stop)
        self.service = MagicMock()
        self.session = FakeSession()
        self.service.create_you_tube_video_upload.return_value = self.session
        self.mock_get_service.return_value = self.service

        self.dir = tempfile.mkdtemp()
        self.video = os.path.join(self.dir, "promo.mp4")
        with open(self.video, "wb") as f:
            f.write(b"MP4DATA")
        env = patch.dict(
            os.environ, {youtube.UPLOAD_DIR_ENV_VAR: self.dir}, clear=False
        )
        env.start()
        self.addCleanup(env.stop)

    def test_upload_from_path(self):
        result = _upload(
            customer_id="123-456-7890",
            videos=[
                {
                    "path": self.video,
                    "title": "Spring promo",
                    "description": "New range",
                    "ai_generated": False,
                }
            ],
            channel_id="UCabc",
        )

        self.assertEqual(result["uploaded"], 1)
        self.assertEqual(
            result["videos"][0]["resource_name"],
            "customers/1/youTubeVideoUploads/9",
        )
        self.assertEqual(self.session.uploaded, (b"MP4DATA", 7, "video/mp4"))
        self.mock_get_service.assert_called_once_with(
            "YouTubeVideoUploadService", login_customer_id=None
        )
        _, kwargs = self.service.create_you_tube_video_upload.call_args
        request = CreateYouTubeVideoUploadRequest(kwargs["request"])
        self.assertEqual(request.customer_id, "1234567890")
        upload = request.you_tube_video_upload
        self.assertEqual(upload.video_title, "Spring promo")
        self.assertEqual(upload.channel_id, "UCabc")
        self.assertEqual(upload.video_privacy.name, "UNLISTED")
        self.assertEqual(
            upload.video_content_metadata.generative_content_disclosure.name,
            "NON_GENERATIVE_CONTENT",
        )

    def test_bad_video_does_not_stop_batch(self):
        result = _upload(
            customer_id="1",
            videos=[
                {"path": self.video, "title": "<bad>"},
                {"path": self.video, "title": "x" * 101},
                {"path": "/etc/hosts", "title": "outside"},
                {"path": self.video, "title": "Good"},
            ],
        )

        self.assertEqual(result["uploaded"], 1)
        self.assertEqual(result["failed"], 3)
        self.assertIn("outside", result["videos"][2]["error"])
        self.assertEqual(
            self.service.create_you_tube_video_upload.call_count, 1
        )

    def test_local_paths_disabled_when_hosted(self):
        with patch.dict(
            os.environ,
            {
                "GOOGLE_ADS_MCP_OAUTH_CLIENT_ID": "id",
                "GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET": "secret",
            },
        ):
            os.environ.pop(youtube.UPLOAD_DIR_ENV_VAR)
            result = _upload(
                customer_id="1", videos=[{"path": self.video, "title": "A"}]
            )

        self.assertIn("disabled", result["videos"][0]["error"])
        self.service.create_you_tube_video_upload.assert_not_called()

    def test_url_to_private_host_is_rejected(self):
        result = _upload(
            customer_id="1",
            videos=[{"url": "http://127.0.0.1/video.mp4", "title": "A"}],
        )

        self.assertIn("non-public", result["videos"][0]["error"])
        self.service.create_you_tube_video_upload.assert_not_called()

    def test_url_is_downloaded_then_uploaded(self):
        def fake_download(url, directory):
            path = os.path.join(directory, "remote.mp4")
            with open(path, "wb") as f:
                f.write(b"REMOTE")
            return path

        with patch.object(youtube, "_download", side_effect=fake_download):
            result = _upload(
                customer_id="1",
                videos=[{"url": "https://cdn.example.com/a.mp4", "title": "A"}],
            )

        self.assertEqual(result["uploaded"], 1)
        self.assertEqual(self.session.uploaded[0], b"REMOTE")

    @patch("ads_mcp.tools.youtube.run_search")
    def test_list_video_uploads(self, mock_search):
        mock_search.return_value = [
            {
                "you_tube_video_upload.state": "PROCESSED",
                "you_tube_video_upload.video_id": "abcdefghijk",
            }
        ]

        result = youtube.list_video_uploads(
            customer_id="1",
            resource_names=["customers/1/youTubeVideoUploads/9"],
            states=["PROCESSED"],
        )

        self.assertEqual(
            result, [{"state": "PROCESSED", "video_id": "abcdefghijk"}]
        )
        conditions = mock_search.call_args.kwargs["conditions"]
        self.assertIn(
            "you_tube_video_upload.resource_name IN "
            "('customers/1/youTubeVideoUploads/9')",
            conditions,
        )

    def test_create_video_assets(self):
        self.service.mutate.return_value = MutateGoogleAdsResponse()

        youtube.create_video_assets(
            customer_id="1",
            videos=[{"video_id": "abcdefghijk", "name": "Promo"}],
        )

        _, kwargs = self.service.mutate.call_args
        request = MutateGoogleAdsRequest(kwargs["request"])
        asset = request.mutate_operations[0].asset_operation.create
        self.assertEqual(
            asset.youtube_video_asset.youtube_video_id, "abcdefghijk"
        )
        self.assertEqual(asset.name, "Promo")

    def test_create_video_assets_rejects_urls(self):
        with self.assertRaises(ToolError):
            youtube.create_video_assets(
                customer_id="1",
                videos=[{"video_id": "https://youtu.be/abcdefghijk"}],
            )


class TestRealClientWiring(unittest.TestCase):
    """Checks the real google-ads client builds an upload-capable service."""

    def test_service_returns_resumable_session_factory(self):
        from google.ads.googleads.client import GoogleAdsClient
        from google.oauth2.credentials import Credentials

        client = GoogleAdsClient(
            credentials=Credentials(token="fake"),
            developer_token="dev",
            use_proto_plus=True,
        )
        service = client.get_service("YouTubeVideoUploadService", version="v26")
        stub = service._transport.create_you_tube_video_upload
        # The gRPC transport must delegate uploads to REST rather than erroring.
        self.assertNotEqual(type(stub).__name__, "_ErrorStub")

        session = service.create_you_tube_video_upload(
            request=youtube._upload_request("1", {"title": "t"}, None)
        )
        self.assertEqual(type(session).__name__, "ResumableUploadSession")
        self.assertIn(
            "/resumable/upload/v26/customers/1/youTubeVideoUploads:create",
            session.upload_url,
        )


if __name__ == "__main__":
    unittest.main()
