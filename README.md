# Google Ads MCP Server (read + write)

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE) [![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/downloads/) [![Fork of googleads/google-ads-mcp](https://img.shields.io/badge/fork%20of-googleads%2Fgoogle--ads--mcp-lightgrey.svg)](https://github.com/googleads/google-ads-mcp)

An [MCP](https://modelcontextprotocol.io) server for the
[Google Ads API](https://developers.google.com/google-ads/api) (v26). Use it from
Claude, ChatGPT, Cursor, Codex or any MCP client to report on Google Ads accounts
and to create, change and remove campaigns, budgets, keywords, ads and more.

This is a fork of [googleads/google-ads-mcp](https://github.com/googleads/google-ads-mcp), maintained by [AI Shopping Feeds](https://github.com/AI-Shopping-Feeds). The upstream server is read-only. This fork adds:

- **write tools**: any create/update/remove through `GoogleAdsService.Mutate`, plus shortcuts for common changes
- **Google Ads API v26** (`google-ads>=35.0.0`), including v26.1
- **policy issues** (disapproved ads, keywords and assets with reasons), **offline conversion uploads**, **Merchant Center linking**, **MCC hierarchy** and **Keyword Planner**
- **YouTube video uploads** through the Ads API, ready to turn into video ads
- **every other API method** (112 services) through a generic `call_service` tool
- a **read-only mode** (`GOOGLE_ADS_MCP_READ_ONLY=true`)

Part of the AI Shopping Feeds MCP family: **Google Ads** · [Google Merchant Centre](https://github.com/AI-Shopping-Feeds/google-merchant-centre-mcp) · [Google Analytics](https://github.com/AI-Shopping-Feeds/google-analytics-mcp) · [YouTube Studio](https://github.com/AI-Shopping-Feeds/youtube-studio-mcp).

## Let your agent set it up

Paste this into Claude Code, Codex, Cursor or any agent that can read web pages and edit files:

```text
Set up the Google Ads MCP server for me by following https://raw.githubusercontent.com/AI-Shopping-Feeds/google-ads-mcp/main/skills/google-ads-mcp/SKILL.md
```

The agent checks whether it's already connected, installs the runner if you
agree, walks you through the developer token and Google sign-in, adds the server to your
client's config without touching your other servers, and checks it works by
calling `customers_list_accessible_customers`.

The same file is an [Agent Skill](https://agentskills.io), so your agent can keep it as a guide to using the tools well. For Claude Code, copy the folder into your skills:

```bash
git clone --depth 1 https://github.com/AI-Shopping-Feeds/google-ads-mcp.git /tmp/google-ads-mcp
cp -r /tmp/google-ads-mcp/skills/google-ads-mcp ~/.claude/skills/
```

Other agents that support skills load the same `skills/google-ads-mcp` folder from their own skills directory.

## What it can do

29 tools, named `<namespace>_<tool>` (for example `mutate_update_campaign_status`). Every write tool accepts `validate_only` to check a change without applying it.

### Read

| Area | Tools |
|---|---|
| Accounts | `customers_list_accessible_customers`, `customers_get_account_hierarchy` |
| Reporting | `search_search` (GAQL), `metadata_get_resource_metadata` |
| Policy | `policy_list_policy_issues`: disapproved and limited ads, keywords and assets with reasons |
| Keyword research | `planning_generate_keyword_ideas`, `planning_generate_keyword_historical_metrics`, `planning_suggest_geo_targets` |
| Merchant Center | `merchant_center_list_links` |
| YouTube | `youtube_list_video_uploads` |
| API | `services_list_services`: every service and method, with request fields |

### Write

| Area | Tools |
|---|---|
| Any resource | `mutate_mutate`: create, update or remove anything across all 65 operation types, atomically |
| Shortcuts | `mutate_update_campaign_status`, `mutate_update_ad_group_status`, `mutate_update_ad_status`, `mutate_update_campaign_budget`, `mutate_add_keywords`, `mutate_add_negative_keywords`, `mutate_update_keyword`, `mutate_remove_resources` |
| Recommendations | `mutate_apply_recommendations`, `mutate_dismiss_recommendations` |
| Conversions | `conversions_upload_click_conversions` |
| Merchant Center | `merchant_center_invite_link`, `merchant_center_respond_to_invitation`, `merchant_center_remove_link` |
| YouTube | `youtube_upload_videos`, `youtube_create_video_assets` |
| Any RPC | `services_call_service`: Customer Match, reach planning, account creation and the rest |

### Safety

- Every write tool takes `validate_only: true` to check a change with Google without applying it.
- `mutate` is atomic unless you pass `partial_failure: true`.
- Tools carry MCP annotations (read-only, write, destructive) so clients can ask before risky calls.
- `GOOGLE_ADS_MCP_READ_ONLY=true` removes every tool that can change an account.
- Video uploads read local files only inside `GOOGLE_ADS_MCP_UPLOAD_DIR`, and URL downloads must point at public addresses.

## Supported clients

| Client | Works? | How |
|---|---|---|
| Claude Code | ✅ | Local server, `claude mcp add` (below) |
| Claude Desktop | ✅ | Local server, `claude_desktop_config.json` |
| Cursor | ✅ | Local server, `~/.cursor/mcp.json` |
| VS Code (Copilot) | ✅ | Local server, `.vscode/mcp.json` (uses `servers` instead of `mcpServers`) |
| Codex | ✅ | Local server, `~/.codex/config.toml` |
| Gemini CLI | ✅ | Local server, `~/.gemini/settings.json` |
| Windsurf and other local clients | ✅ | Local server, same JSON entry |
| Claude.ai and ChatGPT | ✅ when hosted | Host it over HTTPS with Google sign-in, then add it as a custom connector. See [docs/hosting.md](docs/hosting.md). |

## Setup

### 1. Install uv

The server runs with `uvx` from [uv](https://docs.astral.sh/uv/getting-started/installation/)
(`brew install uv` on macOS) and needs Python 3.10 or later. It installs straight
from this repository:

```shell
uvx --from git+https://github.com/AI-Shopping-Feeds/google-ads-mcp.git google-ads-mcp
```

The `google-ads-mcp` package on PyPI is Google's read-only upstream release, so install from this repository as above. Pin a release by adding `@vX.Y.Z` to the URL.

### 2. Get credentials

1. **Developer token:** in a Google Ads manager account, go to Tools → API Center.
   Writing to real accounts needs Basic or Standard access.
2. **Google Cloud project:** enable the [Google Ads API](https://console.cloud.google.com/apis/library/googleads.googleapis.com)
   and create an OAuth client (Desktop app).
3. **Sign in** with Application Default Credentials:

   ```shell
   gcloud auth application-default login \
     --scopes https://www.googleapis.com/auth/adwords,https://www.googleapis.com/auth/cloud-platform \
     --client-id-file=PATH_TO_OAUTH_CLIENT_JSON
   ```

   The credentials file path it prints is `GOOGLE_APPLICATION_CREDENTIALS`.

If you reach accounts through a manager account, also set `GOOGLE_ADS_LOGIN_CUSTOMER_ID`.

### 3. Add it to your client

Replace the placeholders. Keep your other servers in each file.

**Claude Code**

```bash
claude mcp add --scope user google-ads \
  --env GOOGLE_APPLICATION_CREDENTIALS=/abs/path/credentials.json \
  --env GOOGLE_PROJECT_ID=YOUR_PROJECT_ID \
  --env GOOGLE_ADS_DEVELOPER_TOKEN=YOUR_DEVELOPER_TOKEN \
  -- uvx --from git+https://github.com/AI-Shopping-Feeds/google-ads-mcp.git google-ads-mcp
```

**Claude Desktop, Cursor, Gemini CLI, Windsurf** (and VS Code under `servers`)

```json
{
  "mcpServers": {
    "google-ads": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/AI-Shopping-Feeds/google-ads-mcp.git", "google-ads-mcp"],
      "env": {
        "GOOGLE_APPLICATION_CREDENTIALS": "/abs/path/credentials.json",
        "GOOGLE_PROJECT_ID": "YOUR_PROJECT_ID",
        "GOOGLE_ADS_DEVELOPER_TOKEN": "YOUR_DEVELOPER_TOKEN"
      }
    }
  }
}
```

Desktop apps often can't find `uvx` on the PATH; if the server doesn't start, use
the full path from `which uvx` as the `command`.

**Codex** (`~/.codex/config.toml`)

```toml
[mcp_servers.google-ads]
command = "uvx"
args = ["--from", "git+https://github.com/AI-Shopping-Feeds/google-ads-mcp.git", "google-ads-mcp"]
env = { GOOGLE_APPLICATION_CREDENTIALS = "/abs/path/credentials.json", GOOGLE_PROJECT_ID = "YOUR_PROJECT_ID", GOOGLE_ADS_DEVELOPER_TOKEN = "YOUR_DEVELOPER_TOKEN" }
```

### 4. Check it works

Restart or reload the client, then ask it to "list my Google Ads accounts". It should
call `customers_list_accessible_customers`.

## Configuration

| Variable | Required | What it does |
|---|---|---|
| `GOOGLE_ADS_DEVELOPER_TOKEN` | yes | Your Google Ads API developer token |
| `GOOGLE_APPLICATION_CREDENTIALS` | yes* | Path to Application Default Credentials (*or a gcloud default login) |
| `GOOGLE_PROJECT_ID` | recommended | Google Cloud project with the Google Ads API enabled |
| `GOOGLE_ADS_LOGIN_CUSTOMER_ID` | no | Manager (MCC) account ID to call through; tools also accept `login_customer_id` |
| `GOOGLE_ADS_MCP_READ_ONLY` | no | `true` removes every write tool |
| `GOOGLE_ADS_MCP_UPLOAD_DIR` | no | Folder that local video files may be uploaded from |
| `GOOGLE_ADS_MCP_MAX_DOWNLOAD_MB` | no | Size cap for videos downloaded from URLs (default 2048) |
| `GOOGLE_ADS_MCP_TOOLS_CONFIG` | no | Path to a `tools_config.yaml` to enable, disable or rename tool groups |

## Example prompts

```text
Show me last week's spend, conversions and CPA by campaign for account 123-456-7890.
```

```text
Which ads and keywords are disapproved, and why?
```

```text
Pause every campaign with 'Black Friday' in the name. Validate first and show me what will change.
```

```text
Upload these 3 videos as unlisted and turn them into video assets for my Performance Max campaign.
```

## More docs

- [Hosting over HTTP with Google sign-in, Cloud Run and Podman](docs/hosting.md), for Claude.ai, ChatGPT and shared servers
- [Advanced configuration](docs/configuration.md): tool groups, prefixes, MCP resources and `google-ads.yaml`
- [Agent skill](skills/google-ads-mcp/SKILL.md): setup and usage guide for agents
- [Release process](docs/releasing.md)

## Contributing and licence

Issues and pull requests are welcome on [this repository](https://github.com/AI-Shopping-Feeds/google-ads-mcp). See
[CONTRIBUTING.md](CONTRIBUTING.md).

Licensed under the [Apache License 2.0](LICENSE). Based on [googleads/google-ads-mcp](https://github.com/googleads/google-ads-mcp) by Google.

- The server sends your Google Ads data to the agent or LLM you connect it to.
- Upstream adds an extra header to API calls so Google can measure usage of the MCP server.
