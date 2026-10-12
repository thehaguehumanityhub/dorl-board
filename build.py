#!/usr/bin/env python3
"""Build the Democracy and Rule of Law board embed for humanityhub.org.

Weekly pipeline (run by GitHub Actions):
  1. Fetch the public Trello board through the official REST API.
  2. Enrich each link card with the source page's own metadata
     (title, summary, event date), cached in data/metadata.json so
     only new links are fetched.
  3. Apply manual fixes from overrides.json.
  4. Render template.html into dorl-embed.html (an inline fragment
     for the Shortcoder loader).

Local test without network:  python build.py --board-json board.json --offline
"""
import argparse, datetime as dt, html, json, os, re, sys, time
from html.parser import HTMLParser
from urllib.parse import urlparse, unquote
from urllib.request import Request, urlopen

BOARD_ID = "Pl5oOXPv"
EXCLUDE_LISTS = {"Collective's Shared Resources"}   # Signal invite + Drive link stay on Trello
NEW_DAYS = 7
NL_HOSTS = ("democratiemonitor.nl", "democratiecoalitie.nl", "wrr.nl", "tweedekamer.nl",
            "coc.nl", "universiteitleiden.nl")
UA = "Mozilla/5.0 (compatible; THHH-board-bot/1.0; +https://www.humanityhub.org)"
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "data", "metadata.json")
OVERRIDES = os.path.join(HERE, "overrides.json")

# ---------- Trello ----------
def fetch_board():
    key, token = os.environ.get("TRELLO_KEY"), os.environ.get("TRELLO_TOKEN")
    if not (key and token):
        # No credentials: use the public board's JSON export (unofficial, may be throttled)
        print("No Trello API credentials found, using the public JSON export")
        req = Request(f"https://trello.com/b/{BOARD_ID}.json", headers={"User-Agent": UA, "Accept": "application/json"})
        with urlopen(req, timeout=60) as r:
            return json.load(r)
    url = (f"https://api.trello.com/1/boards/{BOARD_ID}?fields=name,url,dateLastActivity"
           "&lists=open&list_fields=name,pos,color,closed"
           "&cards=open&card_fields=name,desc,idList,pos,shortUrl,shortLink,dueComplete,closed"
           f"&key={key}&token={token}")
    with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=30) as r:
        return json.load(r)

# ---------- Page metadata ----------
class Meta(HTMLParser):
    def __init__(self):
        super().__init__(); self.m = {}; self.title = ""; self._t = False; self.ld = []; self._ld = False
    def handle_starttag(self, tag, a):
        a = dict(a)
        if tag == "meta":
            k = (a.get("property") or a.get("name") or "").lower()
            if k and a.get("content") and k not in self.m: self.m[k] = a["content"]
        elif tag == "title": self._t = True
        elif tag == "script" and a.get("type") == "application/ld+json": self._ld = True; self.ld.append("")
    def handle_endtag(self, tag):
        if tag == "title": self._t = False
        if tag == "script": self._ld = False
    def handle_data(self, d):
        if self._t: self.title += d
        if self._ld: self.ld[-1] += d

def find_start_date(blocks):
    for b in blocks:
        try: j = json.loads(b)
        except Exception: continue
        stack = j if isinstance(j, list) else [j]
        while stack:
            o = stack.pop()
            if isinstance(o, dict):
                if "startDate" in o and isinstance(o["startDate"], str): return o["startDate"][:10]
                stack.extend(v for v in o.values() if isinstance(v, (dict, list)))
            elif isinstance(o, list): stack.extend(o)
    return ""

def enrich(url):
    try:
        with urlopen(Request(url, headers={"User-Agent": UA, "Accept-Language": "en,nl;q=0.8"}), timeout=15) as r:
            if "html" not in r.headers.get("Content-Type", ""): return {"ok": True}
            raw = r.read(600_000).decode(r.headers.get_content_charset() or "utf-8", "replace")
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}
    p = Meta()
    try: p.feed(raw)
    except Exception: pass
    m = p.m
    title = html.unescape(m.get("og:title") or m.get("twitter:title") or p.title or "").strip()
    site = html.unescape(m.get("og:site_name") or "").strip()
    if site: title = re.sub(r"\s*[|\-–—:]\s*" + re.escape(site) + r"\s*$", "", title)
    desc = html.unescape(m.get("og:description") or m.get("description") or "").strip()
    return {"ok": True, "title": title[:160], "desc": desc[:260], "site": site[:60],
            "event_date": find_start_date(p.ld)}

# ---------- Fallback title from the URL ----------
def from_url(url):
    p = urlparse(url); host = p.netloc.replace("www.", "")
    skip = r"\d+|en|nl|home|p|e|news|events?|event-details|activiteiten|publications|publicaties|rapporten|agenda|our-events|calendar|posts|story|latest|items|file|d|view|wp-content|uploads|opinions|news-content|how-we-can-help|insights|meeting|register|projects|ministries|documents|policy-notes|homenews|administration|watch|unodc"
    segs = [s for s in unquote(p.path).split("/") if s and not re.fullmatch(skip, s)]
    slug = segs[-1] if segs else ""
    slug = re.sub(r"\.(pdf|html?)$", "", slug); slug = re.sub(r"-\d{6,}.*$", "", slug)
    t = re.sub(r"[-_]+", " ", slug).strip()
    t = re.sub(r"^\d{4,}\s+", "", t); t = re.sub(r"\s+en$", "", t)
    if (not t or len(t) < 4 or re.fullmatch(r"[0-9a-f ]{20,}", t)
            or (re.fullmatch(r"[A-Za-z0-9]{6,10}", t) and re.search(r"\d", t))
            or "youtube" in host or "drive.google" in host or "linkedin" in host):
        t = {"youtube.com": "Video on YouTube", "drive.google.com": "Shared document (Google Drive)",
             "news.un.org": "UN News story", "luma.com": "Event on Luma",
             "linkedin.com": "LinkedIn post"}.get(host, "Link from " + host)
    return t[0].upper() + t[1:], host

def created(card_id):
    return dt.datetime.fromtimestamp(int(card_id[:8], 16), dt.timezone.utc).strftime("%Y-%m-%d")

def clean(s):
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s or "")
    return re.sub(r"\s+", " ", re.sub(r"[*_#>`]", "", s)).strip()[:240]

# ---------- Main ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board-json", help="use a Trello JSON export instead of the API")
    ap.add_argument("--offline", action="store_true", help="skip fetching page metadata")
    ap.add_argument("--out", default=os.path.join(HERE, "dorl-embed.html"))
    a = ap.parse_args()

    board = json.load(open(a.board_json)) if a.board_json else fetch_board()
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    over = json.load(open(OVERRIDES)) if os.path.exists(OVERRIDES) else {}
    now = dt.datetime.now(dt.timezone.utc)

    lists = sorted([l for l in board["lists"] if not l.get("closed") and l["name"] not in EXCLUDE_LISTS],
                   key=lambda l: l["pos"])
    out, fetched = [], 0
    for l in lists:
        cards = sorted([c for c in board["cards"] if c["idList"] == l["id"] and not c.get("closed")],
                       key=lambda c: c["pos"])
        items = []
        for c in cards:
            name = c["name"].strip()
            m = re.match(r"(https?://\S+)$", name)
            if m:
                url = m.group(1); title, host = from_url(url); desc = ""
                meta = cache.get(url)
                stale = meta and not meta.get("ok") and meta.get("tries", 0) < 3
                if not a.offline and (meta is None or stale):
                    meta = enrich(url); meta["tries"] = (cache.get(url) or {}).get("tries", 0) + 1
                    cache[url] = meta; fetched += 1; time.sleep(1)
                if meta and meta.get("ok"):
                    title = meta.get("title") or title; desc = meta.get("desc", "")
                    if meta.get("site"): host = meta["site"]
            else:
                url, host, title, desc = c["shortUrl"], "Collective note", name, clean(c.get("desc"))
                mm = re.search(r"https?://[^\s)\]]+", c.get("desc") or "")
                if mm: url = mm.group(0); host = urlparse(url).netloc.replace("www.", "")
            o = over.get(c.get("shortLink") or "", {})
            title, desc = o.get("title", title), o.get("desc", desc)
            raw_host = urlparse(url).netloc.replace("www.", "")
            items.append({
                "title": title, "url": url, "host": host,
                "favicon": raw_host if raw_host != "trello.com" else "",
                "kind": "PDF" if urlparse(url).path.lower().endswith(".pdf") else ("Video" if "youtube" in raw_host else ""),
                "lang": "NL" if raw_host.endswith(NL_HOSTS) else "",
                "desc": desc, "done": bool(c.get("dueComplete")),
                "added": created(c["id"]), "event": (cache.get(url) or {}).get("event_date", ""),
            })
        out.append({"name": l["name"], "color": l.get("color"), "items": items})

    data = {"board": board["name"], "url": board["url"], "updated": now.strftime("%Y-%m-%d"),
            "newDays": NEW_DAYS, "lists": out}
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    tpl = open(os.path.join(HERE, "template.html"), encoding="utf-8").read()
    open(a.out, "w", encoding="utf-8").write(tpl.replace("/*DATA*/null", payload))
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    json.dump(cache, open(CACHE, "w"), ensure_ascii=False, indent=1, sort_keys=True)
    n = sum(len(l["items"]) for l in out)
    print(f"{n} cards in {len(out)} lists; fetched metadata for {fetched} new links -> {a.out}")

if __name__ == "__main__":
    sys.exit(main())
