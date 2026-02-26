"""Setup Salesforce SSO with Azure AD OIDC federation.

Interactive script that configures both sides:
- Azure AD: Entra App Registration with OIDC settings
- Salesforce: Auth Provider + Registration Handler via sf CLI

Follows the same patterns as hooks/postprovision.py (run(), _graph_patch(),
idempotent check-before-create). Not integrated into the postprovision hook
because Salesforce is not part of the Azure infra lifecycle.

Prerequisites:
- az CLI logged in (az login)
- sf CLI installed (npm install -g @salesforce/cli) — optional, can do manual deploy

Usage:
    python scripts/setup-salesforce-sso.py
"""

import json
import os
import subprocess
import sys
import tempfile
import textwrap


# === Shared helpers (same pattern as hooks/postprovision.py) ===


def run(cmd: str, parse_json: bool = False):
    """Run a shell command and return stdout (or parsed JSON)."""
    result = subprocess.run(
        cmd, capture_output=True, text=True, shell=True,
        env={**os.environ, "MSYS_NO_PATHCONV": "1"},
    )
    if result.returncode != 0:
        return None
    out = result.stdout.strip()
    if not out:
        return None
    if parse_json:
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            return None
    return out


def run_interactive(cmd: str) -> int:
    """Run a command with visible output (for interactive steps like browser login)."""
    result = subprocess.run(
        cmd, shell=True,
        env={**os.environ, "MSYS_NO_PATHCONV": "1"},
    )
    return result.returncode


def _write_temp_json(data):
    """Write data as JSON to a temp file and return the file path."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(data, f)
    f.close()
    return f.name


def _graph_patch(object_id: str, body: dict):
    """PATCH a Microsoft Graph application resource."""
    body_file = _write_temp_json(body)
    try:
        return run(
            f'az rest --method PATCH '
            f'--url "https://graph.microsoft.com/v1.0/applications/{object_id}" '
            f'--headers "Content-Type=application/json" '
            f'--body "@{body_file}"',
            parse_json=True,
        )
    finally:
        os.unlink(body_file)


# === Paths ===

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
SF_METADATA_DIR = os.path.join(
    REPO_ROOT, "salesforce", "force-app", "main", "default",
)


# === Steps ===


def step0_prerequisites():
    """Step 0: Verify az CLI logged in and check for sf CLI."""
    print("=" * 60)
    print("  Step 0: Prerequisites")
    print("=" * 60)

    # Check az CLI
    account = run("az account show", parse_json=True)
    if not account:
        print("  ERROR: az CLI not logged in. Run 'az login' first.")
        sys.exit(1)
    tenant_id = account.get("tenantId", "")
    print(f"  az CLI: logged in (tenant: {tenant_id})")

    # Check sf CLI
    sf_version = run("sf --version")
    if not sf_version:
        print("\n  sf CLI not found.")
        print("  Install with: npm install -g @salesforce/cli")
        answer = input("  Continue without sf CLI? (y/N): ").strip().lower()
        if answer != "y":
            sys.exit(1)
        print("  WARNING: Steps 2, 5 will require manual action")
        return tenant_id, False

    print(f"  sf CLI: {sf_version.splitlines()[0]}")
    return tenant_id, True


def step1_create_entra_app(tenant_id: str):
    """Step 1: Create Entra App Registration for Salesforce SSO.

    Idempotent — checks by displayName before creating (same as postprovision.py).
    No redirect URI yet — Salesforce domain is unknown until Step 2.
    """
    print("\n" + "=" * 60)
    print("  Step 1: Create Entra App Registration")
    print("=" * 60)

    env_name = os.environ.get("AZURE_ENV_NAME", "")
    display_name = f"Salesforce SSO ({env_name})" if env_name else "Salesforce SSO"

    # Idempotent: check by displayName before creating
    app_id = run(
        f"az ad app list --filter \"displayName eq '{display_name}'\" "
        "--query \"[0].appId\" -o tsv"
    )

    if app_id:
        print(f"  Already exists: {app_id}")
    else:
        app_id = run(
            f'az ad app create --display-name "{display_name}" '
            "--sign-in-audience AzureADMyOrg --query appId -o tsv"
        )
        if not app_id:
            print("  ERROR: Failed to create app registration")
            sys.exit(1)
        print(f"  Created: {app_id}")

    # Get object ID for Graph API calls
    obj_id = run(f'az ad app show --id "{app_id}" --query id -o tsv')

    # Set identifier URI
    uri = f"api://{app_id}"
    run(f'az ad app update --id "{app_id}" --identifier-uris "{uri}"')
    print(f"  Identifier URI: {uri}")

    # Configure optional ID token claims via Graph API
    _graph_patch(obj_id, {
        "optionalClaims": {
            "idToken": [
                {"name": "email", "essential": False},
                {"name": "given_name", "essential": False},
                {"name": "family_name", "essential": False},
                {"name": "preferred_username", "essential": False},
            ]
        }
    })
    print("  Optional claims: email, given_name, family_name, preferred_username")

    # Create client secret
    secret = run(
        f'az ad app credential reset --id "{app_id}" --query password -o tsv'
    )
    if not secret:
        print("  ERROR: Failed to create client secret")
        sys.exit(1)
    print(f"  Client secret: created (length: {len(secret)})")

    # Create service principal (idempotent)
    sp_id = run(f'az ad sp show --id "{app_id}" --query id -o tsv')
    if not sp_id:
        sp_id = run(f'az ad sp create --id "{app_id}" --query id -o tsv')
        print(f"  Service principal: created ({sp_id})")
    else:
        print(f"  Service principal: exists ({sp_id})")

    return app_id, obj_id, secret


def step2_authenticate_salesforce(has_sf_cli: bool):
    """Step 2: Authenticate to Salesforce org via browser login."""
    print("\n" + "=" * 60)
    print("  Step 2: Authenticate to Salesforce")
    print("=" * 60)

    if not has_sf_cli:
        print("  sf CLI not available — manual input required")
        instance_url = input(
            "  Enter Salesforce instance URL "
            "(e.g., https://myorg.my.salesforce.com): "
        ).strip().rstrip("/")
        admin_username = input(
            "  Enter Salesforce admin username "
            "(e.g., admin@myorg.com): "
        ).strip()
        return instance_url, admin_username

    # Check if already authenticated to this alias
    org_info = run(
        "sf org display --target-org sf-sso-target --json", parse_json=True
    )
    if org_info and org_info.get("status") == 0:
        result = org_info.get("result", {})
        instance_url = result.get("instanceUrl", "")
        admin_username = result.get("username", "")
        if instance_url:
            print(f"  Already authenticated: {instance_url}")
            print(f"  Admin user: {admin_username}")
            reuse = input("  Use this org? (Y/n): ").strip().lower()
            if reuse != "n":
                return instance_url, admin_username

    # Interactive browser login
    print("  Opening browser for Salesforce login...")
    rc = run_interactive("sf org login web --alias sf-sso-target")
    if rc != 0:
        print("  ERROR: Salesforce login failed")
        sys.exit(1)

    # Retrieve org info after login
    org_info = run(
        "sf org display --target-org sf-sso-target --json", parse_json=True
    )
    if not org_info or org_info.get("status") != 0:
        print("  ERROR: Could not retrieve org info after login")
        sys.exit(1)

    result = org_info.get("result", {})
    instance_url = result.get("instanceUrl", "")
    admin_username = result.get("username", "")
    print(f"  Instance URL: {instance_url}")
    print(f"  Admin user: {admin_username}")

    return instance_url, admin_username


def step3_update_redirect_uri(app_id: str, obj_id: str, instance_url: str):
    """Step 3: Update Entra App with Salesforce callback URL.

    Now that we know the Salesforce domain (from Step 2), set the redirect URI.
    Same chicken-and-egg pattern as postprovision.py adding the ApiHub redirect
    URI after discovering the project internal ID.

    Sets redirect URI + ID token issuance in a single PATCH to avoid overwriting
    nested web properties.
    """
    print("\n" + "=" * 60)
    print("  Step 3: Update Redirect URI")
    print("=" * 60)

    redirect_uri = f"{instance_url}/services/authcallback/AzureAD"

    _graph_patch(obj_id, {
        "web": {
            "redirectUris": [redirect_uri],
            "implicitGrantSettings": {
                "enableIdTokenIssuance": True
            }
        }
    })
    print(f"  Redirect URI: {redirect_uri}")
    print("  ID token issuance: enabled")


def step4_generate_metadata(
    tenant_id: str, app_id: str, secret: str,
    instance_url: str, admin_username: str,
):
    """Step 4: Generate Salesforce Auth Provider metadata with actual values.

    The Apex Registration Handler class is committed to the repo (static).
    The Auth Provider XML is generated here because it contains tenant-specific
    values (same principle as postprovision.py building JSON bodies at runtime).
    """
    print("\n" + "=" * 60)
    print("  Step 4: Generate Salesforce Metadata")
    print("=" * 60)

    # Create authproviders directory if needed
    auth_provider_dir = os.path.join(SF_METADATA_DIR, "authproviders")
    os.makedirs(auth_provider_dir, exist_ok=True)

    # Generate Auth Provider XML with actual values
    auth_provider_xml = textwrap.dedent(f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <AuthProvider xmlns="http://soap.sforce.com/2006/04/metadata">
            <friendlyName>Azure AD</friendlyName>
            <providerType>OpenIdConnect</providerType>
            <authorizeUrl>https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize</authorizeUrl>
            <tokenUrl>https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token</tokenUrl>
            <userInfoUrl>https://graph.microsoft.com/oidc/userinfo</userInfoUrl>
            <defaultScopes>openid email profile offline_access</defaultScopes>
            <consumerKey>{app_id}</consumerKey>
            <consumerSecret>{secret}</consumerSecret>
            <registrationHandler>AzureADRegistrationHandler</registrationHandler>
            <executionUser>{admin_username}</executionUser>
            <sendAccessTokenInHeader>true</sendAccessTokenInHeader>
            <sendClientCredentialsInHeader>false</sendClientCredentialsInHeader>
        </AuthProvider>
    """)

    auth_provider_path = os.path.join(
        auth_provider_dir, "AzureAD.authprovider-meta.xml"
    )
    with open(auth_provider_path, "w", encoding="utf-8") as f:
        f.write(auth_provider_xml)
    print(f"  Written: {os.path.relpath(auth_provider_path, REPO_ROOT)}")

    # Verify Apex class exists (should be committed to repo)
    cls_path = os.path.join(
        SF_METADATA_DIR, "classes", "AzureADRegistrationHandler.cls"
    )
    meta_path = cls_path + "-meta.xml"
    if os.path.exists(cls_path) and os.path.exists(meta_path):
        print("  Verified: AzureADRegistrationHandler class exists")
    else:
        print(
            f"  WARNING: AzureADRegistrationHandler.cls not found at "
            f"{os.path.relpath(cls_path, REPO_ROOT)}"
        )


def step5_deploy(has_sf_cli: bool):
    """Step 5: Deploy Auth Provider + Registration Handler to Salesforce."""
    print("\n" + "=" * 60)
    print("  Step 5: Deploy to Salesforce")
    print("=" * 60)

    sf_project_dir = os.path.join(REPO_ROOT, "salesforce")

    if not has_sf_cli:
        print("  SKIPPED: sf CLI not available")
        print("  Deploy manually:")
        print(f"    cd {sf_project_dir}")
        print(
            "    sf project deploy start --source-dir force-app "
            "--target-org sf-sso-target --wait 10"
        )
        return False

    print("  Deploying Auth Provider + Registration Handler...")
    rc = run_interactive(
        f'cd "{sf_project_dir}" && '
        "sf project deploy start --source-dir force-app "
        "--target-org sf-sso-target --wait 10"
    )

    if rc == 0:
        print("  Deployment successful!")
        return True
    else:
        print("  ERROR: Deployment failed (see output above)")
        return False


def step6_verify(app_id: str, instance_url: str, tenant_id: str):
    """Step 6: Verify configuration and print summary."""
    print("\n" + "=" * 60)
    print("  Step 6: Verify & Summary")
    print("=" * 60)

    # Verify Entra app redirect URI
    app = run(
        f'az ad app show --id "{app_id}" '
        '--query "{{appId:appId, redirectUris:web.redirectUris}}" -o json',
        parse_json=True,
    )
    if app:
        print(f"  Entra App ID:     {app.get('appId', '?')}")
        print(f"  Redirect URIs:    {app.get('redirectUris', [])}")
    else:
        print(f"  Entra App ID:     {app_id}")

    sso_url = f"{instance_url}/services/auth/sso/AzureAD"

    print(f"\n  {'=' * 50}")
    print("  SSO Configuration Complete!")
    print(f"  {'=' * 50}")
    print(f"\n  Entra App ID:    {app_id}")
    print(f"  Tenant ID:       {tenant_id}")
    print(f"  SF Instance:     {instance_url}")
    print(f"\n  Test SSO:        {sso_url}")
    print(f"\n  Next steps:")
    print("  1. Open the SSO URL above in a browser")
    print("  2. Sign in with your Azure AD account")
    print("  3. Verify you land in Salesforce as the correct user")
    print("  4. (Optional) Enable 'Azure AD' on your My Domain login page:")
    print("     Setup > My Domain > Authentication Configuration > Edit")


def main():
    print("\n" + "=" * 60)
    print("  Salesforce SSO with Azure AD — OIDC Setup")
    print("=" * 60 + "\n")

    tenant_id, has_sf_cli = step0_prerequisites()
    app_id, obj_id, secret = step1_create_entra_app(tenant_id)
    instance_url, admin_username = step2_authenticate_salesforce(has_sf_cli)
    step3_update_redirect_uri(app_id, obj_id, instance_url)
    step4_generate_metadata(
        tenant_id, app_id, secret, instance_url, admin_username,
    )
    step5_deploy(has_sf_cli)
    step6_verify(app_id, instance_url, tenant_id)


if __name__ == "__main__":
    main()
