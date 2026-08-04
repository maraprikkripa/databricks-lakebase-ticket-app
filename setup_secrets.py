"""
One-time setup script: creates the Databricks secret scope and stores the
Lakebase connection URL. Run this once from a Databricks notebook (or
locally with the Databricks CLI configured) - never commit the resulting
secret value anywhere.

Usage:
    python setup_secrets.py
"""
from databricks.sdk import WorkspaceClient
from databricks.sdk.service import workspace
import getpass

w = WorkspaceClient()

w.secrets.create_scope(scope="database")
w.secrets.put_secret(
    scope="database",
    key="lakebase-url",
    string_value=getpass.getpass("Paste your Lakebase URL: ")
)

w.secrets.put_acl(
    scope="database",
    principal="users",
    permission=workspace.AclPermission.READ,
)
