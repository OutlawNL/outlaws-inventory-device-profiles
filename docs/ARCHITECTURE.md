# Architecture

Outlaw's Inventory is a FastAPI application with SQLite persistence.

## Main functional areas

- Inventory
- Firmware
- System Checks
- Settings
- Authentication and MFA
- Backups and restore
- Notifications

## System Checks internals

System Checks persist their results in:

- `health_checks` for online, disk and HTTP(S) results
- `update_checks` for APT package checks

The user interface exposes one combined System Checks concept.

## Local service identity

The Outlaw's Inventory web application runs as the dedicated local system account `outlaws-inventory`. This account is non-interactive and is separate from any human Linux administrator account.

## Remote access

Remote managed-server access uses a dedicated SSH key and the separate remote service account `outlaw` with narrowly scoped sudo permissions.


## Installation health contract

From v0.14.1, installation success is defined by the running application, not merely by successful file copying. `install.sh` requires a healthy `/system/ready` response with the expected application version before reporting completion.

## Security boundary

The application process is deliberately non-root. Privileged local actions cross a narrow sudo boundary through explicit `systemctl` commands and controlled update/rollback launchers. Full backups, SSH profiles, application self-update and host-level System Actions remain available to authenticated users. Account/authentication administration and explicitly administrator-managed settings require an Administrator. Inventory remains owner-scoped. See SECURITY.md.

Persistent private files are owned by the service account and created with a restrictive systemd umask. See [Security](SECURITY.md) for deployment guidance and trust boundaries.

## Device Profiles

From v0.18.0, reusable product/vendor knowledge can live outside the core application in the public Device Profiles repository. YAML is the human-maintained source format; a validated JSON catalog is the runtime interface. The core remains responsible for parsing/execution strategies, networking and safety boundaries. Exact Device Profile matches can select a specialized core strategy; when no profile matches, existing generic/provider firmware behavior remains unchanged.

## Device Profile boundary

Device-specific knowledge belongs in external Device Profiles. The application core supplies reusable parser capabilities only. A profile defines what the device is, where update information is found, and declaratively how that source is parsed. Adding a device that can be expressed with existing capabilities must not require an application release. Devices without a matching profile continue to use the generic Firmware URL + optional filter workflow.
