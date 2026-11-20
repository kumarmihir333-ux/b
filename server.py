"""Local M11 source-intelligence service. Run with: python server.py"""
from __future__ import annotations

import csv
import hashlib
import io
import html
from html.parser import HTMLParser
import ipaddress
import json
import os
import re
import socket
import sqlite3
import threading
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("M11_DATA_DIR", ROOT / "data")).resolve()
DB_PATH = DATA_DIR / "m11.db"
HOST = os.environ.get("M11_HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))
MAX_FEED_BYTES = 4 * 1024 * 1024
MAX_SOURCES = 30
REFRESH_LOCK = threading.Lock()

DISTRICTS = [
    "Araria", "Arwal", "Aurangabad", "Banka", "Begusarai", "Bhagalpur", "Bhojpur", "Buxar",
    "Darbhanga", "East Champaran", "Gaya", "Gopalganj", "Jamui", "Jehanabad", "Kaimur",
    "Katihar", "Khagaria", "Kishanganj", "Lakhisarai", "Madhepura", "Madhubani", "Munger",
    "Muzaffarpur", "Nalanda", "Nawada", "Patna", "Purnia", "Rohtas", "Saharsa", "Samastipur",
    "Saran", "Sheikhpura", "Sheohar", "Sitamarhi", "Siwan", "Supaul", "Vaishali", "West Champaran",
]
DISTRICT_SOURCE_URL = "https://bvm.bihar.gov.in/district/"
DES_SOURCE_URL = "https://statedata.bihar.gov.in/dataLab/"
DES_SNAPSHOT_DATE = "2026-11-20"
DES_STATE_STATS = [
    ("GSDP at current prices", 1107072, "₹ crore", "2025-26 (advance estimate)", "DES, Bihar"),
    ("GSDP at constant prices", 576645, "₹ crore (2011-12 prices)", "2025-26 (advance estimate)", "DES, Bihar"),
    ("GSDP growth at current prices", 11.77, "%", "2025-26 (advance estimate)", "DES, Bihar"),
    ("GSDP growth at constant prices", 8.74, "%", "2025-26 (advance estimate)", "DES, Bihar"),
    ("Per capita income at current prices", 69321, "₹ per person", "2024-25 (quick estimate)", "DES, Bihar"),
    ("Rice production", 9934021, "metric tonnes", "2024-25", "DES, Bihar"),
    ("Wheat production", 7826998, "metric tonnes", "2024-25", "DES, Bihar"),
    ("Maize production", 6602964, "metric tonnes", "2024-25", "DES, Bihar"),
    ("Literacy rate", 61.8, "%", "Census 2011", "Census 2011"),
]

DEFAULT_SOURCES = [
    {
        "name": "Hindustan Times · Patna",
        "url": "https://www.hindustantimes.com/feeds/rss/cities/patna-news/rssfeed.xml",
        "kind": "feed",
        "category": "News",
    },
    {
        "name": "Bihar DES · Public statistics",
        "url": DES_SOURCE_URL,
        "kind": "bookmark",
        "category": "Dataset",
    },
    {
        "name": "Government of Bihar · District directory",
        "url": DISTRICT_SOURCE_URL,
        "kind": "bookmark",
        "category": "Government",
    },
    {
        "name": "Bihar Chief Minister · Press releases",
        "url": "https://cm.bihar.gov.in/users/PressReleaseN.aspx",
        "kind": "bookmark",
        "category": "Government",
    },
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@contextmanager
def db_connect():
    connection = sqlite3.connect(DB_PATH, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()



def _median(values):
    values=sorted(values);n=len(values)
    if not n:return 0.0
    return values[n//2] if n%2 else (values[n//2-1]+values[n//2])/2

def build_radar_candidates(rows):
    groups={}
    for raw in rows:
        row=dict(raw);key=(row["dataset_id"],row["dataset_name"],row["indicator"],row["unit"],row["district_slug"],row["signal_direction"])
        groups.setdefault(key,[]).append(row)
    buckets={}
    for key,series in groups.items():
        series.sort(key=lambda x:(x["period"],x["id"]));values=[float(x["value_num"]) for x in series];flagged={}
        for i in range(4,len(values)):
            history=values[max(0,i-4):i];baseline=_median(history)
            if abs(baseline)<1e-9:continue
            mad=_median([abs(x-baseline) for x in history]);change=values[i]-baseline;pct=abs(change)/abs(baseline);robust=abs(change)/max(1.4826*mad,abs(baseline)*.05,1e-9)
            if pct>=.25 and robust>=2.5:flagged[i]={"row":series[i],"baseline":baseline,"change_pct":pct,"sign":1 if change>0 else -1}
        for i,hit in flagged.items():
            streak=1;j=i-1
            while j in flagged and flagged[j]["sign"]==hit["sign"]:streak+=1;j-=1
            row=hit["row"];bucket_key=(key[0],key[1],key[2],key[3],row["period"],hit["sign"],key[5])
            buckets.setdefault(bucket_key,[]).append({**hit,"district_slug":row["district_slug"],"district_name":row["district_name"],"streak":streak,"publisher":row["publisher"] or row["source_name"],"source_url":row["source_page"] or row["source_url"],"value":row["value_num"],"unit":row["unit"]})
    candidates=[]
    for key,hits in buckets.items():
        dataset_id,dataset_name,indicator,unit,period,sign,direction=key;districts=sorted({h["district_slug"] for h in hits})
        breadth=2 if len(districts)>=5 else 1 if len(districts)>=2 else 0
        max_change=max(h["change_pct"] for h in hits);magnitude=2 if max_change>=.50 else 1
        persistent=sum(1 for h in hits if h["streak"]>=2);persistence=2 if persistent>=2 else 1
        source_count=len({h["source_url"] for h in hits if h["source_url"]});evidence=2 if source_count>=2 else 1 if source_count==1 else 0;score=magnitude+persistence+breadth+evidence
        favorable={"higher_beneficial":1,"lower_beneficial":-1}.get(direction);adverse={"higher_adverse":1,"lower_adverse":-1}.get(direction)
        category="opportunity" if favorable==sign else "concern" if adverse==sign else "unclassified";movement="rose" if sign>0 else "fell"
        if category=="opportunity":title=f"Potential positive shift · {indicator}";recommendation="Check the source and neighboring indicators. If corroborated, identify what changed and whether the improvement persists before recommending replication."
        elif category=="concern":title=f"Potential concern · {indicator}";recommendation="Verify the latest source, compare affected districts and periods, then route the confirmed issue to the responsible team for review."
        else:title=f"Unclassified change · {indicator}";recommendation="Confirm the measure’s favorable direction and validate the source before describing this as an opportunity or a concern."
        summary=f"{len(districts)} district(s) {movement} by at least {max_change*100:.0f}% from a four-period median during {period}. Candidate signal only; this does not establish an event or cause."
        matrix={"total":score,"maximum":8,"threshold":6,"magnitude":{"score":magnitude,"max":2,"change_pct":round(max_change*100,1),"rule":"25% change = 1; 50% = 2"},"persistence":{"score":persistence,"max":2,"districts_repeating":persistent,"rule":"repeated across 2+ adjacent periods = 2"},"breadth":{"score":breadth,"max":2,"districts":len(districts),"rule":"2–4 districts = 1; 5+ = 2"},"evidence":{"score":evidence,"max":2,"source_pages":source_count,"rule":"one or more linked source pages = 1; 2+ distinct URLs = 2"}}
        fingerprint=hashlib.sha256("|".join(map(str,(dataset_id,indicator,unit,period,sign,direction))).encode()).hexdigest()
        evidence_rows=[{"district":h["district_name"],"district_slug":h["district_slug"],"period":h["row"]["period"],"value":h["value"],"baseline":round(h["baseline"],4),"change_pct":round(h["change_pct"]*100,1),"publisher":h["publisher"],"source_url":h["source_url"]} for h in hits]
        candidates.append({"fingerprint":fingerprint,"category":category,"title":title,"summary":summary,"indicator":indicator,"dataset_name":dataset_name,"period":period,"score":score,"matrix":matrix,"evidence":evidence_rows,"recommendation":recommendation,"status":"pinned" if score>=6 and breadth>=1 and evidence>=1 else "watch"})
    return sorted(candidates,key=lambda x:(x["score"],len(x["evidence"]),x["indicator"]),reverse=True)

def upsert_entity(db, entity_type: str, name: str, slug: str, properties: dict | None = None) -> int:
    db.execute("INSERT OR IGNORE INTO entities(entity_type,name,slug,properties_json,created_at) VALUES(?,?,?,?,?)", (entity_type,name,slug,json.dumps(properties or {},ensure_ascii=False),now_iso()))
    return db.execute("SELECT id FROM entities WHERE entity_type=? AND slug=?", (entity_type,slug)).fetchone()["id"]


def link_entities(db, from_id: int, to_id: int, relation: str, source_url: str = "", confidence: float = 1.0, status: str = "approved") -> None:
    db.execute("INSERT OR IGNORE INTO relationships(from_entity_id,to_entity_id,relation_type,source_url,confidence,status,created_at) VALUES(?,?,?,?,?,?,?)", (from_id,to_id,relation,source_url,confidence,status,now_iso()))


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with db_connect() as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                kind TEXT NOT NULL CHECK(kind IN ('feed','bookmark')),
                category TEXT NOT NULL DEFAULT 'News',
                created_at TEXT NOT NULL,
                last_checked TEXT,
                status TEXT NOT NULL DEFAULT 'ready',
                error TEXT
            );
            CREATE TABLE IF NOT EXISTS app_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS stories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                guid TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL,
                published_at TEXT,
                first_seen TEXT NOT NULL,
                UNIQUE(source_id, guid)
            );
            CREATE INDEX IF NOT EXISTS stories_published ON stories(published_at);
            CREATE INDEX IF NOT EXISTS stories_first_seen ON stories(first_seen);
            CREATE TABLE IF NOT EXISTS entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                name TEXT NOT NULL,
                slug TEXT NOT NULL,
                properties_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                UNIQUE(entity_type, slug)
            );
            CREATE TABLE IF NOT EXISTS datasets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                external_key TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL,
                source_name TEXT NOT NULL,
                source_url TEXT NOT NULL,
                accessed_at TEXT NOT NULL,
                reporting_period TEXT NOT NULL DEFAULT '',
                row_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
                dataset_id INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
                district_slug TEXT NOT NULL,
                indicator TEXT NOT NULL,
                value_num REAL,
                value_text TEXT NOT NULL,
                unit TEXT NOT NULL DEFAULT '',
                period TEXT NOT NULL DEFAULT '',
                signal_direction TEXT NOT NULL DEFAULT 'neutral',
                source_page TEXT NOT NULL DEFAULT '',
                publisher TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
                review_note TEXT NOT NULL DEFAULT '',
                reviewed_at TEXT,
                reviewed_by TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(dataset_id, district_slug, indicator, period)
            );
            CREATE INDEX IF NOT EXISTS observations_district ON observations(district_slug,status);
            CREATE TABLE IF NOT EXISTS relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
                to_entity_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
                relation_type TEXT NOT NULL,
                source_url TEXT NOT NULL DEFAULT '',
                confidence REAL NOT NULL DEFAULT 1.0,
                status TEXT NOT NULL DEFAULT 'approved' CHECK(status IN ('pending','approved','rejected')),
                created_at TEXT NOT NULL,
                UNIQUE(from_entity_id,to_entity_id,relation_type)
            );
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                district_slug TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft'
            );
            CREATE TABLE IF NOT EXISTS pattern_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mode TEXT NOT NULL,
                title TEXT NOT NULL,
                query_json TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS radar_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint TEXT NOT NULL UNIQUE,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                indicator TEXT NOT NULL,
                dataset_name TEXT NOT NULL,
                period TEXT NOT NULL,
                score INTEGER NOT NULL,
                matrix_json TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                recommendation TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'watch' CHECK(status IN ('pinned','watch','dismissed')),
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL
            );
        """)
        observation_columns={row[1] for row in db.execute("PRAGMA table_info(observations)")}
        if "publisher" not in observation_columns:
            db.execute("ALTER TABLE observations ADD COLUMN publisher TEXT NOT NULL DEFAULT ''")
        if "signal_direction" not in observation_columns:
            db.execute("ALTER TABLE observations ADD COLUMN signal_direction TEXT NOT NULL DEFAULT 'neutral'")
        if "reviewed_by" not in observation_columns:
            db.execute("ALTER TABLE observations ADD COLUMN reviewed_by TEXT NOT NULL DEFAULT ''")
        seeded=db.execute("SELECT value FROM app_meta WHERE key='starter_sources_seeded'").fetchone()
        if not seeded:
            for item in DEFAULT_SOURCES:
                db.execute(
                    "INSERT OR IGNORE INTO sources(name,url,kind,category,created_at,status) VALUES(?,?,?,?,?,?)",
                    (item["name"], item["url"], item["kind"], item["category"], now_iso(), "ready"),
                )
            db.execute("INSERT OR REPLACE INTO app_meta(key,value) VALUES('starter_sources_seeded','yes')")
        for district in DISTRICTS:
            slug = re.sub(r"[^a-z0-9]+", "-", district.lower()).strip("-")
            db.execute("INSERT OR IGNORE INTO entities(entity_type,name,slug,properties_json,created_at) VALUES('District',?,?,?,?)", (district, slug, json.dumps({"state":"Bihar","source":DISTRICT_SOURCE_URL}), now_iso()))
        db.execute("INSERT OR IGNORE INTO entities(entity_type,name,slug,properties_json,created_at) VALUES('State','Bihar','bihar',?,?)", (json.dumps({"official_district_count":38,"source":DISTRICT_SOURCE_URL}), now_iso()))
        source = db.execute("SELECT id FROM sources WHERE url=?", (DES_SOURCE_URL,)).fetchone()
        if source:
            dataset_key = f"des-homepage-{DES_SNAPSHOT_DATE}"
            db.execute("INSERT OR IGNORE INTO datasets(external_key,name,description,source_id,source_name,source_url,accessed_at,reporting_period,row_count,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,'approved',?)", (dataset_key,"Bihar DES homepage indicators","A dated snapshot of state-level indicators displayed by the Bihar Directorate of Economics & Statistics Data Lab.",source["id"],"Directorate of Economics & Statistics, Bihar",DES_SOURCE_URL,DES_SNAPSHOT_DATE,"Mixed reporting periods; see each observation",len(DES_STATE_STATS),now_iso()))
            dataset = db.execute("SELECT id FROM datasets WHERE external_key=?", (dataset_key,)).fetchone()
            state = db.execute("SELECT id FROM entities WHERE entity_type='State' AND slug='bihar'").fetchone()
            for indicator,value,unit,period,publisher in DES_STATE_STATS:
                label = f"{value:,.2f}".rstrip("0").rstrip(".") if isinstance(value,float) else f"{value:,}"
                db.execute("INSERT OR IGNORE INTO observations(entity_id,dataset_id,district_slug,indicator,value_num,value_text,unit,period,source_page,publisher,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,'approved',?)", (state["id"],dataset["id"],"bihar",indicator,float(value),label,unit,period,DES_SOURCE_URL,publisher,now_iso()))
        for source_row in db.execute("SELECT id,name,url,category FROM sources").fetchall():
            source_slug = f"source-{source_row['id']}"
            source_entity_id = upsert_entity(db,"Source",source_row["name"],source_slug,{"url":source_row["url"],"category":source_row["category"]})
            if source_row["url"] == DES_SOURCE_URL:
                dataset = db.execute("SELECT id,name FROM datasets WHERE external_key=?", (f"des-homepage-{DES_SNAPSHOT_DATE}",)).fetchone()
                if dataset:
                    dataset_entity_id = upsert_entity(db,"Dataset",dataset["name"],f"dataset-{dataset['id']}",{"source":DES_SOURCE_URL,"accessed_at":DES_SNAPSHOT_DATE})
                    state_entity_id = db.execute("SELECT id FROM entities WHERE entity_type='State' AND slug='bihar'").fetchone()["id"]
                    link_entities(db,source_entity_id,dataset_entity_id,"publishes_dataset",DES_SOURCE_URL)
                    link_entities(db,state_entity_id,dataset_entity_id,"has_dataset",DES_SOURCE_URL)
                    for observation in db.execute("SELECT id,indicator,value_text,unit,period,publisher FROM observations WHERE dataset_id=?",(dataset["id"],)).fetchall():
                        obs_entity_id=upsert_entity(db,"IndicatorObservation",observation["indicator"],f"des-observation-{observation['id']}",{"value":observation["value_text"],"unit":observation["unit"],"period":observation["period"]})
                        link_entities(db,state_entity_id,obs_entity_id,"has_observation",DES_SOURCE_URL)
                        link_entities(db,obs_entity_id,dataset_entity_id,"sourced_from",DES_SOURCE_URL)


def validate_public_https_url(raw: str) -> str:
    parsed = urllib.parse.urlparse(raw.strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Use a public HTTPS URL for the publisher homepage or RSS/Atom feed.")
    hostname = parsed.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith(".localhost") or hostname.endswith(".local"):
        raise ValueError("Local and private-network addresses are not allowed.")
    try:
        addresses = {ipaddress.ip_address(info[4][0]) for info in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)}
    except (OSError, ValueError):
        raise ValueError("The source host could not be resolved.") from None
    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError("The source must resolve only to public internet addresses.")
    return urllib.parse.urlunparse(parsed._replace(fragment=""))


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        validate_public_https_url(newurl)
        return super().redirect_request(request, fp, code, message, headers, newurl)


def strip_markup(value: str) -> str:
    value = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", value or "")
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()[:2400]


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def child_text(node: ET.Element, names: set[str]) -> str:
    for child in node.iter():
        if child is node:
            continue
        if local_name(child.tag) in names:
            value = child.attrib.get("href") or child.text or ""
            if value.strip():
                return value.strip()
    return ""


def normalize_date(value: str) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class FeedDiscoveryParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "link":
            return
        values = {key.lower(): value or "" for key, value in attrs}
        rel = {part.lower() for part in values.get("rel", "").split()}
        kind = values.get("type", "").lower().split(";", 1)[0].strip()
        if "alternate" in rel and kind in {"application/rss+xml", "application/atom+xml", "application/rdf+xml", "application/xml", "text/xml"}:
            href = values.get("href", "").strip()
            if href:
                self.links.append(href)


def read_public_source(url: str) -> bytes:
    safe_url = validate_public_https_url(url)
    opener = urllib.request.build_opener(SafeRedirect())
    request = urllib.request.Request(safe_url, headers={"User-Agent": "M11-Source-Reader/1.0 (+local research tool)", "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, text/html;q=0.9"})
    with opener.open(request, timeout=12) as response:
        payload = response.read(MAX_FEED_BYTES + 1)
    if len(payload) > MAX_FEED_BYTES:
        raise ValueError("Source is larger than the 4 MB safety limit.")
    return payload


def parse_feed(payload: bytes, source_url: str) -> list[dict] | None:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return None
    root_name = local_name(root.tag)
    if root_name not in {"rss", "rdf", "feed"} and not any(local_name(x.tag) in {"channel", "entry"} for x in root.iter()):
        return None
    entries = [node for node in root.iter() if local_name(node.tag) in {"item", "entry"}]
    results = []
    for entry in entries[:120]:
        title = strip_markup(child_text(entry, {"title"}))
        link = child_text(entry, {"link"})
        if link and not link.startswith(("http://", "https://")):
            link = urllib.parse.urljoin(source_url, link)
        if not title or not link.startswith(("http://", "https://")):
            continue
        guid = child_text(entry, {"guid", "id"}) or link
        summary = strip_markup(child_text(entry, {"description", "summary", "encoded", "content"}))
        published = normalize_date(child_text(entry, {"pubdate", "published", "updated", "date"}))
        results.append({"guid": guid[:1000], "title": title[:500], "summary": summary, "url": link[:2000], "published_at": published})
    return results


def fetch_feed(url: str) -> list[dict]:
    safe_url = validate_public_https_url(url)
    payload = read_public_source(safe_url)
    entries = parse_feed(payload, safe_url)
    if entries is not None:
        return entries

    # Allow a public publisher homepage when it advertises an RSS or Atom feed.
    discoverer = FeedDiscoveryParser()
    try:
        discoverer.feed(payload.decode("utf-8", errors="replace"))
    except Exception:
        pass
    for href in discoverer.links[:5]:
        try:
            feed_url = validate_public_https_url(urllib.parse.urljoin(safe_url, href))
            entries = parse_feed(read_public_source(feed_url), feed_url)
            if entries is not None:
                return entries
        except (ValueError, OSError, urllib.error.URLError, ET.ParseError):
            continue
    raise ValueError("No RSS or Atom feed was found. Add the publisher's public feed URL, or use a bookmark for reference.")


def refresh_source(source: dict) -> tuple[int, str | None]:
    try:
        entries = fetch_feed(source["url"])
        checked = now_iso()
        with db_connect() as db:
            for story in entries:
                db.execute("""
                    INSERT INTO stories(source_id,guid,title,summary,url,published_at,first_seen)
                    VALUES(?,?,?,?,?,?,?)
                    ON CONFLICT(source_id,guid) DO UPDATE SET
                      title=excluded.title, summary=excluded.summary, url=excluded.url,
                      published_at=COALESCE(excluded.published_at,stories.published_at)
                """, (source["id"], story["guid"], story["title"], story["summary"], story["url"], story["published_at"], checked))
                source_row=db.execute("SELECT name,category FROM sources WHERE id=?",(source["id"],)).fetchone()
                source_entity_id=upsert_entity(db,"Source",source_row["name"],f"source-{source['id']}",{"url":source["url"],"category":source_row["category"]})
                stable=hashlib.sha256(f"{source['id']}:{story['guid']}".encode("utf-8")).hexdigest()
                story_entity_id=upsert_entity(db,"NewsStory",story["title"],f"story-{stable}",{"url":story["url"],"published_at":story["published_at"],"source_id":source["id"]})
                link_entities(db,source_entity_id,story_entity_id,"published_story",story["url"])
            db.execute("UPDATE sources SET last_checked=?,status='connected',error=NULL WHERE id=?", (checked, source["id"]))
        return len(entries), None
    except Exception as exc:
        message = str(exc).replace("\n", " ")[:240]
        with db_connect() as db:
            db.execute("UPDATE sources SET last_checked=?,status='error',error=? WHERE id=?", (now_iso(), message, source["id"]))
        return 0, message


def json_bytes(value) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "M11Local/1.0"

    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def send_json(self, status: int, value) -> None:
        payload = json_bytes(value)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def read_json(self, max_bytes: int = 12000) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length < 1 or length > max_bytes:
            raise ValueError("Request body is missing or too large.")
        data = json.loads(self.rfile.read(length))
        if not isinstance(data, dict):
            raise ValueError("Expected a JSON object.")
        return data

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/ontology":
            params=urllib.parse.parse_qs(parsed.query)
            query=(params.get("q",[""])[0] or "").strip()[:100]
            entity_type=(params.get("type",[""])[0] or "").strip()[:40]
            scope=(params.get("scope",["development"])[0] or "development")
            clauses=["1=1"];values=[]
            if query:clauses.append("(name LIKE ? OR slug LIKE ?)");values.extend([f"%{query}%",f"%{query}%"])
            if entity_type:clauses.append("entity_type=?");values.append(entity_type)
            elif scope=="development":clauses.append("entity_type IN ('State','District','Dataset','IndicatorObservation','Source','Scheme','Department','Project')")
            elif scope=="media":clauses.append("entity_type IN ('Source','NewsStory')")
            with db_connect() as db:
                nodes=[dict(row) for row in db.execute(f"SELECT id,entity_type,name,slug,properties_json FROM entities WHERE {' AND '.join(clauses)} ORDER BY entity_type,name LIMIT 400",values).fetchall()]
                node_ids=[n["id"] for n in nodes]
                edges=[]
                if node_ids:
                    slots=','.join('?' for _ in node_ids)
                    edges=[dict(row) for row in db.execute(f"""SELECT r.id,r.from_entity_id,r.to_entity_id,r.relation_type,r.source_url,r.confidence,
                        a.name AS from_name,a.entity_type AS from_type,b.name AS to_name,b.entity_type AS to_type
                        FROM relationships r JOIN entities a ON a.id=r.from_entity_id JOIN entities b ON b.id=r.to_entity_id
                        WHERE r.status='approved' AND r.from_entity_id IN ({slots}) AND r.to_entity_id IN ({slots}) LIMIT 800""",node_ids+node_ids).fetchall()]
                counts=[dict(row) for row in db.execute("SELECT entity_type,COUNT(*) AS count FROM entities GROUP BY entity_type ORDER BY entity_type").fetchall()]
            return self.send_json(200,{"nodes":nodes,"edges":edges,"counts":counts})
        if parsed.path == "/api/dashboard":
            with db_connect() as db:
                districts=[]
                for row in db.execute("SELECT id,name,slug FROM entities WHERE entity_type='District' ORDER BY name"):
                    count=db.execute("SELECT COUNT(*) FROM observations WHERE district_slug=? AND status='approved'",(row["slug"],)).fetchone()[0]
                    districts.append({"id":row["id"],"name":row["name"],"slug":row["slug"],"observation_count":count})
                state_observations=[dict(row) for row in db.execute("""
                    SELECT o.id,o.indicator,o.value_num,o.value_text,o.unit,o.period,o.source_page,o.publisher,d.source_name,d.source_url,d.accessed_at
                    FROM observations o JOIN datasets d ON d.id=o.dataset_id
                    WHERE o.district_slug='bihar' AND o.status='approved' ORDER BY o.indicator
                """).fetchall()]
                pending=db.execute("SELECT COUNT(*) FROM observations WHERE status='pending'").fetchone()[0]
                datasets=db.execute("SELECT COUNT(*) FROM datasets").fetchone()[0]
                story_count=db.execute("SELECT COUNT(*) FROM stories").fetchone()[0]
            return self.send_json(200,{"districts":districts,"state_observations":state_observations,"pending_reviews":pending,"datasets":datasets,"stories":story_count,"district_source":DISTRICT_SOURCE_URL,"data_source":DES_SOURCE_URL})
        if parsed.path == "/api/radar":
            with db_connect() as db:
                rows=[dict(row) for row in db.execute("SELECT id,category,title,summary,indicator,dataset_name,period,score,matrix_json,evidence_json,recommendation,status,first_seen,last_seen FROM radar_signals ORDER BY CASE status WHEN 'pinned' THEN 0 WHEN 'watch' THEN 1 ELSE 2 END,score DESC,last_seen DESC LIMIT 200").fetchall()]
            for row in rows:
                row["matrix"]=json.loads(row.pop("matrix_json") or "{}")
                row["evidence"]=json.loads(row.pop("evidence_json") or "[]")
            return self.send_json(200,rows)
        if parsed.path == "/api/patterns/data":
            with db_connect() as db:
                observations=[dict(row) for row in db.execute("""SELECT o.id,o.district_slug,e.name AS district_name,o.indicator,o.value_num,o.value_text,o.unit,o.period,o.publisher,d.name AS dataset_name,d.source_name,d.source_url,o.source_page FROM observations o JOIN datasets d ON d.id=o.dataset_id JOIN entities e ON e.entity_type='District' AND e.slug=o.district_slug WHERE o.status='approved' AND o.value_num IS NOT NULL ORDER BY o.district_slug,o.indicator,o.period""").fetchall()]
                stories=[dict(row) for row in db.execute("""SELECT s.title,s.summary,COALESCE(s.published_at,s.first_seen) AS occurred_at,s.url,so.name AS source_name FROM stories s JOIN sources so ON so.id=s.source_id ORDER BY occurred_at LIMIT 5000""").fetchall()]
                runs=[dict(row) for row in db.execute("SELECT id,mode,title,created_at,result_json FROM pattern_runs ORDER BY id DESC LIMIT 30").fetchall()]
            for run in runs:
                try: run["result"]=json.loads(run.pop("result_json"))
                except (ValueError,TypeError): run["result"]={}
            return self.send_json(200,{"observations":observations,"stories":stories,"runs":runs})
        if parsed.path == "/api/catalog":
            with db_connect() as db:
                rows=db.execute("""
                    SELECT d.id,d.name,d.description,d.source_name,d.source_url,d.accessed_at,d.reporting_period,d.row_count,d.status,d.created_at,
                    SUM(CASE WHEN o.status='approved' THEN 1 ELSE 0 END) AS approved_count,
                    SUM(CASE WHEN o.status='pending' THEN 1 ELSE 0 END) AS pending_count
                    FROM datasets d LEFT JOIN observations o ON o.dataset_id=d.id GROUP BY d.id ORDER BY d.created_at DESC
                """).fetchall()
            return self.send_json(200,[dict(row) for row in rows])
        if parsed.path == "/api/reviews":
            with db_connect() as db:
                rows=db.execute("""
                    SELECT o.id,o.indicator,o.value_text,o.unit,o.period,o.signal_direction,o.district_slug,o.created_at,o.source_page,
                    e.name AS district_name,d.name AS dataset_name,d.source_name,d.source_url
                    FROM observations o JOIN entities e ON e.slug=o.district_slug AND e.entity_type='District'
                    JOIN datasets d ON d.id=o.dataset_id WHERE o.status='pending' ORDER BY o.created_at
                """).fetchall()
            return self.send_json(200,[dict(row) for row in rows])
        if parsed.path == "/api/workflows":
            with db_connect() as db:
                pending=db.execute("SELECT COUNT(*) FROM observations WHERE status='pending'").fetchone()[0]
                broken=db.execute("SELECT id,name,error,last_checked FROM sources WHERE status='error'").fetchall()
                unchecked=db.execute("SELECT COUNT(*) FROM sources WHERE kind='feed' AND (last_checked IS NULL OR last_checked < ?)",(datetime.fromtimestamp(datetime.now(timezone.utc).timestamp()-86400,timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z"),)).fetchone()[0]
                latest=db.execute("SELECT created_at FROM reports ORDER BY created_at DESC LIMIT 1").fetchone()
            tasks=[]
            if pending: tasks.append({"type":"review","priority":"high","count":pending,"title":f"Review {pending} imported indicator rows","detail":"Unreviewed values are hidden from the district dashboard."})
            for source in broken: tasks.append({"type":"source","priority":"medium","count":1,"title":f"Reconnect {source['name']}","detail":source["error"] or "The feed did not refresh successfully."})
            if unchecked: tasks.append({"type":"refresh","priority":"low","count":unchecked,"title":f"Refresh {unchecked} feed source(s)","detail":"No successful capture in the last 24 hours."})
            return self.send_json(200,{"tasks":tasks,"pending_reviews":pending,"failed_sources":len(broken),"feeds_needing_refresh":unchecked,"last_report":latest["created_at"] if latest else None})
        if parsed.path == "/api/reports":
            with db_connect() as db:
                rows=db.execute("SELECT id,title,district_slug,created_at,status FROM reports ORDER BY created_at DESC LIMIT 100").fetchall()
            return self.send_json(200,[dict(row) for row in rows])
        report_match=re.fullmatch(r"/api/reports/(\d+)",parsed.path)
        if report_match:
            with db_connect() as db:
                row=db.execute("SELECT id,title,district_slug,content,created_at,status FROM reports WHERE id=?",(int(report_match.group(1)),)).fetchone()
            return self.send_json(200,dict(row)) if row else self.send_json(404,{"error":"Report not found."})
        district_match=re.fullmatch(r"/api/districts/([a-z0-9-]+)",parsed.path)
        if district_match:
            slug=district_match.group(1)
            with db_connect() as db:
                district=db.execute("SELECT id,name,slug,properties_json FROM entities WHERE entity_type='District' AND slug=?",(slug,)).fetchone()
                if not district:return self.send_json(404,{"error":"District not found."})
                observations=db.execute("""
                    SELECT o.id,o.indicator,o.value_num,o.value_text,o.unit,o.period,o.source_page,o.publisher,o.status,d.name AS dataset_name,d.source_name,d.source_url,d.accessed_at
                    FROM observations o JOIN datasets d ON d.id=o.dataset_id WHERE o.district_slug=? AND o.status='approved' ORDER BY o.indicator,o.period DESC
                """,(slug,)).fetchall()
            return self.send_json(200,{"district":dict(district),"observations":[dict(row) for row in observations]})
        if parsed.path == "/api/health":
            with db_connect() as db:
                sources = db.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
                stories = db.execute("SELECT COUNT(*) FROM stories").fetchone()[0]
            return self.send_json(200, {"ok": True, "mode": "local", "sources": sources, "stories": stories, "updated_at": now_iso()})
        if parsed.path == "/api/sources":
            with db_connect() as db:
                rows = db.execute("SELECT id,name,url,kind,category,created_at,last_checked,status,error FROM sources ORDER BY category,name").fetchall()
            return self.send_json(200, [dict(row) for row in rows])
        if parsed.path == "/api/stories":
            params = urllib.parse.parse_qs(parsed.query)
            query = (params.get("q", [""])[0] or "").strip()[:120]
            bucket = params.get("bucket", ["live"])[0]
            source_id = params.get("source", [""])[0]
            clauses, values = [], []
            if query:
                clauses.append("(s.title LIKE ? OR s.summary LIKE ? OR so.name LIKE ?)")
                values.extend([f"%{query}%"] * 3)
            if bucket == "archive":
                clauses.append("COALESCE(s.published_at,s.first_seen) < ?")
                values.append(datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() - 7 * 86400, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"))
            else:
                clauses.append("(s.published_at IS NULL OR s.published_at >= ?)")
                values.append(datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() - 7 * 86400, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"))
            if source_id.isdigit():
                clauses.append("so.id=?")
                values.append(int(source_id))
            where = " WHERE " + " AND ".join(clauses) if clauses else ""
            with db_connect() as db:
                rows = db.execute(f"""
                    SELECT s.id,s.title,s.summary,s.url,s.published_at,s.first_seen,so.id AS source_id,so.name AS source_name,so.category AS source_category
                    FROM stories s JOIN sources so ON so.id=s.source_id{where}
                    ORDER BY COALESCE(s.published_at,s.first_seen) DESC LIMIT 250
                """, values).fetchall()
            return self.send_json(200, [dict(row) for row in rows])

        static = {"/": "index.html", "/index.html": "index.html", "/styles.css": "styles.css", "/motion.css": "motion.css", "/signals.css": "signals.css", "/data.css": "data.css", "/patterns.css": "patterns.css", "/event-analysis.css": "event-analysis.css", "/lusion-theme.css": "lusion-theme.css", "/radar.css": "radar.css", "/world-model-event.schema.json": "world-model-event.schema.json", "/app.js": "app.js"}
        name = static.get(parsed.path)
        if name:
            path = ROOT / name
            try:
                payload = path.read_bytes()
            except OSError:
                return self.send_error(404)
            content_type = "text/html; charset=utf-8" if name.endswith("html") else ("text/javascript; charset=utf-8" if name.endswith("js") else ("application/schema+json; charset=utf-8" if name.endswith("json") else "text/css; charset=utf-8"))
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            return self.wfile.write(payload)
        self.send_error(404)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/radar/scan":
            try:
                with db_connect() as db:
                    rows=db.execute("""SELECT o.id,o.dataset_id,d.name AS dataset_name,o.district_slug,e.name AS district_name,o.indicator,o.value_num,o.unit,o.period,o.publisher,o.signal_direction,o.source_page,d.source_name,d.source_url FROM observations o JOIN datasets d ON d.id=o.dataset_id JOIN entities e ON e.entity_type='District' AND e.slug=o.district_slug WHERE o.status='approved' AND o.value_num IS NOT NULL AND o.period<>'' ORDER BY d.name,o.indicator,o.district_slug,o.period""").fetchall()
                    candidates=build_radar_candidates(rows);now=now_iso()
                    for item in candidates:
                        existing=db.execute("SELECT status FROM radar_signals WHERE fingerprint=?",(item["fingerprint"],)).fetchone()
                        status="dismissed" if existing and existing["status"]=="dismissed" else "pinned" if existing and existing["status"]=="pinned" else item["status"]
                        db.execute("""INSERT INTO radar_signals(fingerprint,category,title,summary,indicator,dataset_name,period,score,matrix_json,evidence_json,recommendation,status,first_seen,last_seen) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(fingerprint) DO UPDATE SET category=excluded.category,title=excluded.title,summary=excluded.summary,score=excluded.score,matrix_json=excluded.matrix_json,evidence_json=excluded.evidence_json,recommendation=excluded.recommendation,status=?,last_seen=excluded.last_seen""",(item["fingerprint"],item["category"],item["title"],item["summary"],item["indicator"],item["dataset_name"],item["period"],item["score"],json.dumps(item["matrix"],ensure_ascii=False),json.dumps(item["evidence"],ensure_ascii=False),item["recommendation"],status,now,now,status,now))
                    results=[dict(r) for r in db.execute("SELECT id,category,title,summary,indicator,dataset_name,period,score,matrix_json,evidence_json,recommendation,status,first_seen,last_seen FROM radar_signals WHERE status!='dismissed' ORDER BY CASE status WHEN 'pinned' THEN 0 ELSE 1 END,score DESC,last_seen DESC LIMIT 200").fetchall()]
                for row in results:row["matrix"]=json.loads(row.pop("matrix_json"));row["evidence"]=json.loads(row.pop("evidence_json"))
                return self.send_json(200,{"signals":results,"scanned_observations":len(rows),"threshold":6})
            except sqlite3.Error as exc:return self.send_json(500,{"error":f"Radar scan failed: {exc}"})
        radar_signal_match=re.fullmatch(r"/api/radar/signals/(\d+)",path)
        if radar_signal_match:
            try:
                data=self.read_json();status=str(data.get("status",""))
                if status not in {"pinned","watch","dismissed"}:raise ValueError("Choose pin, watch, or dismiss.")
                with db_connect() as db:
                    cursor=db.execute("UPDATE radar_signals SET status=? WHERE id=?",(status,int(radar_signal_match.group(1))))
                    if not cursor.rowcount:return self.send_json(404,{"error":"Radar signal not found."})
                return self.send_json(200,{"id":int(radar_signal_match.group(1)),"status":status})
            except (ValueError,json.JSONDecodeError) as exc:return self.send_json(400,{"error":str(exc)})
        if path == "/api/patterns/runs":
            try:
                data=self.read_json(max_bytes=500_000)
                mode=str(data.get("mode",""))
                if mode not in {"indicator","news"}: raise ValueError("Choose indicator or news coverage mode.")
                title=re.sub(r"\s+"," ",str(data.get("title","Pattern review")).strip())[:180]
                query=json.dumps(data.get("query",{}),ensure_ascii=False)
                result=json.dumps(data.get("result",{}),ensure_ascii=False)
                with db_connect() as db:
                    cursor=db.execute("INSERT INTO pattern_runs(mode,title,query_json,result_json,created_at) VALUES(?,?,?,?,?)",(mode,title,query,result,now_iso()))
                return self.send_json(201,{"id":cursor.lastrowid,"title":title,"created_at":now_iso()})
            except (ValueError,json.JSONDecodeError) as exc:return self.send_json(400,{"error":str(exc)})
        if path == "/api/imports":
            try:
                data=self.read_json(max_bytes=2_500_000)
                name=re.sub(r"\s+"," ",str(data.get("name","")).strip())[:160]
                source_name=re.sub(r"\s+"," ",str(data.get("source_name","")).strip())[:120]
                if not name or not source_name: raise ValueError("Dataset name and publisher are required.")
                source_url=validate_public_https_url(str(data.get("source_url","")))
                content=str(data.get("csv",""))
                if not content or len(content.encode("utf-8"))>2_000_000: raise ValueError("Choose a CSV file smaller than 2 MB.")
                reader=csv.DictReader(io.StringIO(content.lstrip("\ufeff")))
                headers={str(h or "").strip().lower().replace(" ","_") for h in (reader.fieldnames or [])}
                required={"district","indicator","value"}
                if not required.issubset(headers): raise ValueError("CSV needs these columns: district, indicator, value. Optional columns: unit, period, source_page, signal_direction.")
                aliases={"purnea":"purnia","purniya":"purnia","gaya ji":"gaya","kaimur (bhabua)":"kaimur","east champaran":"east champaran","purbi champaran":"east champaran","purvi champaran":"east champaran","west champaran":"west champaran","paschim champaran":"west champaran","purvi champaran":"east champaran","jahaanabad":"jehanabad"}
                known={re.sub(r"[^a-z0-9]+"," ",d.lower()).strip():re.sub(r"[^a-z0-9]+","-",d.lower()).strip("-") for d in DISTRICTS}
                parsed_rows=[]; errors=[]
                for line,row in enumerate(reader,start=2):
                    if line>5001: errors.append("CSV exceeds the 5,000 row limit.");break
                    row={str(k or "").strip().lower().replace(" ","_"):str(v or "").strip() for k,v in row.items()}
                    raw_district=row.get("district","").lower()
                    district_key=aliases.get(raw_district,raw_district)
                    district_key=re.sub(r"[^a-z0-9]+"," ",district_key).strip()
                    if district_key not in known: errors.append(f"Row {line}: unknown district '{row.get('district','')}'.");continue
                    indicator=row.get("indicator","")[:180]
                    raw_value=row.get("value","")[:100]
                    if not indicator or not raw_value: errors.append(f"Row {line}: indicator and value are required.");continue
                    signal_direction=row.get("signal_direction","neutral").strip().lower() or "neutral"
                    if signal_direction not in {"higher_beneficial","higher_adverse","lower_beneficial","lower_adverse","neutral"}:errors.append(f"Row {line}: signal_direction must be higher_beneficial, higher_adverse, lower_beneficial, lower_adverse, or neutral.");continue
                    numeric=re.sub(r"[₹,%\s]","",raw_value).replace(",","")
                    try:value_num=float(numeric)
                    except ValueError:value_num=None
                    source_page=row.get("source_page","")
                    if source_page:
                        try:source_page=validate_public_https_url(source_page)
                        except ValueError:errors.append(f"Row {line}: source_page must be a public HTTPS URL.");continue
                    parsed_rows.append({"district_slug":known[district_key],"district_name":DISTRICTS[[re.sub(r"[^a-z0-9]+"," ",x.lower()).strip() for x in DISTRICTS].index(district_key)],"indicator":indicator,"value_text":raw_value,"value_num":value_num,"unit":row.get("unit","")[:80],"period":row.get("period","")[:80] or str(data.get("period","")).strip()[:80],"signal_direction":signal_direction,"source_page":source_page,"scheme":row.get("scheme","")[:160],"project":row.get("project","")[:160],"department":row.get("department","")[:160]})
                if not parsed_rows: raise ValueError("No valid rows found. " + (" ".join(errors[:3]) if errors else "Check your CSV."))
                dataset_key="import-"+hashlib.sha256((name+source_url+content).encode("utf-8")).hexdigest()[:24]
                with db_connect() as db:
                    db.execute("INSERT OR IGNORE INTO sources(name,url,kind,category,created_at,status) VALUES(?,?, 'bookmark','Dataset',?,'bookmark')",(source_name,source_url,now_iso()))
                    source_id=db.execute("SELECT id FROM sources WHERE url=?",(source_url,)).fetchone()["id"]
                    source_entity_id=upsert_entity(db,"Source",source_name,f"source-{source_id}",{"url":source_url,"category":"Dataset"})
                    cursor=db.execute("INSERT INTO datasets(external_key,name,description,source_id,source_name,source_url,accessed_at,reporting_period,row_count,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,'pending',?)",(dataset_key,name,str(data.get("description", "")).strip()[:1000],source_id,source_name,source_url,now_iso(),str(data.get("period","")).strip()[:80],len(parsed_rows),"pending",now_iso()))
                    dataset_id=cursor.lastrowid
                    dataset_entity_id=upsert_entity(db,"Dataset",name,f"dataset-{dataset_id}",{"source":source_url,"status":"pending"})
                    link_entities(db,source_entity_id,dataset_entity_id,"publishes_dataset",source_url,status="pending")
                    for row in parsed_rows:
                        district_entity=db.execute("SELECT id FROM entities WHERE entity_type='District' AND slug=?",(row["district_slug"],)).fetchone()
                        cursor=db.execute("INSERT INTO observations(entity_id,dataset_id,district_slug,indicator,value_num,value_text,unit,period,signal_direction,source_page,publisher,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?, 'pending',?)",(district_entity["id"],dataset_id,row["district_slug"],row["indicator"],row["value_num"],row["value_text"],row["unit"],row["period"],row["signal_direction"],row["source_page"] or source_url,source_name,now_iso()))
                        obs_entity_id=upsert_entity(db,"IndicatorObservation",row["indicator"],f"import-observation-{cursor.lastrowid}",{"district":row["district_name"],"value":row["value_text"],"unit":row["unit"],"period":row["period"],"review_status":"pending"})
                        link_entities(db,district_entity["id"],obs_entity_id,"has_observation",row["source_page"] or source_url,0.8,"pending")
                        link_entities(db,obs_entity_id,dataset_entity_id,"sourced_from",row["source_page"] or source_url,0.8,"pending")
                        if row["scheme"]:
                            scheme_slug="scheme-"+hashlib.sha256(row["scheme"].lower().encode("utf-8")).hexdigest()[:20]
                            scheme_id=upsert_entity(db,"Scheme",row["scheme"],scheme_slug,{"source":source_url})
                            link_entities(db,obs_entity_id,scheme_id,"indicates_scheme",row["source_page"] or source_url,0.8,"pending")
                            if row["department"]:
                                department_slug="department-"+hashlib.sha256(row["department"].lower().encode("utf-8")).hexdigest()[:20]
                                department_id=upsert_entity(db,"Department",row["department"],department_slug,{"source":source_url})
                                link_entities(db,scheme_id,department_id,"managed_by",row["source_page"] or source_url,0.8,"pending")
                        if row["project"]:
                            project_slug="project-"+hashlib.sha256(row["project"].lower().encode("utf-8")).hexdigest()[:20]
                            project_id=upsert_entity(db,"Project",row["project"],project_slug,{"source":source_url})
                            link_entities(db,obs_entity_id,project_id,"indicates_project",row["source_page"] or source_url,0.8,"pending")
                return self.send_json(201,{"dataset_id":dataset_id,"name":name,"imported":len(parsed_rows),"errors":errors[:20],"status":"pending review"})
            except sqlite3.IntegrityError as exc:
                return self.send_json(409,{"error":"This dataset or one of its rows is already imported. Change the dataset name or correct duplicate rows."})
            except (ValueError,json.JSONDecodeError) as exc:
                return self.send_json(400,{"error":str(exc)})
        review_match=re.fullmatch(r"/api/reviews/(\d+)",path)
        if review_match:
            try:
                data=self.read_json()
                decision=data.get("decision")
                if decision not in {"approved","rejected"}:raise ValueError("Choose approve or reject.")
                note=str(data.get("note","")).strip()[:500]
                reviewer=re.sub(r"\s+"," ",str(data.get("reviewer","")).strip())[:80]
                with db_connect() as db:
                    row=db.execute("SELECT * FROM observations WHERE id=? AND status='pending'",(int(review_match.group(1)),)).fetchone()
                    if not row:return self.send_json(404,{"error":"Pending observation not found."})
                    db.execute("UPDATE observations SET status=?,review_note=?,reviewed_at=?,reviewed_by=? WHERE id=?",(decision,note,now_iso(),reviewer,row["id"]))
                    obs_slug=f"import-observation-{row['id']}"
                    obs_entity_record=db.execute("SELECT properties_json FROM entities WHERE entity_type='IndicatorObservation' AND slug=?",(obs_slug,)).fetchone()
                    if obs_entity_record:
                        obs_properties=json.loads(obs_entity_record["properties_json"] or "{}")
                        obs_properties["review_status"]=decision
                        db.execute("UPDATE entities SET properties_json=? WHERE entity_type='IndicatorObservation' AND slug=?",(json.dumps(obs_properties,ensure_ascii=False),obs_slug))
                    if decision=='approved':
                        dataset=db.execute("SELECT source_url FROM datasets WHERE id=?",(row["dataset_id"],)).fetchone()
                        obs_entity=db.execute("SELECT id FROM entities WHERE entity_type='IndicatorObservation' AND slug=?",(f"import-observation-{row['id']}",)).fetchone()
                        district_entity=db.execute("SELECT id FROM entities WHERE entity_type='District' AND slug=?",(row["district_slug"],)).fetchone()
                        if obs_entity and district_entity:
                            link_entities(db,district_entity["id"],obs_entity["id"],"has_observation",dataset["source_url"])
                            db.execute("UPDATE relationships SET status='approved' WHERE (from_entity_id=? OR to_entity_id=?) AND status='pending'",(obs_entity["id"],obs_entity["id"]))
                            linked=db.execute("SELECT to_entity_id,relation_type FROM relationships WHERE from_entity_id=? AND relation_type IN ('indicates_scheme','indicates_project') AND status='approved'",(obs_entity["id"],)).fetchall()
                            for relation in linked:link_entities(db,district_entity["id"],relation["to_entity_id"],relation["relation_type"].replace('indicates_','has_'),dataset["source_url"])
                        if obs_entity:
                            dataset_entity=db.execute("SELECT id FROM entities WHERE entity_type='Dataset' AND slug=?",(f"dataset-{row['dataset_id']}",)).fetchone()
                            if dataset_entity:link_entities(db,obs_entity["id"],dataset_entity["id"],"sourced_from",dataset["source_url"])
                    db.execute("UPDATE datasets SET status=CASE WHEN NOT EXISTS(SELECT 1 FROM observations WHERE dataset_id=? AND status='pending') THEN 'approved' ELSE 'pending' END WHERE id=?",(row["dataset_id"],row["dataset_id"]))
                return self.send_json(200,{"id":row["id"],"status":decision})
            except (ValueError,json.JSONDecodeError) as exc:return self.send_json(400,{"error":str(exc)})
        if path == "/api/reports":
            try:
                data=self.read_json()
                slug=str(data.get("district_slug", "bihar")).strip().lower()
                with db_connect() as db:
                    entity=db.execute("SELECT name,slug FROM entities WHERE entity_type IN ('District','State') AND slug=?",(slug,)).fetchone()
                    if not entity:return self.send_json(404,{"error":"Choose a listed Bihar district or the state."})
                    rows=db.execute("""
                        SELECT o.indicator,o.value_text,o.unit,o.period,o.source_page,o.publisher,d.source_name,d.source_url
                        FROM observations o JOIN datasets d ON d.id=o.dataset_id WHERE o.district_slug=? AND o.status='approved' ORDER BY o.indicator
                    """,(slug,)).fetchall()
                    stories=db.execute("SELECT s.title,s.url,s.published_at,so.name AS source_name FROM stories s JOIN sources so ON so.id=s.source_id WHERE s.title LIKE ? OR s.summary LIKE ? ORDER BY COALESCE(s.published_at,s.first_seen) DESC LIMIT 10",(f"%{entity['name']}%",f"%{entity['name']}%")).fetchall()
                    title=f"{entity['name']} development evidence brief"
                    lines=[f"# {title}","",f"Generated {now_iso()}","","## Verified indicators",""]
                    for row in rows:lines.append(f"- **{row['indicator']}:** {row['value_text']} {row['unit']} ({row['period']}). Source: {row['publisher'] or row['source_name']} via [{row['source_name']}]({row['source_page'] or row['source_url']}).")
                    if not rows:lines.append("No approved district-level indicators are currently in the M11 archive.")
                    lines.extend(["",f"## News leads mentioning {entity['name']}",""])
                    for row in stories:lines.append(f"- [{row['title']}]({row['url']}) — {row['source_name']} ({row['published_at'] or 'date not provided'}).")
                    if not stories:lines.append("No captured feed headlines mention this place. No other stories were assumed to be related.")
                    else:lines.append("These headlines are research leads only; a mention does not verify an outcome.")
                    lines.extend(["","## Evidence and limitations","","This draft uses only observations approved in the M11 review queue. Verify each cited source and reporting period before publication. News signals are leads and do not establish a development outcome."])
                    content="\n".join(lines)
                    cursor=db.execute("INSERT INTO reports(title,district_slug,content,created_at,status) VALUES(?,?,?,?,'draft')",(title,slug,content,now_iso()))
                    report_id=cursor.lastrowid
                return self.send_json(201,{"id":report_id,"title":title,"district_slug":slug,"content":content,"created_at":now_iso(),"status":"draft"})
            except (ValueError,json.JSONDecodeError) as exc:return self.send_json(400,{"error":str(exc)})
        if path == "/api/sources":
            try:
                data = self.read_json()
                kind = data.get("kind", "feed")
                if kind not in {"feed", "bookmark"}:
                    raise ValueError("Source type must be a feed or a bookmark.")
                name = re.sub(r"\s+", " ", str(data.get("name", "")).strip())[:100]
                if not name:
                    raise ValueError("Add a name for this source.")
                url = validate_public_https_url(str(data.get("url", "")))
                category = str(data.get("category", "News")).strip()[:40] or "News"
                with db_connect() as db:
                    count = db.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
                    if count >= MAX_SOURCES:
                        raise ValueError(f"This local workspace is limited to {MAX_SOURCES} sources.")
                    cursor = db.execute("INSERT INTO sources(name,url,kind,category,created_at,status) VALUES(?,?,?,?,?,?)", (name, url, kind, category, now_iso(), "ready" if kind == "feed" else "bookmark"))
                    source_id = cursor.lastrowid
                    row = db.execute("SELECT id,name,url,kind,category,created_at,last_checked,status,error FROM sources WHERE id=?", (source_id,)).fetchone()
                return self.send_json(201, dict(row))
            except sqlite3.IntegrityError:
                return self.send_json(409, {"error": "That source is already in your registry."})
            except (ValueError, json.JSONDecodeError) as exc:
                return self.send_json(400, {"error": str(exc)})
        if path == "/api/refresh":
            if not REFRESH_LOCK.acquire(blocking=False):
                return self.send_json(409, {"error": "A refresh is already running."})
            try:
                with db_connect() as db:
                    sources = [dict(row) for row in db.execute("SELECT id,name,url FROM sources WHERE kind='feed' ORDER BY name LIMIT ?", (MAX_SOURCES,)).fetchall()]
                counts, errors = {}, []
                with ThreadPoolExecutor(max_workers=4) as pool:
                    futures = [pool.submit(refresh_source, source) for source in sources]
                    for source, future in zip(sources, futures):
                        count, error = future.result()
                        counts[source["name"]] = count
                        if error:
                            errors.append({"source": source["name"], "error": error})
                with db_connect() as db:
                    total = db.execute("SELECT COUNT(*) FROM stories").fetchone()[0]
                return self.send_json(200, {"checked": len(sources), "new_or_updated": sum(counts.values()), "total_archived": total, "counts": counts, "errors": errors, "updated_at": now_iso()})
            finally:
                REFRESH_LOCK.release()
        return self.send_error(404)

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        match = re.fullmatch(r"/api/sources/(\d+)", parsed.path)
        if not match:
            return self.send_error(404)
        with db_connect() as db:
            cursor = db.execute("DELETE FROM sources WHERE id=?", (int(match.group(1)),))
        if cursor.rowcount == 0:
            return self.send_json(404, {"error": "Source not found."})
        return self.send_json(200, {"deleted": True})


if __name__ == "__main__":
    init_db()
    print(f"M11 AI source intelligence: http://{HOST}:{PORT}")
    print(f"Local archive database: {DB_PATH}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
