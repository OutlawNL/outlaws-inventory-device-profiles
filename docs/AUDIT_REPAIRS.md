# v0.18.8 audit repairs

This release repairs the v0.18.6 audit findings while retaining existing screens, styling, navigation, operational permissions and Device Profile support. No features or controls were added or removed.

## Repairs

| Audit finding | Implementation |
|---|---|
| A01 MFA recovery | Resolve the actual user ID, read current account state and consume recovery codes in one transaction; concurrent reuse is rejected. Security changes revoke pending challenges and trusted-device state. |
| A02 Attachment ownership | Check ownership before any device attachment mutation, including the real HTTP route. |
| A03 Recovery safety | Never roll back from an incomplete safety copy. Restore the complete prior state on a later failure; retain recovery material if recovery also fails. Updater rollback requires a completed snapshot and handles explicit failure exits. |
| A04 APT truthfulness | Stop on failed metadata refresh or package listing before running informational probes. |
| A05 SSH fingerprints | Shared host-key policy validates configured SHA-256/MD5 fingerprints before authentication, including onboarding. Existing unpinned connection behavior is retained. |
| A06 Privileged updater | A root-owned verifier retrieves release/checksum metadata independently from the fixed official GitHub repository, verifies a private package copy and validates archive members. Root executes only that verified copy. App-facing updater state/logs are written as the service user. Installed code is root-owned; runtime data remains service-owned. |
| A07 Backup checksums | Require exact manifest coverage and reject duplicate/invalid entries. Hash and archive the same staged files. |
| A08 Initial check | Keep the same initial check and resulting navigation, but run blocking work in a worker thread. |
| A09 Check All transactions | Fetch each result outside a write transaction; commit per device and isolate unexpected check failures. |
| A10 Scheduling | Catch up missed daily/backup runs and calculate health boundaries using complete timestamps, including intervals over an hour. |
| A11 Profile outage | Preserve cached profiles; an unavailable matched profile without cache yields Unknown instead of silently selecting a legacy provider. Saving/viewing a device still works. |
| A12 SSH profile save | Correct owner binding and per-owner uniqueness. |
| A13 Disabled checks | Preserve an empty Ping/Disk/HTTP selection. |
| A14 Historical firmware | Preserve explicitly stored latest/manual confirmations. EoS alone no longer invents a latest version from current firmware. |
| A15 Documentation | Align authorization, release-line and backup-retention documentation with implementation. |

Further repairs include the missing HTTP error import, safe return URLs, bounded/randomized initial attachments, HTML escaping of displayed profile metadata, locale/timezone validation, consistent installer paths, and bounded profile-document downloads. Database connections close deterministically. Backup/restore obtain exclusive database/data-operation access and leave WAL/SHM lifecycle to SQLite; ordinary connections remain concurrent.

Catalog v7 retains all 109 profiles and their existing rules. Its builder validates all input before publication, rejects duplicate identities and restores the previous artifacts when publication fails.

## Compatibility and validation boundary

The root-side release verification becomes active once the new helper is installed. It checks the fixed official repository over HTTPS and uses the existing configured token for private repository access. This is independent origin verification, not a new signed-release/key-management system. Existing Production/Acceptance controls and update screens remain unchanged. If official verification cannot complete, installation stops safely rather than trusting service-provided metadata.

No database fields, visible controls, CSS or layout were added. Existing manually confirmed firmware values remain available. Incorrect green results and failed operations are corrected as described above.

The release is tested locally with temporary databases, official-document fixtures, concurrent recovery attempts, simulated I/O/network failures, actual web-route ownership checks, shell recovery logic and package verification. A Debian/systemd installation/update/rollback acceptance run on AppServer-02 remains necessary before production promotion. No application server was changed during development.

A comprehensive dependency-CVE scan, browser/device visual matrix and adversarial PDF CPU/memory stress campaign are not part of these regression tests. Firmware downloads now have byte/time bounds; those bounds are not a hard process-level CPU limit on third-party parsing.
