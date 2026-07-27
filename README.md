# yatutbuv — travel log project

A small, fast, OpenStreetMap-based travel log. **Flat files are the database;
the uMap map is a generated view that auto-refreshes from GitHub.**

Your original 24 MB uMap map is now ~3.6 MB of clean data, split so it's easy
to edit and cheap to render. (The old "Lived" layer is deliberately not part of
this project — maintain those pins by hand in uMap if you want them.)

```
yatutbuv/
├─ data/                      ← YOUR SOURCE OF TRUTH (edit these)
│  ├─ points.csv             ← one row per place (686 rows)
│  ├─ routes.csv             ← index of routes (293 rows: name, mode, date, km)
│  └─ routes/                ← one GPX per route (drop new ones here)
├─ build/                     ← generated GeoJSON (this is what gets published)
├─ scripts/
│  ├─ extract_from_umap.py   ← one-time migration (already run — don't run again)
│  ├─ build_map.py           ← run after every edit
│  └─ add_point.py           ← quick "search a place → add a row" helper
├─ backups/                   ← your original .umap (kept LOCAL, never pushed)
├─ docs/onedrive_photo_gps_task.md  ← notes for the optional photo-GPS idea
├─ requirements.txt
└─ .gitignore
```

## 0. One-time setup

```bash
cd C:\Users\mykha\OneDrive\Car\yatutbuv
pip install -r requirements.txt      # just needs "shapely"
python scripts\build_map.py          # regenerate build/ from the data
```

## 1. Daily workflow

**Add a place** — edit `data/points.csv` (add a row), or:

```bash
python scripts\add_point.py --layer Hotels --country AT "Hotel Sacher Vienna"
python scripts\add_point.py --layer Places "Historic Centre of Vienna" --date 2025
python scripts\add_point.py --layer Ski --country CH "Titlis" --lat 46.77 --lon 8.43
```

**Add a route** — export it as **GPX**, drop the file into `data/routes/`, then
add one line to `data/routes.csv`:

```
file,mode,name,date,distance_km,notes
2027__Krakow-Vienna.gpx,drive,2027 Kraków–Vienna,2027,,
```

Leave `distance_km` blank; the build fills it in. `mode` ∈ {drive, ride, train,
waterways}.

**Rebuild** after any change:

```bash
python scripts\build_map.py
```

## 2. Publish to GitHub (so uMap auto-refreshes)

Nothing sensitive lives in this project anymore, so the whole thing can go in
one **public** repo — except `backups/`, which still holds the original .umap
with the old private data and is git-ignored.

Once:
1. Create a **public** repo (e.g. `yatutbuv`) and push this folder.
   Verify `git status` never lists anything under `backups/`.
2. **Settings → Pages → Deploy from a branch → main / root.**
   Files are then served at
   `https://<your-user>.github.io/yatutbuv/build/<Layer>.geojson`
   (GitHub Pages sends the `Access-Control-Allow-Origin: *` header uMap needs —
   public sites only).

Every update after that:
```bash
python scripts\build_map.py
git add -A && git commit -m "trip update" && git push
```

## 3. Wire uMap to the published data (one-time, ~15 min)

For each layer (Places, Hotels, Airports, Transport, Football_stadiums, Ski,
Border_Crossing, Car_Rentals, drive, ride, train, waterways):

1. Edit the layer → **Remote data**.
2. **URL**: `https://<your-user>.github.io/yatutbuv/build/<Layer>.geojson`
3. **Format**: geojson. Leave "dynamic" **off**.
4. Delete the old inline features (the remote file replaces them).
5. **Point layers** → set display mode to **Clustered** (keeps it fast as it grows).
6. **Route layers** → optionally set a minimum zoom so they don't draw at
   whole-continent view.

## 4. Gotchas worth knowing

- **Excel + European locale**: opening `points.csv` in Excel may save it with
  `;` separators / comma decimals. The scripts tolerate that. (LibreOffice or
  Google Sheets avoid it entirely.)
- **OneDrive + Git**: a `.git` folder syncing through OneDrive can occasionally
  conflict. If git complains about locked objects, move the repo out of the
  OneDrive path.
- **Migration fixes applied**: `UK`→`GB` (16 pts) and `NE`→`NL` (Schiphol,
  Eindhoven). Years pulled from descriptions into the `date` column. Route
  geometry simplified for display; the full original is in `backups/`.

## 5. Housekeeping rules

1. **One trip = one complete, real journey.** Never truncate a route to skip an
   overlap with another; never let one record depend on another.
2. **Edit `data/`, never `build/` or the uMap layers directly** — `build/` is
   disposable output.
3. **Controlled vocabularies**: `country` = ISO 3166 alpha-2; `mode` ∈
   {drive, ride, train, waterways}; `date` = `YYYY` or `YYYY-MM-DD`.
4. **Date everything you can** — it's the axis for every stat.
5. **Store routes as exported; let `build_map.py` simplify.** Don't pre-trim.
6. **Pick one rule for repeat visits** (one pin with many dates, or one pin per
   visit) and stick to it.
7. **Commit to git regularly** — that's your undo and history.
