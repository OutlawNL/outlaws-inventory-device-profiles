# Installation

## Supported platform

Outlaw's Inventory is installed on a Debian-compatible Linux host.

## Supported release baseline

- Fresh installation: current release
- In-place update: v0.15.0 or newer
- Backup restore: backup created by v0.15.0 or newer

## Clean installation

Extract the release ZIP and run:

```bash
sudo ./install.sh
```

The installer creates the local non-interactive service account `outlaws-inventory`, installs dependencies and the Python virtual environment, writes the systemd service and validates the running application.

A successful installer exit means:

- `outlaws-inventory.service` is active;
- `/system/ready` returns `ready: true`;
- the running application version matches the release being installed.

If startup fails, the installer exits non-zero and prints service/journal diagnostics.

`install.sh` is for a clean installation only. Existing installations use `update.sh`.

## First browser setup

Open:

```text
http://<server>:8000/setup
```

Choose either:

- New Installation
- Restore from Backup

## Service identity

The local service runs as:

```text
outlaws-inventory
```

This account is non-interactive and uses `/usr/sbin/nologin`.

Managed remote hosts use a separate account:

```text
outlaw
```

## Updating

For normal operation use Settings → Application Version. Command-line update remains available:

```bash
sudo ./update.sh
```

The current updater accepts installed versions v0.15.0 or newer.

## Rebuilding a host

For disaster recovery:

1. create/download a current `.oi-backup`;
2. build a clean Debian-compatible host;
3. install the current release;
4. restore the backup through `/setup`;
5. allow the restore wizard to refresh current System Checks;
6. use Reconfigure System Checks for any rebuilt managed host that no longer has the required remote account/key configuration.

## Network exposure

The built-in service listens on port 8000 over HTTP. Keep it on a trusted network. For remote access use a VPN or an HTTPS reverse proxy with a trusted certificate; do not expose port 8000 directly through Internet port forwarding.

The service runs with `UMask=0077` so newly created runtime files are private by default. See [Security](SECURITY.md) for the deployment and secrets model.
