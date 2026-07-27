# Task brief: OneDrive photo-GPS as a travel-log aid

**Audience:** an LLM assistant picking this task up later, with no memory of the
originating conversation. This file is self-contained — read it as the full spec.

**Status:** optional / "nice to have". Explicitly NOT a blocker for the main
project. Only pursue if a genuinely low-effort path exists (see "Definition of
done" and "Anti-goals").

---

## 1. Background: the wider project

The user maintains a personal travel log as a map (originally built in Google My
Maps, later migrated to **uMap** on OpenStreetMap). It records places he has
visited and routes he has travelled.

- **Points** (~715 today, expected to grow): categorized into layers such as
  `Places`, `Hotels`, `Airports`, `Lived`, `Transport`, `Football_stadiums`,
  `Ski`, `Border_Crossing`, `Car_Rentals`. Point names carry a country-code
  prefix (`"AT - Vienna ..."`) and some descriptions carry a year.
- **Routes** (~293): `LineString`s split by mode into layers `drive`, `ride`,
  `train`, `waterways`. Built in an external OSM router (e.g. GraphHopper) and
  uploaded manually.

The agreed architecture going forward is **flat files as the source of truth,
map as a generated view**:

- `points.csv` — one row per point (`layer, name, country, lat, lon, date, description`).
  This is the editable database. Points are cheap (~0.3 MB for all of them).
- `routes/` — GPX/GeoJSON files, one per route, dropped in as exported.
- A Python build script converts these into per-layer GeoJSON, simplifies route
  geometry, normalizes country codes, and the map (uMap, via cached "remote
  data" layers pointing at GitHub-hosted GeoJSON) renders them.

**Guiding philosophy: the log is CURATED, not a firehose.** The user
deliberately decides what is meaningful and pins it by hand. Any photo-GPS work
must respect this — the goal is to *assist* curation, never to auto-dump every
location the phone ever recorded.

---

## 2. The specific sub-task

The user has a **large photo library on OneDrive**, and many photos carry GPS
coordinates in EXIF metadata. Question: can this be leveraged, cheaply, to help
maintain the travel log?

The naive idea — "map every geotagged photo" — is explicitly REJECTED because:

1. It contradicts the curated philosophy (it's a firehose).
2. The volume would be enormous and hurt map performance.
3. Most of those points are noise (home, commute, duplicates).

So the task is to find a **low-hanging** version that adds value without those
downsides.

---

## 3. Recommended approach (the "low-hanging" version)

Treat the photos as a **memory/lookup aid**, not as a map layer. Concretely:

### Step A — Extract, don't display

Write a small Python script that walks a **locally-synced OneDrive folder** (see
§4 on why local, not the API), reads GPS + timestamp from each photo's EXIF, and
writes a single intermediate file:

`photo_locations.csv` with columns:

| column   | meaning                                   |
|----------|-------------------------------------------|
| date     | photo timestamp (EXIF `DateTimeOriginal`) |
| lat      | decimal degrees                           |
| lon      | decimal degrees                           |
| filename | source path (for the user to open it)     |

Tooling options: `Pillow` (`PIL.ExifTags`) for a pure-Python route, or shelling
out to `exiftool` if it's available (more robust across formats/HEIC). Handle
photos with no GPS by skipping them silently.

### Step B — Two ways the user consumes it (both optional, user's choice)

1. **Lookup mode (primary, safest).** When the user is adding a trip from
   memory, they grep/filter `photo_locations.csv` by date to recover *where* and
   *when* they were — then hand-pin the meaningful stop into `points.csv`. The
   photos never enter the map; they just jog the memory and supply accurate
   coordinates/dates. This fits the curated philosophy perfectly.

2. **Optional "forgot to log" heatmap.** Optionally generate ONE extra GeoJSON
   heatmap layer from `photo_locations.csv`, shipped **off by default**
   (`displayOnLoad: false` in uMap). Its only job is to reveal clusters of
   places the user visited but never pinned, so he can decide whether to curate
   them. It must stay visually and logically separate from the real curated
   layers.

---

## 4. Implementation notes / gotchas

- **Access: prefer a locally-synced folder over the Microsoft Graph API.** If
  the OneDrive folder is synced to disk (Windows/Mac OneDrive client, or
  `rclone`), the script just reads local files — no auth, no API. Only reach for
  the **Microsoft Graph API** (`/me/drive`) if local sync is impossible; it adds
  OAuth/app-registration overhead that likely breaks the "low-effort" test.
- **EXIF GPS format.** Coordinates are stored as degrees/minutes/seconds with
  N/S/E/W refs; convert to signed decimal degrees. Watch the ref signs
  (S and W are negative).
- **Accuracy.** Phone GPS EXIF is typically ~10–50 m accurate — fine for
  "which town/venue", not for precise addresses.
- **Missing/stripped GPS.** Many photos won't have GPS (screenshots, edited
  copies, privacy-stripped uploads). Expect a large fraction to be skipped.
- **HEIC/HEIF.** iPhone photos are often HEIC; `Pillow` may need
  `pillow-heif`, or use `exiftool`.
- **Scale.** The library is large — process incrementally and cache results
  (e.g. skip files already in `photo_locations.csv`) so reruns are fast.
- **Privacy.** `photo_locations.csv` is a detailed movement history; keep it
  local / out of any public repo. This matters especially given the log already
  contains sensitive data elsewhere (the `Lived` layer holds home addresses and
  at least one named real person — unrelated to this task, but a reminder that
  map visibility settings deserve a check).

---

## 5. Definition of done

A working `extract_photo_gps.py` that turns a local photo folder into
`photo_locations.csv`, plus a short note to the user on how to use it in lookup
mode. The heatmap layer is a stretch goal, not required.

## 6. Anti-goals (do NOT do these)

- Do NOT auto-add photo points into the curated `points.csv` or any real layer.
- Do NOT build a full Graph API / OAuth integration unless local sync is
  genuinely unavailable.
- Do NOT dump the full photo history onto the map as visible points.
- Do NOT let this block or complicate the core CSV→GeoJSON→uMap pipeline.

---

## 7. One-line summary

Extract `date, lat, lon, filename` from geotagged photos in a locally-synced
OneDrive folder into a private `photo_locations.csv`, used mainly as a
date-based memory aid for hand-curating the travel log — with an optional,
off-by-default heatmap of "places visited but not yet pinned". Keep it cheap;
skip it if it isn't.
