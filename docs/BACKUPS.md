# Backups and restore

A complete `.oi-backup` is intended for:

- disaster recovery;
- migration to a new Debian host;
- acceptance testing;
- rebuilding an installation.

## Supported baseline

v0.15.0 supports full backups created by Outlaw's Inventory **v0.15.0 or newer**.

Older pre-release backup formats and migration paths are not part of the current support contract. Create a fresh current backup before rebuilding or migrating.

## Included data

A full backup contains application-owned persistent data such as:

- SQLite database;
- Inventory data and categories;
- users and application settings;
- attachments and avatars;
- SSH profiles and application-managed SSH keys;
- locally stored application secrets.

Linux users, VM/container hostname and network configuration are outside the backup.

### Backup sensitivity

A full backup is deliberately a **complete recovery artifact**. It includes the application-managed `keys` and `secrets` data required to restore the same instance, including a configured GitHub access token and SMTP secret. Restore puts this protected material back and normalizes its private permissions.

The normal Outlaw's Inventory distribution ZIP does **not** contain instance-specific tokens, credentials, runtime data or other local secrets. Installing the application ZIP therefore does not copy the originating installation's GitHub access into another instance.

Treat every downloaded `.oi-backup` as credential-bearing sensitive data. Do not give a personal/full backup to another user or use it to seed an unrelated installation unless transferring those credentials is explicitly intended. For a separate private-beta installation, configure that installation with its own repository-scoped read-only GitHub token.

## Setup restore workflow

On a clean installation:

1. open `/setup`;
2. choose Restore from Backup;
3. select a `.oi-backup`;
4. the archive is validated before application data is replaced;
5. after a successful restore, the wizard displays **Backup restored successfully**;
6. the wizard then runs the current System Checks refresh;
7. after refresh completion, continue to login.

If validation or restore fails, the restore is reported as failed and System Checks are not run.

If the backup restores correctly but one or more System Checks fail, the restore still remains successful. This is expected when a managed server was rebuilt and no longer contains its remote `outlaw` account/key/permissions. Use **Reconfigure System Checks** on that device.

## Status data in backups

Health and update results stored in a backup are last-known historical state, not guaranteed current state. Setup therefore refreshes current System Checks before the first login.

Notifications are suppressed during this recovery-time refresh.

## Permissions after restore

After restore, Outlaw's Inventory normalizes runtime permissions for the database, private SSH keys and local secrets.

The local `outlaws-inventory` service account is created by `install.sh` and is not restored from the backup.

## Backup history status

The backup list separates file integrity from restore compatibility.

- `Restorable`: valid and compatible with the running release.
- `Unsupported`: valid archive, but created before the supported baseline or by a newer application version.
- `Invalid`: archive integrity/format validation failed.

Download remains available for every existing backup file, including Unsupported and Invalid files. This allows an administrator to copy recovery material off the server even when the current application refuses to restore it.

## Filenames

New backups include the creating application version in the filename. This is informational only; the validated manifest content is the source of truth for restore decisions.

## Retention

`Keep automatic backups` controls automatic backups only.

Manual backups and pre-restore recovery backups are not counted against the automatic retention limit and are not automatically deleted.

## Backup inspection cache — v0.14.9

The Settings backup list caches expensive archive/checksum inspection results using the physical file signature (name, size, modification time and change time). This avoids hashing all retained backups on every Settings page load.

The cache is operational metadata only and is not included in a full backup. Restore never relies on cached integrity results: `Validate and restore` always performs a fresh complete archive/checksum validation.
