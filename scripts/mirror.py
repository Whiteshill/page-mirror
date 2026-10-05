import hashlib
import html
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

import feedparser

FEED_URL = os.environ.get("FEED_URL", "").strip()
if not FEED_URL:
    sys.exit("The FEED_URL secret is missing or empty.")

POSTS_DIR = "_posts"
IMAGES_DIR = "assets/images"
os.makedirs(POSTS_DIR, exist_ok=True)
os.makedirs(IMAGES_DIR, exist_ok=True)

# Work out the blog's address prefix so image links work
repo = os.environ.get("GITHUB_REPOSITORY", "owner/repo").split("/")[1]
BASE = "" if repo.endswith(".github.io") else "/" + repo

feedparser.USER_AGENT = "Mozilla/5.0 (compatible; page-mirror)"
feed = feedparser.parse(FEED_URL)
if not feed.entries:
    sys.exit("No posts found in the feed. Check the feed address.")

# Keys of posts we have already created
done = {n.rsplit("-", 1)[-1].removesuffix(".html") for n in os.listdir(POSTS_DIR)}


def download_image(url, key, number):
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read()
            kind = response.headers.get("Content-Type", "").split(";")[0].strip()
    except Exception as error:
        print("Could not download image:", url, error)
        return None
    extension = {"image/png": ".png", "image/gif": ".gif", "image/webp": ".webp"}.get(kind, ".jpg")
    filename = f"{key}-{number}{extension}"
    with open(os.path.join(IMAGES_DIR, filename), "wb") as file:
        file.write(data)
    return f"{BASE}/assets/images/{filename}"


new_posts = 0
for entry in feed.entries:
    identity = entry.get("id") or entry.get("link") or entry.get("title") or ""
    if not identity:
        continue
    key = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:10]
    if key in done:
        continue

    if entry.get("content"):
        body = entry.content[0].value
    else:
        body = entry.get("summary", "")

    # Find images, falling back to the feed's media attachments
    image_urls = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', body)
    if not image_urls:
        for media in entry.get("media_content", []):
            url = media.get("url")
            if url and media.get("medium", "image") == "image":
                body += f'<p><img src="{url}"></p>'
                image_urls.append(url)

    # Copy images onto the blog so the links don't expire
    for number, url in enumerate(image_urls, start=1):
        local = download_image(html.unescape(url), key, number)
        if local:
            body = body.replace(url, local)

    title = entry.get("title", "").strip()
    if not title:
        text = " ".join(re.sub(r"<[^>]+>", " ", body).split())
        title = text[:80] or "Facebook post"

    now = datetime.now(timezone.utc)
    if entry.get("published_parsed"):
        when = min(datetime(*entry.published_parsed[:6], tzinfo=timezone.utc), now)
    else:
        when = now

    link = entry.get("link", "")
    lines = [
        "---",
        "layout: post",
        "title: " + json.dumps(title, ensure_ascii=False),
        "date: " + when.strftime("%Y-%m-%d %H:%M:%S +0000"),
        "---",
        "{% raw %}",
        body,
        "{% endraw %}",
    ]
    if link:
        lines.append(f'<p><a href="{link}">View the original post on Facebook</a></p>')

    filename = f"{when.strftime('%Y-%m-%d')}-{key}.html"
    with open(os.path.join(POSTS_DIR, filename), "w", encoding="utf-8") as file:
        file.write("\n".join(lines) + "\n")
    new_posts += 1

print(f"Added {new_posts} new post(s).")
