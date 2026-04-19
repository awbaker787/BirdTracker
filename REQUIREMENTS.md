# BirdTracker — Requirements Document

## Overview

BirdTracker is a personalized birding web app that connects to eBird to show a user which bird species have been recently reported near them (or in their state, or anywhere in the USA) that they have not yet recorded in their personal eBird year list. Results are sorted nearest first by distance from the user's home location.

**Live URL:** https://birdtracker123.streamlit.app
**GitHub:** https://github.com/awbaker787/BirdTracker
**Local path:** `C:\gitawb\birding-app`

---

## Tech Stack

| Layer | Technology |
|---|---|
| UI framework | Python + Streamlit |
| eBird data | eBird API v2 (public observations) |
| Personal list | Playwright headless browser scraping of authenticated eBird year list |
| Map | Folium + streamlit-folium (interactive) |
| Cookie persistence | streamlit-cookies-controller |
| Encryption | cryptography (Fernet / AES-128) |
| Deployment | Streamlit Community Cloud (free tier) |
| Source control | Git + GitHub |

---

## Pages & Navigation

The app uses `st.navigation` (Streamlit multi-page). Three pages appear in the top nav bar:

### 1. Find My Needs (default page)
The main search and results page.

**Sidebar — Settings section (collapsed expander):**
- Latitude / Longitude inputs (pre-filled from saved defaults)
- State Code input (e.g., US-FL)
- Local radius slider (km)
- "Save as defaults" button — persists current sidebar values to cookies

**Sidebar — Filter section (always visible):**
- Quick day buttons: 1d / 3d / 7d / 14d
- Custom days number input
- "Find My Needs" primary button

**Main area (after search):**
- Three species-count metrics: World / US / State year list totals
- Interactive Folium map (full width, 520px height):
  - Layered markers: Local (orange), State (blue), USA (green)
  - MarkerCluster for performance (capped at 400 per layer on map)
  - Click popup per marker: common name, scientific name, location, last seen date, distance in miles, count
  - Layer toggle control (top-right of map)
  - Street map + Satellite tile options
  - Red "home" marker for user's location
- Three result tabs below the map:
  - **Local** — birds within radius km, not yet seen this year anywhere
  - **[State]** — birds reported in state, not yet seen in state this year
  - **USA** — birds reported anywhere in the US, not yet seen in the US this year
- Each tab: sortable dataframe (Miles Away / Common Name / Scientific Name / Last Seen / Location / Count) + Download CSV button
- "Refresh Year List from eBird" button — clears cached session list and re-scrapes

**Error Log:**
- All exceptions captured with full traceback into `st.session_state["_err_log"]`
- Displayed persistently in a collapsible "Error Log" expander at page bottom
- Does not disappear on rerun

---

### 2. Profile
Manages eBird login credentials only.

- If not yet saved: input form for Username, Password, API Key + "Save & remember me" button
- If saved: "Connected as [username]" success badge
- Collapsible "Edit credentials" expander to update or clear saved credentials
- Credentials stored as a single encrypted JSON cookie (`bd_creds`)
- Error Log expander at bottom

---

### 3. Settings
Manages default search location and filter values.

- Latitude / Longitude
- State Code
- Local radius (km) slider
- Default days back number input
- "Save Settings" button — persists to cookie (`bd_prefs`)
- Values pre-fill the Find My Needs sidebar on every visit
- Error Log expander at bottom

---

## Authentication & Credentials

### eBird API Key
- Required for all eBird API v2 calls (nearby observations, regional observations)
- Stored in `bd_creds` cookie, never in source code or Streamlit secrets

### eBird Login (personal year list)
- eBird API does not expose personal lists — solved by scraping the authenticated eBird web interface
- Uses Playwright headless Chromium to log in via Cornell SSO (`secure.birds.cornell.edu/cassso`)
- Fills `#input-user-name` and `#input-password`, clicks `#form-submit`
- After login, navigates to `/lifelist?r={region}&time=year` for each region
- Extracts `data-species-code` and `<span class="Heading-main">` from rendered HTML
- Playwright launched with cloud-safe flags: `--no-sandbox`, `--disable-setuid-sandbox`, `--disable-dev-shm-usage`, `--disable-gpu`, `--single-process`
- Year list cached in `st.session_state` for the duration of the session (not re-scraped on each search)

---

## Cookie Storage

All user data is stored in the browser using two encrypted cookies:

| Cookie | Contents | Expires |
|---|---|---|
| `bd_creds` | JSON `{"u": username, "p": password, "k": api_key}` — Fernet encrypted | 1 year |
| `bd_prefs` | JSON `{"lat", "lng", "state", "dist", "days"}` — Fernet encrypted | 1 year |

- Encryption key is a hardcoded Fernet key in source (acceptable for a personal app)
- One `cc.set()` call per save action (avoids Streamlit duplicate-key errors from multiple calls)
- Library: `streamlit-cookies-controller`

---

## Data Flow

```
User clicks "Find My Needs"
│
├─ Load credentials from bd_creds cookie
├─ Load preferences from bd_prefs cookie
│
├─ Check st.session_state for cached year list
│   └─ If missing: Playwright login → scrape /lifelist for world, US, state_code
│
├─ eBird API: recent_observations_nearby(lat, lng, dist_km, days_back)  → local needs
├─ eBird API: recent_observations_in_region(state_code, days_back)       → state needs
├─ eBird API: recent_observations_in_region("US", days_back)             → USA needs
│
├─ NeedsFinder: subtract personal year list, dedupe by species (keep closest), sort by dist_miles
│
├─ Filter by date cutoff (days_back)
│
├─ Render Folium map with three layers
└─ Render three list tabs with dataframes + CSV download
```

---

## Core Logic

### Distance
Haversine formula — returns miles between two lat/lng pairs.

### NeedsFinder
- Takes eBird API client + personal list + user lat/lng
- `local_needs(lat, lng, dist_km, days_back)` — calls nearby observations
- `state_needs(state_code, days_back)` — calls regional observations
- `usa_needs(days_back)` — calls US-wide observations
- `_dedupe()` — for each species, keeps only the single closest sighting

### Year List Scraper
- Scrapes three regions sequentially (world, US, state) in one Playwright session
- Returns `{region_key: set(species_codes)}`

---

## Deployment

- **Platform:** Streamlit Community Cloud (free)
- **Trigger:** Auto-redeploys on every push to `main` branch on GitHub
- **System deps:** `packages.txt` — provides libnss3, libgbm1, and other Chromium OS libs needed for Playwright on Linux
- **Browser install:** `playwright install chromium` runs once per deployment via `@st.cache_resource` in `app.py`
- **No secrets required** in Streamlit Cloud dashboard — all credentials stored in user's browser cookies

---

## User (Default Configuration)

- **eBird username:** awbaker
- **Home location:** Delray Beach / Palm Beach, FL (Lat: 26.4615, Lng: -80.0728)
- **Default state:** US-FL
- **Default radius:** 25 km
- **Default days back:** 7

---

## Known Issues / Limitations

1. **Playwright on Streamlit Cloud** — headless Chromium sometimes crashes with "Page crashed" error. Cloud-safe flags added but not fully reliable on free tier (limited RAM).
2. **USA layer performance** — USA-wide results can return thousands of records; map caps at 400 markers per layer, full list still shown in tab.
3. **Year list scrape latency** — First run per session takes ~15–20 seconds for Playwright login + three region scrapes.
4. **Cookie library compatibility** — `streamlit-cookies-controller` replaces `extra-streamlit-components` which caused duplicate-key errors when setting multiple cookies in one script run.
5. **Fernet key in source** — Encryption key is hardcoded (repo is public). Cookies are obfuscated but not cryptographically protected against someone with repo access + physical browser access.
