# Phase 3 — Public Deployment Walkthrough

**Sprint:** Local repo → GitHub Pages live URL
**Owner:** You (with exact commands provided)
**Estimated time:** 10–15 minutes total

---

## Step 1 — Place new files in your local working folder

From this `RBIS-cebu-city-phase3/` outputs folder, copy into `C:\RBIS-cebu-city\`:

```powershell
Copy-Item -Path ".\RBIS-cebu-city-phase3\index.html" -Destination "C:\RBIS-cebu-city\index.html" -Force
Copy-Item -Path ".\RBIS-cebu-city-phase3\README.md"  -Destination "C:\RBIS-cebu-city\README.md"  -Force
Copy-Item -Path ".\RBIS-cebu-city-phase3\LICENSE"    -Destination "C:\RBIS-cebu-city\LICENSE"    -Force
```

(The only change in `index.html` from Phase 2 is the footer link, now pointing at the actual GitHub repo URL.)

---

## Step 2 — Pre-flight: Verify nothing sensitive will be committed

Run this in PowerShell from `C:\RBIS-cebu-city`. It checks that `.env` is not staged and confirms the file structure is correct **before** you connect to GitHub.

```powershell
cd C:\RBIS-cebu-city

# Check 1: .env must NOT be visible to git
Write-Host "`n=== Files git WILL track ===" -ForegroundColor Cyan
Get-ChildItem -Recurse -File |
  Where-Object { $_.FullName -notmatch '\\node_modules\\' -and $_.Name -ne '.env' } |
  ForEach-Object { $_.FullName.Replace((Get-Location).Path, '.') }

# Check 2: .env should be in scripts folder but NOT listed above
Write-Host "`n=== .env files (should exist locally but NOT appear above) ===" -ForegroundColor Yellow
Get-ChildItem -Recurse -Force -Filter '.env' |
  ForEach-Object { Write-Host "  $($_.FullName)" -ForegroundColor Yellow }

# Check 3: confirm .gitignore is in place
Write-Host "`n=== .gitignore present? ===" -ForegroundColor Cyan
if (Test-Path ".\.gitignore") { Write-Host "  ✓ root .gitignore exists" -ForegroundColor Green }
if (Test-Path ".\scripts\.gitignore") { Write-Host "  ✓ scripts/.gitignore exists" -ForegroundColor Green }
```

**Expected output structure** (the "files git WILL track" list):

```
.\.gitignore
.\index.html
.\LICENSE
.\README.md
.\data\cost-rates.json
.\data\roads.geojson
.\scripts\.env.example
.\scripts\.gitignore
.\scripts\export-roads.js
.\scripts\package.json
.\scripts\PHASE_1_CHECKLIST.md
```

**Critical**: `.env` must appear in the second section (yellow), NOT in the first. If `.env` shows up in "files git WILL track", **STOP** and message me before continuing — the .gitignore isn't working and we'd leak the database password.

---

## Step 3 — Create the GitHub repo

In a browser:

1. Go to **[https://github.com/new](https://github.com/new)**
2. Repository name: `RBIS-cebu-city` (must match exactly — case sensitive in URLs)
3. Description: `Roads & Bridges Inventory dashboard for the City of Cebu DEPW`
4. Visibility: **Public** ●
5. **DO NOT** check "Add a README", "Add .gitignore", or "Choose a license" — we already have all three locally. Adding them on GitHub creates merge conflicts.
6. Click **Create repository**

You'll land on an empty repo page with setup instructions. Ignore them — use my commands below instead.

---

## Step 4 — Initialize git and push

In PowerShell, from `C:\RBIS-cebu-city`:

```powershell
cd C:\RBIS-cebu-city

# Initialize git
git init
git branch -M main

# Configure your identity (only if you haven't already, globally)
# Replace with your actual GitHub email
git config user.name "Kopher15"
git config user.email "your-github-email@example.com"

# Stage everything (gitignore protects .env automatically)
git add .

# Final sanity check — review what's about to be committed
git status

# Look for .env in the green "Changes to be committed" list. It MUST NOT be there.
# If you see it, run: git rm --cached scripts/.env  and re-run git status

# First commit
git commit -m "Initial commit: RBIS dashboard with PostGIS-backed static GeoJSON"

# Add the GitHub remote and push
git remote add origin https://github.com/Kopher15/RBIS-cebu-city.git
git push -u origin main
```

**On first push, GitHub will prompt for authentication.** Two options:

- **Browser auth** (easiest): if Git Credential Manager is installed (Git for Windows installs it by default), a browser window opens — log into GitHub, authorize, done.
- **Personal Access Token (PAT)**: go to [github.com/settings/tokens](https://github.com/settings/tokens) → Generate new token (classic) → check `repo` scope → copy the token → paste it as your password when prompted.

After push completes, refresh the GitHub repo page in your browser. You should see all your files listed.

---

## Step 5 — Enable GitHub Pages

On the GitHub repo page (`https://github.com/Kopher15/RBIS-cebu-city`):

1. Click **Settings** (top tab, far right)
2. In left sidebar, click **Pages**
3. Under "Build and deployment":
   - **Source**: Deploy from a branch
   - **Branch**: `main`  /  `/ (root)`
   - Click **Save**
4. GitHub shows: *"Your site is live at https://kopher15.github.io/RBIS-cebu-city/"*
5. **Wait 1–2 minutes** for first deploy. Pages tab will show a green checkmark when ready.

If you see a yellow "in progress" indicator, wait. First deploy is the slowest (~60–90 seconds).

---

## Step 6 — Smoke test the live URL

Open: **`https://kopher15.github.io/RBIS-cebu-city/`**

Check each:

- [ ] Header logos render correctly
- [ ] Inspection bar shows **14.7%** (red fill, "1,173 of 7,995 fully assessed")
- [ ] All 6 KPI cards have numbers
- [ ] Charts render
- [ ] Districts panel shows NORTH and SOUTH
- [ ] Roads table loads
- [ ] Map modal opens and roads render colored by condition
- [ ] Footer "Data Source" link goes to `https://github.com/Kopher15/RBIS-cebu-city`
- [ ] Browser console (F12) shows no red errors

If everything passes — **you have shipped a public government data dashboard.** 🇵🇭

If anything fails — paste the symptom and I'll diagnose.

---

## Step 7 — The refresh workflow (for the future)

This is your steady-state. Every time DEPW updates inspection data in PostGIS:

```powershell
cd C:\RBIS-cebu-city\scripts
npm run export

cd ..
git add data/roads.geojson
git commit -m "Refresh: <today's date> inspection update"
git push
```

GitHub Pages auto-deploys within 60 seconds. Refresh the live URL — new numbers appear.

That's the entire workflow. No build step. No server restart. No Render dashboard.

---

## Troubleshooting

**"Your site is live" but browser shows 404 / old content:**
GitHub Pages is CDN-cached. Hard refresh with **Ctrl+F5**, or wait 5 minutes for cache to expire.

**Inspection bar shows wrong number on live site but correct locally:**
You probably forgot to push the new `roads.geojson`. Run `git status` in the project root and check.

**Map says "Map data unavailable":**
`data/roads.geojson` isn't in the repo. Confirm with `git ls-files data/`. If missing, run `git add data/roads.geojson && git commit -m "Add roads geojson" && git push`.

**Push fails with "permission denied":**
Either your GitHub auth token is wrong, or the repo name is mistyped. Double-check both.

**`.env` accidentally pushed:**
Immediately rotate the database password (treat it as compromised). Then:
```powershell
git rm --cached scripts/.env
git commit -m "Remove accidentally committed .env"
git push
# Note: this removes it from HEAD but it's still in git history.
# For a public repo with a leaked secret, the safest move is to rotate the password.
```

---

## Phase 3 Sign-Off

When the live URL passes the Step 6 checklist, reply:

> **"Phase 3 verified. RBIS is live."**

That closes the project.

After that, optional follow-ups (not blocking):

- DEPW triages the 16 unnamed segments (data quality cleanup)
- Add the bridges table to PostGIS, add a `bridges.geojson` export, extend dashboard to show bridges (was deferred earlier)
- Add a "Last refreshed" date to the inspection bar that reads from the GeoJSON's metadata

But none of that blocks shipping the roads dashboard today.
