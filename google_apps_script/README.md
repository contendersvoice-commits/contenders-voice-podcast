# Automatic Future-Post Bridge (Google Apps Script — $0/month)

Substack blocks GitHub Actions' datacenter IPs when reading `contendersvoice.substack.com/feed` directly. This tiny script runs for free on Google's cloud under the **Contender's Voice** Google account, checks for brand-new posts every hour (using Substack's RSS feed first and Contender's Voice's Gmail inbox as an automatic fallback), and wakes up GitHub Actions whenever Hutch publishes something new.

---

## One-Time 2-Minute Setup

### Step 1: Create a Single-Repo Token on `contendersvoice-commits`
1. Make sure you are signed into **`contendersvoice-commits`** on GitHub.
2. Go to **[github.com/settings/personal-access-tokens/new](https://github.com/settings/personal-access-tokens/new)** *(Fine-grained personal access token)*.
3. **Token name:** `apps-script-watcher`
4. **Expiration:** `1 year` (or `Custom` / max expiration; GitHub reminds you by email before expiry).
5. **Repository access:** Select **Only select repositories** → pick **`contenders-voice-podcast`**.
6. **Permissions → Repository permissions:**
   - **Contents:** `Read and write`
   - *(Everything else stays `No access`.)*
7. Click **Generate token** and copy it (`github_pat_...`).

*(You can also delete your temporary `temp-setup` classic token at [github.com/settings/tokens](https://github.com/settings/tokens) right here!)*

---

### Step 2: Paste the Script into Google Apps Script
1. Sign into Chrome with the **Contender's Voice Google account** (the Gmail subscribed to `contendersvoice.substack.com` — helpful for the Gmail backup!).
2. Open **[script.google.com](https://script.google.com/)** → click **New project**.
3. Click the project title (*Untitled project*) and rename it **`Contenders Voice Podcast Watcher`**.
4. Delete any starter code in `Code.gs` and paste the entire contents of **`substack_watcher.gs`**. Click the **Save** icon (`Cmd+S`).

---

### Step 3: Store the Token Safely in Script Properties
1. In the left sidebar of Apps Script, click the **Project Settings** gear icon (`⚙`).
2. Scroll to **Script Properties** → click **Add script property**:
   - **Property:** `GITHUB_TOKEN`
   - **Value:** *(paste your `github_pat_...` token)*
3. Click **Save script properties**.

---

### Step 4: Test & Turn On the Hourly Trigger
1. Switch back to the **Editor** (`< >` icon in the left sidebar).
2. In the top toolbar dropdown (next to *Debug*), select **`testFeedAccess`** and click **Run**.
   - Google will ask once to authorize URL fetching & Gmail read access on that account → click **Review permissions → Advanced → Go to Contenders Voice Podcast Watcher → Allow**.
   - Check the **Execution log**: you should see `GitHub OK!` and `RSS result: 20 written posts retrieved.` (plus Gmail check).
3. Now change the top toolbar dropdown to **`installHourlyTrigger`** and click **Run** once.
   - Check the **Triggers** clock icon (`⏰`) in the left sidebar: you'll see **`syncNewSubstackPosts`** scheduled **Every hour**!

Done! From now on, whenever Hutch publishes a new post on Substack, this watcher spots it within the hour, sends it to GitHub, and GitHub Actions automatically generates the MP3 and updates Substack's **Podcast** tab—with zero involvement from you, your in-laws, or Antigravity.
