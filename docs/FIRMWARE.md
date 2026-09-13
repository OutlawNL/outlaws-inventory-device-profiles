# Firmware monitoring

Outlaw's Inventory has two complementary firmware paths.

## Device Profile path

When Vendor + Model match an installed Device Profile, the profile is authoritative for the firmware check. The profile contains product knowledge — source location and declarative extraction instructions — while the application core provides only generic parser capabilities.

A new supported device should normally be added by publishing a new/updated Device Profile and catalog, without changing the Outlaw's Inventory application.

## Generic path

If no Device Profile matches, firmware monitoring continues to support the existing generic workflow. Configure:

- **Firmware URL** — the vendor/support page OI should inspect.
- **Firmware Filter / Keyword** — optional model/product identifier used to focus the generic parser on the relevant part of a shared page.

The generic parser remains intentionally available even as the Device Profiles catalog grows.

As of v0.18.4, declarative PDF profiles require catalog v4 scope/title rules. PDF contents are authoritative; missing dates are not replaced with download-page dates. See DEVICE_PROFILES.md.
