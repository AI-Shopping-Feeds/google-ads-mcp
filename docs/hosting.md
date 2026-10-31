# Hosting the Google Ads MCP server

Run the server over Streamable HTTP with Google sign-in when several people or
agents share it, or when you want to use it from **Claude.ai** or **ChatGPT**.
Those clients only connect to remote HTTPS servers. Each user signs in with
their own Google account through the server's OAuth proxy, so no credentials sit
in the client.

## Google sign-in with the FastMCP OAuth proxy

The server supports FastMCP's [OAuth proxy](https://gofastmcp.com/servers/auth/oauth-proxy) feature for dynamic user authentication. This is useful when running the server as a web service.

To enable it, set the following environment variables:

- `GOOGLE_ADS_MCP_OAUTH_CLIENT_ID`: Your Google Cloud OAuth 2.0 Client ID.
- `GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET`: Your Google Cloud OAuth 2.0 Client Secret.
- `GOOGLE_ADS_MCP_BASE_URL`: (Optional) The base URL where the server is accessible (defaults to `http://localhost:8080`).
- `GOOGLE_ADS_MCP_JWT_SIGNING_KEY`: (Optional) Secret key used to sign FastMCP JWT tokens across multiple server instances or deployments.
- `GOOGLE_ADS_MCP_STORAGE_TYPE`: (Optional) Storage backend for OAuth state (`filetree`, `redis`, `firestore`, or `memory`).
- `GOOGLE_ADS_MCP_STORAGE_PATH`: (Optional) Directory path for `filetree` persistent storage.
- `GOOGLE_ADS_MCP_STORAGE_REDIS_URL`: (Optional) Redis URL for `redis` persistent storage.
- `GOOGLE_ADS_MCP_STORAGE_FIRESTORE_PROJECT`: (Optional) Google Cloud project for `firestore` persistent storage. Defaults to the project inferred from Application Default Credentials. Setting it selects the `firestore` backend even if `GOOGLE_ADS_MCP_STORAGE_TYPE` is unset.
- `GOOGLE_ADS_MCP_STORAGE_FIRESTORE_DATABASE`: (Optional) Firestore database name for `firestore` persistent storage. Defaults to `(default)`.
- `GOOGLE_ADS_MCP_STORAGE_ENCRYPTION_KEY`: (Optional) Encryption key for stored OAuth tokens.
- `GOOGLE_ADS_MCP_STORAGE_DISABLE_ENCRYPTION`: (Optional) Set to `true` to disable token encryption.

The `redis` and `firestore` backends need their storage library installed
alongside the server: `pip install py-key-value-aio[redis]` and
`pip install google-ads-mcp[firestore]` respectively.

Once this is enabled, you can authenticate to the API through your MCP client.

When these variables are set, the server automatically switches to the
`streamable-http` transport instead of `stdio`.

You will need to run the server as a separate process and configure your MCP
client to connect to the Streamable HTTP endpoint (for example,
`http://localhost:8080/mcp`).

## Local WSL and Podman deployment

This deployment has been tested with rootless Podman in WSL and exposes a single
Streamable HTTP endpoint at `http://localhost:8080/mcp`. Build the image from
the repository inside WSL:

```shell
podman build --tag localhost/google-ads-mcp:latest --file Dockerfile .
```

Keep server credentials out of MCP client configuration. The tested Quadlet
loads Google Ads and OAuth settings from a private host-side file through
`EnvironmentFile=` and uses a separate named volume for persistent encrypted
OAuth state:

```ini
[Container]
Image=localhost/google-ads-mcp:latest
PublishPort=127.0.0.1:8080:8080
EnvironmentFile=/absolute/host/path/google-ads-mcp.env
Volume=google-ads-mcp-oauth.volume:/var/lib/google-ads-mcp:rw
ReadOnly=true
NoNewPrivileges=true
DropCapability=all
```

The environment file and the OAuth-state volume serve different purposes: the
volume does not contain the `.env` file. Keep the environment file outside the
repository, restrict it to the service owner, and never commit it. Antigravity
and Codex then need only the MCP endpoint and their own OAuth authorization;
they do not need the server's Google Ads developer token, OAuth client secret,
or signing and storage keys. Publish port 8080 only on the loopback interface
when the server is intended for local agents.

The endpoint deliberately keeps stateful Streamable HTTP enabled. It supports
legacy MCP 2025 clients that use `Mcp-Session-Id` and GET SSE as well as MCP
2026 clients that use sessionless POST requests and `subscriptions/listen`.
Do not enable FastMCP's `stateless_http` option on this shared endpoint; doing
so removes the legacy GET channel.

The server runs on FastMCP 4 (`fastmcp>=4.0.6,<5`) paired with `mcp[cli]>=2.0.0,<3`. The Docker build also applies a version-guarded
OAuth metadata workaround for Codex CLI 0.146. It stops advertising the RFC
9207 authorization-response `iss` parameter as mandatory while FastMCP still
includes it in redirects. The build fails if the expected FastMCP major version or
patch location changes, so upgrades require explicit interoperability tests.

For Codex, configure and authenticate the server as described in the
[official Codex MCP documentation](https://developers.openai.com/codex/mcp/):

```shell
codex mcp add google_ads --url http://localhost:8080/mcp
codex mcp login google_ads
```

For Antigravity, configure the same URL as `serverUrl` in its MCP configuration.
This key is required for Streamable HTTP in Antigravity 2.8.1 and Antigravity
IDE 2.5.5; `httpUrl` is not accepted by those versions. After authentication,
both clients should list the namespaced tools from
[Tools available](#tools-available), such as
`customers_list_accessible_customers`, `search_search` and `mutate_mutate`.


## Antigravity / Antigravity IDE

1.  Install [Antigravity](https://antigravity.google/product/antigravity-cli)
    or Antigravity IDE.

1.  Configure your server. Refer to the docs at [https://antigravity.google/docs/mcp](https://antigravity.google/docs/mcp) for details on setting up MCP servers.

- Option 1: Using FastMCP OAuth Proxy (Streamable HTTP)

  You can run the server as a separate process and configure your MCP client
  to connect to the Streamable HTTP endpoint (for example,
  `http://localhost:8080/mcp`).
  This also allows using FastMCP's [OAuth proxy](https://gofastmcp.com/servers/auth/oauth-proxy) feature for dynamic user authentication.

  Antigravity 2.8.1 and Antigravity IDE 2.5.5 require `serverUrl` for a
  Streamable HTTP server. Do not use the older `httpUrl` key. Server-side
  credentials belong in the server process, not in this client configuration.

    ```json
    {
      "mcpServers": {
        "google-ads-mcp": {
          "serverUrl": "http://localhost:8080/mcp"
        }
      }
    }
    ```

- Option 2: the Application Default Credentials method

    This remains a supported alternative, but it provides less credential
    isolation than the server-managed Streamable HTTP deployment above. The MCP
    client starts the server and its configuration contains the ADC file path
    and Google Ads developer token. Prefer the Quadlet deployment when several
    local clients share the same server or client configuration may be copied,
    synchronized, or inspected by other tools.

    Replace `PATH_TO_CREDENTIALS_JSON` with the path you copied in the previous
    step.

    We also recommend that you add a `GOOGLE_CLOUD_PROJECT` attribute to the
    `env` object. Replace `YOUR_PROJECT_ID` in the following example with the
    [project ID](https://support.google.com/googleapi/answer/7014113) of your
    Google Cloud project.

    ```json
    {
      "mcpServers": {
        "google-ads-mcp": {
          "command": "pipx",
          "args": [
            "run",
            "--spec",
            "git+https://github.com/AI-Shopping-Feeds/google-ads-mcp.git",
            "google-ads-mcp"
          ],
          "env": {
            "GOOGLE_APPLICATION_CREDENTIALS": "PATH_TO_CREDENTIALS_JSON",
            "GOOGLE_PROJECT_ID": "YOUR_PROJECT_ID",
            "GOOGLE_ADS_DEVELOPER_TOKEN": "YOUR_DEVELOPER_TOKEN"
          }
        }
      }
    }
    ```

- Option 3: the Python client library method

    ```json
    {
      "mcpServers": {
        "google-ads-mcp": {
          "command": "pipx",
          "args": [
            "run",
            "--spec",
            "git+https://github.com/AI-Shopping-Feeds/google-ads-mcp.git",
            "google-ads-mcp"
          ],
          "env": {
            "GOOGLE_PROJECT_ID": "YOUR_PROJECT_ID",
            "GOOGLE_ADS_DEVELOPER_TOKEN": "YOUR_DEVELOPER_TOKEN"
          }
        }
      }
    }
    ```


## Deployment to Google Cloud Platform

Instead of hosting this MCP server locally, you can host it on Google Cloud Run or on any other cloud-based infrastructure. This is useful if you want to share the server across different agents or run it as a web service.

Note that this only supports authentication with an OAuth Client ID and Client Secret pair through the OAuth proxy (Option #1 above).

### Prerequisites

1.  A Google Cloud project.
2.  The `gcloud` CLI installed, authenticated, and active project set.
    ```shell
    gcloud config set project YOUR_PROJECT_ID
    ```

### Step 1: Build and Push Docker Image

You can use Cloud Build to build and push the image to Artifact Registry without needing Docker installed locally.

1.  Create a repository in Artifact Registry:
    ```shell
    gcloud artifacts repositories create mcp-servers --repository-format=docker --location=us-central1
    ```
2.  Build and submit the image:
    ```shell
    gcloud builds submit --tag us-central1-docker.pkg.dev/YOUR_PROJECT_ID/mcp-servers/google-ads-mcp:latest .
    ```
    Replace `YOUR_PROJECT_ID` with your Google Cloud project ID.

### Step 2: Deploy to Google Cloud Run

Make sure to set the required environment variables:

- `GOOGLE_PROJECT_ID`: Your Google Cloud project ID.
- `GOOGLE_ADS_DEVELOPER_TOKEN`: (Optional) The developer token you want the MCP server to use (see above).
- `GOOGLE_ADS_MCP_OAUTH_CLIENT_ID`: The OAuth Client ID you want the MCP server to use.
- `GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET`: The OAuth Client secret you want the MCP server to use.
- `GOOGLE_ADS_MCP_BASE_URL`: The base URL where your MCP server is accessible: this will be automatically assigned by Google Cloud Run after your first deployment. You can update the environment variables after deployment. 
- `GOOGLE_ADS_MCP_JWT_SIGNING_KEY`: (Recommended for production) Persistent JWT signing key across Cloud Run instances.
- `GOOGLE_ADS_MCP_STORAGE_TYPE`: (Recommended for production) Storage backend to persist OAuth tokens across instances. Set it to `firestore` to use Firestore through Application Default Credentials, which needs no VPC connector, or to `redis` along with `GOOGLE_ADS_MCP_STORAGE_REDIS_URL`.

  Using `firestore` requires three things: build the image with the extra
  installed (change the Dockerfile to `uv pip install --system .[firestore]`),
  create a Firestore database in the project, since one is not provisioned
  automatically, and grant the Cloud Run service account `roles/datastore.user`.
  Note that entries are not expired automatically: the store filters expired
  entries on read but never deletes them, and `expires_at` is written as a
  string, so a Firestore TTL policy cannot collect them either. Plan on a
  periodic cleanup job for long-running deployments. Redis expires entries on
  its own.
- `FASTMCP_HOST`: Set this to `0.0.0.0` to allow FastMCP to accept connections from all IP addresses.
- `GOOGLE_ADS_LOGIN_CUSTOMER_ID`: Required if your access to the customer account is through a manager account. Set it to the customer ID of the manager account. See [Login Customer Id](#login-customer-id) above for details.

```shell
gcloud run deploy google-ads-mcp \
  --image us-central1-docker.pkg.dev/YOUR_PROJECT_ID/mcp-servers/google-ads-mcp:latest \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars="GOOGLE_PROJECT_ID=YOUR_PROJECT_ID,GOOGLE_ADS_DEVELOPER_TOKEN=YOUR_DEVELOPER_TOKEN,GOOGLE_ADS_MCP_OAUTH_CLIENT_ID=YOUR_CLIENT_ID,GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET=YOUR_CLIENT_SECRET,GOOGLE_ADS_MCP_BASE_URL=YOUR_BASE_URL,GOOGLE_ADS_MCP_JWT_SIGNING_KEY=YOUR_JWT_SIGNING_KEY,GOOGLE_ADS_MCP_STORAGE_TYPE=firestore,FASTMCP_HOST=0.0.0.0"
```

### Step 3: Configure MCP Client

Once deployed, update your MCP client configuration (refer to the docs at [https://antigravity.google/docs/mcp](https://antigravity.google/docs/mcp)) to use the Cloud Run URL.

```json
{
  "mcpServers": {
    "google-ads-mcp": {
      "httpUrl": "https://your-cloud-run-url.a.run.app/mcp"
    }
  }
}
```


## Connect Claude.ai and ChatGPT

Once the server is reachable over HTTPS (for example on Cloud Run as above):

- **Claude (web or desktop):** Customize → Connectors → Add custom connector,
  paste `https://YOUR_SERVER/mcp`, then Connect and sign in with Google.
- **ChatGPT:** Settings → Apps & Connectors (custom connectors need developer
  mode, under Advanced settings). Create a connector with the same URL and
  choose OAuth.
- **Claude Code:** `claude mcp add --transport http --scope user google-ads
  https://YOUR_SERVER/mcp`, then `/mcp` → google-ads → Authenticate.
