"""
Allen Universal Crawler
=======================
Autonomous recursive BFS web crawler for mapping an authenticated ed-tech platform.
Uses Playwright (sync API) for browser automation and BeautifulSoup for DOM parsing.

Usage:
    1. Run: python allen_universal_crawler.py
    2. Log in manually in the browser window that opens.
    3. Press Enter in the terminal once you're on the main dashboard.
    4. The crawler will autonomously map the entire platform.

Output:
    universal_curriculum.json — hierarchical curriculum data updated in real-time.
"""

import json
import re
import time
import random
import hashlib
from collections import deque
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from bs4 import BeautifulSoup, Tag


# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────

OUTPUT_FILE = "universal_curriculum.json"
DELAY_RANGE = (2, 5)            # seconds between page visits
PAGE_LOAD_TIMEOUT = 30_000      # ms — Playwright page load timeout
MAX_RETRIES = 2                 # retries on navigation failure
SCROLL_PAUSE = 1.0              # seconds to wait after scrolling for lazy content

# Words in URLs/link text that signal we should NOT follow the link
BLACKLIST_KEYWORDS = [
    "logout", "log-out", "signout", "sign-out",
    "profile", "my-profile",
    "support", "help", "contact",
    "settings", "preferences",
    "cart", "checkout", "payment", "billing",
    "notify", "notification",
    "feedback", "survey",
    "advertisement", "promo",
]

# File extensions we track as downloadable resources (not pages to crawl)
RESOURCE_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".ppt", ".pptx",
    ".xls", ".xlsx", ".csv", ".zip", ".rar",
    ".mp4", ".mp3", ".webm", ".ogg",
    ".png", ".jpg", ".jpeg", ".gif", ".svg",
}


# ──────────────────────────────────────────────
# Utility helpers
# ──────────────────────────────────────────────

def human_delay():
    """Sleep for a random human-like interval."""
    delay = random.uniform(*DELAY_RANGE)
    print(f"   ⏳ Waiting {delay:.1f}s ...")
    time.sleep(delay)


def is_same_domain(url: str, base_domain: str) -> bool:
    """Return True if *url* belongs to the same domain as *base_domain*."""
    try:
        parsed = urlparse(url)
        return parsed.netloc == "" or parsed.netloc == base_domain
    except Exception:
        return False


def is_blacklisted(url: str, text: str = "") -> bool:
    """Return True if the URL or anchor text contains a blacklisted keyword."""
    combined = (url + " " + text).lower()
    return any(kw in combined for kw in BLACKLIST_KEYWORDS)


def is_resource_link(url: str) -> bool:
    """Return True if the URL points to a downloadable resource."""
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in RESOURCE_EXTENSIONS)


def normalize_url(url: str) -> str:
    """Strip fragments and trailing slashes for deduplication."""
    parsed = urlparse(url)
    clean = parsed._replace(fragment="")
    normalized = clean.geturl().rstrip("/")
    return normalized


def url_fingerprint(url: str) -> str:
    """Short hash for logging readability."""
    return hashlib.md5(url.encode()).hexdigest()[:8]


# ──────────────────────────────────────────────
# Data-extraction logic
# ──────────────────────────────────────────────

def extract_page_data(soup: BeautifulSoup, url: str) -> dict:
    """
    Parse the DOM and pull out structured ed-tech data.
    Returns a dict with chapter names, lectures, durations, resources, etc.
    """
    page_data = {
        "url": url,
        "title": "",
        "breadcrumb": [],
        "chapters": [],
        "lectures": [],
        "resources": [],
        "modules": [],
        "raw_headings": [],
        "scraped_at": datetime.now().isoformat(),
    }

    # ── Page title ──
    title_tag = soup.find("title")
    if title_tag:
        page_data["title"] = title_tag.get_text(strip=True)

    # ── Breadcrumbs (common in LMS platforms) ──
    for bc in soup.select(
        "nav[aria-label*='breadcrumb'] a, "
        ".breadcrumb a, .breadcrumbs a, "
        "[class*='breadcrumb'] a, "
        "ol.breadcrumb li"
    ):
        text = bc.get_text(strip=True)
        if text:
            page_data["breadcrumb"].append(text)

    # ── All headings (h1 – h4) ──
    for level in range(1, 5):
        for h in soup.find_all(f"h{level}"):
            text = h.get_text(strip=True)
            if text:
                page_data["raw_headings"].append({"level": level, "text": text})

    # ── Chapters & Modules ──
    chapter_selectors = [
        "[class*='chapter']", "[class*='Chapter']",
        "[class*='module']", "[class*='Module']",
        "[class*='unit']", "[class*='Unit']",
        "[class*='section-title']",
        "[class*='topic']", "[class*='Topic']",
        "[data-type='chapter']", "[data-type='module']",
    ]
    seen_chapters = set()
    for sel in chapter_selectors:
        for el in soup.select(sel):
            text = el.get_text(strip=True)
            if text and len(text) > 2 and text not in seen_chapters:
                seen_chapters.add(text)
                entry = {"name": text}
                link = el.find("a", href=True)
                if link:
                    entry["link"] = link["href"]
                page_data["chapters"].append(entry)

    # ── Lectures / Lessons / Videos ──
    lecture_selectors = [
        "[class*='lecture']", "[class*='Lecture']",
        "[class*='lesson']", "[class*='Lesson']",
        "[class*='video']", "[class*='Video']",
        "[class*='content-item']", "[class*='ContentItem']",
        "[class*='playlist']", "[class*='PlayList']",
        "[class*='session']",
        "[data-type='lecture']", "[data-type='video']",
    ]
    seen_lectures = set()
    for sel in lecture_selectors:
        for el in soup.select(sel):
            text = el.get_text(" ", strip=True)
            if text and len(text) > 2 and text not in seen_lectures:
                seen_lectures.add(text)
                entry = {"title": text[:300]}  # cap length for sanity

                # Try to find an associated duration string (e.g. "12:34", "1h 23m")
                dur = _extract_duration(el)
                if dur:
                    entry["duration"] = dur

                link = el.find("a", href=True)
                if link:
                    entry["link"] = link["href"]

                page_data["lectures"].append(entry)

    # ── Duration patterns anywhere on the page ──
    if not any(l.get("duration") for l in page_data["lectures"]):
        # Fallback: scan the entire page for duration-like strings
        duration_pattern = re.compile(
            r'\b(\d{1,3}:\d{2}(?::\d{2})?)\b'   # 12:34 or 1:23:45
            r'|'
            r'\b(\d+\s*(?:hr|hour|h)\s*\d*\s*(?:min|m)?)\b',  # 1h 23m
            re.IGNORECASE,
        )
        for match in duration_pattern.finditer(soup.get_text()):
            val = match.group(0).strip()
            # attach to the nearest un-durated lecture if possible
            for lec in page_data["lectures"]:
                if "duration" not in lec:
                    lec["duration"] = val
                    break

    # ── Resources: PDFs, downloads, RACE links ──
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True)

        if is_resource_link(href):
            page_data["resources"].append({
                "type": _guess_resource_type(href),
                "name": text or Path(urlparse(href).path).name,
                "url": href,
            })

        # RACE / Practice / Quiz links
        lower_text = (text + " " + href).lower()
        if any(kw in lower_text for kw in ["race", "practice", "quiz", "test", "assignment", "exercise"]):
            page_data["resources"].append({
                "type": "practice",
                "name": text,
                "url": href,
            })

    # ── Modules (fallback: look for card-style layouts) ──
    card_selectors = [
        "[class*='card']", "[class*='Card']",
        "[class*='tile']", "[class*='Tile']",
        "[class*='course-item']", "[class*='CourseItem']",
        "[class*='subject']", "[class*='Subject']",
    ]
    seen_modules = set()
    for sel in card_selectors:
        for el in soup.select(sel):
            text = el.get_text(" ", strip=True)[:200]
            if text and len(text) > 3 and text not in seen_modules:
                seen_modules.add(text)
                entry = {"name": text}
                link = el.find("a", href=True)
                if link:
                    entry["link"] = link["href"]
                page_data["modules"].append(entry)

    # Deduplicate resources
    unique_resources = []
    seen_res_urls = set()
    for r in page_data["resources"]:
        key = r.get("url", "") + r.get("name", "")
        if key not in seen_res_urls:
            seen_res_urls.add(key)
            unique_resources.append(r)
    page_data["resources"] = unique_resources

    return page_data


def _extract_duration(element: Tag) -> str | None:
    """Try to find a duration string inside or near `element`."""
    text = element.get_text(" ", strip=True)
    # HH:MM:SS or MM:SS
    m = re.search(r'\b(\d{1,3}:\d{2}(?::\d{2})?)\b', text)
    if m:
        return m.group(1)
    # "1h 23m" style
    m = re.search(r'\b(\d+\s*(?:hr|hour|h)\s*\d*\s*(?:min|m)?)\b', text, re.IGNORECASE)
    if m:
        return m.group(0).strip()
    return None


def _guess_resource_type(url: str) -> str:
    """Return a human-readable type from the file extension."""
    ext = Path(urlparse(url).path).suffix.lower()
    mapping = {
        ".pdf": "PDF",
        ".doc": "Document", ".docx": "Document",
        ".ppt": "Presentation", ".pptx": "Presentation",
        ".xls": "Spreadsheet", ".xlsx": "Spreadsheet",
        ".csv": "CSV",
        ".zip": "Archive", ".rar": "Archive",
        ".mp4": "Video", ".webm": "Video",
        ".mp3": "Audio", ".ogg": "Audio",
        ".png": "Image", ".jpg": "Image", ".jpeg": "Image",
        ".gif": "Image", ".svg": "Image",
    }
    return mapping.get(ext, "File")


# ──────────────────────────────────────────────
# Persistence
# ──────────────────────────────────────────────

class CurriculumStore:
    """Thread-safe-ish JSON store that flushes after every update."""

    def __init__(self, path: str = OUTPUT_FILE):
        self.path = Path(path)
        self.data: dict = {
            "platform": "",
            "crawl_started": datetime.now().isoformat(),
            "total_pages_crawled": 0,
            "pages": {},          # url -> page_data
            "hierarchy": {},      # auto-built tree
        }
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
                print(f"   📂 Resumed from existing {self.path} "
                      f"({self.data.get('total_pages_crawled', 0)} pages)")
            except json.JSONDecodeError:
                print(f"   ⚠️  Corrupt {self.path}, starting fresh.")

    def add_page(self, page_data: dict):
        url = page_data["url"]
        self.data["pages"][url] = page_data
        self.data["total_pages_crawled"] = len(self.data["pages"])
        self.data["last_updated"] = datetime.now().isoformat()
        self._rebuild_hierarchy()
        self._flush()

    def _rebuild_hierarchy(self):
        """Build a breadcrumb-based tree from all crawled pages."""
        tree: dict = {}
        for url, page in self.data["pages"].items():
            crumbs = page.get("breadcrumb", [])
            if not crumbs:
                # Use the first heading as a fallback key
                key = page.get("title", url)
                tree.setdefault(key, {"url": url, "children": {}})
                continue
            node = tree
            for crumb in crumbs:
                node = node.setdefault(crumb, {"children": {}}).setdefault("children", {})
            # Leaf
            leaf_key = page.get("title", url)
            node[leaf_key] = {"url": url}
        self.data["hierarchy"] = tree

    def _flush(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)  # atomic on most OSes

    @property
    def visited_urls(self) -> set[str]:
        return set(self.data.get("pages", {}).keys())


# ──────────────────────────────────────────────
# Link discovery
# ──────────────────────────────────────────────

def discover_links(page, base_domain: str, current_url: str) -> list[str]:
    """
    Use Playwright's page to discover all navigable links.
    Returns a list of absolute, normalized, in-domain URLs.
    """
    links: set[str] = set()

    try:
        html = page.content()
    except Exception:
        return []

    soup = BeautifulSoup(html, "html.parser")

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(strip=True)

        # Skip anchors, javascript, mailto, tel
        if href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue

        abs_url = urljoin(current_url, href)
        abs_url = normalize_url(abs_url)

        if not is_same_domain(abs_url, base_domain):
            continue
        if is_blacklisted(abs_url, text):
            continue
        if is_resource_link(abs_url):
            continue  # we capture these in extraction, not crawling

        links.add(abs_url)

    # Also check buttons with onclick navigation or data-href
    for btn in soup.find_all(["button", "div", "span"], attrs={"data-href": True}):
        href = btn.get("data-href", "").strip()
        if href:
            abs_url = normalize_url(urljoin(current_url, href))
            if is_same_domain(abs_url, base_domain) and not is_blacklisted(abs_url):
                links.add(abs_url)

    return sorted(links)


# ──────────────────────────────────────────────
# Scroll helper (to load lazy content)
# ──────────────────────────────────────────────

def scroll_page(page):
    """Scroll to the bottom of the page to trigger lazy-loaded content."""
    try:
        prev_height = page.evaluate("document.body.scrollHeight")
        for _ in range(5):  # max 5 scroll iterations
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(SCROLL_PAUSE)
            new_height = page.evaluate("document.body.scrollHeight")
            if new_height == prev_height:
                break
            prev_height = new_height
        # Scroll back to top
        page.evaluate("window.scrollTo(0, 0)")
    except Exception:
        pass


# ──────────────────────────────────────────────
# Main crawler
# ──────────────────────────────────────────────

def crawl():
    print("=" * 60)
    print("  🕷️  Allen Universal Crawler")
    print("=" * 60)

    store = CurriculumStore()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=False,
            args=["--start-maximized"],
        )
        context = browser.new_context(
            viewport=None,             # use full window size
            no_viewport=True,
            java_script_enabled=True,
            ignore_https_errors=True,
        )
        page = context.new_page()
        page.set_default_timeout(PAGE_LOAD_TIMEOUT)

        # ── Navigate to the platform and let the user log in ──
        print("\n📌 A browser window has opened.")
        print("   1. Navigate to the Allen platform login page.")
        print("   2. Log in with your credentials.")
        print("   3. Make sure you land on the MAIN DASHBOARD.")
        print("   4. Come back here and press ENTER.\n")

        page.goto("https://www.allen.in/", wait_until="domcontentloaded")

        input("✅ Press ENTER once you are logged in and on the dashboard ▶ ")

        # ── Capture starting point ──
        start_url = normalize_url(page.url)
        base_domain = urlparse(start_url).netloc
        store.data["platform"] = base_domain

        print(f"\n🏠 Starting URL  : {start_url}")
        print(f"🌐 Base domain   : {base_domain}")
        print(f"📄 Output file   : {OUTPUT_FILE}\n")
        print("-" * 60)

        # ── BFS setup ──
        queue: deque[str] = deque()
        visited: set[str] = set(store.visited_urls)  # resume support

        # Seed with the current page
        if start_url not in visited:
            queue.append(start_url)

        # Also discover initial links
        initial_links = discover_links(page, base_domain, start_url)
        for link in initial_links:
            if link not in visited:
                queue.append(link)

        page_count = len(visited)

        # ── BFS loop ──
        while queue:
            url = queue.popleft()

            if url in visited:
                continue
            visited.add(url)

            page_count += 1
            fp = url_fingerprint(url)
            print(f"\n[{page_count:>4}] 🔗 {fp}  {url}")

            # Navigate with retries
            success = False
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT)
                    page.wait_for_load_state("networkidle", timeout=15_000)
                    success = True
                    break
                except PlaywrightTimeout:
                    print(f"   ⚠️  Timeout on attempt {attempt}/{MAX_RETRIES}")
                    if attempt < MAX_RETRIES:
                        time.sleep(2)
                except Exception as e:
                    print(f"   ❌ Navigation error: {e}")
                    break

            if not success:
                print("   ⏭️  Skipping this page.")
                continue

            # Wait for any dynamic rendering
            time.sleep(1)

            # Scroll to trigger lazy loading
            scroll_page(page)

            # ── Extract data ──
            try:
                html = page.content()
                soup = BeautifulSoup(html, "html.parser")
                page_data = extract_page_data(soup, url)
                store.add_page(page_data)

                # Summary
                n_chap = len(page_data["chapters"])
                n_lec = len(page_data["lectures"])
                n_res = len(page_data["resources"])
                n_mod = len(page_data["modules"])
                print(f"   📊 Chapters: {n_chap}  |  Lectures: {n_lec}  |  "
                      f"Resources: {n_res}  |  Modules: {n_mod}")
            except Exception as e:
                print(f"   ❌ Extraction error: {e}")

            # ── Discover new links ──
            try:
                actual_url = normalize_url(page.url)  # handle redirects
                if actual_url != url:
                    visited.add(actual_url)

                new_links = discover_links(page, base_domain, actual_url)
                added = 0
                for link in new_links:
                    if link not in visited and link not in queue:
                        queue.append(link)
                        added += 1
                if added:
                    print(f"   🔍 Discovered {added} new links  (queue: {len(queue)})")
            except Exception as e:
                print(f"   ⚠️  Link discovery error: {e}")

            # Human delay before next page
            if queue:
                human_delay()

        # ── Done ──
        print("\n" + "=" * 60)
        print(f"  ✅ Crawl complete!  Total pages: {page_count}")
        print(f"  📄 Data saved to: {Path(OUTPUT_FILE).resolve()}")
        print("=" * 60)

        input("\nPress ENTER to close the browser ▶ ")
        browser.close()


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────

if __name__ == "__main__":
    crawl()
