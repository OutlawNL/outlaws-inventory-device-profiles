# Outlaw's Inventory

Outlaw's Inventory is a self-hosted inventory and maintenance application for homelabs and technology-heavy households. It keeps device inventory, firmware information, server health, operating-system updates and supported application updates in one interface without requiring a hosted service.

The current release is **v0.18.8**. The supported technical baseline is **v0.15.0 or newer**.

## What It Does

- Device inventory with categories, ownership, notes, attachments and activity history
- Firmware tracking using GitHub, vendor pages, generic parsing and Device Profiles
- Device Profiles with live Vendor + Model matching and declarative parser instructions
- System Checks for Ping, Disk Usage, APT package updates and HTTP(S)
- Managed Linux-host access over SSH using a dedicated `outlaw` account
- Application Checks for Pi-hole DNS/update health and Minecraft runtime/version health for Java servers
- Controlled Pi-hole and Minecraft updates with action history
- Multi-user accounts with Administrator and User roles
- TOTP MFA, trusted devices and active-session management
- E-mail notifications with per-category controls and event deduplication
- Full application backup/restore, including database, attachments, SSH keys and local secrets
- Verified self-update and rollback workflow
- Device Report PDF export
- Responsive desktop, tablet and mobile interface

Outlaw's Inventory is designed to remain **self-hosted**. A centrally hosted/SaaS edition is not part of the product direction.

## Requirements

Recommended deployment:

- Debian-compatible Linux server, VM or container
- systemd
- Python and system packages installed by `install.sh`
- Network access to devices and update sources you choose to monitor
- SSH access for managed Linux-host checks and actions
- A modern browser

The application listens on TCP port `8000` by default. For access beyond a trusted local network, place it behind a trusted HTTPS reverse proxy or access it through a VPN. Do not expose the built-in HTTP service directly to the public Internet.

## Fresh Installation

Extract the release ZIP on a clean Debian-compatible host and run:

```bash
sudo ./install.sh
```

The installer creates the local non-interactive `outlaws-inventory` service account, installs the application in `/opt/outlaws-inventory`, creates the Python environment, installs the systemd service and verifies `/system/ready` before reporting success.

Then open:

```text
http://<server>:8000/setup
```

Setup can create the first Administrator account or restore a supported `.oi-backup`. After creating the administrator account:

1. Review **Settings → Device Profiles** and use **Check Now** to fetch the public profile catalog immediately.
2. Add Inventory items normally. Vendor + Model are matched against Device Profiles automatically; no separate profile installation step is required.
3. Configure System Checks only for hosts you actually want Outlaw's Inventory to manage.
4. Configure notifications/backups after the basic Inventory is working.
5. Keep the built-in HTTP listener on a trusted network; use VPN or a trusted HTTPS reverse proxy for remote access.

See [Installation](docs/INSTALL.md) for the complete installation and recovery flow.

## Updating

For normal use, update through **Settings → Application Version**. The updater validates the release, creates rollback material, preserves persistent data, restarts the service and verifies that the expected application/database version is running.

Command-line updating is also available:

```bash
sudo ./update.sh
```

Supported in-place updates start at **v0.15.0**. Older release lines are not part of the current upgrade contract.

## Backup and Restore

Full `.oi-backup` archives include the database, attachments, account pictures, SSH keys and locally stored secrets. Treat downloaded backups as sensitive credentials and store them accordingly. A configured GitHub access token and SMTP secret are part of those local secrets and are restored for complete recovery. Release/distribution ZIPs do not contain instance-specific secrets or runtime credentials.

Restore performs archive/path checks, size limits, manifest validation, SHA-256 verification and SQLite integrity validation before applying data. A pre-restore recovery backup is created before an existing installation is replaced.

See [Backups and Restore](docs/BACKUPS.md).

## Security Model

Outlaw's Inventory is intended for trusted self-hosted environments, but it still applies application-level security controls:

- Argon2 password hashing
- TOTP MFA and recovery codes
- hashed session/trusted-device tokens
- HttpOnly, SameSite cookies; Secure cookies when served over HTTPS
- origin/SameSite CSRF protections and CSRF tokens for JSON mutations
- Server-side authorization for administrator account/authentication management while preserving established authenticated-user maintenance workflows
- bounded and validated backup/device imports
- bounded image and attachment uploads
- restricted runtime permissions for database, secrets, SSH keys, backups, uploads and account pictures
- narrowly scoped sudo commands for application restart/reboot/shutdown and self-update helpers
- optional SSH host-fingerprint pinning for managed hosts

Read [Security](docs/SECURITY.md) before making an installation remotely reachable.

## Managed Hosts

Two Linux identities have deliberately different roles:

- `outlaws-inventory` — local non-interactive account running the application
- `outlaw` — account on managed remote Linux hosts used for System Checks and supported managed actions

Configure/Reconfigure System Checks provisions only the access required for the enabled managed checks/actions. See [Managed Hosts](docs/MANAGED_HOSTS.md).

## Status Semantics

Enabled System/Application Checks contribute to aggregate status; disabled checks do not.

- **Critical** — an enabled health check is actually unhealthy
- **Attention** — action is required, such as an available update or warning threshold
- **Unknown** — the application could not establish a trustworthy result
- **Maintenance** — the host is intentionally excluded from normal health processing
- **OK** — all enabled checks have a healthy, current result

## Supported Baseline and Limitations

- Fresh installs use the current release.
- Updates and backup restores support v0.15.0 and newer.
- v0.14.38 → v0.15.0 was the historical transition into the current baseline; pre-v0.15.0 compatibility is intentionally not maintained.
- Managed actions currently target supported Debian/Linux host workflows.
- Application-specific automation is currently implemented for Pi-hole and Minecraft Java server workflows; other devices can still use inventory, firmware and generic health functionality.
- Firmware/vendor-page parsing depends on external sites and may require provider updates when those sites change.
- Outlaw's Inventory does not provide a hosted relay, cloud tunnel or managed public endpoint.
- The built-in web listener is HTTP. Use a reverse proxy with a trusted certificate or a VPN for secure remote access.

## Screenshots

The interface is a single Classic dark UI optimized for desktop while remaining usable on tablet and mobile. Public project screenshots can be added to the repository without being required by the installable release package; avoid publishing screenshots containing real usernames, internal addresses, hostnames or other homelab data.

## Repository Structure

```text
app/          application code, templates, static files and providers
scripts/      restricted self-update and rollback helpers
tests/        release-contract and regression tests
docs/         architecture, operations, security and development documentation
install.sh    clean installation
update.sh     supported in-place update
```

## Documentation

- [Installation](docs/INSTALL.md)
- [Security](docs/SECURITY.md)
- [Backups and Restore](docs/BACKUPS.md)
- [Managed Hosts](docs/MANAGED_HOSTS.md)
- [System Checks](docs/SYSTEM_CHECKS.md)
- [Device Profiles](docs/DEVICE_PROFILES.md)
- [Application Updates](docs/APPLICATION_UPDATES.md)
- [Firmware](docs/FIRMWARE.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Database Design](docs/DATABASE_DESIGN.md)
- [UI Style](docs/UI_STYLE.md)
- [Release Process](docs/RELEASE_PROCESS.md)
- [Roadmap](docs/TODO.md)
- [Changelog](CHANGELOG.md)

## Project Status

Outlaw's Inventory is being prepared for wider self-hosted use. Installation, security and operational documentation are treated as part of the product rather than as developer-only notes.

Licensing, public contribution workflow and public support policy are intentionally separate publication decisions and are not defined by this release.
