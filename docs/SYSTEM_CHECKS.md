# System Checks

System Checks is the server-focused health, update and maintenance interface.

## Check Groups

### System Checks

- Ping
- Disk
- APT Package Updates

### Application Checks

- HTTP(S)
- Pi-hole
- Minecraft

Only enabled checks contribute to the aggregate server status. Disabling a check persists and does not silently recreate or re-enable it.

## Status Semantics

- **Critical** — an enabled health/service check is unhealthy.
- **Attention** — a valid check found an actionable warning or available update.
- **Unknown** — a configured check could not establish a trustworthy result.
- **Maintenance** — the server is intentionally excluded from normal processing.
- **OK** — all enabled checks are healthy/current.

Ping is not a mandatory prerequisite for an OK result when it is disabled.

## Managed SSH

SSH-based checks and managed actions use the remote account `outlaw` with a dedicated SSH key and narrowly scoped passwordless sudo rules. Configure/Reconfigure can bootstrap or repair this access using temporary administrator/root credentials; those credentials are not stored.

## Scheduling

Regular health checks run on the configured health cadence (10 minutes by default). Daily work runs System → Application → Firmware in the configured schedule.

The System Checks overview also refreshes its displayed state silently while open and immediately when restored/shown after returning from a detail page.

## Check Now

**Check Now** refreshes the enabled checks for that server using the same status semantics as scheduled execution.

## Pi-hole

Pi-hole health separates service health from update lookup health:

- DNS is tested with a real DNS query to `127.0.0.1:53` on the regular health cadence.
- Full Core/Web Interface/FTL version checks use `pihole -up --check-only` during the daily Application Check and on Check Now.
- A DNS failure is Critical.
- A valid available update is Attention.
- A failed/incomplete version lookup while DNS responds is Unknown, not Critical and not Up to Date.
- Diagnostic update-check output is retained on the detail page.
- Managed update execution uses **Update Pi-hole** and is followed by a fresh check.

## Minecraft

Minecraft checks detect the configured systemd service, installed server JAR/version, runtime state and configured port. Release information is resolved from the official Mojang version manifest.

**Upgrade Minecraft** stops the service, downloads and verifies the official JAR, retains one previous JAR, restarts the service, waits for the configured port and rolls back automatically if the new version fails to become healthy.

## Maintenance

Maintenance is an intentional exclusion. Scheduled checks and notifications are suppressed while maintenance is active. OI-driven application updates temporarily protect the affected health state during the managed action and refresh it afterwards.

## Reconfigure System Checks

After a remote host rebuild or SSH configuration change, use **Reconfigure System Checks** to repair the managed account, key, required packages and controlled sudo rules. Reconfiguration is explicit and idempotent; it does not run automatically.
