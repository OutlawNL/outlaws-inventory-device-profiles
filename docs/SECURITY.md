# Security

## Deployment boundary

Outlaw's Inventory is self-hosted software. The built-in Uvicorn listener is intended for a trusted LAN or a protected private network. Do not forward port 8000 directly from the Internet.

For remote use, prefer a VPN or terminate HTTPS at a reverse proxy with a trusted certificate. HTTPS is important because session cookies can only receive the Secure attribute when the application is reached through HTTPS (directly or through a correctly configured proxy).

## Authentication

- Passwords are hashed with Argon2.
- TOTP MFA is supported and can be required for Administrator accounts.
- Session, MFA-challenge and trusted-device tokens are random and only token hashes are stored in the database.
- Authentication cookies are HttpOnly and SameSite=Strict; they are Secure when the request is HTTPS.
- Password changes and MFA changes invalidate other sessions where appropriate.
- Login attempts are rate-limited in the application process.

## Authorization

Administrator privileges are required for account and authentication administration and for global settings that are explicitly marked as administrator-managed.

Authenticated users retain the operational capabilities available before v0.16.25, including application maintenance, backups, SSH profiles, data-integrity checks and host-level System Actions. Inventory records remain scoped to their owner where the multi-user data model applies. Authorization changes that intentionally reduce existing capabilities are treated as product changes rather than implicit hardening.

## CSRF and browser controls

State-changing browser requests are protected by SameSite cookies plus origin/fetch-site validation. JSON mutations additionally require the session CSRF token. Responses set no-sniff, frame-deny, referrer, permissions and no-store headers.

## Secrets and files

The application stores persistent data below `/opt/outlaws-inventory/data` by default. Sensitive material includes:

- SQLite database
- private SSH keys
- SMTP password
- GitHub access token when configured
- downloaded full backups
- attachments and account pictures

Runtime normalization restricts private files to the service account. The systemd service uses `UMask=0077` so newly created files are private by default. Private SSH keys and local secret files use mode `0600`; private data directories use restrictive modes.

Full backups contain secrets and must be protected like credentials. This is intentional for complete disaster recovery: the backup includes application-managed keys and local secrets such as a configured GitHub access token and SMTP secret, and restore reinstates them.

Release/distribution ZIPs are a different trust boundary: they must not contain runtime data, instance tokens, credentials, keys or local secrets. A fresh installation therefore receives no GitHub access token from the release package.

## Upload/import boundaries

- Account pictures are restricted to validated JPG/PNG/WEBP input and 5 MB.
- Device attachments are bounded to 50 MB and stored under random server-generated names.
- Device import archives have compressed/uncompressed size and entry-count limits, reject unsafe/duplicate paths and verify attachment checksums.
- Full backup restore has archive size/entry limits, rejects unsafe/duplicate paths and verifies the manifest and SHA-256 checksums before extraction/restoration.

## Managed SSH hosts

Managed Linux hosts use the dedicated `outlaw` account. Configure/Reconfigure installs a dedicated public key and only the sudo commands required for supported checks/actions. A host fingerprint can be pinned in the SSH profile; pinning is recommended for stable hosts.

Never reuse a personal SSH private key for public/shared installations when a dedicated Outlaw's Inventory key can be used.

## Privileged local actions

The web service itself runs as the non-interactive `outlaws-inventory` account. Sudoers grants only explicit commands needed for restart, reboot, poweroff and the controlled self-update/rollback launchers. The application does not run as root.

## Backups and recovery

Restore performs fresh validation even when the Settings page has cached prior inspection results. Existing data is backed up before restore. Backup files can contain credentials and should not be uploaded to issue trackers or shared for support without sanitization.

## Public reports and bug reports

Before sharing screenshots, logs, exported devices or diagnostics, check them for:

- internal IP addresses and DNS names;
- usernames and e-mail addresses;
- serial numbers and MAC addresses;
- SSH fingerprints/keys;
- access tokens or SMTP credentials.

Never publish a full `.oi-backup` as a bug-report attachment or share one with another user/instance unless transferring its credentials is explicitly intended. Private-beta installations should use their own repository-scoped read-only GitHub token. Public releases are intended to retrieve public GitHub release assets without requiring a personal access token.

## Device Profiles trust boundary

Device Profiles are declarative data, not executable extensions. The application accepts only fixed core strategies, requires HTTPS profile sources and validates the downloaded JSON catalog before replacing the local cache. A catalog outage does not disable the last validated cached profiles. The initial v1 profile repository includes a SHA-256 manifest; cryptographic signing of trusted profile releases is required before broad community contribution is enabled.

## v0.18.8 updater verification

The privileged updater independently checks release metadata and SHA256SUMS from the fixed official GitHub repository, then executes a root-private verified copy. Service-writable pending metadata is not an authority for the expected checksum. App-facing progress/log writes run as the service user. Installed code and the Python environment are root-owned; only runtime data is writable by the application. Existing private-repository access uses the configured token. See AUDIT_REPAIRS.md for compatibility and validation scope.
