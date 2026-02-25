# Salesforce Meta-Tool: The Billion-Dollar Agent Loop Applied to Enterprise

> **6 tools. ~200 lines of logic. The entire Salesforce platform.**
>
> This project is a companion to [The Billion-Dollar Agent Loop](https://www.linkedin.com/pulse/billion-dollar-agent-loop-ozgur-karahan-fszae/) — a concrete implementation of domain-scoped MCP servers for enterprise AI agents, with end-to-end identity propagation.

## The Idea

Claude Code generates over $1B in annualized revenue with a deceptively simple architecture: a single agent loop with ~18 curated tools. Its secret weapon isn't the model — it's **Bash as a meta-tool**. One tool, one interface, access to the entire developer ecosystem (git, npm, docker, kubectl, terraform, ...).

This project applies the same pattern to enterprise:

```
Developer World                    Enterprise World
─────────────────                  ─────────────────
Bash (meta-tool)          →        Salesforce MCP Server (meta-tool)
  └─ git, npm, docker               └─ list, describe, query, search, write, approve
     kubectl, terraform                 covers any object, any field, any workflow

Single agent loop          →        Single agent loop
  └─ Plan → Execute → Verify          └─ Plan → Execute → Verify
```

**Bash doesn't implement git.** It delegates to git. The agent builds the command.

**The Salesforce MCP server doesn't implement CRM logic.** It delegates to Salesforce. The agent builds the query.

The MCP server is a thin metadata-driven bridge: the agent discovers objects, learns field schemas, then constructs SOQL queries, SOSL searches, and CRUD operations on the fly. No hardcoded Salesforce objects. No predefined reports. No brittle integrations. Just 6 tools that cover the entire platform.

## But Isn't That Dangerous?

This is the question every enterprise architect asks — and the right question.

Claude Code solves this with OS-level sandboxing. But enterprise agents can't sandbox Salesforce behind a container. **The data is live. The actions are real. A rogue agent could delete production records.**

Our answer: **the agent inherits the user's identity.**

```
┌──────────┐     ┌──────────────┐     ┌──────┐     ┌───────────────────┐     ┌────────────┐
│  User     │────▶│  AI Foundry  │────▶│ APIM │────▶│  Salesforce MCP   │────▶│ Salesforce  │
│ (browser) │ JWT │  Agent       │ JWT │      │ JWT │  Server           │ JWT │ REST API   │
└──────────┘     └──────────────┘     └──────┘     └───────────────────┘     └────────────┘
     │                                                                            │
     └────────────── same user identity, same permissions ────────────────────────┘
```

The user's Salesforce OAuth token flows through every layer — untouched, unescalated. The MCP server never stores tokens. It passes them through. The Salesforce API enforces the same CRUD permissions, field-level security, sharing rules, and approval workflows that apply when the user logs into Salesforce directly.

**The agent can only do what the user can do.** Not more. Not less. Not different.

This is what makes the meta-tool pattern safe for enterprise: the power comes from the model's ability to compose operations, not from elevated access. A sales rep's agent can query their own accounts and create opportunities — but can't access other reps' pipeline, modify system fields, or bypass approval workflows. The security boundary isn't the agent. It's Salesforce itself.

## The Architecture

```
                    ┌─────────────────────────────────────────────────┐
                    │                Azure                            │
                    │                                                 │
┌──────────┐       │  ┌───────────┐    ┌──────────────────────────┐  │
│  Browser  │──────│─▶│ Chat App  │───▶│  AI Foundry Agent        │  │
│  MSAL.js  │      │  │ (FastAPI) │    │  "salesforce-assistant"  │  │
└──────────┘       │  └───────────┘    │  model: gpt-4o           │  │
                   │                   │  tools: [salesforce_mcp]  │  │
                   │                   └───────────┬──────────────┘  │
                   │                               │ MCP protocol    │
                   │                   ┌───────────▼──────────────┐  │
                   │                   │  APIM Gateway            │  │
                   │                   │  validate-jwt (SF OIDC)  │  │
                   │                   │  RFC 9728 PRM            │  │
                   │                   └───────────┬──────────────┘  │
                   │                               │ bearer token    │
                   │                   ┌───────────▼──────────────┐  │
                   │                   │  Salesforce MCP Server   │  │
                   │                   │  6 tools, ~200 lines     │  │
                   │                   │  FastMCP + httpx          │  │
                   │                   └───────────┬──────────────┘  │
                   │                               │                 │
                   └───────────────────────────────│─────────────────┘
                                                   │ user's SF token
                                       ┌───────────▼──────────────┐
                                       │  Salesforce REST API     │
                                       │  enforces: CRUD, FLS,    │
                                       │  sharing, approvals      │
                                       └──────────────────────────┘
```

## The 6 Tools — 1,235 Tokens for All of Salesforce

Here's the part that surprises people: **the entire tool surface costs less than 1% of the model's context window.**

Measured with gpt-4o's tokenizer (`o200k_base`):

| Tool | Tokens | What it does |
|------|--------|-------------|
| `list_objects` | 117 | Discover objects (1000+ in a typical org) — filter by name/label |
| `describe_object` | 109 | Field schemas, types, required flags, picklists, external IDs |
| `soql_query` | 225 | Full SOQL: relationships, aggregates, GROUP BY, auto-pagination |
| `search_records` | 175 | SOSL full-text search across multiple objects simultaneously |
| `write_record` | 226 | Create, update, upsert (by external ID), delete — with validation |
| `process_approval` | 129 | Submit, approve, reject — Salesforce approval workflows |
| **Server instructions** | **254** | Workflow guidance, conventions, when-to-use-which-tool |
| | | |
| **Total** | **1,235** | **0.96% of gpt-4o's 128K context window** |

Compare that with the alternatives:

| Approach | Token cost | Coverage |
|----------|-----------|----------|
| Full OpenAPI spec | 5,000-15,000 | Hundreds of endpoints, most irrelevant |
| RAG documentation chunks | 2,000-10,000 | Partial, depends on retrieval quality |
| One tool per object | ~500 x N objects | Scales linearly, N can be 100+ |
| **This MCP server** | **1,235 fixed** | **All objects, all fields, all operations** |

The token cost is **fixed** regardless of how many Salesforce objects exist. An org with 50 custom objects pays the same 1,235 tokens as an org with 500. The agent discovers schemas at runtime via `describe_object` — the tool definitions don't change.

This is the meta-tool advantage: instead of encoding domain knowledge in the tool definitions (which consumes tokens), you encode **discovery primitives** that let the agent learn the domain on the fly. The Salesforce metadata API becomes the agent's documentation.

### What Each Tool Does

**`list_objects`** — The entry point. Salesforce orgs have 1000+ objects (standard + custom). The agent filters by name or label to find what it needs. Returns: name, label, queryable/createable/updateable/deletable flags. Think `ls` for Salesforce.

**`describe_object`** — The schema inspector. Given an object name (e.g., `Account`), returns every field with its API name, data type, whether it's required, picklist values, relationship references, and external ID flags. The agent calls this *before* writing — it learns the interface, not guesses. Think `man` or `--help`.

**`soql_query`** — The precision read tool. The agent constructs a complete SOQL query — it supports the full syntax: relationship queries (`SELECT Account.Name FROM Contact`), aggregates (`COUNT`, `SUM`), `GROUP BY`, `HAVING`, date functions, subqueries. Auto-paginates large result sets (Salesforce pages at ~2000 records). Think `grep` or `SQL`.

**`search_records`** — The discovery tool. SOSL full-text search across multiple objects at once — useful when the agent doesn't know *which* object contains the data. Search for "Acme" and find it in Accounts, Contacts, and Opportunities simultaneously. Think `find` or `rg`.

**`write_record`** — The mutation tool. Four operations: `create` (new record), `update` (partial modify by ID), `upsert` (create-or-update by external ID), `delete` (permanent removal). Validates field names against the schema before sending — catches typos before they hit the API. Think `echo >` or `rm`.

**`process_approval`** — The workflow tool. Submit records for approval, approve or reject pending work items. Integrates with Salesforce's built-in approval workflows — the same ones configured by admins in Setup. Think `git push` — a governed state transition.

Just as Bash gives a developer agent access to the entire OS ecosystem, these 6 tools give an enterprise agent access to the entire Salesforce platform — any object, any field, any record, any workflow.

The agent doesn't need a hardcoded `get_accounts()` function. It calls `describe_object("Account")`, learns the schema, and builds a SOQL query. Just like Claude Code doesn't need a hardcoded `run_tests()` function — it reads the project, finds the test framework, and runs the right command.

## Why Identity Propagation Matters

Without identity propagation:
```
User A (sales rep) → Agent → Service Account → Salesforce
                                  ↑
                    This account has admin access.
                    Agent sees ALL data. Can modify ANYTHING.
                    "List all opportunities" returns the entire pipeline.
                    "Delete this record" works on any record.
```

With identity propagation:
```
User A (sales rep) → Agent → User A's token → Salesforce
                                  ↑
                    Same permissions as User A in Salesforce.
                    Agent sees only User A's data (sharing rules).
                    Field-level security enforced. Approval workflows active.
                    "Delete this record" fails if User A can't delete it.
```

**The agent becomes a power tool, not a privileged backdoor.** The user's Salesforce profile, permission sets, sharing rules, and org-wide defaults all apply — exactly as if the user were clicking buttons in the Salesforce UI. The difference is the agent can compose multi-step operations intelligently.

## How The Token Flows

1. **User signs in** via MSAL.js in the browser → gets an Azure AD token
2. **Chat App** passes the token to AI Foundry as a `UserTokenCredential`
3. **AI Foundry Agent** hits the Salesforce MCP tool → triggers OAuth consent (first time only)
4. **User authenticates with Salesforce** via OAuth2 authorization code + PKCE
5. **ApiHub** stores the Salesforce token on the Foundry project connection
6. **Agent calls MCP server** — APIM validates the SF JWT (`validate-jwt` with OIDC discovery)
7. **MCP server** receives the bearer token via middleware, passes it directly to Salesforce REST API
8. **Salesforce** enforces permissions based on the authenticated user's profile

The MCP server is stateless. It never stores, caches, or refreshes tokens. The bearer token middleware extracts the token from the request and sets it as a context variable — the Salesforce client uses it directly. This is the entire identity propagation code:

```python
class BearerTokenMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        auth = request.headers.get("authorization", "")
        token = auth[7:] if auth.lower().startswith("bearer ") else None
        tok = _request_token.set(token)
        try:
            return await call_next(request)
        finally:
            _request_token.reset(tok)
```

Seven lines. That's the security boundary.

## Quick Start

### Prerequisites
- Azure subscription with Azure Developer CLI (`azd`)
- Salesforce org with a Connected App (OAuth2 + PKCE)
- Python 3.11+

### Deploy

```bash
# Clone and configure
git clone <this-repo>
cd meta-tool-salesforce

# Set Salesforce credentials
azd env set SF_INSTANCE_URL "https://your-org.my.salesforce.com"
azd env set SF_CONNECTED_APP_CLIENT_ID "<consumer-key>"
azd env set SF_CONNECTED_APP_CLIENT_SECRET "<consumer-secret>"

# Deploy everything
azd up
```

`azd up` deploys the full stack: Container Apps Environment, APIM Gateway, AI Foundry project, Chat App, Salesforce MCP server, OAuth connections, and the Foundry agent — all via Bicep.

### Post-deployment

```bash
# Configure SF Connected App callback URL
python scripts/configure-sf-connected-app.py

# Grant OAuth consent for the SF MCP connection
python scripts/grant-sf-mcp-consent.py

# Verify end-to-end identity propagation
python scripts/test-agent-oauth.py
```

## Project Structure

```
meta-tool-salesforce/
├── azure.yaml                    # azd project: 2 services (chat-app, salesforce-mcp)
├── src/
│   ├── salesforce-mcp/
│   │   ├── app.py                # The MCP server — 6 tools, bearer passthrough
│   │   └── salesforce_client.py  # Async Salesforce REST client with auth
│   └── chat-app/
│       ├── app.py                # FastAPI backend — MSAL → Foundry agent bridge
│       └── static/               # Vanilla JS SPA with MSAL.js
├── infra/
│   ├── main.bicep                # Orchestrator — all Azure resources
│   └── modules/                  # Modular Bicep (APIM, Container Apps, AI Foundry, ...)
├── hooks/
│   └── postprovision.py          # Creates Entra app + Foundry agent + OAuth connections
└── scripts/                      # Setup, consent, and test scripts
```

## The Formula

From the article, applied here:

```
User Message
  → Agent plans (which Salesforce objects? which fields?)
  → Agent executes (describe → query → write → verify)
  → Agent verifies (did the SOQL return expected data? did the write succeed?)
  → TODO tracking (multi-step operations stay on track)
  → Loop (or ask the user for clarification)
```

The agent doesn't just execute a single API call. It **composes** operations: describe an object to learn its schema, query related records, create a new record with the right field names, and verify the result. The same loop, the same pattern, the same simplicity — just pointed at a different domain.

## Key Takeaway

> **Agents are a workflow integration problem, not an AI problem.**

The model is the same (gpt-4o). The loop is the same (execute → observe → repeat). The innovation is the **meta-tool pattern**: a small, metadata-driven MCP server that gives an agent access to an entire domain — while the user's identity ensures the agent can never exceed the user's own permissions.

Bash made Claude Code a $1B product. Domain-scoped MCP servers can do the same for enterprise.

---

*See the full analysis in [The Billion-Dollar Agent Loop](https://www.linkedin.com/pulse/billion-dollar-agent-loop-ozgur-karahan-fszae/) on LinkedIn.*
