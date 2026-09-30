# YouTube channels, by the numbers

A static GitHub Pages site with daily-updated statistics for the YouTube channels listed in
`channels.txt` (starting with [Current Concept](https://www.youtube.com/@currentconcept)),
plus a box for looking up any other channel on the spot.

A GitHub Action runs every morning (04:17 UTC), pulls data from the YouTube Data API v3,
writes `data/<channel>/latest.json` and `data/<channel>/history.json` for each channel,
commits them, and deploys the site. No build step, no dependencies.

## Tabs: `channels.txt`
Put one channel per line: `@handle`, a `youtube.com/@handle` link, or a `UC…` channel ID.
The first line is the tab that opens by default. Saving the file on GitHub starts a run,
and the new tabs appear once it finishes. Tab channels collect daily history; anything
removed from the list keeps its old data folder but loses its tab.

## Looking up any channel
Paste a handle or link into the box at the top and press **Look up**. This fetches the
channel straight from your browser, so it needs an API key saved in that browser
(open **API key for lookups**). The key stays in the browser's local storage and is never uploaded.

Use a **second key** for this, not the one in your GitHub secret: in Google Cloud Console
create another API key, restrict it to YouTube Data API v3, and under Application restrictions
choose **Websites** and add `https://<your-username>.github.io/*`. That key then only works on your site.

A lookup costs roughly 2 quota units per 50 videos plus 1 per video whose comments are read
(capped at the 40 most-viewed and 20 newest). Results are cached in the browser for 6 hours;
**Fetch again** refreshes early. Lookups are single snapshots, so the Momentum section needs a tab.
Links like `?c=veritasium` open that channel directly.

## What's on the page
- Live counter since the last upload, predicted next upload, and how unusual the current wait is
- Upload "skyline": every video on a timeline, height by views
- Gaps between uploads, drought records, burstiness, weekday × hour heatmap, uploads per month
- Views over time (log scale), length vs views, views vs age with a power-law fit
- Leaderboards: most viewed, fastest, best liked, most discussed
- Momentum from daily snapshots: subscriber curve, top gainers, back-catalogue share
- Top-liked comment channel-wide and per video, plus the most-replied comment
- Oddities: Benford's law, Gini coefficient, title word counts, title A/B comparisons, watch-time ceiling
- Sortable table of every video; a toggle to include or exclude Shorts

## Setup (about 10 minutes)
1. **Get an API key.** In [Google Cloud Console](https://console.cloud.google.com/) create a project,
   enable **YouTube Data API v3**, then Credentials → Create credentials → API key.
   Restrict the key to the YouTube Data API.
2. **Create the repo.** New GitHub repository, upload everything in this folder
   (keep the `.github/workflows` folder).
3. **Add the secret.** Repo → Settings → Secrets and variables → Actions → New repository secret,
   name `YT_API_KEY`, value = your key.
4. **Turn on Pages.** Settings → Pages → Source: **GitHub Actions**.
5. **First run.** Actions tab → *Update channel stats* → *Run workflow*. After it finishes, the site
   is live at `https://<your-username>.github.io/<repo-name>/`.

## Notes
- Quota: a run costs roughly 1 unit per video plus a handful more, well under the free 10,000/day.
  Comments are refreshed daily for videos from the last 45 days and weekly (Sundays) for older ones.
  Set `FULL_REFRESH=1` in the workflow env to refresh all of them.
- "Top comment" means the most-liked among the 100 most relevant threads the API returns per video.
- Shorts are identified by length (3 minutes or less), since the API has no Shorts flag.
- GitHub may pause scheduled workflows in repos with no activity for 60 days. If the data stops
  updating, re-enable the workflow from the Actions tab.
- Local preview: `python -m http.server` in this folder, then open http://localhost:8000
  (opening `index.html` directly from disk won't load the JSON). A key restricted to your
  github.io address won't work on localhost.
