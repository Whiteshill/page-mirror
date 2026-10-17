import base64
import hashlib
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "").strip()
GROUP_URL = os.environ.get("GROUP_URL", "").strip()
CLEAR_FIRST = os.environ.get("CLEAR_FIRST", "") == "true"

if not APIFY_TOKEN:
    sys.exit("The APIFY_TOKEN secret is missing or empty.")
if not GROUP_URL:
    sys.exit("The GROUP_URL secret is missing or empty.")

ACTOR_ID = "2chN8UQcH1CfxLRNE"
RESULTS_LIMIT = 5      # posts fetched per run (cost is roughly 0.5p per post)
KEEP_DAYS = 90         # posts older than this are removed
SHOW_AUTHOR = False    # set to True to show who posted

POSTS_DIR = "_posts"
IMAGES_DIR = "assets/images"
os.makedirs(POSTS_DIR, exist_ok=True)
os.makedirs(IMAGES_DIR, exist_ok=True)

repo = os.environ.get("GITHUB_REPOSITORY", "owner/repo").split("/")[1]
BASE = "" if repo.endswith(".github.io") else "/" + repo

group_url = GROUP_URL.split("?")[0].rstrip("/")

# ---- Ask Apify for the latest posts ----
payload = {
    "resultsLimit": RESULTS_LIMIT,
    "startUrls": [{"url": group_url}],
    "viewOption": "CHRONOLOGICAL",
}
request = urllib.request.Request(
    f"https://api.apify.com/v2/acts/{ACTOR_ID}/run-sync-get-dataset-items",
    data=json.dumps(payload).encode("utf-8"),
    headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + APIFY_TOKEN,
    },
    method="POST",
)
try:
    with urllib.request.urlopen(request, timeout=330) as response:
        items = json.loads(response.read().decode("utf-8"))
except urllib.error.HTTPError as error:
    sys.exit(f"Apify returned an error: {error.code} {error.read().decode('utf-8', 'replace')[:300]}")
except Exception as error:
    sys.exit(f"Could not reach Apify: {error}")

if not isinstance(items, list) or not items:
    sys.exit("Apify returned no posts.")

# ---- Optional one-off clear-out (only when ticked on a manual run) ----
if CLEAR_FIRST:
    for name in os.listdir(POSTS_DIR):
        if name.endswith(".html"):
            os.remove(os.path.join(POSTS_DIR, name))
    for name in os.listdir(IMAGES_DIR):
        os.remove(os.path.join(IMAGES_DIR, name))
    print("Cleared existing mirrored posts and images.")

done = {n.rsplit("-", 1)[-1].removesuffix(".html") for n in os.listdir(POSTS_DIR)}


def find_post_id(item):
    for key in ("postId", "post_id", "id", "legacyId"):
        if item.get(key):
            return str(item[key])
    for att in item.get("attachments") or []:
        if not isinstance(att, dict):
            continue
        match = re.search(r"set=gm\.(\d+)", str(att.get("url", "")))
        if match:
            return match.group(1)
        feedback_id = (att.get("feedback") or {}).get("id", "")
        try:
            decoded = base64.b64decode(feedback_id).decode("utf-8")
            match = re.search(r"feedback:(\d+)", decoded)
            if match:
                return match.group(1)
        except Exception:
            pass
    return ""


def find_date(item):
    for key in ("time", "timestamp", "createdAt", "created_time", "publishedAt", "date"):
        value = item.get(key)
        if not value:
            continue
        try:
            if isinstance(value, (int, float)):
                seconds = value / 1000 if value > 1e11 else value
                return datetime.fromtimestamp(seconds, timezone.utc)
            text = str(value).replace("Z", "+00:00")
            return datetime.fromisoformat(text).astimezone(timezone.utc)
        except Exception:
            continue
    return None


def best_image(node):
    for key in ("photo_image", "image", "viewer_image", "preview_image", "large_share_image"):
        value = node.get(key)
        if isinstance(value, dict) and value.get("uri"):
            return value["uri"]
    if isinstance(node.get("thumbnail"), str):
        return node["thumbnail"]
    return None


def find_images(item):
    urls = []

    def walk(node):
        if isinstance(node, dict):
            found = best_image(node)
            if found:
                urls.append(found)
                return
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(item.get("attachments") or [])
    return list(dict.fromkeys(urls))


def has_video(item):
    return any(
        isinstance(att, dict) and "video" in str(att.get("__typename", "")).lower()
        for att in item.get("attachments") or []
    )


def download_image(url, key, number):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as response:
            data = response.read()
            kind = response.headers.get("Content-Type", "").split(";")[0].strip()
    except Exception as error:
        print("Could not download image:", error)
        return None
    extension = {"image/png": ".png", "image/gif": ".gif", "image/webp": ".webp"}.get(kind, ".jpg")
    filename = f"{key}-{number}{extension}"
    with open(os.path.join(IMAGES_DIR, filename), "wb") as file:
        file.write(data)
    return f"{BASE}/assets/images/{filename}"


def link_urls(match):
    url = match.group(1)
    trail = ""
    while url and url[-1] in ".,;:!?)":
        trail = url[-1] + trail
        url = url[:-1]
    return f'<a href="{url}" target="_blank" rel="noopener">{url}</a>{trail}'


def text_to_html(text):
    paragraphs = [p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    out = []
    for paragraph in paragraphs:
        safe = html.escape(paragraph)
        safe = re.sub(r"(https?://[^\s<]+)", link_urls, safe)
        out.append("<p>" + safe.replace("\n", "<br>\n") + "</p>")
    return "\n".join(out)


def make_title(text):
    first_line = next((l.strip() for l in text.splitlines() if l.strip()), "")
    if not first_line:
        return "Post from the group"
    if len(first_line) <= 200:
        return first_line
    return first_line[:200].rsplit(" ", 1)[0] + "…"


now = datetime.now(timezone.utc)
new_posts = 0

for index, item in enumerate(items):
    if not isinstance(item, dict):
        continue
    text = (item.get("text") or "").strip()
    images = find_images(item)
    if item.get("attachments") and not images:
        print("No image found in attachment types:", [a.get("__typename") for a in item["attachments"] if isinstance(a, dict)])
    if not text and not images:
        continue

    post_id = find_post_id(item)
    identity = post_id or (text[:300] + "|" + "|".join(images))
    key = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:10]
    if key in done:
        continue

    when = find_date(item) or (now - timedelta(minutes=index))
    when = min(when, now)

    body_parts = []
    for number, url in enumerate(images, start=1):
        local = download_image(url, key, number)
        if local:
            body_parts.append(f'<p><img src="{local}" alt=""></p>')
    if text:
        body_parts.append(text_to_html(text))
    if has_video(item):
        body_parts.append("<p><em>This post includes a video, which you can watch on Facebook.</em></p>")
    if SHOW_AUTHOR and (item.get("user") or {}).get("name"):
        body_parts.append(f"<p><small>Posted by {html.escape(item['user']['name'])}</small></p>")

    original = item.get("url") or item.get("postUrl") or item.get("topLevelUrl")
    if not original:
        original = f"{group_url}/posts/{post_id}/" if post_id else group_url

    lines = [
        "---",
        "layout: post",
        "title: " + json.dumps(make_title(text), ensure_ascii=False),
        "date: " + when.strftime("%Y-%m-%d %H:%M:%S +0000"),
        "---",
        "{% raw %}",
        "\n".join(body_parts),
        "{% endraw %}",
        f'<p><a href="{original}" target="_blank" rel="noopener">View the original post on Facebook</a></p>',
    ]

    filename = f"{when.strftime('%Y-%m-%d')}-{key}.html"
    with open(os.path.join(POSTS_DIR, filename), "w", encoding="utf-8") as file:
        file.write("\n".join(lines) + "\n")
    done.add(key)
    new_posts += 1

print(f"Added {new_posts} new post(s).")

# ---- Delete posts older than KEEP_DAYS ----
cutoff = (now - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
for name in os.listdir(POSTS_DIR):
    if not name.endswith(".html"):
        continue
    if name[:10] < cutoff:
        os.remove(os.path.join(POSTS_DIR, name))
        key = name[11:-5]
        for image in os.listdir(IMAGES_DIR):
            if image.startswith(key + "-"):
                os.remove(os.path.join(IMAGES_DIR, image))
        print("Deleted old post:", name)
