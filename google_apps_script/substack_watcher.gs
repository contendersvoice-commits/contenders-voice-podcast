/**
 * Contender's Voice — Free Substack-to-GitHub-Podcast Watcher (Google Apps Script)
 * -------------------------------------------------------------------------------
 * Runs on Google's free cloud servers (no credit card, no local computer needed).
 *
 * Primary source: fetches https://contendersvoice.substack.com/feed
 * Backup source:  checks Contender's Voice Gmail for newly published Substack emails
 *                 (if Substack ever throttles/blocks HTTP requests)
 *
 * Whenever a new written Substack post appears, it adds it to state/backfill_queue.json
 * and triggers GitHub Actions (repository_dispatch: sync-podcast) automatically.
 */

const DEFAULTS = {
  GITHUB_OWNER: "contendersvoice-commits",
  GITHUB_REPO: "contenders-voice-podcast",
  SUBSTACK_SUBDOMAIN: "contendersvoice",
};

function getConfig_() {
  const props = PropertiesService.getScriptProperties();
  const token = (props.getProperty("GITHUB_TOKEN") || "").trim();
  return {
    token,
    owner: (props.getProperty("GITHUB_OWNER") || DEFAULTS.GITHUB_OWNER).trim(),
    repo: (props.getProperty("GITHUB_REPO") || DEFAULTS.GITHUB_REPO).trim(),
    subdomain: (props.getProperty("SUBSTACK_SUBDOMAIN") || DEFAULTS.SUBSTACK_SUBDOMAIN).trim(),
  };
}

/**
 * Run this once in the Apps Script editor to verify RSS, Gmail, and GitHub access.
 */
function testFeedAccess() {
  const cfg = getConfig_();
  Logger.log("Checking GitHub token and repository access...");
  if (!cfg.token) {
    throw new Error("Missing Script Property GITHUB_TOKEN. See google_apps_script/README.md.");
  }
  const epFile = ghGetFile_(cfg, "state/episodes.json");
  const epCount = Object.keys((JSON.parse(epFile.text).episodes || {})).length;
  Logger.log("GitHub OK! Tracked episodes in state/episodes.json: " + epCount);

  Logger.log("Testing live Substack RSS fetch...");
  const rssPosts = fetchFromSubstackRss_(cfg.subdomain);
  Logger.log("RSS result: " + rssPosts.length + " written posts retrieved.");
  if (rssPosts.length > 0) {
    Logger.log("Latest RSS post: [" + rssPosts[0].slug + "] " + rssPosts[0].title);
  }

  Logger.log("Checking Gmail fallback search...");
  const mailPosts = fetchFromGmailFallback_(cfg.subdomain);
  Logger.log("Gmail fallback result: " + mailPosts.length + " recent post emails found.");
}

/**
 * Run this once to install (or reset) an automatic hourly trigger on syncNewSubstackPosts.
 */
function installHourlyTrigger() {
  const existing = ScriptApp.getProjectTriggers();
  for (let i = 0; i < existing.length; i++) {
    if (existing[i].getHandlerFunction() === "syncNewSubstackPosts") {
      ScriptApp.deleteTrigger(existing[i]);
    }
  }
  ScriptApp.newTrigger("syncNewSubstackPosts")
    .timeBased()
    .everyHours(1)
    .create();
  Logger.log("Installed hourly trigger for syncNewSubstackPosts().");
}

/**
 * Main hourly job: checks for any new written Substack posts and triggers GitHub Actions.
 */
function syncNewSubstackPosts() {
  const cfg = getConfig_();
  if (!cfg.token) {
    throw new Error("Missing Script Property GITHUB_TOKEN.");
  }

  let discovered = [];
  try {
    discovered = fetchFromSubstackRss_(cfg.subdomain);
    Logger.log("Fetched " + discovered.length + " posts from Substack RSS.");
  } catch (rssErr) {
    Logger.log("RSS fetch warning (" + rssErr + "); trying Gmail fallback...");
    discovered = fetchFromGmailFallback_(cfg.subdomain);
    Logger.log("Gmail fallback found " + discovered.length + " recent posts.");
  }

  if (discovered.length === 0) {
    Logger.log("No posts returned from either source; exiting cleanly.");
    return;
  }

  const epFile = ghGetFile_(cfg, "state/episodes.json");
  const episodes = (JSON.parse(epFile.text).episodes) || {};

  const queueFile = ghGetFile_(cfg, "state/backfill_queue.json");
  const queueData = JSON.parse(queueFile.text);
  const existingPosts = Array.isArray(queueData.posts) ? queueData.posts : [];

  const knownSlugs = {};
  for (const slug of Object.keys(episodes)) {
    knownSlugs[slug] = true;
  }
  for (const post of existingPosts) {
    if (post && post.slug) knownSlugs[post.slug] = true;
  }

  // Also respect ignore_slugs.txt so excluded posts are not re-queued
  try {
    const ignoreFile = ghGetFile_(cfg, "ignore_slugs.txt");
    for (const line of ignoreFile.text.split(/\r?\n/)) {
      const cleaned = line.trim();
      if (cleaned && !cleaned.startsWith("#")) {
        const slug = cleaned.includes("/p/")
          ? cleaned.replace(/\/+$/, "").split("/p/").pop().split("?")[0]
          : cleaned;
        knownSlugs[slug] = true;
      }
    }
  } catch (e) {
    Logger.log("Optional ignore_slugs.txt read skipped: " + e);
  }

  const newPosts = discovered.filter((p) => p.slug && !knownSlugs[p.slug]);
  if (newPosts.length === 0) {
    Logger.log("No new written Substack posts since last check.");
    return;
  }

  Logger.log("Queueing " + newPosts.length + " new post(s): " + newPosts.map((p) => p.slug).join(", "));
  const updatedPosts = newPosts.concat(existingPosts);
  updatedPosts.sort((a, b) => (b.post_date || "").localeCompare(a.post_date || ""));

  ghPutFile_(
    cfg,
    "state/backfill_queue.json",
    JSON.stringify({ posts: updatedPosts }, null, 2) + "\n",
    queueFile.sha,
    "Queue new Substack post(s): " + newPosts.map((p) => p.slug).join(", ")
  );

  ghDispatchSync_(cfg);
  Logger.log("Dispatched GitHub Actions sync-podcast workflow.");
}

function fetchFromSubstackRss_(subdomain) {
  const rssUrl = "https://" + subdomain + ".substack.com/feed";
  const resp = UrlFetchApp.fetch(rssUrl, {
    muteHttpExceptions: true,
    followRedirects: true,
    headers: {
      "User-Agent": "ContendersVoicePodcastWatcher/1.0 (+https://www.contendersvoice.com/)",
      "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
    },
  });
  if (resp.getResponseCode() !== 200) {
    throw new Error("HTTP " + resp.getResponseCode() + " fetching " + rssUrl);
  }

  const doc = XmlService.parse(resp.getContentText());
  const channel = doc.getRootElement().getChild("channel");
  const contentNs = XmlService.getNamespace("content", "http://purl.org/rss/1.0/modules/content/");
  const items = channel.getChildren("item");
  const out = [];

  for (let i = 0; i < items.length; i++) {
    const item = items[i];
    const link = (item.getChildText("link") || "").trim();
    const slug = slugFromUrl_(link);
    if (!slug) continue;

    const encEl = item.getChild("enclosure");
    const encType = encEl && encEl.getAttribute("type") ? encEl.getAttribute("type").getValue() : "";
    const encUrl = encEl && encEl.getAttribute("url") ? encEl.getAttribute("url").getValue() : "";
    if (encType.toLowerCase().startsWith("audio/")) continue;

    const bodyHtml = item.getChildText("encoded", contentNs) || "";
    if (bodyHtml.includes("Audio edition of ") && bodyHtml.includes("Contender's Voice")) continue;

    let coverImage = "";
    if (encType.toLowerCase().startsWith("image/") && encUrl) {
      coverImage = decodeSubstackCdn_(encUrl);
    } else {
      const m = bodyHtml.match(/<img[^>]+src="([^"]+)"/i);
      if (m) coverImage = decodeSubstackCdn_(htmlDecode_(m[1]));
    }

    const pubRaw = (item.getChildText("pubDate") || "").trim();
    const pubIso = pubRaw ? new Date(pubRaw).toISOString() : new Date().toISOString();

    out.push({
      slug,
      title: (item.getChildText("title") || slug).trim(),
      subtitle: (item.getChildText("description") || "").trim(),
      post_date: pubIso,
      post_url: link,
      cover_image: coverImage,
      body_html: bodyHtml,
    });
  }
  return out;
}

function fetchFromGmailFallback_(subdomain) {
  const query = "from:" + subdomain + "@substack.com newer_than:14d";
  const threads = GmailApp.search(query, 0, 15);
  const out = [];
  const seen = {};
  const postUrlRe = new RegExp("https://" + subdomain + "\\.substack\\.com/p/([a-z0-9-]+)", "i");

  for (let t = 0; t < threads.length; t++) {
    const msgs = threads[t].getMessages();
    for (let m = 0; m < msgs.length; m++) {
      const msg = msgs[m];
      const html = msg.getBody() || "";
      if (html.includes("Audio edition of ") && html.includes("Contender's Voice")) continue;

      const match = html.match(postUrlRe);
      if (!match) continue;
      const slug = match[1];
      if (seen[slug]) continue;
      seen[slug] = true;

      let coverImage = "";
      const imgMatch = html.match(/<img[^>]+src="(https:\/\/substack(?:cdn\.com|-post-media\.s3\.amazonaws\.com)[^"]+)"/i);
      if (imgMatch) coverImage = decodeSubstackCdn_(htmlDecode_(imgMatch[1]));

      out.push({
        slug,
        title: msg.getSubject() || slug,
        subtitle: "",
        post_date: msg.getDate().toISOString(),
        post_url: "https://" + subdomain + ".substack.com/p/" + slug,
        cover_image: coverImage,
        body_html: html,
      });
    }
  }
  return out;
}

function slugFromUrl_(url) {
  if (!url || !url.includes("/p/")) return "";
  return url.replace(/\/+$/, "").split("/p/").pop().split("?")[0];
}

function decodeSubstackCdn_(url) {
  if (url && url.includes("substackcdn.com/image/fetch/")) {
    const idx = url.indexOf("https%3A") !== -1 ? url.indexOf("https%3A") : url.indexOf("http%3A");
    if (idx !== -1) {
      try {
        return decodeURIComponent(url.slice(idx));
      } catch (e) {
        return url;
      }
    }
  }
  return url;
}

function htmlDecode_(str) {
  return (str || "")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");
}

function ghGetFile_(cfg, path) {
  const url = "https://api.github.com/repos/" + cfg.owner + "/" + cfg.repo + "/contents/" + path;
  const resp = UrlFetchApp.fetch(url, {
    headers: {
      "Authorization": "Bearer " + cfg.token,
      "Accept": "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "ContendersVoiceWatcher/1.0",
    },
  });
  const meta = JSON.parse(resp.getContentText());
  let text = "";
  if (meta.content) {
    const bytes = Utilities.base64Decode(meta.content.replace(/\s+/g, ""));
    text = Utilities.newBlob(bytes).getDataAsString("UTF-8");
  } else if (meta.download_url) {
    text = UrlFetchApp.fetch(meta.download_url).getContentText("UTF-8");
  }
  return { sha: meta.sha, text };
}

function ghPutFile_(cfg, path, contentStr, sha, message) {
  const url = "https://api.github.com/repos/" + cfg.owner + "/" + cfg.repo + "/contents/" + path;
  const payload = {
    message,
    content: Utilities.base64Encode(Utilities.newBlob(contentStr, "application/json", path).getBytes()),
    sha,
  };
  const resp = UrlFetchApp.fetch(url, {
    method: "put",
    contentType: "application/json",
    payload: JSON.stringify(payload),
    headers: {
      "Authorization": "Bearer " + cfg.token,
      "Accept": "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "ContendersVoiceWatcher/1.0",
    },
  });
  if (resp.getResponseCode() < 200 || resp.getResponseCode() >= 300) {
    throw new Error("GitHub PUT failed: " + resp.getResponseCode() + " " + resp.getContentText());
  }
}

function ghDispatchSync_(cfg) {
  const url = "https://api.github.com/repos/" + cfg.owner + "/" + cfg.repo + "/dispatches";
  const resp = UrlFetchApp.fetch(url, {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify({ event_type: "sync-podcast" }),
    headers: {
      "Authorization": "Bearer " + cfg.token,
      "Accept": "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "ContendersVoiceWatcher/1.0",
    },
  });
  if (resp.getResponseCode() !== 204 && resp.getResponseCode() !== 200) {
    throw new Error("GitHub dispatch failed: " + resp.getResponseCode() + " " + resp.getContentText());
  }
}
