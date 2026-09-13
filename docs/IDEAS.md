# Ideas

Ideas are possibilities, not commitments. An item becomes planned only after it moves to `ROADMAP.md`.

At every release, review this file and decide whether each idea should remain, move to the roadmap, or be removed.


## Software Checks / Software Version Tracking

Explore a separate software-version tracking area for desktop software, plugins and tools that do not reliably update themselves or expose their update state elsewhere.

Initial candidates include:

- DJI Reframe for DaVinci Resolve;
- VST/VST3 audio plugins;
- standalone audio tools and utilities;
- other manually maintained desktop plugins or applications.

Possible first version:

- software name and platform;
- installed/current version;
- latest available version;
- release date and official source URL;
- OK / Attention / Unknown status;
- optional device/computer association later.

Design boundary: Pi-hole and Minecraft remain **Application Checks** because Outlaw's Inventory manages them as applications on managed hosts, including runtime/service state and update handling. They must not be duplicated under Software Checks. Software Checks is intended for standalone software where version/update tracking is the primary concern.

Status: idea / collect more real-world candidates before moving to the roadmap.

## Backup health

Possible lightweight checks for the last successful backup of:

- Proxmox VMs and containers
- Time Machine
- iPhone or iCloud device backups, where technically accessible
- Minecraft worlds
- NAS backup jobs
- Docker volumes
- rsync jobs

The goal would be a simple “is a recent backup available?” status, not replacing the original backup product.

Status: idea / low priority.


## Visual identity and interface refresh

Explore a cleaner visual language inspired by the setup wizard while preserving usability and the established information architecture.

Possible areas:

- a recognisable Outlaw's Inventory logo or mark;
- subtle icons where they add meaning rather than decoration;
- refined typography using widely available or safely bundled web fonts;
- more depth and hierarchy in cards and status areas;
- restrained illustrations or device imagery;
- consistent branding across setup, login, application and email;
- preserve compatibility across Safari, Edge, Chrome, iPad and phones.

The refresh must not reduce clarity or turn the interface into a decorative dashboard.

Status: idea / requires design exploration.

## Guided tour

Consider a lightweight contextual tour after the first-run checklist, highlighting the Dashboard, Inventory, Firmware, Health and Settings without blocking normal use.

Status: idea / evaluate after first-run wizard testing.

## Parked menu ideas

Backup and Network menu items were removed in v0.12.0. Reconsider only when a concrete user need exists.

## User Manual

Create a separate practical end-user manual focused on tasks rather than project internals:

- Add a device
- Configure firmware checks
- Add a server
- Configure System Checks
- Configure notifications
- Create and restore backups
- Troubleshoot common problems

This manual must remain separate from the technical project documentation under Settings > Documentation.

Status: future idea.

## Vendor-managed firmware reminders

Some devices use a vendor application or service instead of a public firmware feed, for example SMART HJC Device Manager, DJI Fly, DJI Assistant or Garmin Connect.

Future option:

- Mark firmware as Vendor-managed
- Record the installed version and vendor application
- Configure a manual verification reminder
- Suggested intervals: 3, 6 or 12 months
- Never claim that an automatic check succeeded when no public source exists

Status: future idea.

## Device Profiles

The Device Profiles concept moved into active implementation in v0.18.0. See `ROADMAP.md` and `DEVICE_PROFILES.md` for the current architecture and phased rollout. AI-assisted profile authoring and multi-source corroboration remain future ideas within that architecture.
