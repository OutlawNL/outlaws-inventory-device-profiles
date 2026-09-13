# UI Style

## Capitalization

Use **Title Case** for interface labels and control text:

- navigation items;
- page, section, card and accordion titles;
- buttons and action links;
- table headers;
- form labels;
- compact status labels.

Use **sentence case** for explanatory copy, helper text, descriptions, notifications, errors and other complete sentences.

Examples:

- `Account Picture`, `Active Sessions`, `Backup Now`, `Application Version`
- `JPG, PNG or WEBP. Maximum 5 MB.`
- `Notifications are sent only for new or changed action items.`

Do not use CSS text transforms to manufacture capitalization. Product names and acronyms retain their intended spelling, including Outlaw's Inventory, MFA, SSH, HTTP(S), APT and Pi-hole.

## Visual Language

Classic is the single maintained interface. Normal actions use the quiet solid button treatment. Do not reintroduce decorative gradient primary buttons. Destructive actions and live statuses may use semantic color.

Configuration controls remain visually neutral. Live health/status surfaces carry status color.

## Typography

Ordinary data/detail text uses the normal interface size. KPI-sized typography is reserved for Dashboard KPI cards.

Settings group headings and setting rows keep a consistent title/subtitle scale. Opening an accordion must not change the heading size or horizontal position.

## Status Colors

- Green: OK
- Orange: Attention / update available
- Red: Critical / destructive
- Purple: reboot required
- Blue: Maintenance
- Neutral/gray: Unknown or unavailable result

Secondary indicators must not compete visually with the primary status.

## Dashboard

The Dashboard has four primary KPI cards:

- Inventory
- Firmware
- System Checks
- Software Updates

Outlaw's Inventory application updates are shown as a conditional banner rather than a permanent KPI.

Wide desktop: four cards. Intermediate layouts: two columns. Phones: one column.

## Settings

Settings is a single-column accordion with these top-level groups:

- Personal
- Application
- Administration

Only one top-level setting should normally be open at a time. Internal disclosures such as Security, Active Sessions, Trusted Devices, E-mail Server and Release Notes may expand within their parent setting.


## Overview Table Alignment

Overview tables follow one shared alignment rule:

- textual and data columns are left-aligned, including timestamps such as `Last Checked`;
- columns whose primary content is a centered UI control are centered, including both the header and the control;
- status pills and action buttons are examples of centered UI-control columns;
- do not center ordinary text/data columns solely to make all headers look uniform.

Use the shared overview-table CSS convention (the `data-ui-table` hook plus the documented control-column rule) rather than adding unrelated page-specific alignment overrides. This keeps new overview pages consistent by default.

Phone overview tables that only need an identity column plus status use the shared `data-ui-compact-mobile` pattern: identity/name on the left, `Status` centered above the centered status pill. Do not let these tables fall back to the generic card-per-row mobile table treatment.

## System Checks Desktop

The overview uses six columns:

1. Name
2. System
3. Application
4. Last Checked
5. Status
6. Action

System and Application indicators reflect only enabled checks. The desktop table uses a stable distribution and should scroll rather than compress controls into neighbouring cells.

## System Checks Mobile

Phones use the shared compact two-column overview pattern focused on Name and Status. The Name column is left-aligned; the Status header and status pill are centered in the status column. Detail pages preserve the semantic order Checks → Updates → Application → History and use full-width cards.


## Long-running Actions

Long-running maintenance actions must not leave the browser dependent on a POST-only action URL. The visible browser location should remain on, or return to, a normal GET page while progress feedback is shown. Refreshing during or immediately after an action must never expose a raw framework error such as HTTP 405 or 422 and must never unintentionally repeat the POST.

Use the existing spinner/progress treatment for actions that take noticeable time. `Check All` actions use the same button spinner pattern across overview pages. A grouped check that continues independently of the browser must keep its running state server-side, so reloading the overview restores the spinner and keeps it visible until the operation actually finishes. POST action endpoints that may temporarily become the browser location must have a safe GET fallback to the relevant overview/detail page. Static action names such as `check-all` must be registered before dynamic integer routes such as `/{device_id}`.

## Destructive Actions

Permanent Inventory deletion uses an in-application confirmation dialog that names the device, explains that deletion cannot be undone and requires explicit acknowledgement.

Destructive actions remain visually distinct from normal actions. Removing an account picture is not treated as a destructive account operation.

## Maintenance

Maintenance is intentional and non-actionable. It must not make the global Dashboard Critical or Attention by itself. Low-level transport exceptions are diagnostic data, not primary UI copy for a host already clearly Offline or in Maintenance.
