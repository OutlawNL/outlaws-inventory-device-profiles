# Device Profiles

Device Profiles separate reusable product knowledge from the Outlaw's Inventory application core.

## Architectural goal

**Reuse first. Specialize only when necessary.**

**New device support should normally require only a Device Profile update, not an Outlaw's Inventory application release.**

The core application should be able to remain unchanged while the public catalog grows from a few profiles to hundreds or thousands. The daily catalog sync makes new and updated profiles available to an existing compatible OI installation.

The core therefore contains generic, safe parser capabilities. A Device Profile describes:

1. **What is it?** — vendor, model, aliases and category.
2. **Where is the firmware information?** — official support/download page or another declared source.
3. **How should that source be read?** — document discovery hints, exact labels/patterns for firmware version and date, section boundaries for What's New, and validation rules.

Device-specific parser logic does not belong in the core when these declarative capabilities are sufficient.

## Generic parser remains the fallback

Device Profiles do not replace the existing generic firmware parser.

- Exact Device Profile match: use the known, tested profile instructions.
- No Device Profile match: the user can provide a Firmware URL plus an optional Firmware Filter / Keyword; the generic parser continues to work as before.
- A profile is never required merely to keep an Inventory item.

This preserves the useful "give OI a good firmware page and let it find the version" workflow for devices such as Zappi and many ordinary vendor pages.

## Core capabilities versus profile knowledge

The application core may implement reusable capabilities such as:

- HTTPS HTML fetching;
- HTML/link discovery;
- PDF download and text extraction;
- JSON/XML parsing in future capabilities;
- exact label lookup;
- constrained regular-expression value extraction;
- date parsing;
- extracting text between configured section headings;
- result/version validation;
- safe fallback and error reporting.

A Device Profile provides only the declarative instructions for those capabilities. For example, a PDF-based profile can state that the firmware value is found after `Aircraft Firmware:` or `Firmware Version:` without adding model-specific Python code.

Only a genuinely new *generic source/parser capability* should require a future OI application release.

## User experience

The normal Inventory workflow remains unchanged. A user enters Vendor and Model. Once both contain enough information, OI checks the locally cached catalog.

- Exact match: the Firmware section shows `Device Profile found`; firmware monitoring is managed by that profile.
- No match: firmware URL and optional Firmware Filter / Keyword remain available for generic parsing.
- Existing Inventory devices are matched dynamically too; no migration or manual profile attachment is required.

## Trusted catalog and synchronization

The official catalog is hosted in:

`OutlawNL/outlaws-inventory-device-profiles`

OI caches the lightweight catalog index under the persistent data directory. A repository outage does not disable already cached profiles and does not make device health Critical.

The catalog index contains matching metadata only: identity/aliases, profile version, runtime profile URL and SHA-256 hash. Full profile parser instructions are **not** downloaded for every catalog entry. Runtime profiles are downloaded on demand only when they are needed. When an Inventory item matches an entry, OI downloads and hash-verifies that one runtime profile and caches it locally. Existing Inventory items are reconciled during the daily sync. Profiles no longer used by any Inventory item are removed from the local installed-profile cache.

The catalog is checked before the configured daily Update Checks. Settings → Device Profiles also provides **Check Now**. Settings distinguishes **Available Profiles** in the catalog from **Installed Profiles** actually used by this OI instance, and shows Last Checked, Last Updated, Profiles Updated and an expandable list of installed profiles.

`Last Checked` changes after every successful catalog check. `Last Updated` changes only when the cached catalog/profile revisions change.

## Profile and catalog versioning

Versioning is intentionally separate:

1. `schema_version` — format of Device Profiles.
2. `profile_version` — revision of one profile.
3. detected firmware version — version installed/available on the actual device.
4. `catalog_version` — revision of the generated runtime catalog.

A website/parser-rule correction normally increments only the relevant `profile_version` and `catalog_version`, not the OI application version.

## `release_notes_pdf` capability

v0.18.2 introduces the generic declarative `release_notes_pdf` strategy.

The core can:

1. fetch the profile's HTML source page;
2. normalize links embedded in ordinary HTML or escaped page data;
3. locate/rank a PDF using configured document-title and URL hints;
4. download the PDF and extract text;
5. find the exact configured firmware label and extract the value with the profile's constrained pattern;
6. find the configured date label and parse its declared format;
7. extract What's New between configured start/end headings;
8. validate the resulting firmware version.

The core does **not** know that `DJI Neo 2 Firmware:` belongs to a Neo 2 or that `Firmware Version:` belongs to an Osmo Action 4. Those facts live in the profiles.

Initial profiles exercising this capability:

- DJI Neo 2
- DJI Mini 4 Pro
- DJI Mini 5 Pro
- DJI Osmo Action 4

The older experimental `dji_release_notes_pdf` profile strategy remains accepted temporarily for backward compatibility with a cached v1 catalog, but new profiles should use `release_notes_pdf`.

## Security model

Profiles are declarative data only. They cannot contain or execute Python, JavaScript, shell commands or arbitrary templates. The core application implements a fixed allow-list of capabilities and validates the catalog before caching it.

Profile source URLs must use HTTPS. Profile patterns and extraction rules are data supplied to constrained core functions; profiles cannot introduce a new network protocol or arbitrary executable path.

The current catalog uses HTTPS and a SHA-256 manifest. Cryptographic signing of trusted catalog releases remains required before broad community contribution is enabled.

## Evolution

The profile system remains an adapter layer beside existing generic and legacy providers while it matures. Existing checks are not removed merely because profiles exist. Proven legacy device-specific knowledge can later be moved from the application into profiles where the generic capability set permits it.

Future phases include additional generic strategies, Custom Profiles, profile submission/review, signed trusted catalog releases, corroborated multi-source checks and optional AI-assisted authoring. AI may propose profiles; trusted publication remains deterministic and human-controlled.

## Scale rule

A catalog containing hundreds or thousands of profiles must not cause an OI instance to download hundreds or thousands of parser definitions. Catalog synchronization is deliberately cheap; full profiles are demand-loaded only for devices the installation actually owns.

This means an installation can stay on a compatible core release for a long period while the public catalog gains new devices. A core release is only required when a future profile needs a genuinely new generic parser capability.


## v0.18.4 strict document extraction

The generic `release_notes_pdf` engine uses pdfplumber, not the legacy PyPDF text-window heuristics. Profile-specific knowledge stays declarative:

- `discovery.item_selector`: CSS selector for one download entry (never a whole download list).
- `discovery.title_contains`: normalized visible title alternatives; at least one must match.
- `discovery.url_contains`: all configured substrings must match the link.
- `discovery.url_excludes`: reject links containing any listed substring.
- `discovery.url_pattern`: regular expression for language/filename constraints.
- `validation.document_titles`: exact normalized first-line document titles.
- `extraction.scope`: `first_release_first_page`.

Discovery returns a URL only when exactly one distinct candidate survives. Repeated copies of the same link are deduplicated. No URL date or relevance score breaks ambiguities. A new product can use another selector and labels without adding vendor-specific core logic.

The engine reads page one with pdfplumber. It accepts one exact label/value row per field before the first declared What's New heading. It never searches following lines for an unrelated controller/app version. Date formats must parse as real calendar dates. Missing fields stay empty (Unknown in the interface). What's New ends at its declared terminator; no terminator means no summary. First-page-only extraction deliberately fails closed for unrecognized layouts; a spatial fallback is not implemented in this release.

Deploy application v0.18.4 first, then catalog v4, then synchronize with Check Now. Old cached profiles lacking scope/title rules return Unknown until updated. Do not deploy catalog v4 to an older runtime. Snapshot AppServer-02 before acceptance installation; server-side dependency installation and rollback are not proven by local extraction tests.


## v0.18.5 creation lifecycle

The add form calls the match endpoint while vendor/model are entered. That endpoint matches the catalog and ensures the full profile is downloaded, hash-verified and cached. Thus the full profile can already exist before Save. Saving reuses the cached version; scheduled synchronization updates used profiles and prunes unused ones.

After a new device has been saved, a one-time check runs when a firmware URL is configured (including one supplied by the matched profile), the category enables firmware and monitoring is supported. Save waits for the result, then shows the saved device. A failure does not undo creation. This initial check does not change the recurring Auto Check preference or send notifications by itself. Existing first-run/server redirects remain unchanged. The next edit/save does not repeat it.

Catalog v5 adds Goggles 3 and remains compatible with v0.18.4. Each device keeps its own identity/source/label rules; the engine is shared across profiles.


## v0.18.6 declarative extensions

Catalog v6 requires app v0.18.6 for its new rules. Upgrade the app before synchronizing this catalog. Existing catalog v5 profiles remain compatible.

- `extraction.pdf_text.x_tolerance` sets PDF word spacing (0.1–5 points).
- `version.header_pattern` and `release_date.header_pattern` match only the validated first release header. Exactly one capture is required; absence or ambiguity yields Unknown.
- `first_release_for_target` checks at most `max_pages` pages. It skips only release pages with recognized `skip_when_labels` for a different primary component, a matching document title and a valid date. A malformed target release stops extraction, rather than falling back to an older release.
- `html_release` reads a uniquely matched product title/header using profile selectors. Release version/date use declared labels and date formats. Summary comes only from one history entry whose version matches the product header.
- Model names, URL/title rules, labels and HTML selectors belong in external profiles. The app implements transport, parsing, validation and comparison.

Manual overrides retain existing behavior. Lack of a release page is not evidence that the installed version is the manufacturer's latest version. Manufacturer discontinued status is not a promise that firmware updates have ended.
