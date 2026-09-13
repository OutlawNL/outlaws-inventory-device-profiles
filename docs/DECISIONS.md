# Product decisions

- Firmware checking remains the primary product purpose.
- Servers remain in Inventory.
- Server-related online, disk and update information is presented as System Checks.
- Outlaw's Inventory will not become a full monitoring platform.
- The application name is fixed as Outlaw's Inventory.
- Technical documentation is available under Settings > Documentation.
- A separate practical user manual is a future idea.

- Health and Updates category sections are consolidated into one System Checks section.
- Uptime is informational and collected with the existing scheduled SSH check; it is not real-time monitoring.


## System Checks UI

Health and Updates remain unified as System Checks. The old v0.9.6 Health / Updates visual model is the permanent UI reference because it is compact, interactive and information-dense.


## 2026-08-12 — Dashboard and Settings information hierarchy

- Dashboard KPI count is reduced to four to keep the summary row balanced.
- Firmware status and firmware update availability are represented by one Firmware KPI.
- Outlaw's Inventory self-update availability is shown conditionally as a banner, not as a permanent Application Updates KPI.
- Settings stays single-column because expanding full-width configuration content is clearer than a two-column accordion.
- Settings uses subtle Personal, Application and Administration group headings and compact closed rows.


## 2026-08-12 — Destructive Device deletion and UI label casing

- Permanent Device deletion requires an explicit in-app confirmation with an acknowledgement checkbox.
- The confirmation must identify the Device and state that deletion cannot be undone.
- Dashboard `Current Status` and Settings group headings use normal title case instead of all caps.
- Settings headings keep the same typography and horizontal position between collapsed and expanded states.
- Firmware Unknown state does not create a special Dashboard border; only actionable firmware updates change the Firmware card to Attention.


## 2026-08-12 — Dedicated local service account

- The Outlaw's Inventory application runs as local system account `outlaws-inventory`.
- Human administrator usernames are installation-specific and must never be assumed by the product.
- Remote managed hosts continue to use the separate account `outlaw`.
- Existing installs migrate service ownership automatically; the historical human `outlaw` account is left untouched.
- A failed service-account migration must restore the previous system integration as well as application files.


## 2026-08-12 — Installer success and clean recovery

- `install.sh` is a clean-install command, not an in-place updater.
- Existing installations use `update.sh`.
- Installation is successful only after systemd and `/system/ready` confirm the expected running application version.
- A failed first startup must return a failed installer exit and useful diagnostics rather than `Installation complete`.
- Backup restore normalizes application-data permissions on the target host and does not depend on the Linux service identity from the source machine.

## 2026-08-12 — Reconfiguring rebuilt managed hosts

- Inventory identity and System Checks configuration can outlive the operating-system installation of a managed host.
- A rebuilt host may still respond to ping while SSH-based Disk Usage and APT checks fail.
- Outlaw's Inventory therefore offers an explicit `Reconfigure System Checks` workflow for existing servers.
- Reconfiguration reuses managed-host onboarding and must never run automatically on an authentication failure.
- Authentication failure is presented as a configuration issue on Device/System Check Details rather than as raw technical text in the overview.

## 2026-08-12 — Dedicated profile for managed System Checks

- Managed System Checks always use the dedicated `System Checks` SSH profile and `outlaw` remote account.
- General-purpose or historical SSH profiles may remain available for other purposes but are never used for managed-host onboarding/reconfiguration.
- Reconfiguration readiness is determined from fresh live SSH/permission validation, not a previously persisted check failure.

## 2026-08-12 — Backup status is not current status

- Health and System Update results stored in a backup are last-known historical state.
- Setup restore must refresh System Checks before presenting the restored installation as ready.
- The restore refresh reuses the same check execution logic as `Check All`.
- Setup-time refresh does not send notifications.
