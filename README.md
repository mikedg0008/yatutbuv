# Yatutbuv — your travel log

Keep your existing uMap map, account and Git repository. This upgrade makes the
local records easier to maintain; it does not replace the map.

**Open the editor: double-click `Start.cmd`.** If Python or Shapely is missing,
run `setup.cmd` once. It creates a local Python environment and uses your
existing Python installation (Python 3.10 or newer, with Tcl/Tk).

## The normal workflow

1. Open **Start.cmd**.
2. Choose **Places** or **Routes**. Use **Find** to locate an existing record.
3. **Add**, **Edit**, **Delete**, or select a route and **Replace GPX**.
4. Click **Build files** to check the data and generate the map layers.
5. Use **Publish to GitHub** if your uMap layers already read the hosted files.
   Otherwise use the manual update instructions below.

Everything you save in the editor is initially local. Opening the editor,
saving a record or building files does not change the live map. Publishing
requires clicking the publishing button and confirming it.

## Places

Double-click a row to edit it. Enter latitude/longitude, or enter the place
name and optional country, then **Find coordinates** and choose the correct
result. A result is never silently selected for you.

Dates may be blank, a year (`2026`), or a full date (`2026-09-07`). The tool does
not invent dates for old visits. One existing place remains one record: use
the description for additional visit dates if that is your current convention.

## Routes

**Add GPX:** choose a complete journey GPX, give it a name, select a mode and save.
The original is archived unchanged in `data/routes_original/`; a cleaned GPX
goes to `data/routes/`. Distance and altitude summaries come from the original.
See [Route housekeeping](docs/ROUTES.md) for the full step-by-step workflow.

**Re-clean:** regenerate a selected route from its original with Standard,
Fine or All points detail. Old routes are only converted when you choose this.

**Replace:** select an existing journey, click **Replace GPX**, choose the
better file and save. Its ID, name, date and notes stay attached to that journey.
The previous GPX is backed up and removed from the active source folder.

**Edit:** change the name, mode, date, notes or accuracy label without choosing
a GPX. The geometry stays the same.

**Delete:** removes the journey from the index and active GPX folder, after a
local backup. Build and publish to remove it from the generated map too.

Optional accuracy labels: `recorded`, `reconstructed`, `approximate`. Existing
routes start blank; the upgrade does not guess their provenance.

Distances shown in the editor, map and statistics are calculated from GPX
coordinates. Separate recording segments are not connected across gaps. GPX
track points (`trkpt`) and route points (`rtept`) are supported. Elevation extrema
are retained for imported routes; elevation and elapsed time are not used in
distance calculations. These are geometry-derived distances, not odometer
readings. GPX files containing both tracks and routes contribute both; use a
file containing just the representation you intend to log.

## Which files matter?

| Location | Purpose |
|---|---|
| `Start.cmd` | Your normal entry point |
| `data/points.csv` | Editable places |
| `data/routes.csv` | Authoritative list of included journeys |
| `data/routes_original/*.gpx` | Full originals, local only; include in personal backups |
| `data/routes/*.gpx` | Lightweight imported routes and unchanged legacy routes |
| `build/*.geojson` | Generated layers, with the same names as before |
| `build/stats.md` | Current counts and calculated distances |
| `exports/yatutbuv.umap` | Optional local full-map import file |
| `backups/` | Backups made before edits and the previous successful build |
| `map_config.json` | Map URL, layer names and export styling |
| `scripts/`, `tests/` | Implementation; normally leave these alone |

Do not edit `build/`. It is generated. The builder uses the route index;
unindexed GPX files are ignored with a warning. Missing indexed GPX files stop
the build before output changes. Empty layers are exported as empty GeoJSON
so old records cannot survive in stale output files.

The first editor launch adds stable IDs and a route accuracy column to old
CSVs, after backing them up. It preserves existing rows, values and extra
columns. You may still edit CSVs directly. Keep the ID column unchanged, use
UTF-8, and close Excel before editing in the desktop window. Both comma and
semicolon separators and decimal dots/commas are accepted. Close the editor
before editing CSVs manually. For archived imports, CSV `distance_km` retains
distance calculated BEFORE cleaning. Builds use this saved value; legacy routes
still calculate it from their active GPX. Leave computed fields and file links
alone and use Replace GPX or Re-clean to update them.

## Updating the same uMap map

Map: https://umap.openstreetmap.fr/en/map/yatutbuv_1438641

**Already using remote-data layers?** Continue with the existing setup. All 13
GeoJSON layer filenames are retained, including `Lodge`. Publish commits the
known project files and pushes to the existing Git remote. Once hosting has
updated, refresh the map. The tool reports a successful Git push, not proof
that hosting has deployed or uMap has fetched it.

**Still using embedded layers?** A Git push cannot update those automatically.
The supplied original backup has embedded layers; it does not establish the
current live configuration. You can keep the same map and choose either:

- **Manual updates:** build, then open the map in edit mode. Import the relevant
  `build/<layer>.geojson` into the corresponding existing layer, using the
  replacement option rather than appending. Check the result before saving.
  This preserves that layer's existing style. Download a fresh full-map backup
  before the first update. `Output folder` opens `exports/`; `build/` is beside it.
- **Automatic updates:** in each existing layer's Remote data settings, use its
  existing GitHub Pages URL for `build/<layer>.geojson`, format GeoJSON. This is
  a one-time connection on the same map, not a new account or map. Start with
  one layer and check it before changing the rest.

`exports/yatutbuv.umap` is available when a whole-map import is wanted. Its
styling comes from the supplied backup (with the local `Lodge` name), so use
per-layer imports if you have since changed map styles. Do not append the
full-map file to an already populated map: it can duplicate layers. No script
performs imports or changes live uMap settings for you.

See uMap's user documentation: https://discover.umap-project.org/

## Backups and undo

Before each editor save/delete, the affected CSV and old GPX (when relevant)
are copied under `backups/edit-<timestamp>-<suffix>/`, using their original
relative paths. To undo, close the editor and copy those files back to the same
relative paths in the project, then rebuild. A replacement GPX left unindexed
after undo is ignored. Restoring an older CSV restores the whole table to that
time, so it also undoes later edits to that table. Git remains your long-term
history. Backups are local and can be copied to your normal backup storage.

The publishing tool explicitly excludes `backups/`, `exports/` and
`build_private/` and `data/routes_original/` from staging. Back up originals
separately: Git publishing is not their backup. This does not remove files already committed
there or erase Git history. The existing `Lodge` layer remains included in
`build/`, just as in the supplied project; its contents match the old `Lived`
layer. Publication is not a privacy filter.

## Troubleshooting

- **Missing GPX:** restore the named file, or deliberately remove its row from
  `routes.csv` if that journey should no longer be logged. Do not rerun the
  original migration. It is disabled to protect current records.
- **Project already open:** close the other editor/command and retry. Locks are
  released automatically when the owning process exits.
- **Git push failed:** local data and the build remain. Check connectivity or
  existing Git credentials, then retry Publish. There is no automatic force
  push, merge or repository reconfiguration.
- **Unrelated files staged:** finish or unstage that separate Git work first.
- **Map unchanged after push:** check deployment and the layer's Remote data
  settings. Embedded layers require an import.
- **Python/Tk/Shapely error:** run `setup.cmd`; if Python itself is absent, use
  your normal Python installer with Tcl/Tk enabled. Git must already work for
  publishing, as in your previous setup.

Optional commands (close the editor first):

```text
python scripts/build_map.py --check
python scripts/build_map.py
python scripts/publish.py
python -m unittest discover -s tests -v
```

If using the local environment, replace `python` with
`.venv\Scripts\python.exe`. The old `add_point.py` command remains available;
address searches now ask you to choose the result. Photo-GPS extraction remains
optional and separate from this upgrade.
