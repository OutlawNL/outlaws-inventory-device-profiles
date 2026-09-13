# Application Updates

Outlaw's Inventory has two distinct application-update concepts.

## Managed Applications

Managed application checks are attached to servers through **System Checks → Application Checks**.

### Pi-hole

- regular DNS health check;
- daily/on-demand Core, Web Interface and FTL version lookup;
- Attention when a valid update is available;
- Unknown when version lookup fails while DNS remains healthy;
- controlled **Update Pi-hole** action with retained diagnostic/history output.

### Minecraft Java Server

- runtime/service and configured-port health;
- installed JAR version detection;
- latest official Mojang release lookup;
- controlled **Upgrade Minecraft** with SHA-1/version verification and one-JAR rollback protection.

Managed application actions temporarily suppress false health notifications while the application is intentionally being restarted/updated.

## Outlaw's Inventory Self-Update

The application checks its own GitHub release metadata from **Settings → Application Version**. Installation is performed by the restricted self-update helper. Success requires the helper to complete and the restarted application to report the target version with working database access.

The browser polls update status independently across the service restart. Failed updates can expose the tail of the update log for diagnosis. Command-line updates retain the two newest full timestamped backups. The independent self-update helper cleans timestamped updater backups and maintains the current rollback snapshot plus two historical code snapshots. Full application backups are managed separately.

The supported in-place update baseline is v0.15.0 or newer.


## Production and Acceptance channels

The updater can follow either **Production** or **Acceptance** from Settings → Application Version. Production only considers the latest normal GitHub Release. Acceptance also considers published GitHub pre-releases. Draft releases are ignored in both channels.

Changing channel saves immediately and performs a fresh release check. Update availability and the version offered for installation are always derived from the active channel. A pre-release therefore makes an Acceptance instance show Update Available, while a Production instance remains Up to Date until that same release is promoted to a normal GitHub Release.

Promotion does not require a rebuild: the tested ZIP and checksum from Acceptance must remain the same artifacts when the GitHub Release is promoted to Production.
