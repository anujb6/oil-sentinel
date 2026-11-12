# OIL SENTINEL — Free, iPhone- and Siri-ready oil storage monitor

**Everything runs on no-cost public resources. No subscription, credit card, paid satellite feed or EIA API key required.**

The project is a small browser-based app installable on the iPhone Home Screen. A scheduled GitHub Action fetches official EIA crude stocks and new Copernicus Sentinel-2 imagery; GitHub Pages hosts the resulting static files. Apple's Shortcuts app can read the latest spoken report aloud through Siri.

### What it actually measures

| Feature | Data source | Reliability |
|---|---|---|
| US commercial crude stock, ex-SPR | Official EIA weekly XLS | Authoritative for the published period |
| Cushing crude stock | Official EIA weekly XLS | Authoritative for the published period |
| Gasoline and distillate stocks | Official EIA weekly XLS | Authoritative for the published period |
| Inventory build/draw heuristic | Explicit two-series calculation | Research context, not predictive |
| Satellite scene dates & clouds | Sentinel-2 L2A via Earth Search | Public scene metadata; cloud percentage applies to the tile |
| Satellite RGB crops | Windowed read of public Sentinel-2 COG (best-effort) | Illustrative only, no tank-level barrels |
| WTI indicative quote (optional) | AmericasOilWatch public API / futures data | Not guaranteed live, may differ from broker CFD |
| Forecast surprise comparison | You type consensus weekly change locally | Manual; no paid expectations feed |

**Core honesty rule:** Copernicus Sentinel-2 has 10 m pixels, insufficient to measure weekly floating-roof tank fill height. Do not use satellite photos to invent a value like '+0.3 million barrels'. The precise Cushing and US inventory stock levels come from EIA instead. Free NAIP aerial imagery can be 1m, but normally refreshes on a multi-year cadence, not weekly.

## Set up in a public GitHub repository (no command line required)

1. Sign in to a free account at [github.com](https://github.com/). Click **New repository**, name it `oil-sentinel`, choose **Public**, create it.
2. Unzip `Oil-Sentinel-Free.zip` on a computer (or iPhone Files if comfortable). Open the `oil-sentinel` folder and **upload its contents**, not the outer folder or zip, to your repository via **Add file → Upload files**. GitHub's web uploader may not include dotfolders from mobile; make sure `.github/workflows/update-and-deploy.yml` is actually present. If it is missing, create it via GitHub's **Add file → Create new file** with that exact path and paste its contents.
3. In the repository, open **Settings → Pages → Build and deployment → Source**, choose **GitHub Actions**.
4. Open **Actions → Refresh oil intelligence and deploy iPhone app → Run workflow**. Enable workflows if GitHub asks. The first job runs the EIA/STAC fetch, then publishes the page.
5. Open `https://YOUR-USERNAME.github.io/oil-sentinel/` in Safari; replace `YOUR-USERNAME` with your GitHub handle. From **Share → Add to Home Screen**, choose **Oil Sentinel**. This installs the PWA for one-tap access. If you renamed the repo, replace `oil-sentinel` in the URL.
6. In the app, choose **Siri & iPhone**; use the displayed URL for the voice Shortcut. See `IPHONE_SETUP.md`.

The `.github/workflows/update-and-deploy.yml` file automatically refreshes daily at 05:15 UTC and runs six additional checks per day on Wednesday and Thursday between 15:10 and 20:10 UTC. GitHub scheduled workflows can be delayed or paused; GitHub may disable them after 60 days of public repo inactivity. Press **Run workflow** manually if needed. GitHub Pages requires a public repo for the no-cost plan. The free tier has fair-use limits, but this light workflow is designed to stay well below them.

**This file package does not deploy itself.** Until a GitHub repository is created and its Pages workflow is run, no live URL or Siri address exists. The included `site/data.json` contains a clearly labelled *historical demo* based on the week ending 2026-10-30, so you can inspect the app before the first refresh.

## Run/test locally (optional)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt pytest
python scripts/update.py
python -m http.server 8000 -d site
# Open http://localhost:8000
pytest -q
```

To skip satellite image rendering for a quick test, call `build(render_images=False)` from Python. Internet access is required to fetch fresh sources. When a source is unavailable, the app labels the partial/stale state rather than making up current readings.

## Files

- `site/index.html`, `site/style.css`, `site/app.js`: complete responsive mobile dashboard, no CDN.
- `site/data.json`: initially historical demo; generated with live EIA stock data after successful workflow.
- `site/briefing.txt`: the plain-language response for the Siri voice Shortcut.
- `site/manifest.webmanifest`, `site/sw.js`, icons: home-screen installation and offline shell.
- `scripts/update.py`: data-ingestion engine and optional true-colour satellite image crop generator.
- `.github/workflows/update-and-deploy.yml`: free scheduled update, publish to GitHub Pages.
- `tests/test_update.py`: smoke tests for data parsing, pressure logic, catalog handling, and honesty around stale inputs.

## Data/source links

- EIA weekly petroleum status report: https://www.eia.gov/petroleum/supply/weekly/
- Official EIA Cushing series: https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?f=W&n=PET&s=W_EPC0_SAX_YCUOK_MBBL
- EIA downloadable public XLS template: https://www.eia.gov/dnav/pet/hist_xls/W_EPC0_SAX_YCUOK_MBBLw.xls
- Copernicus data: https://dataspace.copernicus.eu/
- Copernicus browser: https://browser.dataspace.copernicus.eu/
- Earth Search free STAC: https://element84.com/earth-search/
- Optional WTI quote: https://americasoilwatch.com/api
- Apple Siri & Shortcuts: https://support.apple.com/en-ie/guide/shortcuts/apd07c25bb38/ios

## Trading use

Treat this as a **physical-inventory information source**, not an automated buy/sell signal. For an EIA surprise, compare the actual US crude change to a reliable consensus, plus Cushing, gasoline/distillates, refinery utilization, production, and price action. During EIA release hours, delayed GitHub Actions execution and web-cache propagation mean this app should **not** be used for second-by-second news trading.

## License

MIT for original code. Third-party data remains subject to original provider terms and attribution. No suggestion of affiliation or endorsement by EIA, ESA, Copernicus, GitHub, Apple, or Element 84.
