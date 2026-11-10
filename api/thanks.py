"""Vercel function: GET /api/thanks?url=<youtube link>  ->  JSON list of Super Thanks."""
import json
import re
from collections import defaultdict
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from youtube_comment_downloader import YoutubeCommentDownloader, SORT_BY_RECENT


def video_id_from(url: str):
    m = re.search(r"(?:v=|youtu\.be/|shorts/|live/|embed/)([A-Za-z0-9_-]{11})", url)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url.strip()):
        return url.strip()
    return None


def parse_amount(paid: str):
    paid = paid.replace("‏", "").replace("‎", "").strip()
    num = re.search(r"[\d.,]+", paid)
    if not num:
        return paid, 0.0
    currency = paid.replace(num.group(0), "").strip() or "?"
    try:
        return currency, float(num.group(0).replace(",", ""))
    except ValueError:
        return currency, 0.0


def get_super_thanks(url: str):
    vid = video_id_from(url)
    if not vid:
        raise ValueError("Couldn't find a video ID in that link.")
    watch_url = f"https://www.youtube.com/watch?v={vid}"

    found, seen = {}, set()
    for c in YoutubeCommentDownloader().get_comments_from_url(watch_url, sort_by=SORT_BY_RECENT):
        cid = c.get("cid", "")
        if cid in seen:
            continue
        seen.add(cid)
        paid = c.get("paid")
        if paid:
            cur, val = parse_amount(paid)
            found[cid] = {
                "name": c.get("author", ""),
                "amount": paid.replace("‏", "").replace("‎", "").strip(),
                "currency": cur,
                "value": val,
                "comment": c.get("text", ""),
                "time": c.get("time", ""),
                "link": f"{watch_url}&lc={cid}",
            }

    results = list(found.values())
    totals = defaultdict(lambda: {"total": 0.0, "count": 0})
    for r in results:
        totals[r["currency"]]["total"] += r["value"]
        totals[r["currency"]]["count"] += 1

    return {
        "video_id": vid,
        "scanned": len(seen),
        "count": len(results),
        "results": results,
        "totals": [{"currency": k, **v} for k, v in sorted(totals.items(), key=lambda x: -x[1]["count"])],
    }


class handler(BaseHTTPRequestHandler):
    def _send(self, status, body):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = parse_qs(urlparse(self.path).query).get("url", [""])[0]
        if not url:
            return self._send(400, {"error": "Add ?url=<YouTube link>"})
        try:
            self._send(200, get_super_thanks(url))
        except ValueError as e:
            self._send(400, {"error": str(e)})
        except Exception as e:  # YouTube changes / blocks
            self._send(502, {"error": f"Couldn't load comments from YouTube: {e}"})
