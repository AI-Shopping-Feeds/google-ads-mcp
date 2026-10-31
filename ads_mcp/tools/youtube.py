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

"""Tools for uploading videos to YouTube through the Google Ads API and turning them into assets.

Uploads use YouTubeVideoUploadService, so they need no YouTube Data API
project or quota. Without a channel ID, videos go to a Google-managed
channel tied to the Ads account and can only be UNLISTED.
"""

import ipaddress
import mimetypes
import os
import shutil
import socket
import tempfile
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Literal
import anyio
from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

import ads_mcp.utils as utils
from ads_mcp.tools.search import search as run_search
from ads_mcp.tools.mutate import _mutate_operations

youtube_mcp = FastMCP("youtube")

# Local video files may only be read from inside this directory when it is set.
UPLOAD_DIR_ENV_VAR = "GOOGLE_ADS_MCP_UPLOAD_DIR"
# Largest file, in megabytes, downloaded from a URL before uploading.
MAX_DOWNLOAD_MB_ENV_VAR = "GOOGLE_ADS_MCP_MAX_DOWNLOAD_MB"
_DEFAULT_MAX_DOWNLOAD_MB = 2048

_MAX_TITLE = 100
_MAX_DESCRIPTION = 5000


def _is_hosted() -> bool:
    """True when the server runs over HTTP for remote users (OAuth proxy mode)."""
    return bool(
        os.environ.get("GOOGLE_ADS_MCP_OAUTH_CLIENT_ID")
        and os.environ.get("GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET")
    )


def _resolve_local_path(path: str) -> str:
    """Returns the real path of a local video, enforcing the upload directory rules."""
    real = os.path.realpath(os.path.expanduser(path))
    allowed = os.environ.get(UPLOAD_DIR_ENV_VAR)
    if allowed:
        root = os.path.realpath(os.path.expanduser(allowed))
        if os.path.commonpath([real, root]) != root:
            raise ValueError(
                f"'{path}' is outside {UPLOAD_DIR_ENV_VAR} ({root})."
            )
    elif _is_hosted():
        raise ValueError(
            "Local file paths are disabled on a hosted server. Use a URL, or set "
            f"{UPLOAD_DIR_ENV_VAR} to allow a directory."
        )
    if not os.path.isfile(real):
        raise ValueError(f"'{path}' is not a file.")
    return real


def _check_public_host(url: str) -> None:
    """Rejects non-HTTP(S) URLs and hosts that resolve to private addresses."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError(f"'{url}' is not an http(s) URL.")
    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as ex:
        raise ValueError(f"Cannot resolve '{parsed.hostname}': {ex}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise ValueError(
                f"'{parsed.hostname}' resolves to a non-public address ({ip})."
            )


class _CheckedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-checks every redirect target so a redirect cannot reach a private host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _check_public_host(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _download(url: str, directory: str) -> str:
    """Streams a public URL to a temporary file and returns its path."""
    _check_public_host(url)
    limit = (
        int(os.environ.get(MAX_DOWNLOAD_MB_ENV_VAR, _DEFAULT_MAX_DOWNLOAD_MB))
        * 1024
        * 1024
    )
    name = os.path.basename(urllib.parse.urlparse(url).path) or "video"
    target = os.path.join(directory, name)
    opener = urllib.request.build_opener(_CheckedRedirectHandler)
    with opener.open(url, timeout=60) as response, open(target, "wb") as out:
        copied = 0
        while chunk := response.read(1024 * 1024):
            copied += len(chunk)
            if copied > limit:
                raise ValueError(
                    f"'{url}' is larger than {limit // (1024 * 1024)} MB "
                    f"({MAX_DOWNLOAD_MB_ENV_VAR})."
                )
            out.write(chunk)
    return target


def _upload_request(
    customer_id: str, video: Dict[str, Any], channel_id: str | None
) -> Dict[str, Any]:
    title = video.get("title") or ""
    description = video.get("description") or ""
    if not title or len(title) > _MAX_TITLE:
        raise ValueError(
            f"title is required and must be at most {_MAX_TITLE} characters."
        )
    if len(description) > _MAX_DESCRIPTION:
        raise ValueError(
            f"description must be at most {_MAX_DESCRIPTION} characters."
        )
    if any(c in title + description for c in "<>"):
        raise ValueError("title and description cannot contain '<' or '>'.")
    upload: Dict[str, Any] = {
        "video_title": title,
        "video_description": description,
        "video_privacy": video.get("privacy", "UNLISTED"),
    }
    if channel_id:
        upload["channel_id"] = channel_id
    if "ai_generated" in video:
        upload["video_content_metadata"] = {
            "generative_content_disclosure": (
                "GENERATIVE_CONTENT"
                if video["ai_generated"]
                else "NON_GENERATIVE_CONTENT"
            )
        }
    return {"customer_id": customer_id, "you_tube_video_upload": upload}


def _upload_one(
    service: Any,
    cid: str,
    video: Dict[str, Any],
    channel_id: str | None,
    workdir: str,
) -> Dict[str, Any]:
    """Uploads one video and returns its result entry. Never raises."""
    source = video.get("path") or video.get("url")
    entry: Dict[str, Any] = {"source": source, "title": video.get("title")}
    try:
        if bool(video.get("path")) == bool(video.get("url")):
            raise ValueError("Give exactly one of 'path' or 'url'.")
        request = _upload_request(cid, video, channel_id)
        local = (
            _resolve_local_path(video["path"])
            if video.get("path")
            else _download(video["url"], workdir)
        )
        content_type = (
            mimetypes.guess_type(local)[0] or "application/octet-stream"
        )
        utils.logger.info("ads_mcp.upload_videos %s", source)
        session = service.create_you_tube_video_upload(request=request)
        with open(local, "rb") as stream:
            response = session.upload(
                stream,
                size=os.path.getsize(local),
                content_type=content_type,
            )
        entry["resource_name"] = getattr(response, "resource_name", None)
        entry["status"] = "uploaded"
    except Exception as ex:  # one bad video must not stop the batch
        entry["status"] = "error"
        entry["error"] = str(ex)
    return entry


@youtube_mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False)
)
async def upload_videos(
    customer_id: str | int,
    videos: List[Dict[str, Any]],
    ctx: Context,
    channel_id: str | None = None,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Uploads videos to YouTube through the Google Ads API, ready to use in video ads.

    Each video is streamed from a local file or a public URL; never pass video
    bytes as arguments. Videos upload one after another and a failure is
    reported without stopping the rest. Large files can take minutes each, so
    upload a few at a time.

    Uploads are processed by YouTube afterwards: call `list_video_uploads`
    until `state` is PROCESSED to get the `video_id`, then
    `create_video_assets`.

    Args:
        customer_id: The ID of the Google Ads customer.
        videos: Items of the form {"path": "/videos/a.mp4"} or
            {"url": "https://..."}, plus "title" (required, max 100 chars),
            optional "description" (max 5000 chars; neither may contain < or >),
            "privacy" ("UNLISTED" default, or "PUBLIC" on your own channel) and
            "ai_generated" (true/false, the generative-content disclosure).
        channel_id: Your brand channel ID (starts with UC). Omit to upload to
            the Google-managed channel for this Ads account (UNLISTED only).
            Uploading to your own channel needs user OAuth credentials.
        login_customer_id: Optional manager customer ID.
    """
    cid = utils.clean_customer_id(customer_id)
    service = utils.get_googleads_service(
        "YouTubeVideoUploadService", login_customer_id=login_customer_id
    )
    results = []
    workdir = tempfile.mkdtemp(prefix="ads-mcp-video-")
    try:
        await ctx.report_progress(0, len(videos), "Starting uploads")
        for i, video in enumerate(videos, start=1):
            # Uploads block on network I/O, so run them off the event loop.
            entry = await anyio.to_thread.run_sync(
                _upload_one, service, cid, video, channel_id, workdir
            )
            results.append(entry)
            await ctx.report_progress(
                i, len(videos), f"{entry['status']}: {entry['source']}"
            )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    return {
        "uploaded": sum(1 for r in results if r["status"] == "uploaded"),
        "failed": sum(1 for r in results if r["status"] == "error"),
        "videos": results,
        "next_step": "Call list_video_uploads until state is PROCESSED, "
        "then create_video_assets with the video_id values.",
    }


@youtube_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def list_video_uploads(
    customer_id: str | int,
    resource_names: List[str] = [],
    states: List[
        Literal[
            "PENDING",
            "UPLOADED",
            "PROCESSED",
            "FAILED",
            "REJECTED",
            "UNAVAILABLE",
        ]
    ] = [],
    limit: int = 100,
    login_customer_id: str | int | None = None,
) -> List[Dict[str, Any]]:
    """Lists videos uploaded through the Google Ads API with their processing state and YouTube video ID.

    States: PENDING and UPLOADED are still in progress; PROCESSED means the
    video is ready and `video_id` is set; FAILED, REJECTED and UNAVAILABLE
    mean it can't be used.

    Args:
        customer_id: The ID of the Google Ads customer.
        resource_names: Only these uploads (from upload_videos).
        states: Only uploads in these states.
        limit: Maximum rows to return.
        login_customer_id: Optional manager customer ID.
    """
    conditions = []
    if resource_names:
        conditions.append(
            "you_tube_video_upload.resource_name IN ("
            + ", ".join(f"'{r}'" for r in resource_names)
            + ")"
        )
    if states:
        conditions.append(
            "you_tube_video_upload.state IN ("
            + ", ".join(f"'{s}'" for s in states)
            + ")"
        )
    rows = run_search(
        customer_id=customer_id,
        fields=[
            "you_tube_video_upload.resource_name",
            "you_tube_video_upload.video_upload_id",
            "you_tube_video_upload.state",
            "you_tube_video_upload.video_id",
            "you_tube_video_upload.channel_id",
            "you_tube_video_upload.video_title",
            "you_tube_video_upload.video_privacy",
        ],
        resource="you_tube_video_upload",
        conditions=conditions,
        limit=limit,
        login_customer_id=login_customer_id,
    )
    return [
        {k.removeprefix("you_tube_video_upload."): v for k, v in row.items()}
        for row in rows
    ]


@youtube_mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False)
)
def create_video_assets(
    customer_id: str | int,
    videos: List[Dict[str, str]],
    validate_only: bool = False,
    login_customer_id: str | int | None = None,
) -> Dict[str, Any]:
    """Creates YouTube video assets from video IDs, ready to attach to ads.

    Attach the returned asset resource names with `mutate`:
    Performance Max: asset_group_asset_operation with field_type YOUTUBE_VIDEO;
    Demand Gen: ad_group_ad with demand_gen_video_responsive_ad.videos;
    Video campaigns: video_responsive_ad.videos.

    Args:
        customer_id: The ID of the Google Ads customer.
        videos: Items of the form {"video_id": "dQw4w9WgXcQ", "name": "Spring promo"}.
            Use the 11-character YouTube ID, not a URL.
        validate_only: If True, validate the request but do not apply it.
        login_customer_id: Optional manager customer ID.
    """
    cid = utils.clean_customer_id(customer_id)
    ops = []
    for video in videos:
        video_id = video.get("video_id", "")
        if len(video_id) != 11:
            raise utils.ToolError(
                f"'{video_id}' is not an 11-character YouTube video ID."
            )
        asset: Dict[str, Any] = {
            "youtube_video_asset": {"youtube_video_id": video_id}
        }
        if video.get("name"):
            asset["name"] = video["name"]
        ops.append({"asset_operation": {"create": asset}})
    return _mutate_operations(cid, ops, validate_only, False, login_customer_id)
