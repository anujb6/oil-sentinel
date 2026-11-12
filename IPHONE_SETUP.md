# Use Oil Sentinel on your iPhone and with Siri — for free

## 1. Home Screen app
After you publish to GitHub Pages (README steps), open your URL in **Safari**. Tap **Share → Add to Home Screen → Add**. A new Oil Sentinel icon launches the mobile dashboard. It is a progressive web app (PWA); it does not require App Store submission or an Apple Developer subscription.

## 2. Siri voice briefing (no paid apps)
In the built-in **Shortcuts** app:

1. Press **+** to create a shortcut and name it **Oil Check**.
2. Tap **Add Action**, search **URL**; enter `https://YOUR-USERNAME.github.io/oil-sentinel/briefing.txt`. Or copy the exact URL from the dashboard's **Siri & iPhone** tab.
3. Add the action **Get Contents of URL**. The input should be the URL from step 2, using method GET.
4. Add **Speak Text**, using **Contents of URL** as the text. Optionally add **Show Result** after Speak Text if you prefer both speech and onscreen text.
5. Tap **Done**. Say **"Hey Siri, Oil Check"**.

This works because `briefing.txt` is automatically rebuilt whenever GitHub Actions republishes the app. Siri will speak the last *published* snapshot — not a directly polled live feed.

## 3. Optional: one-tap Home Screen Shortcut
In Shortcuts open `Oil Check` → menu → **Add to Home Screen**. This gives you one-tap spoken inventory updates without opening Safari.

## 4. Updating your sources
The free GitHub Action runs once each morning and more often on typical EIA reporting days. To force another download: open your repo in GitHub → **Actions** → **Refresh oil intelligence and deploy iPhone app** → **Run workflow**. The dashboard's **Refresh** button only fetches the latest published file, not a new EIA report. GitHub Actions scheduled jobs may be late; the EIA official report is always the source of record.

## 5. Privacy and cost
Your manually entered expectation is kept **in your device's local browser storage**. No brokerage account, login, email service, payment card or paid API is required. This is a *public* hosted site; don't put passwords, secrets, broker keys, or private information in the repository. No push notifications are included (hosting alone cannot reliably provide them).

## 6. Limitations
- Sentinel-2 scenes are often cloud-obscured and are not live video.
- Satellite tank-level volume changes are NOT inferred; free imagery cannot measure them with defensible accuracy.
- WTI reference quotes may be delayed and follow a different futures instrument than your broker's USOIL price.
- If a source is unavailable, the published build may show labelled stale figures, not silently fabricated data.
- No forecasting model or automated trade execution is included.
