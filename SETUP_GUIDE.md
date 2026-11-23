# Contender's Voice — Automated Podcast Setup Guide ($0/month)

This project automatically turns every written newsletter post on **contendersvoice.substack.com** into a broadcast-mastered MP3 using **Andrew (`en-US-AndrewMultilingualNeural`)**, packages each episode's cover image, title, and formatted article text into a Podcast RSS feed, and keeps Substack's **Podcast** tab updated automatically with zero work for Hutch.

---

## 1. Create a Dedicated Contender's Voice GitHub Account

Keep this completely separate from Luke's personal GitHub account:

1. Open an **Incognito / Private** browser window (so you don't accidentally sign into Luke's personal GitHub).
2. Go to [https://github.com/signup](https://github.com/signup) and sign up using the **Contender's Voice** ministry email.
3. Choose a clean username (for example, `contendersvoice`).
4. Create a new **Public** repository named **`contenders-voice-podcast`** (do **not** check "Add a README"—leave it completely empty).
   - *Why Public?* Public repositories get **free unlimited GitHub Actions minutes** and **free GitHub Pages** with no credit card required. Nothing private lives in this repo—it only mirrors already-public Substack posts.

---

## 2. Optional Tweaks Before Pushing

Before pushing the code, check two tiny files in this folder:

1. **`config/settings.json`**:
   - Update `owner_email` from `contendersvoice@substack.com` to the ministry email you want listed in the public podcast RSS feed.
   - Update `github_owner` to your new GitHub username (though the GitHub Action also auto-detects it).
2. **`config/pronunciations.json`**:
   - Already includes 54 Torah Parsha names and common Hebraic terms. You can add or adjust any word anytime right inside GitHub's web editor.

---

## 3. Push This Project to the Dedicated GitHub Account

In Terminal on your Mac, run the commands below (these set the Git author **only inside this folder**, leaving Luke's personal Git config untouched):

```bash
cd /Users/lukehendrickson/.gemini/antigravity/scratch/contenders-voice-podcast
git config user.name "Contender's Voice"
git config user.email "YOUR_MINISTRY_EMAIL@example.com"
git add .
git commit -m "Initial automated Substack podcast pipeline"
git branch -M main
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/contenders-voice-podcast.git
git push -u origin main
```

*(When Git asks for a password in the browser/credential prompt, make sure you sign in with the **new Contender's Voice** GitHub account, not Luke's personal one.)*

---

## 4. Enable GitHub Pages & Run Your 2-Episode Live Test

1. In your new GitHub repository, open **Settings → Pages**.
2. Under **Build and deployment → Source**, pick **Deploy from a branch**.
3. Set Branch to **`main`** and folder to **`/docs`**, then click **Save**.
4. Open the **Actions** tab → click **Sync Substack Podcast** (if prompted, click **Enable workflows**).
5. Click **Run workflow** (top right):
   - Set **`max_new_episodes`** to **`2`** for your first live test.
   - Click **Run workflow**.
6. Wait ~3–4 minutes until the green checkmark appears. Your live Podcast RSS URL is now:
   ```text
   https://YOUR_GITHUB_USERNAME.github.io/contenders-voice-podcast/podcast.xml
   ```
   And your clean web player page is at:
   ```text
   https://YOUR_GITHUB_USERNAME.github.io/contenders-voice-podcast/
   ```

---

## 5. Connect the Feed to Substack (Without Emailing Subscribers Twice)

1. Go to **`contendersvoice.substack.com/publish/podcast`** (or **Settings → Podcasts**).
2. Choose **I have a podcast hosted elsewhere → Distribute to Substack**.
3. Paste your live RSS feed URL:
   `https://YOUR_GITHUB_USERNAME.github.io/contenders-voice-podcast/podcast.xml`
4. Review the pulled show artwork and 2 test episodes.
5. **Important — prevent duplicate emails:**
   - During setup, choose to import the existing episodes **without emailing subscribers**.
   - Under ongoing sync / publishing settings, set **Auto-publish** to **ON** for the web/Podcast tab, and **keep email delivery OFF** (or set incoming synced episodes to land as Drafts if you ever want to manually click Publish without email — note that if your Substack Podcasts section doesn't expose a "web-only auto-publish without email" toggle, test one post or keep **Auto-publish OFF** so each synced episode appears as a ready draft you publish in 1 click with "Send email" unchecked).
6. Check the **Podcast** tab on `contendersvoice.substack.com` to confirm the artwork, title, audio player, and formatted article text look great!

---

## 6. How to Delete or Exclude Any Episode Anytime

1. **Remove from Substack:** On `contendersvoice.substack.com` → **Posts** (or **Podcast**), click **`...`** on the episode and choose **Unpublish** or **Delete**.
2. **Prevent re-syncing:** Open **`ignore_slugs.txt`** right on GitHub (click the pencil icon), add the post's slug on a new line (the last part after `/p/` in its Substack URL), and commit.
3. Run **Actions → Sync Substack Podcast → Run workflow** (or wait up to 2 hours) — the episode is permanently skipped and removed from `podcast.xml` too.

---

## 7. Backfill All 51 Past Articles (In Smooth Batches)

Once you're happy with the 2 test episodes on Substack:

1. Go to **Actions → Sync Substack Podcast → Run workflow**.
2. Set **`max_new_episodes`** to **`15`** (or **`20`**) and click **Run workflow**.
   - *Why batches of 15–20?* Andrew's natural neural voice streams close to real-time, so each 10–12 minute episode takes ~1.5–2 minutes to synthesize and master. Running 15–20 per click finishes cleanly in ~25–30 minutes and saves progress safely after every batch (plus the 2-hour schedule will also automatically catch up 5 more at a time on its own!).
3. Once the batch completes, run the workflow 2 more times with **`15`** or **`20`** until all 51 past articles are live.
4. From that moment on, every time Hutch publishes a new post on Substack, the audio episode appears automatically within ~2 hours.

---

## 8. Bonus: Connect YouTube, Spotify & Apple Podcasts Later (Same Feed!)

Whenever you're ready to expand beyond Substack, you just paste that **exact same** `podcast.xml` URL once into:
- **YouTube Studio:** `Create → New podcast → Submit RSS feed` (YouTube automatically turns every episode into a video!)
- **Spotify for Creators / Apple Podcasts Connect**
