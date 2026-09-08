# Upgrade notes — September 2026

## Installation

The downloadable package is an **upgrade**, not another copy of your database.
Extract the ZIP, run `Install.cmd`, and select your EXISTING project folder
(the one containing `data/points.csv`, `data/routes.csv` and `scripts/`).

The installer backs up the files it replaces under `backups/upgrade-*`. It
updates scripts, launchers, documentation and dependency requirements. It
creates `map_config.json` only when absent, and merges local-output exclusions
into `.gitignore`. It does not overwrite CSVs, GPX files, generated layers, the
original uMap backup or Git settings. It does not push anything.

Then double-click `Start.cmd` in your existing project. If required, run
`setup.cmd` once. The editor's first launch adds record IDs and the optional
route source and import-statistics columns, with a CSV backup. Normal use is
described in README.md and docs/ROUTES.md.

To roll back the software, close the editor and restore the previous files
from the installer backup. The install manifest lists new files that did not
exist before. CSV backups from first launch are separate under `backups/edit-*`.

## Route archive update

- Add GPX and Replace GPX now keep byte-exact originals in data/routes_original/.
- Active GPXs discard unused metadata and use the existing simplification method.
- Re-clean regenerates Standard, Fine or All points detail from the original.
- Original distance, minimum/maximum altitude and point counts are stored in CSV.
- Imported routes are not simplified again during builds. Legacy display geometry
  stays unchanged; newly cleaned routes retain numeric coordinate precision.
- Exact duplicate imports are rejected. Failed saves preserve the previous record
  and active file. Replacement/deletion never removes archived originals.
- Original archives are excluded from publishing and require personal backups.
- No CSV or GPX data is bundled in the installer. Existing routes are not bulk-converted.

## What changed

- A searchable desktop window for places and routes, plus explicit GPX replacement.
- Stable record IDs, local edit backups and an OS-managed single-project lock.
- The CSV route index controls inclusion. Unindexed files cannot reappear as trips.
- Strict validation of missing sources, CSV shape, coordinates, dates and duplicate IDs/files.
- GPX track segments remain separate, and GPX route points are supported.
- Distances are calculated before the original display simplification.
- The build is prepared before replacing output. Empty layers are retained as empty
  files to clear old remote data. On ordinary build/export write errors, the prior
  build is restored. As with ordinary filesystem operations, abrupt power loss
  during a directory swap may require restoring `backups/previous-build`.
- Place search requires selecting a result; country filters the search.
- Publishing stages an explicit list of project files, checks every Git step,
  and can retry an earlier unpushed commit even when no new files changed.
- The destructive initial migration entry point is retired.
- Same map URL and 13 GeoJSON filenames; unchanged legacy display geometry.

## Verification performed

- Route-archive update: all 32 automated tests passed, including exact archives,
  duplicate imports, repeated cleaning, missing/corrupt archives, write failures,
  preserved original statistics and exclusion of originals from Git publishing.
- Rebuilt a temporary copy of all 715 places and 293 routes and compared all 13
  layer geometries with the previous upgrade output: unchanged.
- On the largest supplied active GPX, cleaning reduced 496,209 bytes to 309,832
  bytes (37.6%) and 9,332 points to 7,713. This example is not a guarantee for
  other recordings. Source files were not modified by this check.

- Recovered the omitted 290 GPX files from the archive's bundled Git objects for
  testing. These recovered data files are not included in this upgrade and do
  not overwrite your local originals.
- Validated all 715 places and 293 routes.
- Verified ID migration preserved every original CSV field value and row.
- Rebuilt all 13 layers: their display geometries match the supplied generated
  layers exactly. Added IDs slightly increase output size to about 3.64 MB.
- Regression tests cover replacements, deletions, orphan files, missing sources,
  invalid coordinates/dates, segment gaps, route points, CSV locales, backups,
  failed writes, repeatable builds, project locking and publishing failures.
- Publishing was tested against a temporary LOCAL Git remote. Your real remote
  and live uMap map were not changed.

The environment used for development is headless Linux. The Python backend and
Git workflow were executed; the Tk desktop window and Windows .cmd/PowerShell
launchers could not be run interactively here. The first launch on Windows is
therefore the remaining platform check. Online place lookup was not exercised
against the live geocoding service.

## Scope

This keeps the existing architecture. No database service, new map, account,
website or hosting migration is introduced. The full-map local export uses
style settings from the supplied original backup; current hosted layers retain
their own styling when they use the generated remote GeoJSON.
