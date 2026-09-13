# v0.18.8 — 2026-09-12 — Safe Device-Profile Version Comparison

- Add an optional, declarative installed-version format to Device Profiles.
- If a stored firmware version does not use the profile's declared format, its result is Unknown; it can never be presented as an update.
- Apply this to DJI O4 Air Unit (often called “Lite”): its official `01.00.0400` version is no longer numerically compared with a Pro-style `01.00.06.00` value.
- DJI O4 Air Unit Pro remains independently comparable and continues to report its official `01.00.07.00` release as an update from `01.00.06.00`.

Requires catalog v8 for the O4 Air Unit rule. Existing screens and controls are unchanged.

# v0.18.7 — 2026-09-12 — Reliability and Security Repairs

- Preserve existing functionality, screens, styling and navigation while repairing audit findings.
- Correct one-time MFA recovery-code consumption and attachment ownership enforcement.
- Protect backup/restore and updater recovery against incomplete safety copies; require complete backup checksum coverage.
- Verify configured SSH fingerprints before authentication and independently verify official releases in the root updater.
- Keep firmware and APT statuses trustworthy during failed checks; preserve cached profiles and explicit historical firmware confirmations.
- Keep the initial device firmware check responsive, shorten Check All transactions and repair scheduler catch-up and long intervals.
- Repair manual SSH profile saving, preserve disabled health checks and align security/maintenance documentation.
- Add behavioral, concurrent, HTTP, recovery-failure and root package-verification regression tests.

Catalog v6 remains compatible. Optional catalog v7 retains the same 109 profiles and hardens only catalog construction. See docs/AUDIT_REPAIRS.md. Validate on AppServer-02 before production promotion.

# v0.18.6 — 2026-09-12 — Consumer Device Profiles

- Support catalog v6: 106 DJI profiles and three Fujifilm profiles; official product pages discover their own current Release Notes documents.
- Add declarative PDF spacing, multiline header extraction and explicit component release selection. O4 Air Unit variants read their own release and never inherit a Pro firmware version.
- Add generic HTML firmware extraction. Move X-T5, XF18–55 and XF16–80 firmware records out of the application catalog into external profiles, including live release dates and release details.
- Keep Osmo and Osmo+ identities distinct; ambiguous profile matches return no match.
- Mark Updated returns to the Firmware overview when started there, and stays on the device page when started there.
- No verified firmware profile is claimed for FinePix S200EXR or XF150–600; existing manually configured values and lifecycle handling are preserved.

Install the application before syncing catalog v6. See docs/DEVICE_PROFILE_COVERAGE.md for scope and exceptions. Validate on AppServer-02 before production promotion.

# v0.18.5 — 2026-09-12 — Initial Firmware Check & Goggles 3

## Added
- Saving a new device now runs one initial firmware check when a firmware source is configured, its category shows firmware and the provider supports monitoring. Device Profile matches supply the source automatically.
- The initial check uses the same result persistence as Check Now, after device creation commits. Failures leave the device saved and offer Check Now as a retry on its device page.
- Device Profiles catalog v5 adds DJI Goggles 3 (17 profiles). Its official PDF was verified: firmware 01.00.1500, released 2026-09-01.

## Behavior
- The initial check is independent of the daily Auto Check setting; it does not enable recurring checks.
- Save waits for the initial check before redirecting. Existing first-run and server-integration redirects remain intact.
- Devices without a configured source or supported firmware monitoring are saved without a check.
- Editing an existing device does not trigger this initial check again.
- The full Device Profile is already fetched and SHA256-verified when the add form finds a catalog match. Save and checks reuse the cached profile; unused profiles are removed during synchronization.
- Device-specific profiles remain separate while sharing one generic engine. Catalog v5 is also compatible with OI v0.18.4.

# v0.18.4 — 2026-09-12 — Profile-Driven PDF Extraction

## Changed
- Device Profile firmware checks use pdfplumber 0.11.10. Pillow is upgraded to 12.3.0 to satisfy its dependency requirements.
- Document discovery selects one download item matching the profile title, URL constraints and language pattern. Ambiguous or missing matches return Unknown.
- Profiles declare the expected document title and first-release/first-page scope. Date and device firmware are extracted from exact label/value rows in that release only.
- Missing PDF dates remain unknown; download-page dates and older release entries cannot fill them in.
- What's New preserves wrapped bullet text and stops at the declared Notes heading.
- Removed the explanatory catalog paragraph from Settings → Device Profiles.

## Device Profiles
- Requires updated catalog v4 for this strict extraction route. Install OI v0.18.4 before updating the profile repository and synchronizing profiles.
- All 15 existing DJI profiles refreshed; Goggles N3 added (16 profiles). Product-specific source URLs, selectors, titles and labels remain in profiles, not core code.
- Existing on-demand catalog/profile caching and hash verification remain in use.

## Validation
- Live discovery and PDF extraction checked for all 16 profiles; snapshots included for offline regression tests.
- Tests cover wrong-product documents, accessory firmware, missing/invalid/duplicate dates, ambiguous links and multiple releases sharing a firmware version.
- Acceptance installation and in-place updater validation on AppServer-02 remain required before production promotion.

# v0.18.3 — 2026-09-11 — On-Demand Device Profiles & DJI Expansion

## Added
- Expanded the verified DJI Device Profiles batch to 15 profiles across current/recent Osmo cameras, mobile gimbals and RS gimbals, alongside the existing Mini 4 Pro, Mini 5 Pro and Neo 2 profiles.
- Added a lightweight catalog/runtime split: the catalog contains matching metadata and a hash-pinned runtime profile URL, while full parser instructions are downloaded only for devices actually present in Inventory.
- Added an Available Profiles count next to Installed Profiles in Settings.

## Fixed
- Improved generic profile label extraction for PDF table layouts where labels and values are emitted in separate columns/lines, including DJI release dates and Mini 4 Pro firmware versions.
- Parser failures no longer overwrite What's New; a separate troubleshooting message is shown instead.
- Unused cached Device Profiles are pruned during catalog synchronization.
- Normalized Installed Profiles typography to the established Settings scale.

## Architecture
- Daily Device Profiles synchronization now downloads only the lightweight catalog globally and reconciles full profiles on demand for matching Inventory devices.
- Runtime profiles are SHA-256 verified against the catalog before being cached.
- The generic Firmware URL + optional Filter/Keyword parser remains available for devices without a matching Device Profile.
- Device-specific knowledge remains declarative: the core provides parser capabilities, while profiles define what the device is, where firmware information is found and how it is extracted.

# v0.18.2 — 2026-09-11 — Declarative Device Profile Parsing

## Added
- Added the generic `release_notes_pdf` Device Profile capability.
- Device Profiles can now define document discovery, exact firmware-version extraction, release-date parsing, What's New section boundaries and version validation.
- Added support for catalog profiles for DJI Mini 5 Pro and DJI Osmo Action 4 alongside Neo 2 and Mini 4 Pro.

## Fixed
- Fixed Device Profile PDF parsing so firmware versions are taken from the exact profile-defined label instead of the highest version-like value in the document.
- Fixed release dates so the profile-defined `Date:` value from the Release Notes PDF is authoritative.
- Fixed What's New extraction to use only the profile-defined section rather than generic text from the document.

## Architecture
- Device-specific parsing knowledge now lives in Device Profiles. The core provides generic parser capabilities only.
- New devices expressible with existing capabilities can be added through catalog/profile updates without an Outlaw's Inventory application release.
- The generic Firmware URL + optional Filter/Keyword workflow remains available when no Device Profile matches.

# Changelog

## v0.18.1 — 2026-09-11 — Device Profile Firmware UX & DJI Fix

### Fixed
- Fixed DJI Device Profile firmware discovery for download pages that embed Release Notes PDF URLs in escaped page data.
- DJI Release Notes selection now prefers the requested product and avoids accidentally selecting DJI Assistant release notes.
- Device Profile firmware checks now record `Device Profile` as the automatic check method and `Official` confidence for official profiles.
- Removed an unintended Device Profile block from System Check creation introduced in v0.18.0.

### Changed
- Moved the Device Profile match notice from General into the Firmware section.
- Simplified firmware configuration: Device Profile matches are automatic; devices without a profile expose only Firmware URL and an optional Firmware Filter / Keyword.
- Removed Firmware Provider, Provider Identifier, Firmware Source, Check Method and Confidence dropdowns from the device UI. Existing backend metadata is preserved for compatibility.
- Added an expandable Installed Profiles list under Settings → Device Profiles.

## 0.18.0 — 2026-09-11

### Added
- Introduced the Device Profiles runtime/catalog foundation.
- Added live Device Profile matching while entering Vendor + Model on the device form.
- Added Settings → Device Profiles with catalog version, installed profile count, Last Checked, Last Updated, Profiles Updated and a manual Check Now action.
- Added the first profile-driven firmware strategy: `dji_release_notes_pdf`, which discovers the current official DJI Release Notes PDF and extracts firmware version/date.
- Added documentation for the Device Profiles architecture and staged migration model.

### Changed
- Exact Device Profile matches take precedence over the generic firmware parser; devices without a profile continue to use the existing generic/provider behavior.
- Device Profiles are refreshed before the configured daily Update Checks; cached profiles continue working if the public catalog is temporarily unavailable.
- README first-use guidance now includes Device Profiles.

### Compatibility
- No existing Inventory data or hard-coded provider behavior is removed. Existing DJI/provider logic remains available as fallback while the new profile route is proven.

## v0.17.1 — 11-09-2026 — Release Channel Labels & Backup Security Documentation

- Expand the Application Version release-channel labels from `Prod` / `Acc` to `Production` / `Acceptance` without changing the established toggle behaviour, colours or layout.
- Document the security boundary between clean distribution ZIPs and full recovery backups.
- Explicitly document that full backups intentionally include application-managed keys and local secrets such as configured GitHub and SMTP credentials, and that restore reinstates them.
- Document that full backups are credential-bearing sensitive files and should not be shared between unrelated users or instances.
- Document that private-beta installations should use their own repository-scoped read-only GitHub token.
- Record the public-release goal that public GitHub release updates should not require a personal access token.
- Keep release-channel discovery, updater behaviour, permissions, Dashboard and established layouts unchanged.

## v0.17.0 — 11-09-2026 — Production & Acceptance Release Channels

- Add a direct Prod / Acc release-channel switch to Settings → Application Version.
- Save channel changes immediately and run a fresh GitHub release check after switching.
- Keep Production on GitHub's latest normal release and ignore pre-releases.
- Let Acceptance discover both normal releases and GitHub pre-releases while ignoring drafts.
- Make Latest Release and Update Available status follow the active release channel.
- Give the Application Version card a subtle blue accent while Acceptance is active; Production retains the established appearance.
- Document the immutable Acceptance → Production promotion flow: test the exact pre-release artifact, then promote the same GitHub Release without rebuilding it.
- Add System Maintenance to the roadmap with automatic detection but deliberate user-triggered cleanup as the design principle.
- Keep Dashboard, permissions, updater installation/rollback behavior and established layouts unchanged.

## v0.16.31 — 11-09-2026 — Live Dashboard Status & Documentation

- Refresh Dashboard status silently every minute so System Checks changes appear without navigating away or manually reloading the page.
- Reuse the normal Dashboard rendering and existing System Checks aggregation instead of introducing a second status calculation.
- Update the Current Status hero, Dashboard KPI cards and action items in place without a visible full-page reload or scroll jump.
- Refresh immediately when the Dashboard is restored from browser back/forward cache.
- Add Software Checks / Software Version Tracking to Ideas, with DJI Reframe and VST/audio tools as initial examples.
- Document that Pi-hole and Minecraft remain Application Checks and must not be duplicated under Software Checks.
- Keep v0.16.30 persistent check progress, permissions and established UI layouts unchanged.

## v0.16.29 — 10-09-2026 — Robust Action Flows & Progress Feedback

- Keep System Checks and Firmware `Check All` on their normal overview URL while the check runs, with consistent spinner feedback.
- Prevent refresh during `Check All` from falling into dynamic ID routes or exposing raw HTTP 405/422 framework errors.
- Add safe GET fallbacks for long-running maintenance action URLs, including host updates, application updates, system actions, backups and managed-host validation.
- Preserve POST semantics so refreshing never unintentionally repeats a maintenance action.
- Document the shared long-running-action navigation and progress convention for future functionality.
- Keep v0.16.27 Minecraft status behavior and v0.16.28 table-layout conventions unchanged.

## v0.16.30 — 10-09-2026 — Persistent Check Progress

- Run System Checks and Firmware `Check All` independently from the browser request so refreshing or leaving the page does not cancel the work.
- Keep per-user operation state on the server while a grouped check is running.
- Restore the `Checking…` spinner automatically after a page refresh and keep it visible until the grouped check has actually finished.
- Refresh the normal overview when the background operation completes so the final results are shown.
- Keep Minecraft checking, permissions, table layouts and other functionality unchanged.


## v0.16.28 — 09-09-2026 — Shared Overview Table Alignment

- Standardize desktop overview-table alignment: text and data columns stay left-aligned, while Status and Action control columns center both header and control.
- Correct System Checks `Last Checked` alignment and center only Status and Action.
- Correct Firmware desktop alignment by centering only Status.
- Make Firmware use the same compact two-column phone overview as System Checks instead of the generic card-per-device mobile layout.
- Add shared reusable table classes and document the convention for future overview pages.
- Keep Minecraft status behavior and all other functionality unchanged.

## v0.16.27 — 09-09-2026 — Minecraft Status & Mobile Overview Consistency

- Treat a failed Minecraft release-metadata lookup as Attention when the Minecraft service and listening port remain healthy, instead of incorrectly marking the server Critical.
- Keep real Minecraft runtime, service and listening-port failures Critical and preserve the detailed diagnostic message for version-check failures.
- Align the phone Firmware overview with the compact two-column System Checks layout.
- Center the Status heading over the status indicator in both phone overviews while keeping names left-aligned and allowing long names to wrap.
- Leave desktop and tablet layouts unchanged.

## v0.16.26 — 09-09-2026 — Security Hardening Regression Recovery

- Restored the v0.16.24 authenticated-user maintenance behavior that was unintentionally restricted by the broad Administrator-only middleware added in v0.16.25.
- Kept the non-disruptive v0.16.25 security hardening, including restrictive runtime permissions, bounded/randomized attachment storage and browser/request protections.
- Preserved the corrected System Actions reconnect feedback so successful Restart/Reboot actions return to the open System Actions section.
- Restored the compact two-column System Checks phone layout while leaving desktop and tablet presentation unchanged.
- Added regression coverage to keep hardening changes separate from intentional product authorization changes.

## v0.16.25 — 09-09-2026 — Public Beta Readiness & Security Hardening

- Moved Restart/Reboot completion feedback into the System Actions disclosure and reopen that disclosure after reconnect.
- Added server-side Administrator authorization for full backups, SSH profiles, self-update/rollback, data-integrity administration and host-level System Actions.
- Hardened private runtime data with a restrictive systemd umask and normalized private file permissions.
- Bounded device attachment uploads to 50 MB and store them under random server-generated filenames.
- Generalized remaining homelab-specific example hostnames/addresses and historical environment wording.
- Reworked README for wider self-hosted use and added a dedicated security/deployment guide.
- Documented the self-hosted-only distribution model and safe remote-access boundary.

## v0.16.24 — 03-09-2026 — UI Copy & Documentation Consistency

- Standardized interface labels, headings and actions on Title Case while preserving sentence case for explanatory copy and messages.
- Documented the capitalization convention as a permanent UI rule.
- Simplified Account Picture to image-specific content only and aligned Remove, file selection, Upload and file-format guidance.
- Refreshed README and current project documentation against the v0.16.x application and v0.15.0+ supported baseline.
- Removed stale roadmap/documentation references to already-delivered features and historical v0.14.x development assumptions.

## v0.16.23 — 03-09-2026 — Interface Consistency Polish

- Combined General and Account picture into one calm Account overview panel while preserving the balanced two-column layout.
- Moved the account-picture Remove action below the image and kept the compact chooser and Upload action beside it.
- Combined Active Sessions and Trusted Devices into one shared panel with two independent disclosures.
- Removed accumulated ineffective Release Notes spacing overrides and fixed spacing at the actual expanded release-content boundary.
- Normalized the remaining gradient primary buttons project-wide to the standard solid action style; semantic warning and destructive styles remain unchanged.

## v0.16.22 — 03-09-2026 — Settings Final Polish

- Added consistent breathing room between Application Version Release Notes and its action row in both collapsed and expanded states.
- Reframed General, Account picture and Security as distinct Account panels while preserving the two-column desktop layout.
- Compacted Account picture controls by moving the shorter file selector and upload actions beside the avatar.
- Further reduced closed Active sessions and Trusted devices disclosures to compact rows.
- Added spacing between the Notifications Application URL field and its action buttons.
- Normalized regular Settings actions to the quiet solid button style while retaining semantic destructive styling.
- Left the corrected Device Notes, History and Attachments spacing unchanged.

## v0.16.21 — 03-09-2026 — Account & Spacing Polish

- Reworked the Account header into an even two-column General and Account picture layout.
- Moved Display Name saving directly beside the field and kept username, role and last login as compact account metadata.
- Made Security collapsible and closed by default while preserving password and MFA behavior.
- Tightened closed Active sessions and Trusted devices disclosures.
- Added breathing room below Application Version Release Notes in both collapsed and expanded states.
- Fixed Notes-to-Attachments spacing specifically on device pages without History; the existing History layout is unchanged.
- Left Notifications, Categories, Backup/Restore, SSH Profiles, Documentation and System Actions unchanged.

## v0.16.21 — 03-09-2026 — Final Settings Layout Polish

- Normalized spacing between Notes, optional History and Attachments on device detail pages.
- Reduced unused vertical space in the Account session and trusted-device disclosures.
- Compacted Manual backup and Restore backup into horizontal action rows while preserving all backup behavior.
- Reduced the visual weight of the expanded Application Version release title.
- Tightened vertical padding around the System Actions controls.
- Left Notifications, Categories, Documentation and SSH Profiles unchanged.

## v0.16.19 — 03-09-2026 — Settings and Account Polish

- Increased Settings section, accordion-title and supporting-copy typography slightly for clearer hierarchy while preserving the existing Classic layout.
- Tightened the spacing above the Notifications explanatory note.
- Refined the Account layout rhythm and alignment without changing fields, behavior or account functionality.
- Changed avatar Remove from destructive red styling to a neutral secondary action.
- Replaced the prominent MFA Enabled/Disabled pill with a compact inline state indicator.
- Preserved the existing desktop structure and responsive/mobile behavior.

## v0.16.18 — 03-09-2026 — Notification Preference Autosave

- `Enable e-mail notifications` now saves immediately when toggled.
- All four `Notify for` preferences now save immediately when toggled.
- Added compact Saving / Saved feedback for notification preference changes.
- The collapsed E-mail server section and its Save button remain dedicated to SMTP and mail-server configuration.
- Saving SMTP settings no longer rewrites notification preference booleans on the normal Settings page.
- The first-run notification setup flow remains unchanged.

## v0.16.17 — 03-09-2026 — Pi-hole Update Check Robustness

- Pi-hole version checks are now strictly non-interactive, preventing unexpected Git/GitHub credential prompts from holding a scheduled check open.
- A healthy Pi-hole DNS service with a failed or unrecognized version check is now reported as Unknown instead of Critical.
- Daily checks and Check Now now use the same Pi-hole status semantics.
- Known GitHub credential/access failures are reported with a clear user-facing explanation instead of an unrecognized-result message.
- Pi-hole diagnostic update-check output is retained and available from the System Check detail page.
- The regular DNS refresh preserves an existing Unknown version-check state and its diagnostic message until a full Pi-hole check succeeds.
- Notifications include concrete Unknown Pi-hole update-check failures while keeping the service health distinction clear.

## v0.16.16 — 01-09-2026 — Immediate System Checks Overview Refresh

- System Checks now performs a silent status refresh immediately whenever the overview page is shown or restored from browser back/forward cache.
- Returning from a System Check detail page therefore immediately reflects saved and rechecked status changes without Cmd+R or waiting for the one-minute background refresh.
- The existing silent 60-second overview refresh remains unchanged.
- No full page reload, flash or scroll jump is introduced.

## v0.16.15 — 01-09-2026 — HTTP(S) Immediate Status Refresh

- Saving a changed HTTP(S) URL still runs only the HTTP(S) health check, but now refreshes the device detail after that check completes so the new result is visible immediately.
- The aggregate server status is therefore shown immediately after an HTTP(S) endpoint changes, without waiting for Check Now or the next scheduled cycle.
- The refreshed result is persisted, so returning to the System Checks overview shows the same current status.
- Preserved Enter and blur autosave plus the short Saved confirmation.
- Confirmed the login form uses native focusable controls in DOM order and contains no application-specific tabindex overrides; Safari keyboard navigation remains controlled by Safari/macOS settings.

## v0.16.13 — 01-09-2026 — HTTP(S) Check Configuration and Detail Spacing

- Fixed HTTP(S) health checks incorrectly falling back to the server host when the configured HTTP(S) URL was empty.
- An enabled HTTP(S) check without a URL now reports Unknown / not configured instead of a false green result.
- HTTP(S) URL is now rendered as a proper conditional subsection with the same separator and spacing hierarchy as Disk Usage Thresholds.
- Preserved the v0.16.12 Pi-hole DNS health cadence and all existing System Checks behavior.

## v0.16.12 — 01-09-2026 — Pi-hole Health Cadence and Check Copy

- Pi-hole DNS health now refreshes with the regular 10-minute System Checks health cycle.
- Pi-hole Core/Web Interface/FTL version checks remain part of the daily application check.
- `Check Now` continues to perform the complete Pi-hole application check immediately.
- HTTP(S) URL now uses the same stronger field-heading hierarchy as Disk Usage Thresholds.
- Pi-hole and Minecraft selector descriptions now describe both runtime/health and update checking.

## v0.16.12 — 01-09-2026 — Pi-hole DNS Health

- Pi-hole application checks now perform a real DNS query against the local Pi-hole resolver on `127.0.0.1:53`.
- The DNS probe uses a short timeout and retry and requires a valid `NOERROR` response with at least one answer record.
- Pi-hole details now show `DNS — Responding` alongside Core, Web Interface and FTL update status.
- A failed DNS probe marks the Pi-hole application check Critical/failed even when the web interface or version checks still work.
- No extra packages or sudo permissions are required; the DNS probe runs with Python already present on managed hosts.
- Existing Pi-hole update detection and update execution are unchanged.

## v0.16.12 — 01-09-2026 — Disabled Check Status Calculation

### Fixed
- Disabled checks are now fully excluded from the aggregate System Check status calculation.
- A server with Ping disabled now reports OK when all remaining enabled checks are healthy.
- Unknown is now reserved for an enabled check without a valid current result, or for a server with no active checks at all.
- No changes to check scheduling, History, update execution, or layout.

## v0.16.12 — 01-09-2026 — System Checks UI and Ping Corrections

- Fixed a malformed CSS payload in v0.16.8 that caused the intended Action-column and mobile-width fixes to be ignored by the browser.
- Status and Action controls now align consistently, including rows with available updates.
- Mobile System Check detail cards now fill the available width while preserving Checks → Updates → Application → History order.
- Disabled Ping checks are no longer shown on the System Checks overview.
- Disabling the final remaining health check no longer silently restores Ping.
- Confirmed the 10-minute scheduler already skips disabled health checks.
- Preserved the transient green success notification after successful System Upgrade.
- No changes to upgrade execution, History data, or the application updater.

## v0.16.12 — 01-09-2026 — System Checks UI Corrections

- Fixed horizontal and vertical alignment of Status and Action controls in the six-column System Checks overview.
- Successful System Upgrade feedback now uses the standard green success notification banner.
- Successful Reboot and Minecraft upgrade feedback uses the same success treatment for consistency.
- Fixed mobile System Check detail cards shrinking to content width after the v0.16.7 semantic reordering.
- Mobile order remains Checks → Updates → Application → History, with every card using the full available width.
- No changes to upgrade execution, History data, scheduling or the application updater.

## v0.16.7 — 01-09-2026 — System Check Detail Polish

- Added a transient success message after a successful System Upgrade; it disappears on refresh.
- Grouped History into compact categories such as System Upgrades, Reboots, Minecraft, Pi-hole and Maintenance.
- Moved raw command output one level deeper under a collapsed Command output disclosure so successful upgrades are not visually dominated by harmless apt/debconf warnings.
- Renamed the configurable Online check to Ping and clarified that it uses ICMP; the top-level Online Status remains unchanged.
- Fixed Ping enable/disable persistence so disabling it remains disabled across navigation and refresh, and the overview no longer shows a disabled Ping check.
- Re-enabling Ping immediately runs that check, consistent with the other checks.
- Corrected the mobile System Check detail order to Checks → Updates → Application → History without changing the desktop layout.

## v0.16.6 — 31-08-2026 — Online and Disk Check Persistence

- Fixed Online and Disk selections being recreated or force-enabled when reopening System Check or Device detail pages.
- Disabling Online or Disk now persists across navigation and refresh, matching HTTP(S), APT, Pi-hole and Minecraft behaviour.
- Re-enabling Online or Disk still immediately runs only that newly enabled check.
- Existing results for other checks remain untouched.
- No changes to scheduling, Activity History, updater behaviour or UI layout.

## v0.16.6 — 31-08-2026 — Check State Preservation and Live Overview

### Changed
- Enabling any individual System or Application Check now immediately runs only that newly enabled check.
- Existing results for other enabled checks are preserved instead of being reset to Unknown during autosave.
- This behaviour applies to Online, Disk, HTTP(S), APT Package Updates, Pi-hole and Minecraft.
- Disabling a check removes only that check from the current status calculation; other current results remain intact.
- The System Checks overview now refreshes its status data silently every 60 seconds without reloading the page.
- Live refresh updates the summary and overview card only when their rendered content has actually changed.

### Preserved
- No changes to the 10-minute scheduled System Check cycle.
- No changes to History presentation or logging.
- No changes to update mechanisms or the application updater.
- No full host Check Now is triggered when a single check is enabled.

## v0.16.3 — 31-08-2026 — System/Application Check Organization

### Changed
- Split the System Check detail selectors into **System Checks** and **Application Checks** groups with a subtle divider.
- Kept the existing Online, Disk, HTTP(S), APT Package Updates, Pi-hole and Minecraft selectors unchanged.
- Moved the optional Minecraft server JAR path out of the main Checks card into a collapsed **Configuration** disclosure inside the Minecraft status card.
- Disabling Pi-hole or Minecraft now removes that application from scheduled application checks and, after autosave, refreshes the detail page so its current-status card disappears immediately.
- Re-enabling Pi-hole or Minecraft refreshes the page after autosave so the corresponding current-status card returns.
- Existing Activity History remains available even when an application check is disabled.

### Preserved
- Device History presentation is unchanged.
- No changes to System Check scheduling or check execution logic beyond the existing enable/disable behavior.
- No changes to Pi-hole or Minecraft update mechanisms.
- No changes to the application updater.

## v0.16.2 — 31-08-2026 — System Check Detail Layout

- Reworked the System Check detail page into two independently stacked desktop columns.
- Left column now contains Checks followed directly by History.
- Right column now contains Updates followed directly by the enabled application status card (Minecraft or Pi-hole).
- Removed Success / Failed / Info pills from Device History event rows; historical results remain available inside the expanded event details.
- Preserved the Device History event-count badge and existing disclosure behaviour.
- No changes to Activity History data, action logging, System Checks, application checks or updater behaviour.

## v0.16.1 — 31-08-2026 — Activity History Presentation

### Changed
- Moved Activity History into the right-hand column directly below Updates.
- Reworked history events into compact, neutral disclosure rows with chevrons.
- Removed colored Success/Failed status pills from historical events.
- Event result, summary and command output are shown only when an entry is expanded.
- Failure notices now point to the corresponding History entry instead of obsolete output panels.
- No changes to the Activity History data model or action logging behaviour.

## v0.16.0 — 31-08-2026 — Activity History

- Added a generic per-device Activity History for meaningful maintenance and update events.
- System Upgrade and Reboot actions now create history entries with result, summary and expandable command output.
- Minecraft and Pi-hole application updates now create history entries; Minecraft records the version transition when available.
- Maintenance Mode enabled/disabled changes are recorded.
- Firmware history is recorded only when the user explicitly marks a firmware update as completed; discovery/checks do not create history.
- Removed persistent Upgrade Output, Reboot Output and application Update Output from the current System Checks status cards; detailed output now belongs to the corresponding History event.
- Periodic successful checks are intentionally not recorded in History.

# Changelog

## v0.15.4 — 31-08-2026 — Update Progress Reliability

### Fixed
- Restored the simple application-update progress screen: version plus “This will take about a minute...” with no extra live status text during a normal update.
- Increased the per-request update-status polling timeout from 1.8 seconds to 5 seconds while keeping the 2-second retry cadence between completed polling attempts.
- Temporary polling failures remain non-fatal; the page keeps retrying until the verified target version is reported or the existing 5-minute overall timeout is reached.
- Successful updates still redirect automatically to Settings only after the running application reports the requested version and runtime verification succeeds.

## v0.15.4 — 31-08-2026 — Failed Update Log Visibility

- Failed application updates now expose the last 100 lines of the existing `data/update-staging/update.log` directly on the update failure screen.
- Added a compact **Show update log** disclosure that appears only when an update actually fails and log output is available.
- Update log output is rendered as plain text, preventing log content from being interpreted as HTML.
- The status endpoint reads only the fixed updater log path and never exposes arbitrary files.
- Successful update behaviour is unchanged: after runtime verification, the browser returns to Settings with the existing success message.
- No changes to the updater/rollback engine, data model, normal Settings UI or application features.

## v0.15.2 — 31-08-2026 — Robust Application Update Verification

- Reworked the application-update progress page so it independently polls a persistent update-status endpoint every 2 seconds.
- The UI no longer relies on the original install request surviving the application restart.
- Successful completion now requires three independent conditions: the update helper reported success, the running application reports the requested target version, and the application can access its database.
- Temporary connection failures during restart are treated as expected and polling continues automatically.
- The update page redirects automatically only after the new runtime is positively verified.
- Added a five-minute verification timeout with a clear recovery message instead of an endless spinner.
- Update status responses are explicitly non-cacheable.
- No changes to the updater/rollback engine, UI layout, application features or data model.

## v0.15.1 — 31-08-2026 — Application Update Maintenance

### Fixed
- Pi-hole and Minecraft updates initiated by Outlaw's Inventory now place the managed device in temporary Maintenance while the update is running.
- Recurring health, system and application checks suppress planned update downtime instead of producing false Critical states or notification e-mails.
- Existing user-selected Maintenance state is preserved and is never cleared by an application update.
- Previous health status is restored when temporary Maintenance ends, followed by a fresh application check that records the real post-update result.
- Temporary Maintenance is released in a `finally` path even when an application update fails.
- Health execution re-checks the current Maintenance flag to close the race where a scheduler row was fetched immediately before an update started.

## v0.15.0 — 31-08-2026 — Baseline Cleanup

### Changed
- Established v0.15.0 as the minimum backup/restore baseline; v0.14.38 is accepted only as the one-time update source into v0.15.0.
- Consolidated the current database structure into canonical table definitions for fresh installations.
- Removed historical schema migration ladders that are no longer needed by either active installation.
- Removed abandoned `sa-outlaws-inventory` and legacy System Checks profile migration/cleanup paths.
- Removed obsolete update compatibility routes, aliases and updater exceptions.
- Updater persistent-data validation now applies uniformly to all protected table row counts.

### Preserved
- No UI, layout, text, field, System Checks, scheduler, notification, backup, updater or application behaviour changes.
- Existing v0.14.38 databases are used in place without rewriting current data.
- Backups older than v0.15.0 are intentionally unsupported for restore.
- Updater rollback and retention remain unchanged: two full updater backups; application backup retention remains ten.

## v0.14.38 — 30-08-2026 — Update Backup Retention

### Fixed
- Prevented timestamped updater backups in `/var/backups/outlaws-inventory` from accumulating indefinitely.
- After a fully successful update, only the two newest full timestamped update backups are retained.
- `rollback` and `rollback-history` remain untouched.
- Cleanup only accepts the exact `YYYYMMDD-HHMMSS` backup directory format and ignores symlinks and unrelated directories.
- Backup cleanup failures are reported as warnings without turning an already healthy update into a failed update.

## v0.14.37 — 30-08-2026 — Version Comparison Cleanup

- Removed obsolete compact-version compatibility from the application update checker.
- Application releases are now compared strictly as numeric `major.minor.patch` versions.
- Added regression coverage for older, equal and newer v0.14.x releases and normal cross-minor ordering.
- No functional changes to System Checks, Minecraft integration or the user interface.

## v0.14.37 — 30-08-2026 — Minecraft Status Presentation Refinement

- Empty Application cells on the System Checks overview are now left visually empty instead of showing a dash.
- Reworked the Minecraft status card into a compact three-column property, value and status layout.
- Service name, installed version and configured port are aligned in the middle column; Running, Up to date / Update available and Listening states align on the right.
- Removed the Minecraft Details disclosure and the routine Server JAR path from the normal status presentation.
- Confirmed and regression-tested that Minecraft upgrades retain exactly one `server.jar.outlaws-previous` rollback copy; a later upgrade replaces that single previous copy instead of accumulating backups.

## v0.14.35 — 30-08-2026 — System/Application Layout & Minecraft Health Scheduling

- Split the System Checks overview into dedicated System and Application columns while keeping check indicators on one line.
- Made Minecraft service and configured-port health part of the recurring System Checks health cycle.
- Kept the external Minecraft latest-release lookup in the daily application/update cycle.
- Kept manual Check Now / Check All as a complete refresh.
- Added a compact Minecraft detail presentation as the basis for further refinement.

## v0.14.34 — 30-08-2026 — System Checks Reconfigure & Update Status Fixes

- Fixed Minecraft update permission validation after Reconfigure System Checks.
- Split Reconfigure System Checks choices into Host checks and Application checks.
- Fixed v0.14.x application-version comparison incorrectly treating older GitHub releases as newer.
- Existing `outlaw` SSH profiles are normalized to the canonical `System Checks` profile name when safe.
- Installer/updater no longer emit the confusing `usermod: no changes` message when the service account is already correct.
- Installer/updater now identify the Outlaw's Inventory version being installed or updated.

## v0.14.33 — 30-08-2026 — Minecraft Port Health & Safe Upgrade

- Minecraft System Checks now read `server-port` from `server.properties` and verify that the configured TCP port is actually accepting connections.
- Minecraft Details now show the configured port and `Listening` / `Not listening` state.
- A running Minecraft service with a closed configured port is reported as Critical instead of OK.
- Added **Upgrade Minecraft** when a newer official Java Edition server release is available.
- The managed updater stops the Minecraft service, downloads the latest official Mojang `server.jar`, verifies its SHA-1 and embedded version, replaces the JAR atomically, restarts the service, and waits for the configured port.
- If the new JAR does not start successfully, the previous JAR is restored automatically.
- Reconfigure System Checks can provision the narrowly scoped Minecraft update wrapper and permission on managed hosts.

## v0.14.33 — 30-08-2026 — Minecraft Runtime Health
- Minecraft now checks both server runtime state and installed/latest release versions.
- systemd-managed Minecraft instances are reported as Running, Stopped, Failed/crash-looping or Unknown.
- Repeated rapid systemd restarts are treated as a failed Minecraft runtime instead of a healthy transient Java process.
- A stopped or failed Minecraft service makes the Minecraft check Critical; an available release while the service is running remains an Update/attention state.
- The System Checks overview keeps Minecraft to one compact word plus its status icon; the redundant `update` suffix was removed.
- Minecraft Details now shows service/runtime state, installed version, latest version and detected server JAR.

## v0.14.31 — 30-08-2026 — Robust Minecraft Server JAR Detection
- Minecraft System Checks no longer depend solely on a currently running Java process.
- Automatic detection now inspects matching systemd Minecraft services when the server is stopped or crash-looping.
- `WorkingDirectory` and `ExecStart` are used to resolve the configured server launcher.
- Readable launcher scripts are inspected for their `cd` directory and `java ... -jar ...` command.
- Added common `/home/*/minecraft/server.jar` fallback detection.
- The detected JAR is still read directly for `version.json`, so the installed version can be reported even when Java itself cannot start the server.
- Existing Pi-hole, APT, Disk and legacy-cleanup behaviour is unchanged.

## v0.14.30 — 30-08-2026 — Safe Legacy SSH Profile Cleanup Validation

- Fixes updater rollback when v0.14.29 intentionally removes an unreferenced legacy System Checks SSH profile.
- The updater now snapshots protected SSH profile IDs before migration instead of requiring the total SSH profile row count to remain unchanged.
- Only unreferenced `sa-outlaws-inventory` / legacy System Checks profiles are allowed to disappear during migration.
- Existing or referenced SSH profiles remain protected and cause the update to fail if unexpectedly removed.
- Adds a database foreign-key integrity check after the update.
- Retains the Minecraft application check and legacy cleanup introduced in v0.14.29.

## v0.14.29 — 30-08-2026 — Minecraft Application Checks and Legacy Cleanup
- Added Minecraft Java server application update checks to System Checks.
- Detects the installed server version from `version.json` inside the running server JAR; the JAR path is auto-detected from the Java process with an optional manual override.
- Compares against Mojang's official current Java release metadata.
- Minecraft appears as a single Software Update when a newer release is available.
- Removes only unreferenced `sa-outlaws-inventory` / legacy System Checks SSH profiles; referenced profiles are preserved.
- Keeps the `outlaw` managed-host runtime model introduced in v0.14.27/0.14.28.

## v0.14.28 — 30-08-2026 — System Checks Profile Collision Fix

- Fixed an Internal Server Error when opening Configure/Reconfigure System Checks on installations that already contained a `System Checks` SSH profile from the abandoned `sa-outlaws-inventory` path.
- Existing working `outlaw` SSH profiles, including the legacy `Homelab` profile, are reused instead of creating a duplicate profile.
- If only a stale `System Checks` profile exists, it is preserved under a legacy name so its existing references remain intact, after which the canonical `outlaw` System Checks profile can be created safely.
- No managed-host runtime profile is switched merely by opening the Configure/Reconfigure page.
- Pi-hole integration and the v0.14.27 `outlaw` runtime model remain unchanged.

## v0.14.27 — 30-08-2026 — System Checks Runtime Recovery and Pi-hole Integration

- Restores the proven managed-host runtime identity to the existing `outlaw` account; the local application service remains `outlaws-inventory`.
- Configure/Reconfigure now treats the supplied administrator or root credentials as bootstrap-only and provisions the dedicated System Checks SSH key onto `outlaw`.
- If `outlaw` does not yet exist, Configure System Checks creates it and prepares it for key-based runtime access.
- Removes `sa-outlaws-inventory` from active System Checks provisioning; existing Linux accounts with that name are intentionally not deleted by the updater and can be cleaned up after validation.
- A failed Configure/Reconfigure no longer replaces a device's previously working managed SSH profile or check bindings.
- Pi-hole System Checks use the same `outlaw` runtime identity and receive only the required `pihole -up --check-only` and `pihole -up` sudo permissions when Pi-hole is enabled.
- Pi-hole Core/Web/FTL update detection, one-update dashboard counting and manual update output from v0.14.23 remain integrated.
- Documentation and setup copy now reflect the `outlaw` managed-host runtime account.

## v0.14.26 — 30-08-2026 — Managed Host Reconfigure Recovery

### Reconfigure System Checks
- Rebased the managed SSH account/key provisioning path on the proven v0.14.22 implementation instead of continuing the v0.14.24/v0.14.25 refactor.
- Reconfigure safely repairs the dedicated `sa-outlaws-inventory` SSH directory, `authorized_keys` ownership/mode and missing Outlaw's Inventory public key without duplicating key entries.
- Existing correct configuration is retained where practical; required packages are installed only when missing.
- Locale and timezone are changed only when necessary and remain optional warnings rather than blockers for System Checks setup.

### Sudo permissions
- Existing `/etc/sudoers.d/outlaws-inventory` content is read and preserved.
- Only missing fixed Outlaw's Inventory permissions are appended, including Pi-hole permissions when the Pi-hole check is selected.
- The candidate sudoers file is validated with `visudo -cf` before it can replace the active fragment.
- An unchanged sudoers fragment is not rewritten.
- No changes are made to `/etc/sudoers` or to other files in `/etc/sudoers.d/`.

### Validation and robustness
- Reconfigure validates the real managed SSH key login after configuration.
- APT availability, APT update/upgrade, kernel upgrade and reboot permissions are checked with the dedicated managed account.
- When Pi-hole is enabled, both the fixed check-only and update permissions are validated as well.
- Pi-hole remains selectable on the Reconfigure System Checks page and is rechecked after a successful reconfiguration.
- Added regression coverage for key deduplication, sudoers merge behavior, optional host settings, package idempotency and the complete managed-permission validation set.

### Scope
- Recovery/hardening release for the Reconfigure regressions in v0.14.24-v0.14.25.
- Application Update Checks and the v0.14.23 Dashboard/System Checks UI remain unchanged.

## v0.14.25 — 30-08-2026 — Reconfigure Regression Fix

### Reconfigure System Checks
- Fixed the service-account SSH directory creation regression introduced in v0.14.24: owner and group are now passed separately to `install`.
- Added **Pi-hole** to the Checks selection on the Reconfigure System Checks page.
- Existing System Check selections are reflected when reconfiguring instead of being blindly reselected.
- Pi-hole sudo permissions are provisioned only when the Pi-hole check is selected.
- Successful reconfiguration immediately re-runs an enabled Pi-hole check.

### Idempotency
- Existing correctly configured health and APT check records are left unchanged instead of having their status reset during reconfiguration.
- Existing Pi-hole check records are reused and are not duplicated or reset when already correct.
- Repeated reconfiguration remains safe: managed SSH keys and sudoers files are compared before being changed.

### Scope
- Targeted regression fix for v0.14.24 and the Pi-hole application check introduced in v0.14.23.
- No Dashboard, Firmware, Inventory, authentication, notification or scheduler redesign.

## v0.14.24 — 29-08-2026 — Idempotent System Check Reconfiguration

### System Checks setup
- Made **Reconfigure System Checks** state-based and idempotent: existing correct host configuration is left unchanged.
- Required packages are installed only when missing; package metadata is refreshed only when an install is actually needed.
- The managed service account, SSH directory, authorized key, kernel-upgrade wrapper and sudoers policy are created or corrected only when their current state differs.
- Repeated reconfiguration does not add duplicate SSH keys or sudoers entries.
- Temporary bootstrap SSH configuration is removed and SSH reloaded only when that temporary file actually exists.

### Optional host configuration
- Locale and timezone are now checked before any change is attempted.
- Replaced the container-sensitive `timedatectl set-timezone` setup path with direct Debian timezone-file configuration when a change is required.
- Locale/timezone failures are treated as warnings and can no longer abort the essential System Checks reconfiguration.

### Pi-hole
- Pi-hole check and update sudo permissions are installed through the same idempotent managed-host policy.
- When the Pi-hole check is enabled, reconfiguration now explicitly validates both the fixed `pihole -up --check-only` and `pihole -up` permissions before reporting success.

### Scope
- Bugfix/hardening release for v0.14.23.
- No Dashboard, Firmware, Inventory, authentication, notification, scheduler or database model changes.

## v0.14.23 — 29-08-2026 — Application Update Checks

### System Checks
- Added application-specific update checks as part of System Checks, starting with Pi-hole.
- Pi-hole can be enabled per managed server without separate application configuration.
- Pi-hole checks use the existing managed SSH profile and run `pihole -up --check-only` through a fixed sudo permission.
- System Checks now show compact `Online`, `Disk`, `HTTP(S)` and application names such as `Pi-hole`.
- Pi-hole Core, Web Interface and FTL are shown separately on the server detail page.
- An available Pi-hole update can be installed with **Update Pi-hole**; output is retained and the application is checked again automatically afterwards.

### Dashboard
- Renamed **System Updates** to **Software Updates**.
- Software Updates combines available APT packages with managed application updates.
- Renamed **System Update Action Items** to **Software Update Action Items** and added Pi-hole update entries.

### Scheduling & notifications
- Daily checks now run System Updates, managed Application Updates, Outlaw's Inventory release checks and Firmware checks in sequence.
- Pi-hole update availability and check failures participate in the existing update notification flow.

### Security
- Pi-hole remote execution is restricted to the fixed `pihole -up --check-only` and `pihole -up` commands.
- Existing managed Pi-hole hosts may require one **Reconfigure System Checks** run to add these exact sudo permissions.
- No generic or user-supplied remote command execution was added.

## v0.14.22 — 29-08-2026 — Notification Server Disclosure

### Notifications
- Moved the rarely changed SMTP configuration into an E-mail server disclosure inside Notifications.
- Completed SMTP configurations are collapsed by default; incomplete configurations remain open for setup.
- Kept the existing two equal-width SMTP field columns and Application URL spanning both columns.
- Save notification settings and Send test e-mail remain with the SMTP configuration.

### Scope
- Presentation-only Settings refinement.
- No notification delivery behavior, database, authentication, Firmware, System Checks, scheduler, updater or backup changes.

## v0.14.21 — 29-08-2026 — Settings Corrections

### Account
- Fixed Active Sessions and Trusted Devices disclosure headers so their collapsed height matches the normal Settings accordion height.
- Kept the expanded session and trusted-device content and behavior unchanged.

### Notifications
- Changed the SMTP configuration fields to two equal-width columns.
- Kept Application URL spanning both columns.

### Scope
- Presentation-only correction.
- No Dashboard, authentication/session behavior, notification behavior, database, Firmware, System Checks, scheduler, updater or backup changes.

## v0.14.20 — 29-08-2026 — Settings Layout Polish

### Dashboard
- Reduced Dashboard KPI number sizing slightly so status and card headings remain visually balanced.

### Account
- Simplified the Account layout to reduce nested card borders and make profile, general settings and security read as one coherent section.
- Kept all account, password, MFA, session and trusted-device functionality unchanged.

### Notifications
- Reworked Notifications into a compact left-aligned form instead of stretching fields across the full Settings width.
- Grouped notification choices and SMTP configuration more clearly.
- Kept the Application URL full-width within the compact form.
- Placed Save and Send test e-mail actions together as primary and secondary actions.

### Scope
- Presentation-only refinement.
- No database migration, notification behavior, Firmware, System Checks, scheduler, updater or backup changes.

## v0.14.19 — 29-08-2026 — Permanent Interface Icons

### Interface
- Removed the Icons On/Off preference; the approved restrained icon set is now a permanent part of the interface.
- Removed the now-empty Interface section from Settings.
- Aligned Settings icons with the first title line instead of vertically centering them across title and description.
- Updated the Personal description to “Account and notifications.”

### Cleanup
- Removed remaining active Appearance/theme preference references from templates, first-run setup paths, runtime settings and current roadmap documentation.
- Kept historical changelog entries intact as release history.

### Scope
- Interface cleanup only; no database migration. Existing legacy appearance/theme/icon settings are harmless and ignored.
- No Firmware, System Checks, scheduler, updater or backup behavior changes.

## v0.14.18 — 29-08-2026 — Single Interface Cleanup

### Interface
- Removed the Light theme and theme selector; Outlaw's Inventory now has one maintained Classic interface.
- Removed theme selection from first-run setup and stopped persisting theme changes. Existing legacy theme settings are ignored.
- Renamed the Settings Appearance section to Interface; the optional Icons On/Off preference remains.
- Removed the stray `OI` branding artifact left by the experimental theme work.
- Slightly increased the Outlaw's Inventory sidebar brand and tagline for clearer product identity.
- Kept the approved Classic navigation, Dashboard and Settings icon treatment.

### Cleanup
- Removed active Light-theme CSS and remaining runtime theme-selection paths.
- Added regression coverage so alternate theme selectors and the stray branding mark do not return.

### Scope
- Presentation and setup cleanup only.
- No database migration; legacy theme rows are harmless and ignored.
- No Firmware, System Checks, scheduler, updater or backup behavior changes.

## v0.14.18 — 29-08-2026 — Classic UI Refinement & Theme Cleanup

### Classic UI
- Increased primary navigation text and icon sizing for improved readability.
- Rebuilt Settings summary icon alignment as a stable horizontal icon-and-copy layout.
- Increased Settings heading and supporting-text sizes while preserving existing card geometry.
- Refined Dashboard KPI typography so icons support, rather than dominate, their labels.
- Increased Dashboard secondary/action text readability without changing dashboard structure.
- Normalized table body typography so primary Name values and other columns use the same font size; emphasis now comes from font weight.
- Increased selected secondary text and control typography for consistency across the application.

### Theme Cleanup
- Removed the experimental Transformers and Retro Green themes and their dedicated visual assets.
- Appearance now retains Classic, Light and the optional Icons On/Off preference.
- Removed theme-specific template branches and presentation code.

### Scope
- Presentation cleanup only.
- No database migration or backup format changes.
- No Firmware, System Checks, scheduler or updater behavior changes.

## v0.14.16 — 29-08-2026 — Transformers Full Visual Rebuild

### Transformers
- Rebuilt the Transformers theme from the approved visual mockup instead of layering small CSS changes over Classic.
- Added dedicated local visual assets derived from the approved mockup: custom Outlaw sci-fi emblem and truck line-art.
- Reworked shell proportions, sidebar, command bar, typography, technical grid background, angular metallic panels, navigation, status hero, KPI cards, action cards, tables, controls and Settings presentation.
- Preserved the existing Dashboard information architecture and application functionality; no theme-only content is added.
- Removed Retro Green from the selectable themes for now so only a fully developed alternate theme ships.

### Classic
- Classic and its approved icon treatment remain unchanged.

### Scope
- Presentation and Appearance settings only.
- No database migration, backup format, Firmware, System Checks, scheduler or updater logic changes.

## v0.14.15 — 29-08-2026 — Theme Rebuild & Settings Icon Alignment

### Classic
- Fixed Settings accordion icon alignment: icons now sit beside section titles and descriptions instead of floating above them.
- Sidebar and Dashboard icon treatment from v0.14.14 retained unchanged.
- Classic with Icons Off remains visually unchanged.

### Transformers
- Rebuilt as a visual skin over the existing application layout; no Dashboard content is added, removed or reordered.
- Added dark graphite/black technical background, angular panel treatment, metallic display headings and purple accent lines.
- Added a custom Outlaw sci-fi emblem treatment, stronger navigation styling and distinct KPI icon colors.
- Removed the v0.14.14 experimental Recent Devices blocks and placeholder graphic.

### Retro Green
- Rebuilt as a monochrome retro-PC/CRT visual skin over the existing application layout.
- Added green phosphor typography, subtle scanlines/grid texture, square terminal-style panels and controls, and a retro computer emblem treatment.
- Removed the v0.14.14 experimental Recent Devices blocks.

### Scope
- Appearance/theme presentation only.
- No database migration or backup format changes.
- No Firmware, System Checks, scheduler or updater behavior changes.

## v0.14.15 — 29-08-2026 — Classic Icon Refinement & Visual Themes

### Classic
- Removed Inventory category icons.
- Increased primary navigation icon size and visual weight.
- Corrected Settings icon alignment so icons sit beside section titles instead of above them.
- Improved Dashboard KPI icon size, weight and spacing.
- Classic with Icons Off remains visually unchanged.

### Themes
- Added optional Transformers theme based on the approved dark sci-fi mockup.
- Added optional Retro Green theme with a monochrome green CRT/PC aesthetic.
- Theme styling is isolated from Classic.
- Added theme-specific navigation, dashboard, cards, controls, tables and icon treatments.
- Added a theme-only Recent Devices dashboard panel for the two retro themes.

### Scope
- Presentation and Appearance settings only.
- No database migration or backup format changes.
- No Firmware, System Checks, scheduler or updater behavior changes.

## v0.14.13 — 28-08-2026 — Firmware Release Dates

### Firmware Providers

- Added the official release date for Arturia MiniFuse 2 firmware 1.5.0.212: 2024-10-08.
- Added the official release date for Arturia MiniLab Mk II firmware 1.1.2.1689: 2021-12-30.
- Added the official release date for Creality Ender-3 V3 KE firmware 1.1.0.17: 2025-08-27.
- Added the official release date for GL.iNet GL-MT3000/Beryl AX firmware 4.8.1: 2025-08-19.
- Existing provider lookup, fallback and version-selection behavior is unchanged.

### Scope

- Firmware metadata only.
- No UI, UX, layout, flow, database, backup, scheduler, System Checks or updater changes.

## v0.14.12 — 25-08-2026 — Optional Interface Icons

### Appearance

- Added an optional `Icons` setting under Appearance; it defaults to Off.
- Icons Off preserves the v0.14.11 visual baseline.
- Icons On adds a restrained local SVG icon layer to primary navigation, key Settings sections, Dashboard summary cards and known Inventory categories.
- Custom or unknown categories use one neutral generic package icon.
- No external icon font, CDN or runtime dependency is used.

### Visual Stability

- Existing typography, font sizes, spacing, card geometry, table geometry, button dimensions, colors, borders and application flows are unchanged.
- Existing Save, Back, Delete and other routine action buttons were intentionally left unchanged.
- Native category selectors remain native controls; no custom selector behavior was introduced.

### Scope

- Presentation-only optional icon layer plus its stored Appearance preference.
- No database migration.
- No backup format changes.
- No System Checks, Firmware, scheduler or updater behavior changes.

## v0.14.11 — 13-08-2026 — System Checks Hardening

### Maintenance Mode

- Maintenance Mode now blocks both frequent System Checks and scheduled system-update checks.
- System-update notifications use Maintenance as an independent safety gate, preventing stale failed checks from generating mail.
- Servers in Maintenance are not pinged, checked over HTTP(S), queried over SSH or checked for APT package updates.

### Online Status

- Online Status keeps the existing check method and TCP fallback.
- Added one additional single-ping attempt before the existing TCP fallback to absorb an occasional lost ICMP packet.
- When Online Status is Offline, SSH-dependent Disk Usage and system-update checks are skipped.
- Explicit HTTP(S) checks remain independent of ICMP failure and can still determine service reachability.
- No check thresholds, intervals or user-facing flow were changed.

### Legacy UI Cleanup

- Historical `/health` and `/updates` GET pages now redirect to the supported `/system-checks` interface.
- Removed the four obsolete Health/Updates HTML templates that are no longer used.
- Internal `health` and `updates` implementation names and storage remain unchanged to avoid unnecessary migration risk.
- Notification emails now present both internal health and system-update events under the user-facing category `System Checks`.
- Removed the remaining active `Home Lab` wording from runtime source comments.

### Scope

- Internal hardening and safe legacy UI cleanup only.
- Existing System Checks UI/UX is unchanged.
- Existing scheduler intervals/times are unchanged.
- No database migration.
- No backup format changes.
- No Firmware behavior changes.

## v0.14.10 — 13-08-2026 — Settings Default Collapse Fix

### Settings

- Fixed Application Version opening automatically whenever an update is available or the installed build is newer than the latest known GitHub release.
- Opening Settings normally now leaves Application Version collapsed.
- Application Version only opens automatically when explicitly requested with `update_open=1`.
- Update Available styling and status text remain unchanged.

### Scope

- Settings UI behavior only.
- No database migration.
- No backup format changes.
- No System Checks changes.
- No Firmware behavior changes.

## v0.14.9 — 12-08-2026 — Settings Performance and Maintenance Color

### Settings Performance

- Added a persistent backup inspection cache so Settings no longer re-reads and SHA256-validates every backup on every page load.
- Cache validity is tied to backup filename, size, modification time and change time.
- Missing cache entries are warmed in a background thread after application startup.
- The cache stores only backup inspection metadata and is not included in backups.
- Restore remains fully safe: every restore forces a fresh complete archive/checksum validation and never trusts cached inspection data.
- Backup compatibility (`Restorable`, `Unsupported`, `Invalid`) remains calculated against the currently running application version.

### Dashboard

- The System Checks KPI now uses the blue Maintenance color when one or more systems are in Maintenance and no higher-priority System Check condition is present.
- Global Current Status remains green when Maintenance is the only non-OK state.

### Scope

- Settings backup-list performance and Maintenance KPI color only.
- No database migration.
- No backup archive format changes.
- No Firmware behavior changes.

## v0.14.7 — 12-08-2026 — Maintenance Mode Presentation Fix

### System Checks

- Removed raw SSH transport errors such as `Unable to connect to port 22` from the System Checks overview.
- Offline status is now presented as the host state without exposing a low-level connection exception underneath it.
- System Check Details suppresses raw SSH transport errors when the host is offline.
- Genuine configuration/authentication problems on an otherwise reachable host remain actionable through the existing configuration warning.
- Update/package details remain available when updates are actually present.

### Maintenance Mode

- Maintenance Mode now acts as a presentation override for current System Checks.
- Raw connection errors are hidden while Maintenance Mode is active.
- The Updates card no longer becomes red because of a stale failed SSH check while the server is in Maintenance.
- Stale Upgrade/Reboot actions are not presented as current actions while Maintenance Mode is active.
- Historical check state remains stored; Maintenance changes current presentation, not history.

### Dashboard

- Maintenance-only servers no longer cause `Critical attention required`.
- If everything else is healthy, Current Status remains green with `Everything looks fine`.
- The System Checks tile remains blue when one or more servers are in Maintenance.
- Maintenance servers are excluded from current System Update failure counts and System Update Action Items.
- Real Attention/Critical conditions on non-maintenance systems still take priority and keep the Dashboard orange/red as appropriate.

### Scope

- System Checks, Maintenance Mode and Dashboard presentation only.
- No database migration.
- No backup format changes.
- No Firmware behavior changes.

## v0.14.6 — 12-08-2026 — Backup Hardening and Compatibility Clarity

### Backup History

- Backup files are now always downloadable as long as the file physically exists.
- Restore availability is now independent from download availability.
- Backup history distinguishes `Restorable`, `Unsupported` and `Invalid`.
- `Restorable` is shown in green, `Unsupported` in amber and `Invalid` in red.
- Structurally valid pre-v0.14 backups are shown as `Unsupported` instead of incorrectly appearing simply `Invalid`.
- Backups created by a newer Outlaw's Inventory version are also marked `Unsupported` and cannot be restored until the installation is updated.

### Backup Filenames

- New backup filenames include the creating Outlaw's Inventory version.
- Example: `outlaws-inventory-manual-backup-v0.14.6-20260812-204500.oi-backup`.
- Restore compatibility continues to be determined from the validated internal manifest, never from the filename.

### Retention

- Renamed `Keep latest` to `Keep automatic backups`.
- Automatic retention now explicitly selects only backups whose manifest kind is `automatic`.
- Manual backups are never removed by automatic retention.
- Pre-restore recovery backups are never removed by automatic retention.
- An unreadable/uncertain backup is never automatically deleted merely because its filename looks automatic.

### Updater Hardening

- Update preparation now removes stale `result.json` before creating new update state.
- This prevents an old status file owned by a historical Linux user from blocking a GUI update after migration to the dedicated `outlaws-inventory` service account.

### Scope

- Backup history, retention, filename clarity and updater staging hardening.
- No Inventory feature changes.
- No Firmware behavior changes.
- No backup archive format change.
- Existing backup files remain supported according to the v0.14 baseline rules.

## v0.14.5 — 12-08-2026 — v0.14 Baseline Cleanup and Setup Restore Polish

### Supported Baseline

- Established v0.14.0 as the supported baseline for in-place upgrades.
- Established v0.14.0 as the supported baseline for full backup restore.
- Removed the active pre-v0.14 upgrade-service-user fallback.
- Removed obsolete pre-v0.14 one-time schema/data conversion paths that cannot occur on a supported v0.14.x installation.
- Updated current table creation for SSH profiles and notification state to create the current schema directly.

### Setup Restore

- Split backup restore and current System Checks refresh into two visible verified phases.
- A backup is fully validated and restored before System Checks can start.
- Successful restore now shows `Backup restored successfully` with a clear success indicator.
- The wizard then displays `Refreshing System Checks…`.
- After refresh, the wizard shows `System Checks completed` and enables Continue to login.
- A restore validation/restore failure never starts System Checks.
- A System Checks refresh problem after a successful restore is shown separately and never changes the successful restore result.
- Setup-time System Checks refresh remains notification-free.

### Tests and Documentation

- Renamed pre-v0.14 version-numbered regression test files to functional current names.
- Added explicit v0.14 baseline cleanup contracts.
- Added regression coverage for the staged Setup restore flow.
- Rewrote README and current operational documentation for the v0.14 architecture and recovery workflow.
- Removed historical v0.13 release labels from current UI/CSS documentation comments.

### Scope

- Technical baseline cleanup, current documentation/tests and Setup restore UX.
- No Inventory feature changes.
- No Firmware behavior changes.
- No backup archive format change.
- No user-data deletion.

## v0.14.4 — 12-08-2026 — Refresh Status After Backup Restore

### Setup and Restore

- A successful full backup restore during Setup now automatically refreshes current System Checks before the restore flow completes.
- The refresh uses the same Health and System Update check execution logic as the existing `Check All` action.
- Restored last-known status values are therefore replaced with current results before the first normal login.
- This prevents hosts from initially appearing with stale backup-time update or health states.
- A rebuilt local server can still correctly appear as Attention/Critical after restore when its managed host-side System Checks configuration needs reconfiguration.
- Notifications are intentionally suppressed during this post-restore refresh to avoid sending setup/recovery-time notification mail.

### Check All

- Consolidated the System Checks refresh into a shared execution path used by both the normal `Check All` action and Setup restore.
- Background/setup refresh resolves managed devices through persisted owner IDs rather than requiring an authenticated browser session.
- If an individual Health check raises an unexpected execution error during the refresh, its restored status is changed to Unknown instead of leaving stale backup-time status visible.

### Setup UI

- Restore progress now indicates that current system status is being refreshed after the data restore.
- Restore completion confirms that current System Checks were refreshed.

### Scope

- Setup backup-restore status freshness and Check All execution reuse only.
- No Inventory data model changes.
- No Firmware changes.
- No backup format changes.
- No database migration.

## v0.14.3 — 12-08-2026 — System Checks Reconfiguration Validation Fix

### Fixed

- Fixed `Reconfigure System Checks` failing after the remote host had already been configured correctly.
- Reconfiguration now always uses the dedicated `System Checks` SSH profile and the managed `sa-outlaws-inventory` account.
- Historical/general SSH profiles restored from older backups are no longer reused for managed-host validation.
- This fixes the case where the key was correctly installed for `sa-outlaws-inventory` but validation attempted to log in with another profile username such as `outlaw`.
- Managed-host readiness is now based on fresh SSH and permission checks instead of an old persisted `failed` update-check status.
- Reconfiguration validates all required live capabilities:
  - SSH key login
  - APT availability
  - APT update permission
  - APT upgrade permission
  - Kernel upgrade permission
  - Reboot permission

### UI

- Fixed missing visual separation in `Setup failedConfiguration...`.
- Failed setup now shows a clear `Setup failed` heading and separate message.
- Validation failures can show the individual validation steps and which one failed.
- Reconfigure wording remains visible after a failed POST instead of falling back to `System Check Setup`.
- The form heading now also says `Reconfigure System Checks` when used from an existing Device or System Check Details page.

### Scope

- System Checks reconfiguration/validation and related UI only.
- No Inventory data model changes.
- No Firmware changes.
- No updater changes.
- No backup format changes.
- No database migration.

## v0.14.2 — 12-08-2026 — Reconfigure System Checks

### System Checks

- Added `Reconfigure System Checks` for existing managed servers.
- Intended for hosts that were rebuilt, restored or replaced while the Inventory item and System Checks configuration remained.
- Authentication failures are now recognized as managed-host configuration issues instead of being presented only as generic Critical check failures.
- Device details now show `Attention` when managed SSH access needs reconfiguration.
- Added a clear explanation and Reconfigure action on the Device page.
- Added the same Reconfigure action to System Check Details.
- Reconfiguration uses the existing managed-host setup workflow and re-applies the managed account, authorized SSH key, required packages and controlled sudoers permissions.
- Reconfiguration is always an explicit administrator action and is never performed automatically.
- After successful reconfiguration, the user returns to the Device or System Check Details page that initiated the action.

### System Checks Overview

- Removed the loose raw `Authentication failed.` line beneath a host in the overview.
- Existing package-update expansion beneath the host name is unchanged.
- Non-configuration update errors can still be shown for diagnostics.

### Device Page

- Fixed missing vertical spacing above `Recent activity`.

### Scope

- Managed-host recovery/reconfiguration and small Device/System Checks UI polish.
- No Inventory data model, Firmware, updater, backup format or database migration changes.

## v0.14.1 — 12-08-2026 — Clean Installation and Recovery Hardening

### Fixed

- Fixed a clean-install startup crash caused by a leftover reference to the removed `migrated_ssh_paths` migration variable.
- A fresh database can now initialize without relying on historical migration state.

### Installer

- `install.sh` now verifies that the application actually becomes healthy before reporting `Installation complete`.
- Validation requires `/system/ready` to report `ready: true` and the exact release `APP_VERSION`.
- Also verifies that `outlaws-inventory.service` is actually active.
- On startup failure, the installer now prints service status and the latest journal entries, stops the restart loop and exits with an error.
- `install.sh` refuses to overwrite an existing installation and directs existing installations to `update.sh`.
- Preserved validation that the dedicated `outlaws-inventory` service account is non-interactive and can execute ICMP ping.
- Added `PYTHONDONTWRITEBYTECODE=1` to the service to prevent stale local Python bytecode.

### Restore and Permissions

- Runtime data permissions are normalized after startup and after full backup restore.
- Private SSH keys, secrets and the SQLite database receive restrictive file modes.
- Restoring a current `.oi-backup` on a clean server remains independent of the Linux user that created the backup.

### Update and Rollback

- Existing v0.13.24+ installations remain supported by `update.sh`.
- Updated systemd units also disable local Python bytecode generation.
- Rollback now clears stale Python bytecode and validates the exact target version through `/system/ready` before reporting success.

### Scope

- Installation, startup, restore, update and rollback reliability only.
- No Inventory, Firmware, System Checks, notification or database feature changes.

## v0.14.0 — 12-08-2026 — Dedicated Service Account and Notification Polish

### Local Service Account

- Outlaw's Inventory now runs under the dedicated local system account `outlaws-inventory`.
- The service account uses `/usr/sbin/nologin` and is independent of the human Linux administrator account.
- Fresh installs create a dedicated system group and service account automatically.
- Upgrades from the supported v0.13.x baseline automatically migrate systemd, application ownership and sudoers permissions from the historical local `outlaw` service identity.
- The human `outlaw` Linux account is never removed or modified.
- Self-update and rollback helpers now use the dedicated service account for persistent application-state ownership.
- Failed migration rollback restores the previous systemd unit, sudoers configuration, helper binaries, application code and original application ownership.

### System Checks / Ping

- Fresh installs and upgrades install `iputils-ping` and `libcap2-bin`.
- The installer verifies that the service account can execute an ICMP ping.
- If necessary it attempts to restore `cap_net_raw` on `/usr/bin/ping`.
- A clear installer warning is emitted if the host/container still blocks ICMP ping.

### Notifications

- Health alert emails no longer include raw ping/capability diagnostic text after the human-readable status.
- Example: `VM - AppServer 02: offline` instead of exposing internal `cap_net_raw` diagnostics.
- Fixed singular grammar: `1 item requires attention`.
- Plural remains `2 items require attention`, `3 items require attention`, etc.
- Plain-text notification wording now follows the same singular/plural rules.
- Health and system-update item links use the current `/system-checks` route.
- Application-update notification links remain unchanged and continue to target `Settings → Application Version`.

### Installation and Recovery

- Documented the distinction between the local `outlaws-inventory` service account and remote `sa-outlaws-inventory` managed-host account.
- Clean Debian + current installer + recent `.oi-backup` is the preferred server-recovery workflow.
- Supported upgrade/backup baseline remains v0.13.24.

## v0.13.24 — 12-08-2026 — UI Polish and Safer Device Deletion

### Dashboard

- Removed the grey/white Unknown border from the Firmware summary card.
- Firmware remains visually neutral when there are no firmware updates, even when some firmware checks are Unknown.
- The Firmware card only receives the Attention border when firmware updates are actually available.
- Changed `CURRENT STATUS` styling to normal title case: `Current Status`.
- Removed the forced uppercase transformation and wide letter spacing from that label.

### Settings

- Changed `PERSONAL`, `APPLICATION` and `ADMINISTRATION` to normal title case.
- Group headings now use the same visual scale and left alignment as the Settings rows beneath them.
- Open and closed Settings rows now keep the same title/subtitle font sizes.
- Opening a Settings panel no longer shifts the heading horizontally or changes its typography.
- Existing accordion behavior and all Settings content remain unchanged.

### Device Deletion

- Replaced the browser `confirm()` prompt with an Outlaw's Inventory confirmation dialog.
- The dialog explicitly states that device deletion is permanent and cannot be undone.
- Shows the name of the device that will be deleted.
- Requires confirmation via:
  `I understand that this device will be permanently deleted.`
- The red `Delete Device` button remains disabled until that confirmation checkbox is selected.
- Added a normal `Cancel` action, Escape-key handling and click-outside cancellation.
- The backend delete route is unchanged.

### Scope

- Dashboard and Settings visual polish plus Device deletion confirmation.
- No Inventory data model, Firmware, System Checks, updater or database logic changed.

## v0.13.23 — 12-08-2026 — Dashboard and Settings Simplification

### Dashboard

- Reduced the summary row from six KPI cards to four:
  - Inventory
  - Firmware
  - System Checks
  - System Updates
- Merged `Firmware OK` and `Firmware Updates` into one Firmware card.
- When firmware updates are available, the Firmware card changes to the attention state and shows the number of available updates together with the number already up to date.
- Removed the permanent Application Updates KPI card.
- Outlaw's Inventory application updates are now shown only when relevant, as a conditional update banner directly below Current Status.
- The update banner links to Settings → Application Version.
- Four cards remain four across on large screens, two-by-two on narrower desktop/tablet widths and one column on phones.

### Settings

- Preserved the existing single-column accordion behavior and all existing settings.
- Added visual hierarchy with three groups:
  - Personal
  - Application
  - Administration
- Closed setting panels are now more compact and flatter, reducing the visual effect of a long stack of identical cards.
- Open panels retain the existing full-width content and spacing.
- Opening one setting still closes the previously opened setting.
- No setting was removed or moved to another page.

### Scope

- Dashboard presentation and Settings presentation only.
- No updater, Inventory, Firmware, System Checks, authentication or database behavior changed.

## v0.13.22 — 12-08-2026 — Update Progress Recovery and Manual Rollback State

### Update Progress Screen

- Fixed the update overlay that could remain on `Updating Outlaw's Inventory` after the update had already completed successfully.
- Progress polling still uses `/settings/application-update/status` as the primary source.
- If that request is interrupted during the application restart, the page now checks `/system/ready`.
- When the running application reports the requested `APP_VERSION`, the progress page completes and returns to Settings automatically.
- Added request timeouts and a bounded three-minute fallback so the overlay can no longer spin indefinitely without feedback.

### Manual Updates and Revert

- Manual `sudo ./update.sh` now records the version that was actually installed immediately before the update.
- After the new version has passed file, runtime and persistent-data validation, that previous installation is published as the GUI rollback target.
- `Revert to ...` therefore points to the immediately previous installed version after a manual update as well as after a GUI update.
- Existing rollback state is archived before the new rollback snapshot is published.
- GUI self-updates keep using their existing rollback workflow; manual rollback bookkeeping is disabled when `update.sh` is running inside the self-updater to prevent duplicate snapshots.

### Scope

- Updater/progress/rollback bookkeeping only.
- No Inventory, Firmware or System Checks behavior changed.
- No database migration.

## v0.13.21 — 12-08-2026 — Definitive Runtime Version Verification

### Updater

- Fixed the stale Python bytecode edge case confirmed on a managed application host.
- Update installation now removes all application `__pycache__` directories and `.pyc` / `.pyo` files before the updated service starts.
- The rollback restore path also removes compiled Python bytecode before restarting the restored application.
- Post-update verification now checks the version reported by the running application at `/system/ready`, not only the version string stored in `app/main.py`.
- The update succeeds only when the running process reports the exact expected `APP_VERSION`.
- The GUI self-updater performs an additional independent `/system/ready` runtime-version check before publishing a success result.

### Why

A source file can be correctly replaced while an existing compiled Python cache still contains an older version. In the confirmed v0.13.20 incident, `app/main.py` contained the new version while the running Python process still reported the old version. v0.13.21 explicitly prevents and detects that state.

### Scope

- Updater hardening only.
- No Inventory, Firmware or System Checks behavior changed.
- No database schema migration.

## v0.13.20 — 11-08-2026 — Updater Version Verification

### Updater

- Fixed a case where `update.sh` could report success while a same-size application file remained on the previous version.
- Changed application-file synchronization to content-aware `rsync --checksum`.
- Manual `update.sh` now reads the expected APP_VERSION from the release source.
- Verifies `/opt/outlaws-inventory/app/main.py` immediately after copying files.
- Verifies the installed APP_VERSION again after the application restart.
- Any version mismatch now fails the update and triggers the existing restore path instead of printing `Updated`.

### GUI Self-Updater

- Added independent post-update verification of the installed `/opt/outlaws-inventory/app/main.py`.
- The self-updater may only publish `success` when installed APP_VERSION exactly matches the requested release.
- A mismatch is returned as `Version verification failed` instead of a false successful-update message.

### Scope

- No inventory, firmware or System Checks behavior changed.
- No database schema change.

## v0.13.19 — 11-08-2026 — Mobile System Checks Simplification

### Mobile System Checks

- Reworked the phone view to use the same proven generic mobile card renderer as Inventory and Firmware.
- Added a dedicated mobile source table containing exactly two columns:
  - Name
  - Status
- Removed Checks, Last Checked and Action from the mobile source entirely instead of hiding/re-enabling desktop cells through layered CSS.
- Status remains clickable and opens System Check Details.
- Removed the v0.13.16-v0.13.18 System Checks mobile override stack to prevent further CSS conflicts.
- Desktop and iPad continue to use the existing five-column System Checks table unchanged.

### Validation

- Added regression tests that assert the mobile source has only Name and Status.
- Added regression coverage that desktop remains five columns.
- Added regression coverage that Status links to the existing Details page.

### Scope

- Mobile markup/CSS architecture only.
- No System Checks logic, scheduler logic, update logic or status calculation changed.

## v0.13.18 — 11-08-2026 — Mobile System Checks Regression Fix

### Mobile System Checks

- Fixed the v0.13.17 regression that re-enabled hidden mobile columns.
- Phone overview is again limited to Name and Status only.
- Checks, Last Checked and Action remain hard-hidden on phones.
- Status stays clickable and opens System Check Details.
- Preserved the shared `mobile-card-table` behavior used by Inventory and Firmware.
- Kept Name and Status inside one clean card without overlap.
- Desktop and iPad layouts remain unchanged.

### Scope

- CSS-only regression fix plus version/documentation updates.
- No System Checks logic changed.
- No scheduler, update or status calculation changed.

## v0.13.17 — 11-08-2026 — Mobile System Checks Card Spacing Fix

### Mobile System Checks

- Reused the exact generic `mobile-card-table` renderer already used by Inventory and Firmware.
- Added explicit mobile labels for Name, Checks, Last Checked, Status and Action.
- Kept the phone overview limited to Name and Status.
- Fixed Name and Status so both remain fully inside the same device card.
- Increased internal padding and spacing between mobile device cards.
- Reduced the Status pill to fit cleanly inside the Status row.
- Desktop and iPad layouts are unchanged.

### Scope

- CSS/markup only.
- No System Checks logic, scheduler logic, update logic or status calculation changed.

## v0.13.16 — 11-08-2026 — Mobile System Checks Overview

### Mobile System Checks

- Reused the existing mobile-card-table pattern already used by Inventory and Firmware.
- System Checks now shows only Name and Status on phones.
- Checks, Last Checked and Action are hidden from the phone overview.
- Status remains clickable and opens the existing System Check Details page.
- Package update details and the separate update disclosure are hidden on phones; update state remains visible through Status.
- Removed the desktop minimum-width constraint on phones so the table no longer compresses and overlaps.
- Desktop and iPad layouts are unchanged.

### Scope

- No System Checks logic changed.
- No scheduler, update, device or status calculation changed.
- No desktop layout changes were made.

## v0.13.15 — 09-08-2026 — System Checks Desktop Layout Polish

### System Checks Overview

- Rebalanced the five desktop columns to 24% / 36% / 16% / 12% / 12%.
- Moved Last Checked and Status visually to the left.
- Kept Action on the right with more separation from Status.
- Reduced Status / Action control width slightly while preserving equal geometry.
- Added a minimum desktop table width and horizontal overflow safeguard.
- Smaller desktop browser windows now scroll the table instead of allowing Status / Action controls or text to overlap.
- Preserved the existing update disclosure below the device name unchanged.

### Scope

- No System Checks logic changed.
- No update, status, scheduler or device behavior changed.
- Mobile layout was deliberately not redesigned in this release; that work is reserved for v0.14.

## v0.13.14 — 09-08-2026 — UI Stabilization and Cross-Browser Polish

### System Checks Overview

- Removed the Address column.
- Removed the separate Updates column.
- Preserved the existing update disclosure below the host name exactly as the update entry point.
- Preserved the existing collapsed package-detail behavior.
- Rebalanced the table to five columns: Name, Checks, Last Checked, Status and Action.
- Normalized Status and Action controls to the same fixed height, line height and vertical alignment.
- Added final cross-browser geometry rules for Safari and Edge.
- Added extra width to Checks while keeping Last Checked readable.

### Review

- Reviewed System Checks links, wording and status/action structure.
- Reviewed Check All update execution against the current APT update executor.
- Reviewed legacy Health / Updates template references without changing or removing legacy functionality.
- No functional behavior was changed as part of the consistency review.

### Documentation

- Updated UI style guidance for the five-column System Checks overview.
- Documented the cross-browser Status / Action alignment rule.

## v0.13.13 — 08-08-2026 — System Checks Reliability Fixes

### System Checks

- Fixed Check All so APT package checks actually run.
- Check All now uses the same execute_update_check() path as an individual Check Now.
- APT failures during Check All are stored as failed results instead of being silently discarded.
- Kept System Check selector cards visually neutral; they configure checks and no longer inherit live warning colors.
- Improved Status and Action column alignment with fixed table geometry.
- Improved dark-theme visibility of Disk Usage percentage spinner controls.

### Device Page

- System Checks badge now reports configuration state only.
- Replaced Ready / Attention / Failed with:
  - Enabled
  - Not Configured
- Current System Check health no longer depends on legacy managed-host integration status.

### Application Version

- Added explicit handling for development/manual installations newer than the latest published GitHub release.
- When Installed > Latest Release, Status now shows `Newer Version Installed`.
- Check for updates now reports that the installed version is newer instead of incorrectly saying the older published version is the latest installed version.

### Documentation

- Updated System Checks and UI style documentation for configuration-state semantics and Check All reliability.

## v0.13.12 — 08-08-2026 — System Checks Overview Polish

### System Checks Overview

- Package update details are collapsed by default again.
- Removed the duplicate package-update summary from the expanded row.
- The server name now has one disclosure line such as `3 updates available`.
- Increased the disclosure arrow/text slightly for readability.
- Centered and aligned Status and Action controls consistently.

### System Check Details

- Upgrade Now now shows the same blocking upgrade overlay as the System Checks overview.
- Reboot uses the same operation-overlay pattern.
- The overlay keeps the page blocked while the server operation is running.

### Dashboard

- Replaced the old `health host(s)` wording with normal device wording.
- Singular and plural grammar are handled correctly.

### Documentation

- Updated System Checks and UI style documentation.

## v0.13.11 — 08-08-2026 — System Checks Interaction Polish

### System Checks Overview

- Increased the package-update summary size under server names.
- Package update details are expanded by default when updates are available.
- Kept the Updates column as a simple numeric count.

### System Check Details

- Removed the redundant Available value from the Updates block.
- Package updates are expanded by default.
- The Updates block turns orange while package updates are available.
- The overall Status block reflects Attention, Critical, Reboot Required and Maintenance with matching surface colors.
- Individual Ping, Disk Usage, HTTP(S) and APT Package Updates cards highlight the check that requires attention.
- Moved Check Now into the Checks block.
- Moved Upgrade Now / Reboot into the Updates block.
- Removed the Save button.
- Check settings, Maintenance Mode, Disk thresholds and HTTP(S) URL now autosave.
- Made Disk Usage thresholds more compact.
- Status values link to the relevant section without adopting hyperlink-style visuals.

### Device Page

- All four System Checks summary values link to System Check Details.
- Online Status now shows the actual current state instead of Configured.

### Account Menu

- Removed the small chevron next to the account name.

### Documentation

- Updated System Checks and UI style documentation for autosave, contextual actions and attention-state styling.

## v0.13.10 — 08-08-2026 — APT System Check Configuration

### System Checks

- Added APT Package Updates as a configurable System Check.
- APT Package Updates can now be enabled for an existing or restored managed server from System Check Details.
- Enabling APT Package Updates creates or re-enables the linked APT update check.
- The first APT check runs immediately after enabling it.
- Disabling APT Package Updates disables monitoring without deleting historical update information.
- Disabled APT checks no longer affect the combined server status.
- Added a direct Managed SSH setup link when APT monitoring cannot yet be enabled.
- Reworked the four check options into a compact 2 × 2 layout.

### Device Page

- Uptime now shows the actual formatted uptime value directly on the Device page.
- Removed the old "Available In Details" placeholder.

### Firmware

- Preserved the corrected Creality K1 Max Monochrome / CR4CU220812S11 firmware detection from v0.13.9.

### Documentation

- Updated System Checks documentation for APT Package Updates and restored-server behavior.

## v0.13.9 — 08-08-2026 — System Checks UI Refinement

### System Checks

- Restored the softer v0.9.x check-indicator colors.
- Reduced visual emphasis of Online Status, Disk Usage and HTTP(S) check icons.
- Changed the Updates column to show only the numeric update count.
- Moved the expandable package-update link below the server name, matching the old Updates page.
- Kept package details in a compact row below the main server row.
- Status now shows Attention when Disk Usage is in warning state and no package update is available.
- Status continues to show Update when package updates are available.
- Kept Upgrade Now as the explicit update action.

### System Check Details

- Reordered the top status information:
  - Online Status / Last Checked
  - Disk Usage / Updates Available
  - Uptime / Last Boot
- Moved Maintenance Mode below the regular check selectors.
- Added explanatory Maintenance Mode text.
- Maintenance Mode remains separate from Online Status, Disk Usage and HTTP(S).

### Documentation

- Updated System Checks documentation.
- Updated UI style guidance to preserve subdued check indicators in future releases.

## v0.13.8 — 08-08-2026 — System Checks UI Restoration

### System Checks

- Kept Health and Updates unified as System Checks.
- Rebuilt the System Checks overview using the proven v0.9.6 Health / Updates visual language.
- Restored compact fixed-height server rows.
- Restored the original-style check marks for Online Status, Disk Usage and HTTP(S).
- Restored the established status colors:
  - Green: OK
  - Orange: Update / Attention
  - Red: Critical
  - Purple: Reboot Required
  - Blue: Maintenance
- Package updates expand below the server row instead of enlarging the main row.
- Restored compact package typography and version presentation.
- Name links to the Inventory item.
- Checks and Status link to System Check Details.
- Changed the update action to Upgrade Now for a clearer distinction between status and action.
- Added a compact server summary above the table.
- Preserved Check All, Upgrade, Reboot, Maintenance, uptime and Last Boot functionality.

### System Check Details

- Rebuilt the detail view around the old Health / Updates form hierarchy.
- Kept one combined System Checks detail page.
- Added compact Status, Checks and Updates sections.
- Kept Uptime and Last Boot.
- Kept dynamic Disk Usage thresholds and HTTP(S) URL fields.
- Kept Upgrade, Reboot, Check Now and stored command output.

### Firmware

- Updated the K1 Max Monochrome / CR4CU220812S11 known official fallback to firmware 1.3.5.22 (2026-07-10).
- Kept the Monochrome and CFS / Multicolor tracks separate.

### Documentation

- Added UI_STYLE.md.
- Updated System Checks documentation with the permanent v0.9.6 UI reference.
- Documented inclusive Disk Usage warning / critical thresholds.
- Documented the K1 Max firmware branch.
- Updated product decisions.

## v0.13.7 — 08-08-2026 — System Checks and Interface Polish

- Standardized interface labels, headings, buttons and table columns to Title Case while keeping explanatory text in sentence case.
- Changed the System Checks update expander to a separate full-width row so the main table no longer jumps when packages are expanded.
- Made the Checks column link directly to System Check Details.
- Added regression coverage for Disk Usage warning and critical thresholds.
- Added orange warning presentation at the warning threshold and red Critical status at the critical threshold.
- Consolidated the Device page into one System Checks block and removed the duplicate setup/details presentation.
- Moved Device page Save, Export and Delete actions to one bottom action bar.
- Kept Notes directly below System Checks and Attachments below the editable device form.
- Renamed the default SSH profile presentation to System Checks SSH and removed the private-key filesystem path from the Settings list.
- Compacted Session Settings, User Management and Documentation.
- Replaced remaining user-facing Health scheduling/notification terminology with System Checks.
- Updated Dashboard links so System Checks is the primary server-status destination.

## v0.13.6 — 07-08-2026 — System Checks polish and uptime

### Categories

- Replaced the separate Health and Updates category controls with one System Checks control.
- Existing category configuration is migrated automatically: Health or Updates enabled means System Checks enabled.
- Device pages now use the single System Checks category section.

### System Checks

- Added server uptime collected during the existing scheduled SSH-backed check.
- Added readable uptime such as `12 days, 4 hours`.
- Added Last boot to the System Check detail page.
- Reboot validation now compares the boot time before and after a reboot.
- A server merely becoming reachable again is no longer sufficient proof that a reboot completed.
- Preserved the interactive update, upgrade, reboot, maintenance and status behavior introduced in v0.13.5.

### Settings

- Reduced the Data Integrity status text to the normal interface scale.
- Made Documentation tiles substantially more compact and consistent with other Settings sections.

### Documentation

- Updated System Checks and product decisions for category consolidation, uptime and reboot validation.

## v0.13.5 — 06-08-2026 — Interactive System Checks

### System Checks overview

- Restored the strongest interaction patterns from the former Updates page.
- Package updates can be expanded directly in the Updates column.
- Kernel packages are marked clearly.
- Status badges are clickable.
- Available updates show an orange Upgrade action.
- Reboot-required systems show a purple status and Reboot action.
- Maintenance is again a first-class visible status.
- Systems without an immediate action keep the Details button.

### System Check detail

- Replaced raw package dictionaries with readable package names and version changes.
- Added Upgrade and Reboot actions.
- Added upgrade and reboot output panels.
- Added Check now.
- Added Maintenance control.
- Kept direct Online, Disk and HTTP(S) configuration.

### Adding items

- New physical devices can include an initial attachment before the first save.
- Added duplicate warnings for matching hostname, IPv4 address or MAC address.
- Existing items can be opened instead of creating a duplicate.
- Standalone server creation continues directly to System Check Setup.

### Server setup

- Split configuration into required System Check setup and optional host configuration.
- Required SSH key, service account and limited sudo permissions are clearly identified.
- Locale, timezone and convenience packages are presented as optional.

### Firmware

- Added Vendor-managed as a firmware provider.
- Added Vendor application as a check method.
- Added guidance for firmware managed through mobile apps, desktop applications or vendor services.
- Added manual reminder support to IDEAS.md.

## v0.13.4 — 06-08-2026 — Wizard continuity and System Check detail polish

- Preserved first-run state when adding a new item.
- New servers now continue directly from Next to System Check Setup.
- Successful server setup returns to a confirmation page inside the setup wizard.
- Replaced duplicate success notices with one clear confirmation card.
- Removed the Debian / Ubuntu label from System Check Setup.
- Reduced spacing in Configure and Checks sections.
- Right-aligned Next and added the wizard arrow.
- Server names on System Checks link to the device page without a duplicate hostname.
- Renamed Open to Details.
- Made Online status, Disk usage and HTTP(S) equal-width options.
- Disk thresholds now appear only when Disk usage is enabled.
- HTTP(S) URL remains visible only when HTTP(S) is enabled.

## v0.13.3 — 05-08-2026 — Onboarding and System Checks consolidation

### Setup

- Removed the custom instance name.
- Fixed the product identity as Outlaw's Inventory.
- Reordered administrator username and display-name fields.
- Kept password fields in a logical tab order.
- Left-aligned the technical setup introduction and completion action.
- Kept theme selection and added theme controls under Settings.

### First-run wizard

- Removed hover underlines from Device and Server choices.
- Kept the complete first-run flow inside the wizard.
- New servers continue with Next to System Check Setup.
- Simplified successful server setup to Server added successfully.
- Notifications are collapsed and disabled by default.
- The final step shows Items added.
- The final progress indicator is green.
- The final action is Open Outlaw's Inventory.

### System Checks

- Audited and normalized legacy Health and Updates data.
- Removed integration diagnostics from visible status calculation.
- Fixed Check all to execute all online, disk, HTTP(S) and APT checks.
- Added automatic normalization after restoring older backups.
- Kept legacy database tables and routes for compatibility only.
- Removed duplicate System Check blocks from the device page.
- Added direct editing of:
  - Online status check
  - Disk usage check
  - HTTP(S) URL
  - Disk warning threshold
  - Disk critical threshold
- Removed the separate Configure button from the detail page.
- Corrected Online status display.
- Kept package-update output on the detail page.

### Navigation and documentation

- Removed Help from the main menu.
- Added Settings → Documentation.
- Updated the technical documentation to the current product model.
- Added User Manual as a future idea in IDEAS.md.

## v0.13.2 — 05-08-2026 — Guided setup flow

- Removed hover underlining from the initial New installation and Restore from backup choices.
- Kept notification configuration inside the one-time first-run wizard.
- Added an inline notification form and direct return to Setup complete.
- Changed a new Server action from Save to Next: System Checks during first-run.
- New servers outside first-run now continue directly to System Check Setup.
- Replaced remaining Health and Updates tiles on the item form with one System Checks tile.
- Renamed Reachability to Online status throughout the interface.
- Simplified Requirements and Configuration typography.
- Replaced the configuration text block with a normal bullet list.
- Changed the configuration heading to Configure the following.
- Removed the duplicate Open System Checks button.
- Removed Validate now from the setup-complete screen.
- Added Back to setup wizard when System Check Setup is launched from first-run.
- Restored old Health-style check indicators on the System Checks overview.
- Fixed managed-server setup to create and execute separate Online status and Disk usage checks.
- Kept HTTP(S) checks visible when configured.
- Preserved the working sudo administrator and temporary-root setup paths.

## v0.13.1 — 05-08-2026 — System Checks and wizard polish

- Replaced the large System Checks cards with a compact table based on the former Health and Updates pages.
- Added combined columns for address, checks, updates, last checked, status and action.
- Made server names link to the Inventory detail page.
- Open now leads to a dedicated System Check detail page.
- Added Disk usage to the combined overview and detail page.
- Removed Reboot required and Review setup from the overview.
- Added Check all and Add server actions.
- Added a detail page for status, thresholds, HTTP(S) URL and update packages.
- Moved Virtual machine or container next to the Server type selection.
- Made the System Check Setup full-width and more compact.
- Replaced locale/timezone text fields with one optional configuration checkbox.
- Kept locale and timezone values visible as fixed setup defaults.
- Rebuilt category selection inside the first-run wizard with checkboxes.
- Removed the redirect from the wizard to Settings.
- Normalised oversized typography and spacing.
- Kept server onboarding, sudo flow, temporary-root flow and cleanup behaviour intact.

## v0.13.0 — 05-08-2026 — Onboarding and System Check Setup

- Rebuilt the one-time first-run experience as a linear wizard.
- Added explicit category acceptance: Accept default categories or Add / Remove categories.
- Added an item loop with Device and Server choices, Done and Not now.
- Added firmware follow-up for devices and System Check follow-up for servers.
- Added notifications as the final optional setup step.
- Corrected password-field order and tab order in the new-installation form.
- Removed IPv6 from the device form.
- Consolidated server Health and Updates presentation into System Checks.
- Rebuilt System Check Setup into a compact page.
- Added recommended existing-admin-with-sudo authentication.
- Added optional temporary root-access instructions with copyable commands.
- Added automatic removal of the temporary root-access SSH configuration after successful setup.
- Prevented premature SSH attempts with the not-yet-created service account.
- Improved SSH authentication error messages.
- Kept installer, backup restore, MFA, firmware engine and database structure unchanged.

## v0.12.0 — 05-08-2026 — Servers and System Checks

- Added Type selection: Device or Server.
- Added a dedicated server flow from first-run and Inventory.
- Replaced Managed Host terminology with System Check Setup.
- Added a unified System Checks menu and overview.
- Removed Health, Updates, Backups and Network from the main menu.
- Kept existing Health and Updates routes available internally for compatibility.
- Added server requirements:
  - static IP address;
  - SSH enabled and accessible;
  - temporary root access.
- Added automatic remote preparation:
  - packages: sudo, curl, nano, ca-certificates, locales and tzdata;
  - locale and timezone;
  - dedicated service account `sa-outlaws-inventory`;
  - SSH key;
  - limited sudo permissions;
  - ping, disk, update and reboot checks.
- Added the System Checks scope boundary to project documentation.

## v0.11.0 — 05-08-2026 — First-run guide

- Added a one-time first-run guide after creating a new installation.
- Added recommended steps for:
  - administrator account;
  - categories;
  - first inventory item;
  - firmware check;
  - managed host;
  - notifications.
- Added live completion states based on existing configuration.
- Added Finish setup and Skip for now actions.
- Added slightly larger Setup heading.
- Added subtle hover feedback to setup choices.
- Added a possible contextual guided tour to `IDEAS.md`.
- Restored installations do not trigger the first-run guide.

## v0.10.1 — 04-08-2026 — Setup and restore polish

- Enlarged and strengthened setup branding.
- Centred the setup introduction.
- Added meaningful icons to installation choices.
- Added green, orange and red system-check states.
- Added an explicit warning before restore.
- Added visible restore-in-progress feedback.
- Added a one-time restore completion page.
- Added restored item counts for inventory, categories, users and SSH profiles.
- Added Continue to login after a successful restore.
- Added a visual identity and interface refresh idea to `IDEAS.md`.
- Updated the roadmap and documentation.

## v0.10.0 — 04-08-2026 — Installer and setup wizard

- Rebuilt `install.sh` as a technical bootstrap for clean Debian systems.
- Automatically creates the dedicated `outlaw` service account when required.
- Added a web-based `/setup` wizard.
- Added New installation and Restore from backup paths.
- Added initial administrator, instance name, theme and MFA setup.
- Added backup validation and restore during first setup.
- Added `docs/IDEAS.md` and a mandatory ideas review rule for releases.
- Added backup-health and theme/colour-scheme ideas.

## v0.9.6 — 04-08-2026 — Help, backup layout and responsive shell

- Added a Help page backed by bundled Markdown documentation.
- Added the durable project documentation introduced in v0.9.5.
- Reorganised Backup, Restore & Import into Manual/Restore, Backup schedule, Import device and Backup history.
- Renamed Automatic backup to Backup schedule.
- Removed the intermediate navigation layout.
- Widths above 700 pixels now keep the complete desktop/iPad shell.
- Phone widths and supported phone landscape remain on the hamburger layout.

## v0.9.4 — 04-08-2026 — Import and updater cleanup

- Restored Device Import inside Backup, Restore & Import.
- Install now starts with clean staging metadata and downloads a fresh package.
- Failed packages and stale pending metadata are removed automatically.
- After a successful update, only the current and previous release ZIPs are retained.
- Check for updates remains a check-only action.

## v0.9.3 — 04-08-2026 — Mobile tables and Settings organisation

- Reordered the main Settings sections around daily use.
- Merged Device Import into Backup, Restore & Import.
- Simplified phone tables:
  - Inventory: Name and Category
  - Firmware: Device and Status
  - Health: Host and Checks
  - Updates: Name, Status and Action
- Changed the slogan everywhere to `Know. Your. Gear.`
- Preserved desktop and iPad layouts.

## v0.9.2 — 03-08-2026 — HTML email notifications

- Added dark, branded HTML email templates.
- Kept plain-text fallback for all notifications.
- Added status accents and direct action buttons.
- Updated the SMTP test message to preview the new format.
- Notification triggers, deduplication and recipients remain unchanged.

## v0.9.1 — 03-08-2026 — Phone landscape navigation

- Kept the mobile navigation and phone layout active when a phone is rotated to landscape.
- Used viewport orientation, height and coarse-pointer detection instead of browser or user-agent detection.
- Preserved the existing desktop and iPad layouts.
- Updated the README for portrait and landscape phone support.

# Outlaw's Inventory v0.9.0

## Mobile interface
- Added a phone-focused responsive interface below 700 pixels.
- Added an off-canvas navigation menu for phones.
- Converted data tables into readable mobile cards.
- Optimized Dashboard cards, forms, Settings sections and action controls for touch screens.
- Preserved the existing desktop and iPad layout.

# v0.8.69

- Established the supported pre-release database baseline.
- Removed historical installation-name compatibility from runtime and updater paths.
- Removed packaged database, caches, bytecode and loose historical release notes.
- Replaced version-specific test accumulation with a current release contract.
- Added an automated ZIP release validator.
- Updated README documentation to match the current product and workflows.
- No interface or user-workflow changes.

# v0.8.68

- Restored the `Backups (X)` label to the standard subsection heading size.
- No other interface or functional changes.

# Outlaw's Inventory v0.8.67

## Updater

- Restored the compact spinner-based update screen.
- Removed the separate `Please wait` message.
- Changed the update text to:

  `Installing version v0.8.67.`

  `This will take about a minute...`

- Kept update failures visible with a direct return link to Settings.

## Application Version

- Aligned Replace token and Remove token with the GitHub access-token field.

## Backup & Restore

- Reduced the `Backups (X)` heading to the standard section-title size.
- Kept backup history collapsed by default.

## Interface

- No Dashboard, navigation or workflow changes.

## Validation

- Python source compilation passed.
- All Jinja templates passed syntax parsing.
- ZIP root structure and required installer files were verified.
- ZIP integrity and SHA256 verification passed.

## v0.8.66 — 01-08-2026 — Dashboard application updates

- Replaced the Dashboard Unknown tile with Application updates.
- Split managed System and Application update counts.
- Included Outlaw's Inventory in Application updates.
- Reordered Application Version actions.
- Completed the collapsible GitHub configuration and backup history sections.

## v0.8.64 — 01-08-2026 — Application Version consolidation

- Combined version, release history and update controls into one Settings section.
- Added an automatic orange Update available state.
- Added direct Back navigation from Version History.

## v0.8.63 — 01-08-2026 — Update notifications and updater simplicity

- Restored the simple spinner-based update wait screen with non-technical status text.
- Removed progress percentages, timers, heartbeat warnings and reconnect terminology from the update screen.
- Added a dedicated Outlaw's Inventory update-available email with a direct link to the open update section.
- Prevented instance-wide application update alerts from being sent once per active user.
- Serialized notification dispatch to prevent duplicate mail during overlapping scheduler and check runs.
- Manual application update checks no longer trigger email notifications.
- Neutralised instructional copy that unnecessarily addressed the reader directly.

## v0.8.62 — 01-08-2026 — Unified controls and updater clarity

- Standardised all application action buttons to one height and spacing scale.
- Kept destructive actions visually distinct through colour and confirmation, not size.
- Simplified the updater screen to a clear waiting, reconnecting, success or persistent failure state.
- Prevented a stale updater result from briefly reporting failure after the target version is already running.

## v0.8.61 — 01-08-2026 — Interface density and copy polish

- Standardised routine action buttons to the compact control height used by status actions.
- Kept destructive, system and update-install actions visually prominent.
- Reviewed page subtitles and Settings descriptions for clarity and repetition.
- Removed duplicate firmware-page scripts embedded in the page heading blocks.

## v0.8.60 — 01-08-2026 — Updater install action fix

- Fixed the update action returning `405 Method Not Allowed` when an already-rendered v0.8.58 page requested the install endpoint with GET.
- Kept POST as the only method that performs an installation.
- Added a no-cache compatibility bridge that converts stale GET actions into a real POST request.
- Added explicit submit button types to the update forms.
- Simplified update-check results to `New version available: vX.Y.Z` and `Already on latest version: vX.Y.Z`.
- Updated README updater documentation.

## v0.8.58 — 31-07-2026 — Reliable updater progress and heartbeat

- Replaced the spinner-only update wait screen with phased server-side progress.
- Added persistent update job state, percentage, stage, elapsed time and heartbeat age.
- Update progress survives application restarts and browser reconnection.
- Added stale-job detection when the heartbeat stops updating.
- Added clearer failed-stage reporting while retaining the existing rollback snapshot.
- No changes to the normal application interface.

## v0.8.57 — 31-07-2026 — Multi-user notification deduplication fix

- Scoped notification state to the owning user.
- Prevented users without an event from resetting another user's notification state.
- Preserved existing notification suppression state during database migration.
- Added regression coverage for repeated runs, multiple users and service restarts.
- No interface, layout or text changes.

## v0.8.56 — 30-07-2026 — Account session polish and immediate Health validation

- Active sessions and Trusted devices are now compact, collapsed sections.
- Session rows and actions use a smaller visual hierarchy.
- Fixed Use defaults on per-host Disk Usage thresholds.
- Saving a Health configuration now immediately runs its enabled checks.
- No unrelated interface changes.

## v0.8.55 — 30-07-2026 — Account security and per-host disk thresholds

- Restored Account management inside Settings for every user.
- Renamed the avatar-menu entry from Profile to Settings.
- Implemented trusted devices: a successful MFA login can trust a browser for 30 days.
- Added per-user Active sessions and Trusted devices management, including individual revocation and sign-out-everywhere actions.
- Added configurable Disk Usage warning and critical thresholds per Health host.
- New Disk Usage checks start with administrator defaults; existing checks retain their stored values.
- Added Use defaults to restore the current administrator defaults for an individual Health check.
- Preserved the established interface styling and layout outside the new Account and Health controls.

## v0.8.54 — 30-07-2026 — Scheduler and background-task hardening

### Scheduler
- Isolated Health, daily checks, notifications and automatic backups so one failed job cannot block the others.
- Added bounded internal scheduler-run history for completed and failed background work.
- Removed idle polling cycles from scheduler history.
- Notifications now run explicitly for every active user without relying on a browser session.

### Daily checks
- Preserved the System, Application, Firmware execution order.
- Isolated failures per user and per stage so later checks continue running.
- Last successful run is updated only when the complete daily sequence succeeds.
- Added internal last-attempt and last-error state for diagnostics.

### Backups
- Automatic backup failures now reach scheduler error handling instead of being silently discarded.

## v0.8.53 — 29-07-2026

### Fixed
- Background Disk Usage checks now resolve their device and SSH profile from the check owner instead of requiring an active browser session.
- Scheduled Disk Usage results remain available after refresh, logout and a new login.
- One failed Health check no longer aborts the remaining checks in the scheduler run.
- Health and Dashboard continue to use the same persisted host-level results.

## v0.8.52 — 29-07-2026

### Changed
- Rebuilt Settings as a single-column accordion with only one top-level section open at a time.
- Removed redundant Manage labels and added consistent disclosure indicators and open-state contrast.
- Renamed Authentication to User Management.
- Added a configurable execution time for automatic backups.
- Integrated Application version information, Version History and update access into the same Settings section.
- Standardised Settings card spacing and full-width layout across administrator and user sections.

### Fixed
- Prevented mismatched two-column Settings cards and the empty space caused by role-dependent sections.
- Automatic daily and weekly backups now run at the configured clock time instead of drifting from the previous execution time.

## v0.8.51 — 29-07-2026

### Changed
- Replaced the non-functional Appearance controls with a full-width Application overview and Version History link.
- Reorganised administrator Schedules and Health settings into balanced cards.
- Displayed the actual next Health clock boundary instead of generic text.
- Renamed the manual backup action to Backup now.
- Compacted Authentication session settings and standardised account typography, fields, buttons and alignment.
- Moved Transfer inventory into a secondary collapsible section.
- Applied a Settings-wide spacing and component consistency pass.

## v0.8.50 — 29-07-2026

### Fixed
- Persisted Disk Usage results remain visible after refreshing the Health page.
- Separated managed-host integration validation from individual Health check execution to prevent grouped-check state races.
- Dashboard Current Status no longer reports Attention when no actionable item exists.
- Health tile and Dashboard banner now use the same priority order: Critical, Attention, Unknown, Maintenance, OK.

### Changed
- Added a Version History button to Settings → About, linking to the built-in release notes.
- Added distinct Dashboard presentation for Unknown and Maintenance states.

## v0.8.49 — 28-07-2026

### Changed
- Dashboard Health status and counters now use the same host-level status aggregation as the Health page.
- Firmware dashboard counters now include only devices shown on the Firmware page.
- Health checks run on fixed clock boundaries after startup.
- Daily checks run at one administrator-configured time in the order System, Application, Firmware.
- Administrator settings now separate global Schedules and Health thresholds.
- User roles can be changed directly from the account list without changing data ownership.

### Fixed
- Corrected duplicate Maintenance and per-check Health totals on the Dashboard.
- Corrected contradictory Dashboard action text when Attention was active.
- Improved Authentication account-list spacing, alignment and typography.

## v0.8.48 — 26-07-2026

- Corrected alignment of the Health action column.
- Added an explicit Maintenance status for hosts in maintenance mode.
- Made Health status badges link to the corresponding Health configuration page.

## v0.8.47 — 26-07-2026
- Restored the Health page header to the same shared layout used by Firmware and Updates.
- Restored right-aligned Health actions and consistent Check all button styling.
- Removed the unintended excess whitespace above the Health overview.
- Reduced the Ping, Disk Usage and HTTP(S) option label sizes on the Health configuration page.
- No other functional or visual changes.

## v0.8.46 — 26-07-2026
- Restored separate Checks and Status columns on the Health overview.
- Replaced Online status with OK, Attention, Critical and Unknown host-level states.
- Refined the expandable managed-host summary with compact, actionable integration information.
- Removed the decorative arrow from the Open host integration link.
- Corrected Health page spacing and responsive layout.

## v0.8.45 — 26-07-2026

- Restored session-independent automatic Health scheduling.
- Simplified Health status presentation and managed-host details.
- Improved updater reconnect handling and rollback retention cleanup.

## v0.8.44 — 26-07-2026

### Authentication
- Increased the Outlaw's Inventory product title on both the sign-in and MFA verification screens.

### Health
- Grouped multiple checks for the same host into one Health row.
- Reworked Health configuration so Ping, Disk Usage and HTTP(S) can be enabled together for one host.
- Added global configurable warning and critical thresholds for Disk Usage in Settings.
- Preserved existing Health records through automatic grouping by linked Inventory item.

### Updater
- Improved reconnect detection after a successful application restart so the Updating screen can complete automatically.
- Added cleanup for legacy timestamped rollback backup directories and retained only the newest three.

### Quality assurance
- Updated regression coverage for grouped Health configuration and configurable Disk Usage thresholds.
- Full regression suite: 85 tests passed.

# Changelog

## v0.8.44
- Added updater rollback retention and cleanup of incomplete recovery directories.
- Added a pre-update free-space safety check.
- Added managed-host Disk Usage health checks with warning at 85% and critical at 95%.
- Consolidated password and MFA management on Profile and compacted account metadata.
- Enforced administrator-only authentication settings server-side.
- Corrected device form spacing and completed a CSS consistency pass.


## v0.8.42 — Updater version-order hotfix

- Reissued the MFA release with a version number that correctly follows v0.8.35.
- Restored normal self-update availability from v0.8.35.
- Confirmed the internal updater routes, Settings card, checksum validation, privileged helper and rollback workflow remain present.
- No MFA or profile functionality was removed.

# v0.8.42

## Multi-factor Authentication

- Added TOTP MFA for all user accounts.
- Added QR-code setup for Microsoft Authenticator, Google Authenticator, 2FAS, Aegis and Apple Passwords.
- Added one-time recovery codes.
- Added MFA login challenge handling with expiry and rate limiting.
- Added MFA management to Profile.
- Added administrator MFA reset and optional enforcement for administrator accounts.
- Updated version comparison so v0.8.42 correctly follows the compact v0.8.3x hotfix series.

# Changelog

## v0.8.34
- Fixed full backup restore on SQLite WAL databases by restoring through the backup API.
- Expanded integrity checks for attachments, sessions and user-scoped categories.
- Re-ran multi-user ownership, installer, updater and backup regression checks.

# v0.8.34

- Multi-user integrity hardening, tenant-safe category operations, foreign-key enforcement, integrity audit and performance indexes.

## v0.8.34 - 24-07-2026

- Repaired multi-user ownership for devices, SSH profiles, Health checks and Update checks.
- Added startup ownership integrity audit and automatic repair.
- Added explicit owner fields to Health and Update checks.
- Normalized usernames to lowercase while preserving display-name casing.
- Hardened attachment and check access against cross-user access.
- Added database ownership documentation.

## v0.8.2 - 24-07-2026
- Added administrator authentication, secure sessions, login/logout and MFA-ready user storage.


## v0.7.3 - 23-07-2026 - UI and Code Cleanup

- Consolidated shared button and control styling.
- Reorganized Backup & Restore into separate Create, Restore and automatic-backup areas.
- Reduced attachment typography on device pages.
- Removed unused and generated files from the release package.
- Kept application behavior and data formats unchanged.

## v0.7.2 - 23-07-2026 - Backup & Restore and Device Report Polish

- Standardized backup action button sizing and typography.
- Reduced Last automatic backup typography.
- Added dependency-free vector section icons to Device Report PDFs.
- No database schema or backup format changes.


## v0.7.1 - 23-07-2026 - Device Report and Backup UI Polish

- Refined Device Report typography, hierarchy and rounded-card layout.
- Removed decorative section bullets and duplicate category subtitle.
- Renamed Technical details to Firmware.
- Added a dedicated Notes section that is always included.
- Standardized backup filename and action-button typography.

## v0.7.0 — 23-07-2026 — Full Backup and Restore

- Added complete application data backups with database, attachments, SSH keys and local secrets.
- Added manual, scheduled daily/weekly and retained backup management under Settings.
- Added validated download, delete and restore actions for server-side backups.
- Added uploaded full-backup restore with checksums, archive safety limits and SQLite integrity checks.
- Added automatic pre-restore recovery backups and rollback on restore failures.


## 0.6.9
- Made dashboard action-status pills clickable and linked them to the relevant detail page.
- Added subtle attention outlines only to dashboard cards that require action.
- Hid Support status when an item is marked as a virtual machine or container.
- Combined Device Backup and Device Report into one context-aware Export menu.
- Kept device services and sections driven by category capabilities.

## v0.6.8 - Device Export and Import

- Added portable `.oi-device` exports from every device page.
- Added validated device import under Settings.
- Device exports include all device fields and attachments with SHA-256 checksums.
- Added safe conflict handling: create a copy or replace a matching device.
- Added archive size, path traversal and checksum validation.

## v0.6.7 — 20-07-2026 — Email notifications

- Added configurable SMTP e-mail notifications under Settings.
- Added notification categories for Health, Firmware, managed-host Updates and Outlaw's Inventory releases.
- Added test e-mail support and optional links back to the application.
- Added persistent de-duplication so unchanged action items are not mailed repeatedly.
- SMTP passwords are stored separately in the protected secrets directory.


## v0.6.6 — 20-07-2026 — Device Report redesign and interface polish

- Redesigned Device Report PDF with a white, rounded-card layout aligned with the application interface.
- Improved report field selection and hierarchy for insurance, warranty, repair and resale use.
- Moved firmware detail metadata and actions into Advanced firmware information.
- Restyled Shutdown System as a red outline action.
- Repositioned Device Report export within the device form actions.

## v0.6.5 — 19-07-2026 — Device Report PDF

- Added a professional one-page A4 Device Report for physical inventory items.
- Reports include relevant identity, ownership, warranty, network, firmware, notes and attachment metadata while omitting empty fields.
- Added an Export PDF action to physical device pages; virtual machines and containers are excluded.
- Reports download with a device-specific filename and include generation metadata for insurance, warranty, repair or resale use.

## v0.6.4 — 19-07-2026 — Firmware provider reliability and release history polish

- GL.iNet stable listings now pair the detected version with the date from the same rendered row or embedded download-center data.
- Added conservative Onkyo provider support for HT-R693 and TX-NR616 using official model support pages.
- Added DJI and Onkyo to provider selection and automatic provider inference.
- Brother is marked as an unsupported automatic firmware provider and is excluded from Firmware, Check all and scheduled checks.
- Firmware Check all now shows the same disabled Checking… state and spinner as Health and Updates.
- Release notes once again show a date next to each release and retain the one-line release summary.

## v0.6.3 — 18-07-2026 — Firmware reliability and detail-page consistency

- Fujifilm lens checks now return an automatic version only when the exact model is present on the official firmware page; the XF 150-600 remains blank automatically and can use a manual override.
- GL.iNet release parsing now searches the surrounding release row/card for the matching release date.
- Redesigned Health check and Update check detail/status cards with consistent information grids, actions and footers.
- Standardized destructive actions across Health, Updates and Device details using the same red outline style.
- Back and Save actions are now consistently aligned on edit pages.

## v0.6.1 — 18-07-2026 — Firmware provider reliability

- Fujifilm XF 150-600 no longer reports an invented online version; a manual latest-version override supplies the known baseline while model-specific automatic checks remain enabled.
- Brother DCP-L3510CDW remains deliberately Unknown unless a trustworthy model-specific firmware source is available; generic page numbers are never treated as printer firmware.
- DJI checks now prefer official Download Center release notes and only use official static knowledge as a fallback. Community-only Mini 4 Pro data is no longer accepted as authoritative.
- GL.iNet checks can discover the official Beryl AX/GL-MT3000 stable source automatically and preserve a release date when the official listing publishes one.
- Added regression tests for conservative Fujifilm/Brother behavior, DJI source priority and GL.iNet release parsing.

## v0.6.0 — 18-07-2026 — Firmware Engine 2.0

- Added provider metadata and automatic provider inference while preserving all existing firmware data.
- Added a Latest version override that acts as a safe minimum; newer automatic results still win.
- Added clickable firmware status badges linking directly to the firmware section on the device page.
- Added provider and identifier controls for GitHub, GL.iNet, Garmin, Brother, Fujifilm, generic websites and manual sources.
- Existing current/latest versions, URLs, lookup keys, sources, release notes and check history are migrated automatically.
- Firmware overview remains limited to OK, Update and Unknown.

## v0.5.17 - 18-07-2026

### Fixed
- Reworked browser reconnect polling for application restart, system reboot and self-update.
- Every probe now uses a unique URL and a fresh, non-cached connection.
- Added request aborts and visibility/online recovery so desktop Safari resumes polling reliably after the service restarts.
- Reconnect responses explicitly disable caching and close the HTTP connection.

# Changelog

## v0.5.16 — 18-07-2026

### Fixed
- Replaced the browser-specific reconnect implementations with one persistent server-side reconnect action mechanism.
- Update, application restart and system reboot now wait for a genuinely new application process.
- Application updates additionally require the requested version to be running before returning to Settings.
- Improved compatibility with desktop and iPad Safari by using the same conservative XHR polling flow everywhere.
- Improved contrast of the **Not configured** managed-host badge.
- Restored spacing below the device **Back** and **Save** actions.
- Increased the size and visibility of the **Delete item** action.
- Standardized destructive action colors with **Shutdown System**.


## v0.5.15 — 18-07-2026

### Fixed
- Restored consistent vertical spacing between cards on the Settings page.
- Settings now uses the same 16 px card rhythm as Dashboard and Device Details.

### Notes
- No functional changes, database migration or data changes.
- This release is intended as an end-to-end updater reconnect verification.

## v0.5.14 — 18-07-2026

### Fixed
- Fixed the final application-update reconnect issue.
- The update screen now polls the independent updater result exposed by the newly started application instead of relying on process identity alone.
- The browser returns to Settings only after the requested version is running and the updater has reported success.

### Notes
- Restart and reboot reconnect behavior is unchanged.
- No database migration or data changes.

## v0.5.13 — 18-07-2026

### Fixed
- Fixed the Release notes Internal Server Error and restored rendering of the complete changelog history.
- Replaced separate reconnect implementations with one shared process-aware reconnect mechanism.
- Application restart and system reboot now wait for a genuinely new application process before returning to Settings.
- The updater uses the same reconnect mechanism and additionally verifies that the requested version is running.

### Changed
- Restart and reboot now use the same compact spinner screen as application updates.

### Notes
- The update reconnect fix can be verified during the next application update; restart and reboot can be tested immediately in v0.5.13.
- No database migration or data changes.

## v0.5.12 — 18-07-2026

### Fixed
- Reworked updater reconnect polling to use short-timeout XMLHttpRequest checks that continue reliably while the web service restarts.
- Restored the complete Release notes history from CHANGELOG.md instead of showing only v0.5.1.
- Prevented future release-note pages from depending on a manually maintained single-version template.

### Changed
- Simplified the update heading to “Updating Outlaw's Inventory”; the target version remains on the line below.

### Notes
- No database migration or data changes.

## v0.5.11 — 18-07-2026

### Changed
- Moved Notifications above System actions on Settings.
- Moved System actions to the bottom of Settings.

### Notes
- No functional changes.
- No database migration required.
- Existing data, configuration, SSH profiles, keys, uploads and history are preserved.

## v0.5.10 — 18-07-2026

### Fixed
- Made post-update reconnect detection robust by checking both updater state and the running application version.
- Added cache-busting to updater status polling and a manual Settings fallback if reconnect takes unusually long.

### Changed
- Simplified the update screen to a single spinner.
- The target release version is now shown in the heading and install message.
- Placed the automatic reconnect message on its own line.

### Notes
- No database migration or data changes.

## v0.5.9 — 18-07-2026

### Changed
- Removed bold styling from page summary counters for a calmer, consistent appearance.
- Made the Outlaw's Inventory update status panel more compact.
- Reduced spacing around update status, last checked, release notes and actions.
- Kept the compact update screen and fast automatic reconnect introduced in v0.5.8.

### Notes
- Final stabilization and polish release in the v0.5.x series.
- No database migration or data changes.

## v0.5.8 — 18-07-2026

- Completed the v0.5.x UI consistency pass.
- Standardized page header spacing and action placement across Inventory, Firmware, Health and Updates.
- Standardized Check all controls as secondary actions.
- Limited the version badge to Dashboard and Settings.
- Added a compact updater progress screen with spinner and indeterminate progress bar.
- Reduced updater reconnect polling delay for a faster return to Settings.
- No new functionality or database changes.

## v0.5.7 — 18-07-2026

### Fixed

- The update progress page now detects a completed installation after the web service restarts and automatically returns to Settings.
- Actions inside the update card keep the card open so their result remains visible.

### Changed

- Removed the redundant **Test connection** button.
- Moved **Remove token** next to the token controls.
- After a successful update, the update card and release notes open automatically and a clear success message is shown.
- No database migration is required.

## v0.5.6 — 18-07-2026

### Changed

- Made the **Outlaw's Inventory update** section on Settings collapsible, matching Categories and SSH profiles.
- Reordered Settings sections by expected usage: Outlaw's Inventory update, Categories, SSH profiles, System actions, then Notifications.
- No updater logic, application functionality or other UI behavior was changed.

## v0.5.5 — 18-07-2026

### Fixed
- Fixed the Settings 500 error by removing direct access to root-only rollback metadata.
- Made update and rollback status exchange use app-owned state files.
- Prevented concurrent update and rollback jobs.
- Added stricter package and version validation before installation.
- Made rollback preserve the live database, settings, SSH profiles, keys and uploads in place.
- Limited rollback snapshots to application code instead of copying runtime data.
- Improved atomic status writes and update failure reporting.

## v0.5.4

### Fixed

- Self-updates and rollbacks now run in independent transient systemd jobs instead of as child processes of the web service.
- Stopping `outlaws-inventory.service` no longer terminates the update process halfway through installation.
- The install and rollback routes now verify that the independent job was successfully queued before showing progress.
- Launcher failures are written back to the update status instead of leaving the interface stuck on an installing message.

### Changed

- Added dedicated root-owned update and rollback launchers using `systemd-run`.
- Sudo permissions now allow only the two launchers; the web application no longer invokes the installation helpers directly.

## v0.5.3

### Changed

- Simplified the Outlaw's Inventory update card and removed developer-oriented helper text.
- Checking for updates no longer downloads or installs anything.
- A separate **Install vX.Y.Z** action appears only after a newer release is found.
- Release notes open automatically when an update is available.

### Added

- Keeps exactly one known-good previous application version before every successful update.
- Added **Revert to vX.Y.Z** with confirmation when a rollback version is available.
- Rollback preserves current application data while restoring the previous application code.

### Fixed

- Clears stale `Installing vX.Y.Z…` state after a manual or completed installation.
- Installs and authorizes the dedicated rollback helper.
- Backup pruning no longer removes the dedicated rollback copy.

## v0.5.2

### Fixed

- Migrated SSH profile private-key paths still pointing to `historical pre-release path`.
- Cleared stale update-check failures caused by the renamed installation path.
- Added a defensive migration for stored settings containing the legacy path.
- Audited runtime code and installation scripts for remaining legacy path references; only intentional migration compatibility references remain.


## v0.5.1 - 17-07-2026

### New
- Complete self-update flow under Settings using private GitHub Releases.
- Fine-grained token storage, connection test and release comparison.
- Download and SHA-256 verification of versioned release packages.
- One-click installation with backup, restart validation and automatic rollback.

### Changed
- The update repository is fixed to `OutlawNL/outlaws-inventory`.
- Empty token submissions no longer silently remove the configured token.
- Token removal is now an explicit confirmed action.

## v0.5.0 — Final product migration and internal updater

### Added
- Internal application updater under Settings using GitHub Releases.
- Support for private repositories through a fine-grained read-only token stored outside SQLite.
- Required checksum verification through a `SHA256SUMS` release asset.
- Restricted root-owned self-update helper with a fixed staging location and no command-line arguments.
- Automatic pre-update backups, startup validation and rollback on failure.
- GitHub-ready repository structure with `.gitignore`, `docs/`, scripts and release-contract tests.

### Changed
- Installation directory is now `/opt/outlaws-inventory`.
- Systemd service is now `outlaws-inventory.service`.
- Database is now `data/outlaws-inventory.db`.
- Data-directory environment variable is now `OUTLAWS_DATA_DIR`; the legacy variable remains a compatibility fallback.
- Release archives now extract to `outlaws-inventory-vX.Y.Z`.
- Documentation reflects Outlaw's Inventory as the final product name rather than Homelab Dashboard.

### Migration
- `update.sh` detects an existing v0.4.x installation in `historical pre-release path`.
- All application data, attachments, keys, profiles, checks and settings are copied to the new installation.
- The new service is started and verified before the legacy service and directory are removed.
- A pre-migration backup is retained under `/var/backups/outlaws-inventory`.

## v0.4.31 — 17-07-2026

- Matched Back and Save typography and dimensions on Device forms.
- Moved Online to the Health service card header, aligned with Ready.
- Standardized Ready and Online badge typography.
- Removed icons from Edit and Unlink.
- No other functional or visual changes.

## v0.4.30 — 17-07-2026

- Completed a final interface-wide typography consistency pass.
- Matched Recent activity title, description and historical event text to the established Device-card hierarchy.
- Removed the persistent Saved text and all successful-save confirmation indicators from Settings autosave.
- Autosave remains active; only failures are shown to the user.
- No functional firmware, Health, update, scheduler or managed-host changes.

## v0.4.29 — 17-07-2026

- Aligned the Device Health service card with the established card hierarchy.
- Removed the redundant health status dot and right-aligned the status badge.
- Reduced health-check name emphasis and standardized Edit/Unlink text size, height and width.
- No functional Health or managed-host changes.

## v0.4.28 — 17-07-2026

- Refined the Device Health service card with aligned status, metadata and equal row actions.
- Added a restrained shared line-icon style for local actions and empty states.
- Added a dedicated Recent activity chevron and attachment empty-state icon.
- Kept device and health names non-clickable where no useful navigation target exists.

## v0.4.27 — 17-07-2026

### Changed
- Removed the Dashboard refresh timestamp, refresh explanation, and automatic 30-second page reload.
- Completed the final v0.4 UI consistency review for empty states, typography, spacing, buttons, badges, and form controls.
- Established v0.4.27 as the UI-freeze baseline for future feature development.

### Scope
- No firmware, Health, managed-host, scheduler, update, kernel, or reboot logic changed.

## v0.4.26 — 17-07-2026

### Changed
- Refined the linked Health service card on device pages.
- Reworked the Firmware summary and action layout on device pages.
- Standardized the release ZIP naming convention as `outlaws-inventory-vX.Y.Z.zip`.

## v0.4.25 — 17-07-2026

### Changed
- Shutdown System is now a destructive red action with confirmation.
- Device form Back and Save actions are grouped together at the lower-right.
- Select controls use the same height and visual rhythm as text inputs, including Safari.

### Fixed
- Virtual machine or container is fully hidden for non-Server categories instead of remaining visibly disabled.

## 0.4.24 - 2026-07-17

### Fixed
- Virtual machine/container is available only for Server items.
- Managed-host platform detection now captures KVM/LXC/container results correctly.
- Ready badge contrast is consistent with other green statuses.

### Changed
- Platform is displayed with a friendly name in Managed host integration.
- Row-level actions share one visual component.
- System control buttons are secondary actions.
- Typography and spacing consistency improved.

# Changelog

## v0.5.8 — 18-07-2026

- Completed the v0.5.x UI consistency pass.
- Standardized page header spacing and action placement across Inventory, Firmware, Health and Updates.
- Standardized Check all controls as secondary actions.
- Limited the version badge to Dashboard and Settings.
- Added a compact updater progress screen with spinner and indeterminate progress bar.
- Reduced updater reconnect polling delay for a faster return to Settings.
- No new functionality or database changes.

## v0.4.23 — 17-07-2026
- Rebuilt the Device page hierarchy with General first and history at the bottom.
- Added a Virtual machine or container flag that hides physical ownership and hardware fields.
- Managed host validation now detects KVM, LXC and other virtualization automatically with systemd-detect-virt.
- Historical failed actions are shown as past issues instead of current device failures.
- Refined device activity typography and collapsed presentation.

# v0.4.23

## v0.4.23 — 17-07-2026

### Changed
- Replaced General with a compact Appearance section.
- Added Dark/Light segmented theme control with immediate autosave and reload.
- Prepared an EN/NL language control; NL remains disabled until translations exist.
- Improved link and device-name contrast in the light theme.
- Combined firmware, system and future application checks into one Maintenance schedule.
- Kept Health on a separate, more frequent schedule.
- Removed the redundant automatic-system-update checkbox and firmware-only time field from Settings.
- Unified Settings heading typography.
- Unified status badge dimensions across Firmware, Health, Updates and Dashboard; Reboot required uses a dedicated wider size.

- Unified scheduled-check settings with autosave.
- Collapsible SSH profiles and categories.
- Activity moved to device pages.
- Consistent status badge widths and dashboard naming.
- CSS cache busting.

# Changelog — Outlaw's Inventory

This changelog is reconstructed from the supplied v0.4.9 source. Entries through v0.4.6 come from `app/templates/release_notes.html`; v0.4.9 comes from `README.md`. The source contains no reliable complete entries for v0.4.7 and v0.4.8, so those versions are explicitly marked uncertain rather than invented.

## v0.4.21 — 17-07-2026

### Added
- Automatic scheduled system update checks with configurable 6, 12, 24 or 48 hour intervals.
- Last and next automatic check timestamps on Settings.

### Changed
- Combined upgrade and reboot output into one expandable Activity timeline per host.
- Aligned reboot status and action controls with fixed heights.
- Reorganized Settings into clearer sections and made Categories collapsed by default.

## v0.4.19 — 17-07-2026

### Changed
- Compacted the reboot-required panel and split kernel information into clear running and installed kernel values.
- Aligned the reboot status badge and Reboot action consistently in the Updates table.
- Added firmware release dates below firmware action items on the Dashboard.
- Standardized dashboard action-card header, row and status alignment.

## v0.4.18 — 17-07-2026

### Fixed
- Replaced the fragile argument-specific kernel sudo rule with the root-owned `/usr/local/sbin/outlaws-kernel-upgrade` wrapper.
- Managed-host setup installs the fixed wrapper and grants passwordless sudo only for that argument-free command.
- Managed-host validation verifies both the wrapper file and its exact sudo permission.

### Changed
- Firmware and system update action items now use matching side-by-side dashboard cards on wide displays and stack responsively on smaller displays.
- Existing hosts require one reconfiguration; all future Debian/Ubuntu host configurations receive the wrapper automatically.
- Health layout and behavior remain unchanged.

## v0.4.17 — 17-07-2026

### Fixed
- LXC and other containers no longer receive false reboot-required status from comparison with the shared Proxmox host kernel.
- Invalid unversioned `/vmlinuz` results are ignored.
- Kernel upgrades now re-check packages after the normal upgrade, run the dedicated `linux-image-amd64` command only when needed, and verify that it no longer remains upgradable.
- A failed dedicated kernel installation now produces an explicit failed upgrade result and retained output.
- Reboot failures retain and display the exact remote output instead of only showing generic guidance.

### Changed
- Health integration details now open by clicking **Managed host** below the device name.
- Removed the separate Details button so the Check action aligns consistently for all health rows.

## v0.4.16 — 17-07-2026

### Added
- Kernel package highlighting in the Updates package list.
- Reboot-required detection using `/run/reboot-required` and the active versus installed kernel.
- Confirmed remote reboot action with a blocking wait state, return-to-service detection and automatic update recheck.
- Narrow sudo permissions for the dedicated `linux-image-amd64` upgrade and `/usr/sbin/reboot`.

### Fixed
- Firmware overview and firmware Check all now respect each category's `show_firmware` setting.
- The `linux-image-amd64` meta-package can be installed when normal `apt-get upgrade -y` leaves it behind.

### Upgrade note
- Existing managed hosts need one reconfiguration run to receive the two new sudoers permissions.

## v0.4.14 — 16-07-2026

### Added

- Added a guided **Configure host integration** wizard for Server Inventory items.
- The wizard can create the managed SSH user, install the selected Outlaw public key and create `/etc/sudoers.d/outlaws-inventory`.
- Added remote preflight and validation for Debian/Ubuntu identification, APT availability, key-based login and the exact update/upgrade sudo permissions.
- Successful setup can automatically create or update the linked ping Health check and APT Updates check, then execute both checks.
- Added managed-host status fields to Inventory devices so host management is not technically dependent on the category name.

### Safety

- Bootstrap and sudo passwords are request-only and are never stored in SQLite.
- The generated sudoers file grants only `/usr/bin/apt-get update` and `/usr/bin/apt-get upgrade -y`.
- The remote script is fixed by the application and does not accept arbitrary shell commands.

## v0.4.13 — 16-07-2026

### Changed

- Starting a remote APT upgrade now immediately displays a blocking progress overlay with a spinner and indeterminate progress bar.
- The progress message identifies the target host and explains that installation and the automatic verification check can take several minutes.
- Other buttons and links on the Updates page are temporarily disabled while the upgrade request is running.
- The existing post-upgrade success, failure, stored output and automatic recheck behavior is unchanged.

## v0.4.12 — 16-07-2026

### Added

- Added a confirmed **Upgrade** action to the Updates overview for Debian, Pi-hole and Proxmox APT targets.
- After `apt-get upgrade -y`, the target is checked again automatically and its package status is refreshed.
- Stored upgrade output is available as an expandable section on the Updates overview.
- Added a **System update action items** block to the dashboard.

### Changed

- Dashboard **Attention needed** now includes available or failed system update checks.
- Expanded package lists use smaller, compact typography consistent with the rest of the interface.

## v0.4.11 — 16-07-2026

### Fixed

- Remote APT checks now run the documented `sudo -n /usr/bin/apt-get update` command without the undocumented `-qq` argument, so existing least-privilege sudoers rules match correctly.
- Sudo error guidance now explicitly lists the exact commands that must be allowed.
- GitHub release timestamps are normalized to an ISO date before storage and display.

### Changed

- Moved GitHub URL parsing and Releases API retrieval into the first standalone firmware provider module at `app/providers/github.py`.
- Added regression coverage for the exact APT command and GitHub release-date normalization.

## v0.4.10 — 16-07-2026

### Added

- Added a generic GitHub Releases API provider for public repository and Releases URLs.
- Added mocked regression tests for stable-release selection, version comparison and Updates route ordering.

### Changed

- GitHub drafts and prereleases are ignored.
- Stable GitHub tags such as `v2.2.0` are normalized to `2.2.0` before comparison.
- **Updates > Check all** executes enabled checks concurrently with a maximum of four workers.
- The Updates page displays how many checks completed and whether an unexpected worker failure occurred.
- Firmware lookup failures now retain visible diagnostic text instead of silently returning an empty result.

### Fixed

- Chameleon Ultra with current firmware `2.1` detects stable release `2.2.0` from its GitHub Releases URL.
- Equivalent versions such as `2.2` and `2.2.0` compare as equal.
- An unexpected failure in one remote update check no longer stops the remaining checks.
- Added a trailing-slash-compatible alias for `/updates/check-all/`.

### Operational note

- Public GitHub API requests are unauthenticated and therefore subject to GitHub's unauthenticated rate limit. A rate-limit or network error is shown in the firmware summary and leaves the status `Unknown`.

## v0.4.9 — date not independently established

### Fixed

- Fixed the Updates **Check all** route conflict.
- Registered `/updates/check-all` before dynamic update-check routes.
- Check all runs every enabled update check without requiring form data.
- Individual update checks and the install-updates action were stated to be unchanged.

### Known issue

- A remaining “Check for Updates” problem is reported in the installed application. Its exact cause is not established from source alone.

## v0.4.8 — uncertain

No explicit v0.4.8 release entry exists in the supplied source. Changes cannot be reconstructed confidently.

## v0.4.7 — uncertain

No explicit v0.4.7 release entry exists in the supplied source. Changes cannot be reconstructed confidently.

## v0.4.6 - 11-07-2026

### New
- Minecraft Java server update checks compare the remote server.jar version with Mojang's latest release manifest.
- Update types now include APT, Pi-hole, Proxmox VE and Minecraft Java server.

### Changed
- Update-check forms use clearer labels, hide redundant fields and automatically use the only SSH profile.
- The detail page now shows a clear status card with last check, result and update count.

### Fixed
- Removed the outdated v0.4.1 placeholder from Update actions.

## v0.4.5 - 11-07-2026

### Fixed
- SSH keys are now read from the actual application data directory.
- The updater migrates keys from the previously documented legacy directory and repairs ownership and permissions.
- Update checks show clear guidance when no SSH profile is configured.

### Changed
- A single SSH profile is selected automatically for new update checks.
- Settings now includes Restart Outlaw's Inventory, Reboot System and Shutdown System actions with confirmation for disruptive actions.

## v0.4.1 - 10-07-2026

### New
- Inventory items now store hostname, IPv4, IPv6 and MAC address in a dedicated Network section.

### Changed
- Health and Updates use the linked Inventory network address instead of requiring duplicate host/IP entry.
- Existing linked Health/Updates targets are migrated into Inventory where possible.
- Settings layout cleaned up.

## v0.4.0 - 10-07-2026

### New
- Added the Updates module for read-only Debian/Ubuntu and Proxmox APT update checks over SSH.
- Added SSH profiles in Settings using private keys stored on the application server.
- Update checks can be linked to Inventory items and show package names, installed versions and available versions.
- Added Updates to the Dashboard and item Services section.

### Safety
- v0.4.0 detects updates only; it does not install packages or allow arbitrary commands.

## v0.3.6 - 10-07-2026

### New
- Maintenance mode for intentionally paused Health checks.
- Health and Dashboard pages refresh automatically every 30 seconds without starting extra checks.

### Changed
- Health overview no longer shows response time.
- Offline checks show how long they have been offline while retaining the exact Last online timestamp.
- Dashboard shows its last refresh time and includes Maintenance in the Health summary.

### Fixed
- Background checks keep their configured interval; page refreshes do not trigger additional pings.

## v0.3.4 - 10-07-2026

### New
- Automatic Health checks now run in the background using each check's configured interval.
- Added a Services section to Inventory item pages for Firmware, Health, future Updates and Notifications.
- Existing Health checks can be linked or unlinked from an Inventory item.
- Added subtle category icons to the Inventory list.

### Changed
- The Inventory action is now called Add Item.
- Categories can be renamed in Settings; linked Inventory items are updated automatically.
- Unused custom or built-in categories can be deleted, while categories in use are protected.
- Health setup can be started directly from an Inventory item.

## v0.3.2 - 09-07-2026

### Fixed
- Health checks now set successful Ping/HTTP results to green OK.
- Last online is updated when a health check succeeds.
- Failed checks no longer show misleading response times.
- Health counters on the Health page and Dashboard use normalized status values.

## v0.3.0 - 09-07-2026

### New
- Added the first Health module for lightweight availability checks.
- Added Ping and HTTP check types with response time, last checked and last online tracking.
- Health checks can be linked to Inventory items.
- Dashboard now includes a Health card and opens the Health module.

### Changed
- Health is now a separate module from Firmware and future Updates.
- Backups and Network remain disabled until those modules are built.

## v0.2.14 - 08-07-2026

### New
- Added Canon PIXMA PRO-200 firmware catalog support using the official Canon Europe firmware page.
- Added Brother DCP-L3510CDW support as a conservative provider: the app will not report Brother Firmware Update Tool versions as printer firmware.
- Added Printer as a built-in category.
- Added basic category management in Settings.

### Changed
- Category dropdowns and filters are now alphabetically sorted.

## v0.2.13 - 08-07-2026

### Fixed
- Creality firmware provider now accepts versions only from matching OTA .img firmware filenames.
- Fixed false Creality versions such as 4.3.1 and 3.6.71 being picked up from unrelated page text.
- K1 Max Monochrome and Ender-3 V3 KE use stricter model/variant matching before a firmware version is accepted.

## v0.2.12 - 08-07-2026

### Changed
- Creality firmware provider now uses Creality Cloud as the preferred official source instead of the older creality.com download pages.
- K1 Max firmware lookup distinguishes Monochrome from CFS/Multicolor firmware tracks.

### Fixed
- K1 Max Monochrome with mainboard CR4CU220812S11 now maps to firmware V1.3.5.19.
- Ender-3 V3 KE now maps to firmware V1.1.0.17 from the Creality Cloud firmware page.
- Creality provider will not accidentally suggest the K1 Max CFS/Multicolor 2.x firmware for a Monochrome K1 Max.

## v0.2.11 - 07-07-2026

### New
- Added conservative Creality firmware knowledge-base entries for K1 Max and Ender-3 V3 KE.

### Changed
- Dashboard Firmware OK card now links to the Firmware page.
- Device page bottom actions now include a clear Back button next to Save.

### Fixed
- Creality public firmware pages that are older than the installed printer firmware now result in Unknown instead of false OK or Update.

## v0.2.10 - 07-07-2026

### Fixed
- DJI firmware checks no longer copy the installed/current firmware into the Latest field when the online/provider result is missing or stale.
- Stale DJI provider results now show Unknown instead of a false OK.
- Manual firmware checks no longer use Current as a fallback for Latest.

### Changed
- Purchase price is normalized as a euro value, e.g. € 100,00.

## v0.2.9 - 07-07-2026

### Changed
- Rolled back the broken generated logo/branding experiment and restored a clean stable sidebar.
- DJI firmware handling now uses a conservative DJI Knowledge Base before attempting fragile PDF/download parsing.
- DJI results never show an older public source as Latest when the installed firmware is newer.

### Fixed
- Improved DJI O4 Air Unit Pro/Lite baseline detection.
- Added baseline DJI checks for Mini 4 Pro, Osmo 360, Osmo Action 4, Goggles N3 and Mic Mini.
- Firmware check errors now fall back to Unknown instead of misleading Problem states.

## v0.2.6 - 05-07-2026

### New
- Rebranded the app to Outlaw's Inventory .
- Added the tagline Know your gear.
- Added first Tech Crate logo assets for the sidebar and favicon.
- Added deferred firmware updates with a reason, so an available update can be intentionally postponed.

### Changed
- Devices is now called Inventory.
- Inventory is now a pure inventory view; firmware status no longer appears in the Inventory table.
- Firmware status is now handled only by the Firmware module.
- Support status is shown separately on the device page.
- Firmware statuses are simplified to OK, Update, Deferred and Unknown.

### Fixed
- DJI checks no longer report OK when the detected latest version is older than the installed firmware.
- Existing Discontinued firmware statuses are migrated to OK, while lifecycle/support status stays separate.

## v0.2.5 - 05-07-2026

### New
- Release Notes URL on device pages now has a direct Open button.
- Devices page now shows a device counter that updates with filters.
- Initial DJI Download Center provider added for products with official release notes pages.

### Changed
- Firmware status remains Unknown when current firmware is empty, even if a latest version is known.
- DJI firmware checks now prefer official download pages and release-note PDFs over broad parsing.

### Fixed
- Release-note links are easier to open from device details.

## v0.2.4 - 05-07-2026

### New
- Instax mini Evo added to the Firmware Catalog using the official instax firmware page.
- Advanced firmware information section added to device pages for troubleshooting details.

### Changed
- Normal device pages now show only practical firmware fields; provider/source/confidence details moved into Advanced firmware information.
- Firmware overview now shows all devices, including newly added devices without a catalog match.
- Dashboard Devices, Update and Unknown cards are clickable.

### Fixed
- New devices no longer disappear from the Firmware overview when no firmware provider is known yet.

## v0.2.3 - 05-07-2026

### New
- Firmware Catalog introduced for known products, using normalized official model names instead of broad page parsing.

### Changed
- Known Fujifilm, Ricoh and Arturia devices now prefer catalog matches before any generic parser.
- Firmware checks are stricter: catalog miss plus no reliable source becomes Unknown instead of a guessed version.

### Fixed
- Fujifilm X-T5 no longer returns a date as firmware version.
- Fujifilm XF 18-55 and XF 16-80 map to their official lens firmware entries.
- Ricoh GR III and Arturia MiniFuse/MiniLab checks avoid unrelated older or bundled software versions.

## v0.2.2 - 05-07-2026

### New
- Firmware lookup key added for exact model matching on vendor pages.

### Changed
- Firmware checking now uses provider-specific logic for Fujifilm, Ricoh, Arturia and DJI instead of one broad parser.
- Generic parsing is more conservative and only uses content tied to the exact device/model.

### Fixed
- Fujifilm lens checks no longer reuse another lens version when a model is absent or ambiguous.
- Arturia checks avoid reporting Analog Lab or bundled software versions as device firmware.
- DJI remains Unknown unless a reliable latest-version source is configured.

## v0.2.1 - 05-07-2026

### Changed
- Firmware overview simplified: Source and What's new now live on the individual device page only.
- Firmware table layout is more consistent with Devices.

### Fixed
- Release zip now extracts into its own historical pre-release package folder again.
- Fujifilm lens checks are stricter and no longer reuse another lens version when the exact model is not found.
- Arturia checks no longer report bundled software versions such as Analog Lab as hardware firmware.
- Firmware dates from source pages are displayed consistently as DD-MM-YYYY.

## v0.2.0 - 05-07-2026

### New
- Firmware Intelligence: release date, short "What's new" summary, full release-notes link, source, check method and confidence.
- Lifecycle field added: Active, Legacy and Discontinued.
- Firmware statuses now include Discontinued and Error.
- Display name added for devices.
- Tags added to device pages and Devices filtering.

### Changed
- Dates are now shown as DD-MM-YYYY where possible.
- Firmware page shows source and short release-note summary instead of only version numbers.
- Dashboard wording stays focused on action items.

### Fixed
- DJI checks remain conservative: Unknown is preferred over an unreliable version.
- Arturia checks avoid unrelated bundled software versions.
- Fujifilm/Ricoh-style pages can provide version, release date and description when the source page is structured clearly.

## Roadmap

### Next
- Build the Updates module for OS, applications and packages.
- Improve DJI Download Center provider and PDF parsing for more products.
- Expand the Firmware Knowledge Base and reduce Unknown devices.
- Improve release-note summaries on device pages.
- Refine tags and filters after real-world use.
- Mobile layout improvements.

### Later
- Updates module for OS/app/package updates.
- Notifications for firmware, health and update events.
- Backups page.
- Network page.
- Home Assistant, Proxmox, UniFi and Pi-hole integrations.

### Ideas
- Related devices.
- Warranty reminders.
- Service history.

## v0.1.5 - 05-07-2026

### Fixed
- Arturia firmware checks no longer report unrelated Analog Lab versions.
- Generic firmware checks are more conservative.
- Purchase date and Warranty until can remain empty.

## v0.1.4 - 05-07-2026

### Changed
- Version badge returned to a compact version-only label.
- Firmware table layout made more consistent with Devices.

## v0.1.3 - 05-07-2026

### New
- Device list can be sorted by Name, Category, Vendor and Status.
- Device list can be filtered by Category and Status.
- Device detail pages show a breadcrumb back to Devices.

### Changed
- Device names are clickable in Devices and Firmware.
- Open/Details columns removed for cleaner navigation.
- Device names in the Devices overview match the Firmware page typography.

### Fixed
- Release Notes no longer renders the word Update as a huge status label.
- General card on the Device page no longer stretches vertically under Serial number.
- update.sh preserves the Python virtual environment.

## v0.1.2 - 05-07-2026

- Firmware status changed to Update.
- Release notes page added.
- Light theme setting works.

## v0.1.1 - 05-07-2026

- Ownership fields added.
- Attachment descriptions added.
- Mark as updated button added.

## v0.1.0 - 05-07-2026

- Initial release with dashboard, devices, firmware overview, settings and installer.

## v0.13.25

- Clarified Settings > SSH Profiles with separate Add SSH Profile and Configured Profiles sections.
- Corrected general notification email Dashboard links to the actual Dashboard route (`/`).
- Established v0.13.24 as the supported upgrade and full-backup compatibility baseline for the current pre-release line.
- Removed obsolete pre-release installation-name/path conversion logic; current user data remains untouched.
- Kept idempotent schema guards that protect current installations and future schema evolution; these are not treated as support for obsolete releases.
- Added release checks for the supported upgrade baseline, backup baseline and Dashboard notification target.
