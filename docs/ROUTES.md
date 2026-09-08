# Route housekeeping

## Install this update

Close the travel editor and Excel. Extract the upgrade ZIP, run Install.cmd,
and select your EXISTING project folder. Open Start.cmd in that folder.
No new map, account, repository or map-layer URLs are required. The installer
does not replace your CSVs or GPXs, and preserves an existing map_config.json.
On first launch, missing CSV columns are added after making a backup.

## One new GPX, step by step

1. Open Start.cmd and select Routes.
2. Click Add GPX, then Choose GPX. Select your full downloaded recording.
   You do not have to move or rename it first.
3. Enter the journey name, transport mode, date and any notes. Select an
   accuracy label if known. Leave Map detail at Standard to start.
4. Click Save locally. The program archives the exact original bytes, creates
   a lightweight GPX and adds the journey to routes.csv. The confirmation
   shows original/map point counts, original distance and altitude range.
5. Repeat for your other files. Use Check data, then Build files.
6. Publish to GitHub as before, or import the generated layer if you use manual
   uMap updates. Inspect the route on your existing map before saving a manual
   import. Publishing is never done by importing a GPX into the editor.

## Where the files live

| File/folder | Your role |
|---|---|
| data/routes_original/ | Untouched originals. Include in your personal backups. |
| data/routes/ | Active lightweight GPXs for newly imported routes; old routes remain unchanged until re-cleaned. |
| data/routes.csv | Names, dates, modes, notes, source links and computed statistics. |
| build/ | Generated GeoJSON layers for the map. Never edit by hand. |
| backups/ | Previous CSVs, replaced/deleted active GPXs and software backups. |

Archive filenames are SHA-256 hashes of the original contents. The CSV links
each journey to its archive. This avoids filename collisions and catches an
exact duplicate import even if you rename the downloaded file. It does not
detect overlapping recordings or the same route exported with different bytes.

## Change, replace or delete

- Edit changes metadata only. It does not alter geometry or recompute the
  recorded distance from a simplified line.
- Replace GPX selects a better recording for the SAME journey. Identity and
  metadata survive, statistics refresh, and both archived originals remain.
- Re-clean opens the selected journey using its archived original. Choose
  Fine for more detail, or All points to remove metadata without reducing
  point count. Save, build and publish again. Re-clean never uses the previous
  simplified result when an original is registered.
- For an old route without an archive, Re-clean archives its current GPX first.
  This cannot restore details already removed from that old file. Use Replace
  GPX when you have a more complete original elsewhere.
- Delete removes the CSV entry and active GPX after backup. Archived originals
  are deliberately retained. Build and publish to remove it from the map.

Changing Map detail applies only when importing, replacing or re-cleaning.
There is no automatic bulk conversion of existing routes.

## What cleaning does

It removes timestamps, per-point altitude, extensions and unrelated metadata
from the active copy, and simplifies each line segment independently. Recording
gaps stay separate. It keeps segment endpoints and retained coordinates at
their numeric precision. The builder does not simplify imported routes again.

Standard uses your existing map_config.json simplify_degrees value, normally
0.0001 degrees. Fine uses one fifth of that tolerance. This is the existing
angular-coordinate simplification method, not a uniform metre-based accuracy
guarantee. All points disables point reduction. File reduction depends on the
recording; a sparse track may hardly shrink. Inspect tight bends at high zoom.

Distance is calculated from the original track's latitude/longitude segments
before simplification, without elevation. Minimum/maximum altitude come from
valid numeric elevation samples in the original, including singleton segments.
Missing elevation is left blank, never invented as zero. These extrema are
reported samples, not corrected terrain heights: GPS spikes may affect them.
No automatic altitude correction, ascent calculation or road snapping is done.
GPX tracks and routes are supported; a file containing both contributes both.
Choose a file containing just the representation you intend to log.

The CSV stores original_points, map_points, original_file, original_sha256,
simplify_degrees, min_altitude_m and max_altitude_m. Imported distance_km is the
preserved original distance. GeoJSON contains distance and altitude summaries,
not timestamps, per-point elevations or archive paths. Whether altitude fields
are visible in a popup depends on that layer's existing uMap popup settings;
the editor displays them without any map configuration change.

## Backup and privacy rules

Back up data/ (INCLUDING routes_original), map_config.json and useful backups/
to your usual backup destination. Originals are excluded from Publish to GitHub
and ignored by Git. A fresh clone can display/build imported routes from the
light files and saved statistics, but cannot re-clean them until you restore
their originals. Check data warns about missing archives.

Deleting or replacing a journey does not erase its original archive or backup.
There is no automatic archive purge. A failed save can leave an unused archived
original; this is intentional, and it does not appear on the map. Ignore rules
do not remove anything previously committed to Git or erase existing history.
Public map geometry still reveals the route, including its endpoints.

Close the editor before manually editing CSVs, and close Excel before reopening
it. Edit names, dates, mode, notes and source as needed. Leave IDs, file links
and computed statistics alone; use Replace GPX or Re-clean to update those.
Do not manually overwrite lightweight GPXs for an archived route: that would
leave its original statistics out of sync. Never edit an archived original.
