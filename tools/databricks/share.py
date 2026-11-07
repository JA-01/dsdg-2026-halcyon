"""Grant existing workspace members access to Halcyon project resources.

Pass their sign-in emails as arguments. This adds project permissions without
replacing existing ACLs, inviting new users, or granting administrator access.
"""

import argparse
import json
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.service import catalog, iam, jobs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("emails", nargs="+")
    parser.add_argument("--profile", default="halcyon")
    parser.add_argument("--experiment-id")
    parser.add_argument("--warehouse-id")
    parser.add_argument("--manage-job-email", action="append", default=[],
                        help="Project integrator allowed to edit the setup job; must be in emails")
    args = parser.parse_args()
    state = json.loads((Path.home() / ".local/share/dsdg-databricks/workspace.json").read_text())
    w = WorkspaceClient(profile=args.profile)
    if w.config.host.rstrip("/") != state["host"].rstrip("/"):
        raise ValueError("Authenticated workspace does not match the provisioned workspace")
    emails = sorted(set(args.emails))
    managers = set(args.manage_job_email)
    if not managers.issubset(emails):
        raise ValueError("Every job manager must also be listed as a project member")
    for email in emails:
        found = list(w.users.list(filter=f"userName eq {json.dumps(email)}"))
        if len(found) != 1 or not found[0].active:
            raise ValueError(f"Add/activate {email} in workspace settings before sharing")
    schema_privileges = [catalog.Privilege.USE_SCHEMA, catalog.Privilege.SELECT,
        catalog.Privilege.MODIFY, catalog.Privilege.CREATE_TABLE, catalog.Privilege.CREATE_VOLUME,
        catalog.Privilege.READ_VOLUME, catalog.Privilege.WRITE_VOLUME,
        catalog.Privilege.CREATE_MODEL, catalog.Privilege.EXECUTE]
    w.grants.update("catalog", state["catalog"], changes=[catalog.PermissionsChange(
        principal=email, add=[catalog.Privilege.USE_CATALOG]) for email in emails])
    w.grants.update("schema", f"{state['catalog']}.{state['schema']}", changes=[
        catalog.PermissionsChange(principal=email, add=schema_privileges) for email in emails])
    folder = w.workspace.get_status("/Workspace/Shared/halcyon")
    w.permissions.update("directories", str(folder.object_id), access_control_list=[
        iam.AccessControlRequest(user_name=email, permission_level=iam.PermissionLevel.CAN_EDIT)
        for email in emails])
    # Preserve existing owner/manager access when the ordinary sharing command
    # is rerun; the integrator needs CAN_MANAGE to redeploy Phase 2 job settings.
    existing = w.jobs.get_permissions(str(state["job_id"])).access_control_list or []
    job_levels = {}
    for email in emails:
        levels = {permission.permission_level.value for item in existing
                  if item.user_name == email for permission in item.all_permissions or []}
        job_levels[email] = ("IS_OWNER" if "IS_OWNER" in levels else
                             "CAN_MANAGE" if email in managers or "CAN_MANAGE" in levels else
                             "CAN_MANAGE_RUN")
    w.jobs.update_permissions(str(state["job_id"]), access_control_list=[
        jobs.JobAccessControlRequest(user_name=email,
            permission_level=jobs.JobPermissionLevel(job_levels[email]))
        for email in emails if job_levels[email] != "IS_OWNER"])
    if args.warehouse_id:
        w.permissions.update("warehouses", args.warehouse_id, access_control_list=[
            iam.AccessControlRequest(user_name=email, permission_level=iam.PermissionLevel.CAN_USE)
            for email in emails])
    if args.experiment_id:
        w.permissions.update("experiments", args.experiment_id, access_control_list=[
            iam.AccessControlRequest(user_name=email, permission_level=iam.PermissionLevel.CAN_EDIT)
            for email in emails])
    # Verify direct data grants and project-folder/job ACLs from the service.
    grants = w.grants.get("schema", f"{state['catalog']}.{state['schema']}")
    by_principal = {item.principal: set(item.privileges or []) for item in grants.privilege_assignments or []}
    for email in emails:
        assert set(schema_privileges).issubset(by_principal.get(email, set())), email
    resources = [("directories", str(folder.object_id), "CAN_EDIT"),
                 ("jobs", str(state["job_id"]), "CAN_MANAGE_RUN")]
    if args.warehouse_id:
        resources.append(("warehouses", args.warehouse_id, "CAN_USE"))
    if args.experiment_id:
        resources.append(("experiments", args.experiment_id, "CAN_EDIT"))
    for kind, resource_id, required in resources:
        acl = w.permissions.get(kind, resource_id).access_control_list or []
        for email in emails:
            expected = job_levels[email] if kind == "jobs" else required
            permissions = {permission.permission_level.value for item in acl
                           if item.user_name == email for permission in item.all_permissions or []}
            assert expected in permissions, f"{email}: {expected} missing on {kind}/{resource_id}"
    for email in emails:
        print(f"Granted project edit/data access and job-run access to {email}")
    print("Project notebook folder: /Workspace/Shared/halcyon")


if __name__ == "__main__":
    main()
