#!/usr/bin/env python3
"""Fetch YouTube stats for every channel in channels.txt.

Writes, per channel, data/<slug>/latest.json and data/<slug>/history.json,
plus data/channels.json (the tab list the site reads).
Standard library only. Needs env var YT_API_KEY.
Set FULL_REFRESH=1 to refetch comments on every video.
"""
import datetime as dt
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://www.googleapis.com/youtube/v3/"
KEY = os.environ.get("YT_API_KEY")
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
NOW = dt.datetime.now(dt.timezone.utc)
TODAY = NOW.strftime("%Y-%m-%d")
RECENT_DAYS = 45  # comments on newer videos are refreshed daily, older ones on Sundays
FULL_COMMENT_REFRESH = NOW.weekday() == 6 or os.environ.get("FULL_REFRESH") == "1"


def api(endpoint, **params):
    params["key"] = KEY
    url = API + endpoint + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            msg = json.loads(body)["error"]["message"]
        except Exception:
            msg = body[:500]
        raise RuntimeError(f"YouTube API {endpoint} failed ({e.code}): {msg}") from None


def parse_channel_ref(line):
    """'@name', 'name', 'youtube.com/@name' or a UC... id -> ('handle'|'id', value)."""
    s = line.strip()
    m = re.search(r"youtube\.com/(?:channel/)?(@?[\w.\-]+)", s)
    if m:
        s = m.group(1)
    if re.fullmatch(r"UC[\w-]{22}", s):
        return "id", s
    return "handle", s.lstrip("@")


def slug_for(kind, value):
    return value.lower() if kind == "handle" else value


def iso_duration(s):
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s or "")
    if not m:
        return 0
    d, h, mi, se = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + se


def load(path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return default


def top_comments(video_id):
    """Most-liked 3 among the first 100 relevance-ordered threads."""
    try:
        res = api("commentThreads", part="snippet", videoId=video_id, maxResults=100,
                  order="relevance", textFormat="plainText")
    except RuntimeError as e:  # comments disabled, members-only, etc.
        print(f"  comments unavailable for {video_id}: {e}", file=sys.stderr)
        return []
    out = []
    for item in res.get("items", []):
        s = item["snippet"]["topLevelComment"]["snippet"]
        out.append({
            "author": s.get("authorDisplayName", ""),
            "text": s.get("textOriginal", s.get("textDisplay", ""))[:1200],
            "likes": s.get("likeCount", 0),
            "replies": item["snippet"].get("totalReplyCount", 0),
            "published": s.get("publishedAt"),
        })
    out.sort(key=lambda c: c["likes"], reverse=True)
    return out[:3]


def fetch_channel(kind, value, folder):
    params = {"forHandle": value} if kind == "handle" else {"id": value}
    res = api("channels", part="snippet,statistics,contentDetails", **params)
    if not res.get("items"):
        raise RuntimeError(f"no channel found for {value}")
    ch = res["items"][0]
    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]

    ids, token = [], None
    while True:
        p = dict(part="contentDetails", playlistId=uploads, maxResults=50)
        if token:
            p["pageToken"] = token
        page = api("playlistItems", **p)
        ids += [i["contentDetails"]["videoId"] for i in page.get("items", [])]
        token = page.get("nextPageToken")
        if not token:
            break

    prev = {v["id"]: v for v in load(folder / "latest.json", {}).get("videos", [])}
    videos = []
    for i in range(0, len(ids), 50):
        page = api("videos", part="snippet,statistics,contentDetails,liveStreamingDetails",
                   id=",".join(ids[i:i + 50]))
        for v in page.get("items", []):
            sn, st, cd = v["snippet"], v.get("statistics", {}), v["contentDetails"]
            if sn.get("liveBroadcastContent") in ("live", "upcoming"):
                continue
            published = sn["publishedAt"]
            age = (NOW - dt.datetime.fromisoformat(published.replace("Z", "+00:00"))).days
            old = prev.get(v["id"], {})
            refresh = FULL_COMMENT_REFRESH or age <= RECENT_DAYS or "top_comments" not in old
            thumbs = sn.get("thumbnails", {})
            videos.append({
                "id": v["id"],
                "title": sn["title"],
                "published": published,
                "duration": iso_duration(cd.get("duration")),
                "views": int(st.get("viewCount", 0)),
                "likes": int(st["likeCount"]) if "likeCount" in st else None,
                "comments": int(st["commentCount"]) if "commentCount" in st else None,
                "thumb": (thumbs.get("medium") or thumbs.get("default") or {}).get("url", ""),
                "was_live": "liveStreamingDetails" in v,
                "top_comments": top_comments(v["id"]) if refresh else old.get("top_comments", []),
                "comments_checked": TODAY if refresh else old.get("comments_checked"),
            })
    videos.sort(key=lambda v: v["published"])

    s = ch["statistics"]
    thumbs = ch["snippet"].get("thumbnails", {})
    handle = ch["snippet"].get("customUrl") or (("@" + value) if kind == "handle" else value)
    channel = {
        "id": ch["id"],
        "handle": handle if handle.startswith(("@", "UC")) else "@" + handle,
        "title": ch["snippet"]["title"],
        "avatar": (thumbs.get("high") or thumbs.get("default") or {}).get("url", ""),
        "created": ch["snippet"].get("publishedAt"),
        "subscribers": int(s.get("subscriberCount", 0)),
        "subscribers_hidden": s.get("hiddenSubscriberCount", False),
        "views": int(s.get("viewCount", 0)),
        "video_count": int(s.get("videoCount", 0)),
    }
    return channel, videos


def save(folder, channel, videos):
    folder.mkdir(parents=True, exist_ok=True)
    latest = {"generated_at": NOW.isoformat(timespec="seconds"), "channel": channel, "videos": videos}
    (folder / "latest.json").write_text(json.dumps(latest, ensure_ascii=False, indent=1), encoding="utf-8")

    hist = load(folder / "history.json", {"channel": [], "videos": {}})
    hist["channel"] = [r for r in hist["channel"] if r[0] != TODAY]
    hist["channel"].append([TODAY, channel["subscribers"], channel["views"], len(videos)])
    for v in videos:
        rows = [r for r in hist["videos"].get(v["id"], []) if r[0] != TODAY]
        rows.append([TODAY, v["views"], v["likes"], v["comments"]])
        hist["videos"][v["id"]] = rows
    (folder / "history.json").write_text(json.dumps(hist, separators=(",", ":")), encoding="utf-8")


def migrate_single_channel_layout():
    """Earlier versions wrote data/latest.json directly; move it into its channel folder."""
    old = DATA / "latest.json"
    if not old.exists():
        return
    handle = load(old, {}).get("channel", {}).get("handle", "@currentconcept")
    folder = DATA / handle.lstrip("@").lower()
    folder.mkdir(parents=True, exist_ok=True)
    for name in ("latest.json", "history.json"):
        if (DATA / name).exists() and not (folder / name).exists():
            shutil.move(str(DATA / name), str(folder / name))
    for name in ("latest.json", "history.json"):
        (DATA / name).unlink(missing_ok=True)


def main():
    if not KEY:
        sys.exit("YT_API_KEY is not set")
    DATA.mkdir(exist_ok=True)
    migrate_single_channel_layout()

    lines = (ROOT / "channels.txt").read_text(encoding="utf-8").splitlines()
    refs = [parse_channel_ref(l) for l in lines if l.strip() and not l.strip().startswith("#")]
    seen, tabs, failures = set(), [], []
    for kind, value in refs:
        slug = slug_for(kind, value)
        if slug in seen:
            continue
        seen.add(slug)
        folder = DATA / slug
        try:
            channel, videos = fetch_channel(kind, value, folder)
            save(folder, channel, videos)
            print(f"{channel['title']}: {len(videos)} videos, {channel['subscribers']} subs")
        except RuntimeError as e:
            failures.append(slug)
            print(f"FAILED {value}: {e}", file=sys.stderr)
            if not (folder / "latest.json").exists():
                continue  # keep an old tab if one exists, otherwise skip it
            channel = load(folder / "latest.json", {})["channel"]
        tabs.append({"slug": slug, "handle": channel["handle"], "title": channel["title"],
                     "avatar": channel["avatar"]})

    (DATA / "channels.json").write_text(json.dumps(tabs, ensure_ascii=False, indent=1), encoding="utf-8")
    if failures and len(failures) == len(seen):
        sys.exit("every channel failed")


if __name__ == "__main__":
    main()
