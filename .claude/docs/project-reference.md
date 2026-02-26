# Project Reference — Salesforce MCP Tool

All project-specific technical details. Referenced from [`CLAUDE.md`](../CLAUDE.md).

---

## IaC Principle: Bicep First

Always prioritize Bicep for Azure resource creation. The post-provision hook (`hooks/postprovision.py`) is only for:
- **Foundry Agent** — no ARM resource type; SDK only
- **Entra App Registration** (Chat App SPA) — Graph Bicep extension requires `Application.ReadWrite.All` on the ARM deployment identity, unavailable in managed tenants

## Development Notes

### Environment

- **Platform:** Windows 11 + Git Bash
- **Python:** Use `python` not `python3` (Windows)
- **MSYS path fix:** `export MSYS_NO_PATHCONV=1` before `az` commands with resource ID paths
- **ACR builds:** `az acr build --no-logs` avoids charmap encoding errors on Windows

### Foundry SDK (`azure-ai-projects` v2 beta — Responses API)

- `AIProjectClient` from `azure-ai-projects` — connects to the project endpoint
- Agent creation: `project_client.agents.create_version()` with `PromptAgentDefinition` + `MCPTool`
- Agent execution: `project_client.get_openai_client()` → `openai_client.responses.create()`
- `MCPTool`: `server_label`, `server_url`, `require_approval`, `allowed_tools`, `project_connection_id`
- `server_label` must match `^[a-zA-Z0-9_]+$` — no hyphens
- `gpt-4o` required — other models do NOT support MCP tools
- Agent name: `salesforce-assistant`

### Salesforce MCP Server

- `src/salesforce-mcp/` — FastMCP server with 6 tools: `list_objects`, `describe_object`, `soql_query`, `search_records`, `write_record`, `process_approval`
- Container App `ca-sf-mcp`, port 8000, tagged `azd-service-name: salesforce-mcp`
- `streamable_http_app()` serves MCP at `/mcp` — endpoint must include `/mcp` suffix
- **Bearer passthrough:** `contextvars.ContextVar` + Starlette `BaseHTTPMiddleware` extracts bearer token, `SalesforceClient._request()` uses it directly
- APIM uses `apiType: 'http'` (reverse proxy), NOT `apiType: 'mcp'`
- Metadata caching: 15-min TTL on describe results; SOQL pagination via `query_more()`

### Salesforce MCP Auth (APIM Token Validation)

- `validate-jwt` (NOT `validate-azure-ad-token`) — SF tokens are not Entra tokens
- SF JWT: `tty: "sfdc-core-token"`, RS256, `iss`/`aud` = org instance URL
- OIDC discovery: `{{SfInstanceUrl}}/.well-known/openid-configuration`
- Named Values: `SfInstanceUrl`, `APIMGatewayURL`
- RFC 9728 PRM at `salesforce-mcp/.well-known/oauth-protected-resource`
- ApiHub uses PKCE for SF OAuth — initial failures in SF login history are expected

### Salesforce OAuth Connection

- RemoteTool + ApiHub pattern with OAuth2
- OAuth endpoints: `login.salesforce.com/services/oauth2/authorize` and `/token`
- Scopes: `["api", "refresh_token"]`
- SF Connected App needs ApiHub redirect URI in callback URLs
- Required env vars: `SF_CONNECTED_APP_CLIENT_ID`, `SF_CONNECTED_APP_CLIENT_SECRET`, `SF_INSTANCE_URL`
- Bicep deploys the connection with real SF credentials from azd env vars (no placeholders)
- **IMPORTANT:** Bicep-created connections do NOT register the ApiHub connector. The postprovision hook DELETE+PUTs the connection via ARM REST to trigger ApiHub setup.
- After `azd up` + postprovision, the first agent call triggers `oauth_consent_request` — user completes the native ApiHub PKCE consent flow in the browser to authorize Salesforce access. This works correctly.
- **Optional fallback:** `python scripts/grant-sf-mcp-consent.py` does a direct OAuth flow (no PKCE) and stores the refresh token via DELETE+PUT. Useful for headless/automated setups.
- SF tokens expire after 2h. Chat app's "Re-authenticate" button DELETE+PUTs the connection, triggering a fresh consent flow on the next request.

### Chat App

- `src/chat-app/` — FastAPI backend + vanilla JS SPA with MSAL.js
- `UserTokenCredential` wraps the user's MSAL token for the Foundry SDK
- Token audience: `aud=https://ai.azure.com`, scope `user_impersonation`
- Re-authenticate flow: frontend detects auth errors → `POST /api/reset-mcp-auth` DELETE+PUTs salesforce-oauth connection

### APIM Diagnostics (MCP Compatibility)

- **CRITICAL:** Response body bytes MUST be `0` at All APIs scope — breaks MCP SSE streaming
- Request body logging (8192 bytes) is fine — only response body logging causes issues

### Scripts

- `scripts/test-salesforce-mcp.py` — 11-step end-to-end Salesforce MCP test
- `scripts/test-agent-oauth.py` — Interactive multi-turn agent test (OAuth consent + MCP approval)
- `scripts/grant-sf-mcp-consent.py` — OAuth consent for Salesforce MCP connection
- `scripts/configure-sf-connected-app.py` — Automate SF Connected App callback URL setup
- `scripts/setup-salesforce-sso.py` — Setup Salesforce SSO with Azure AD OIDC federation
- `scripts/sf-auth-code.py` — Quick SF authorization code flow for testing

### Deployment Caveats

- After `azd down --purge`, increment `COGNITIVE_ACCOUNT_SUFFIX` to avoid "Project not found" errors
- Identifier URI format: managed tenant requires `api://{appId}`
- SF JWT uses org-specific instance URL for `iss`/`aud` — NOT `login.salesforce.com`
- `SF_INSTANCE_URL` must be set via `azd env set` before `azd up` for APIM `validate-jwt` to work
- `main.bicepparam` must explicitly map azd env vars to Bicep parameters
