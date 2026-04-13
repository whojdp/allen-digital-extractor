"""
Allen Full-Platform Data Ripper
================================
Autonomously extracts the ENTIRE Allen digital platform content
across all subjects (Physics, Chemistry, Maths) for Class 11 & 12.

Outputs:
    allen_complete_knowledge_base.json — comprehensive hierarchical JSON
    allen_pdfs/                        — all downloaded PDFs organized by class/subject/topic

Usage:
    python allen_full_rip.py

No browser or Chromium login required — uses the intercepted API directly.
"""

import json
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, unquote

# Fix Windows console encoding for emoji/unicode output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import requests


# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────

API_URL = "https://api.allen-live.in/api/v1/pages/getPage"
OUTPUT_FILE = "allen_complete_knowledge_base.json"
PROGRESS_FILE = "rip_progress.json"
PDF_DIR = Path("allen_pdfs")
DELAY_RANGE = (2, 4)  # seconds between API calls

# Read token from secure file
try:
    with open("allen_token.txt", "r") as f:
        auth_token = f.read().strip()
except FileNotFoundError:
    print("CRITICAL ERROR: 'allen_token.txt' not found. Please create it and paste your Bearer token inside.")
    sys.exit(1)

HEADERS = {
    "accept": "application/json",
    "accept-language": "en-US,en;q=0.6",
    "authorization": f"Bearer {auth_token}",
    "content-type": "application/json",
    "origin": "https://allen.in",
    "referer": "https://allen.in/",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/147.0.0.0 Safari/537.36"
    ),
    "x-client-type": "web",
    "x-device-id": "1d37c8b0-df6b-4843-9f2a-a708c6cb160f",
    "x-locale": "en",
    "x-selected-batch-list": (
        "bt_dGHnem4IjNtEOVQjfmW26,"
        "bt_Ez5lOBgnoJadUVdL7IaXM,"
        "bt_Lk86uKMqqav23yczHJHJh"
    ),
    "x-selected-course-id": "cr_cpTLbkqWLu96FPkmfoREz",
    "x-visitor-id": "d5f1d6c0-ebf5-40e7-8448-f103cba77f6a",
}

# Common params
BATCH_IDS = "bt_dGHnem4IjNtEOVQjfmW26,bt_Ez5lOBgnoJadUVdL7IaXM,bt_Lk86uKMqqav23yczHJHJh"
COURSE_ID = "cr_cpTLbkqWLu96FPkmfoREz"
STREAM = "STREAM_JEE_MAIN_ADVANCED"
TAXONOMY_ID = "1739171216OJ"

# Known seed: one Class 11 subject to bootstrap discovery
SEED_SUBJECTS = {
    "Class 11": {
        "Chemistry": {
            "subject_id": "2",
            "class_12_subject_id": "746",
            "class_12_taxonomy_id": TAXONOMY_ID,
            "revision_class": "CLASS_11",
        }
    },
    "Class 12": {
        "Chemistry": {
            "subject_id": "746",
        }
    }
}


# ──────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────

def human_delay():
    """Sleep for a random interval to avoid throttling."""
    delay = random.uniform(*DELAY_RANGE)
    time.sleep(delay)


def api_call(page_url: str, retries: int = 3) -> dict:
    """Make a getPage API call with retries."""
    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(
                API_URL,
                headers=HEADERS,
                json={"page_url": page_url},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") == 200:
                return data
            else:
                print(f"      ⚠️  API returned status {data.get('status')}: {data.get('reason')}")
                if attempt < retries:
                    time.sleep(3)
        except requests.exceptions.RequestException as e:
            print(f"      ❌ Request error (attempt {attempt}/{retries}): {e}")
            if attempt < retries:
                time.sleep(5)
    return {}


def get_widgets_by_type(data: dict) -> dict:
    """Index page_content.widgets by their type."""
    widgets = data.get("data", {}).get("page_content", {}).get("widgets", [])
    index = {}
    for w in widgets:
        wtype = w.get("type", "UNKNOWN")
        index.setdefault(wtype, []).append(w)
    return index


def safe_filename(name: str) -> str:
    """Make a string safe for use as a filename."""
    # Remove or replace unsafe characters
    for ch in r'<>:"/\|?*':
        name = name.replace(ch, "_")
    return name.strip().strip(".")[:150]  # cap length


def build_query_string(params: dict) -> str:
    """Build a URL query string from a dict, encoding values."""
    parts = []
    for k, v in params.items():
        parts.append(f"{k}={quote(str(v), safe='')}")
    return "&".join(parts)


# ──────────────────────────────────────────────
# Progress tracking (resume support)
# ──────────────────────────────────────────────

class Progress:
    """Track which topics have been fully extracted, for resume support."""

    def __init__(self):
        self.path = Path(PROGRESS_FILE)
        self.completed: set = set()  # "Class 11|Chemistry|Mole Concept"
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.completed = set(data.get("completed", []))
                print(f"   📂 Resumed: {len(self.completed)} topics already done")
            except Exception:
                pass

    def mark_done(self, key: str):
        self.completed.add(key)
        self._save()

    def is_done(self, key: str) -> bool:
        return key in self.completed

    def _save(self):
        data = {"completed": sorted(self.completed), "last_updated": datetime.now().isoformat()}
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ──────────────────────────────────────────────
# Phase 1: Discovery
# ──────────────────────────────────────────────

def build_subject_page_url(subject_id: str, is_class_11: bool = True,
                           class_12_subject_id: str = "", class_12_taxonomy_id: str = "") -> str:
    """Build the page_url for a subject-details API call."""
    params = {
        "batch_id": BATCH_IDS,
        "selected_batch_list": BATCH_IDS,
        "selected_course_id": COURSE_ID,
        "stream": STREAM,
        "subject_id": subject_id,
        "taxonomy_id": TAXONOMY_ID,
    }
    if is_class_11 and class_12_subject_id:
        params["class_12_subject_id"] = class_12_subject_id
        params["class_12_taxonomy_id"] = class_12_taxonomy_id or TAXONOMY_ID
        params["revision_class"] = "CLASS_11"

    return "/subject-details?" + build_query_string(params)


def discover_subjects_and_topics() -> dict:
    """
    Discover all subjects and topics across Class 11 and Class 12.
    Returns:
        {
            "Class 11": {
                "Chemistry": {"subject_id": "2", "topics": [{"name": ..., "topic_id": ..., "query": ...}, ...]},
                "Physics": ...,
                "Maths": ...,
            },
            "Class 12": { ... }
        }
    """
    discovery = {}

    print("\n" + "=" * 60)
    print("  PHASE 1: DISCOVERY")
    print("=" * 60)

    # ── Step 1: Discover Class 11 subjects from Chemistry 11 ──
    print("\n📡 Discovering Class 11 subjects...")
    seed = SEED_SUBJECTS["Class 11"]["Chemistry"]
    page_url = build_subject_page_url(
        seed["subject_id"],
        is_class_11=True,
        class_12_subject_id=seed["class_12_subject_id"],
        class_12_taxonomy_id=seed["class_12_taxonomy_id"],
    )
    data = api_call(page_url)
    if not data:
        print("   ❌ Failed to fetch Class 11 seed subject. Aborting.")
        sys.exit(1)

    # Extract subject tabs (all subjects for this class)
    widgets = get_widgets_by_type(data)
    class_11_subjects = _extract_subject_tabs(widgets, is_class_11=True)
    print(f"   ✅ Found Class 11 subjects: {', '.join(class_11_subjects.keys())}")

    # Also extract the Chemistry 11 topics from this same response
    chem_11_topics = _extract_chapters(widgets)
    class_11_subjects["Chemistry"]["topics"] = chem_11_topics
    print(f"   📚 Chemistry Class 11: {len(chem_11_topics)} topics")

    human_delay()

    # Fetch topics for other Class 11 subjects
    for subj_name, subj_data in class_11_subjects.items():
        if subj_name == "Chemistry":
            continue  # already have it
        print(f"\n📡 Fetching {subj_name} Class 11 topics...")
        page_url = build_subject_page_url(
            subj_data["subject_id"],
            is_class_11=True,
            class_12_subject_id=seed["class_12_subject_id"],
            class_12_taxonomy_id=seed["class_12_taxonomy_id"],
        )
        resp_data = api_call(page_url)
        if resp_data:
            w = get_widgets_by_type(resp_data)
            topics = _extract_chapters(w)
            subj_data["topics"] = topics
            print(f"   📚 {subj_name} Class 11: {len(topics)} topics")
        else:
            subj_data["topics"] = []
            print(f"   ⚠️  Failed to fetch {subj_name} Class 11")
        human_delay()

    discovery["Class 11"] = class_11_subjects

    # ── Step 2: Discover Class 12 subjects ──
    print("\n📡 Discovering Class 12 subjects...")
    seed_12 = SEED_SUBJECTS["Class 12"]["Chemistry"]
    page_url_12 = build_subject_page_url(
        seed_12["subject_id"],
        is_class_11=False,
    )
    data_12 = api_call(page_url_12)
    if not data_12:
        print("   ❌ Failed to fetch Class 12 seed subject.")
        discovery["Class 12"] = {}
        return discovery

    widgets_12 = get_widgets_by_type(data_12)
    class_12_subjects = _extract_subject_tabs(widgets_12, is_class_11=False)
    print(f"   ✅ Found Class 12 subjects: {', '.join(class_12_subjects.keys())}")

    # Extract Chemistry 12 topics from this response
    chem_12_topics = _extract_chapters(widgets_12)
    class_12_subjects["Chemistry"]["topics"] = chem_12_topics
    print(f"   📚 Chemistry Class 12: {len(chem_12_topics)} topics")

    human_delay()

    # Fetch topics for other Class 12 subjects
    for subj_name, subj_data in class_12_subjects.items():
        if subj_name == "Chemistry":
            continue
        print(f"\n📡 Fetching {subj_name} Class 12 topics...")
        page_url = build_subject_page_url(
            subj_data["subject_id"],
            is_class_11=False,
        )
        resp_data = api_call(page_url)
        if resp_data:
            w = get_widgets_by_type(resp_data)
            topics = _extract_chapters(w)
            subj_data["topics"] = topics
            print(f"   📚 {subj_name} Class 12: {len(topics)} topics")
        else:
            subj_data["topics"] = []
            print(f"   ⚠️  Failed to fetch {subj_name} Class 12")
        human_delay()

    discovery["Class 12"] = class_12_subjects

    # Summary
    total_topics = sum(
        len(subj.get("topics", []))
        for cls in discovery.values()
        for subj in cls.values()
    )
    print(f"\n{'─'*60}")
    print(f"   📊 Total topics discovered: {total_topics}")
    print(f"{'─'*60}")

    return discovery


def _extract_subject_tabs(widgets: dict, is_class_11: bool) -> dict:
    """Extract subject tabs from LIBRARY_SUBJECT_SIDETAB_WEB widget."""
    subjects = {}
    for w in widgets.get("POLYMORPHIC_WIDGET", []):
        tkey = w.get("data", {}).get("translation_key", "")
        if tkey == "LIBRARY_SUBJECT_SIDETAB_WEB":
            inner = w.get("data", {}).get("data", {})
            tabs = inner.get("subject_tabs", [])
            for tab in tabs:
                name = tab.get("name", "Unknown")
                action_data = (tab.get("action") or {}).get("data", {})
                query = action_data.get("query", {})
                subject_id = query.get("subject_id", "")
                subjects[name] = {
                    "subject_id": subject_id,
                    "query_params": query,
                    "topics": [],
                }
    return subjects


def _extract_chapters(widgets: dict) -> list:
    """Extract chapter/topic list from LIBRARY_SUBJECT_SIDETAB_WEB or LIBRARY_SUBJECT_INFO_WEB."""
    topics = []
    seen = set()

    for w in widgets.get("POLYMORPHIC_WIDGET", []):
        tkey = w.get("data", {}).get("translation_key", "")

        # Chapters can be in SIDETAB or INFO widgets
        inner = w.get("data", {}).get("data", {})
        chapters_list = inner.get("chapters_list", {})
        chapters = chapters_list.get("chapters", [])

        for ch in chapters:
            name = ch.get("name", "Unknown")
            if name in seen:
                continue
            seen.add(name)

            action_data = (ch.get("action") or {}).get("data", {})
            query = action_data.get("query", {})
            tracking = (ch.get("action") or {}).get("tracking_params", {}).get("current", {})

            topics.append({
                "name": name,
                "topic_id": query.get("topic_id", tracking.get("topic_id", "")),
                "subject_id": query.get("subject_id", ""),
                "query_params": query,
            })

    return topics


# ──────────────────────────────────────────────
# Phase 2: Topic Extraction
# ──────────────────────────────────────────────

def build_topic_page_url(query_params: dict) -> str:
    """Build the page_url for a topic-details API call."""
    return "/topic-details?" + build_query_string(query_params)


def extract_topic_content(data: dict) -> dict:
    """Extract all content from a topic-details API response."""
    widgets = get_widgets_by_type(data)
    content = {}

    # ── Header ──
    for w in widgets.get("APP_GENERIC_HEADER_V2", []):
        wd = w.get("data", {})
        subtitles = wd.get("subtitles", [])
        content["header"] = {
            "title": wd.get("title", ""),
            "subtitles": [s.get("text", "") for s in subtitles],
        }

    # ── Process POLYMORPHIC_WIDGETs ──
    for w in widgets.get("POLYMORPHIC_WIDGET", []):
        tkey = w.get("data", {}).get("translation_key", "")

        if tkey == "LIBRARY_VIDEOS_WEB":
            content["concept_videos"] = _extract_videos(w)
        elif tkey == "LIBRARY_ADDITIONAL_MATERIAL_WEB":
            content["additional_materials"] = _extract_materials(w)
        elif tkey == "LIBRARY_STUDY_MODULES_WEB":
            content["study_modules"] = _extract_study_modules(w)
        elif tkey == "LIBRARY_FLASHCARDS_CONTAINER_B1_WEB":
            content["flashcards"] = _extract_flashcards(w)
        elif tkey == "LIBRARY_REVISION_NOTES_WEB":
            content["revision_notes"] = _extract_revision_notes(w)

    # ── Custom Practice (SELECTION_CARD) ──
    for w in widgets.get("SELECTION_CARD", []):
        content["custom_practice"] = _extract_custom_practice(w)

    return content


def _extract_videos(widget: dict) -> dict:
    """Extract concept video lectures."""
    inner = widget.get("data", {}).get("data", {})
    contents = inner.get("contents_list", [])

    lectures = []
    for item in contents:
        lecture = {
            "sequence": item.get("sequence", 0),
            "title": item.get("content_title", "Untitled"),
            "description": item.get("description", ""),
            "duration": item.get("duration", "N/A"),
            "sub_topics": item.get("sub_topics", []),
            "is_locked": item.get("is_locked", False),
            "content_type": item.get("type", ""),
        }

        # Extract content_id (useful for reference)
        action_data = (item.get("content_action") or {}).get("data", {})
        if action_data:
            lecture["content_id"] = action_data.get("content_id", "")

        lectures.append(lecture)

    lectures.sort(key=lambda x: x.get("sequence", 0))

    # Calculate total duration
    total_minutes = 0
    for lec in lectures:
        dur = lec.get("duration", "")
        if ":" in dur:
            parts = dur.split(":")
            if len(parts) == 2:
                total_minutes += int(parts[0]) + (int(parts[1]) / 60)
            elif len(parts) == 3:
                total_minutes += int(parts[0]) * 60 + int(parts[1]) + (int(parts[2]) / 60)

    return {
        "section_title": inner.get("title", "Concept Videos"),
        "count": len(lectures),
        "total_duration_minutes": round(total_minutes, 1),
        "lectures": lectures,
    }


def _extract_materials(widget: dict) -> dict:
    """Extract additional materials (RACE PDFs, Exercise PDFs)."""
    inner = widget.get("data", {}).get("data", {})
    cards = inner.get("cards", [])

    groups = []
    for card in cards:
        group = {
            "title": card.get("card_title", "Untitled"),
            "subtitle": card.get("subtitle", ""),
            "materials": [],
        }

        # Navigate: card_action -> data -> content -> data -> contents_list
        card_action = card.get("card_action", {})
        popup_data = card_action.get("data", {})
        content_widget = popup_data.get("content", {})
        content_data = content_widget.get("data", {})
        contents_list = content_data.get("contents_list", [])

        for item in contents_list:
            material = {
                "title": item.get("content_title", "Untitled"),
                "description": item.get("description", ""),
                "content_type": item.get("type", ""),
                "is_locked": item.get("is_locked", False),
            }

            action_data = (item.get("content_action") or {}).get("data", {})
            if action_data:
                material["content_id"] = action_data.get("content_id", "")
                material["pdf_url"] = action_data.get("uri", "")

            group["materials"].append(material)

        groups.append(group)

    return {
        "section_title": inner.get("title", "Additional Materials"),
        "groups": groups,
    }


def _extract_study_modules(widget: dict) -> dict:
    """Extract study modules (PDF downloads)."""
    inner = widget.get("data", {}).get("data", {})
    contents = inner.get("contents_list", [])

    modules = []
    for item in contents:
        module = {
            "title": item.get("content_title", "Untitled"),
            "description": item.get("description", ""),
            "content_type": item.get("type", ""),
            "is_locked": item.get("is_locked", False),
        }

        action_data = (item.get("content_action") or {}).get("data", {})
        if action_data:
            module["content_id"] = action_data.get("content_id", "")
            module["pdf_url"] = action_data.get("uri", "")

        modules.append(module)

    return {
        "section_title": inner.get("title", "Study Modules"),
        "modules": modules,
    }


def _extract_flashcards(widget: dict) -> dict:
    """Extract flashcards metadata."""
    inner = widget.get("data", {}).get("data", {})
    card = inner.get("card", {})
    return {
        "section_title": inner.get("title", "Flashcards"),
        "subtitle": inner.get("sub_title", ""),
        "card_title": card.get("title", ""),
        "card_subtitle": card.get("subtitle", ""),
        "uri": ((card.get("cta") or {}).get("action") or {}).get("data", {}).get("uri", ""),
    }


def _extract_revision_notes(widget: dict) -> dict:
    """Extract revision notes metadata."""
    inner = widget.get("data", {}).get("data", {})
    return {
        "section_title": inner.get("title", "Revision Notes"),
        "subtitle": inner.get("sub_title", ""),
        "uri": ((inner.get("cta") or {}).get("action") or {}).get("data", {}).get("uri", ""),
    }


def _extract_custom_practice(widget: dict) -> dict:
    """Extract custom practice quiz config."""
    wd = widget.get("data", {})
    options = wd.get("options", [])
    parsed = []
    for opt in options:
        parsed.append({
            "key": opt.get("key", ""),
            "label": opt.get("label", ""),
            "default": (opt.get("default") or {}).get("display_value", ""),
            "choices": [item.get("display_value", "") for item in opt.get("list", [])],
        })
    return {
        "section_title": wd.get("title", "Custom Practice"),
        "subtitle": wd.get("subtitle", ""),
        "options": parsed,
    }


# ──────────────────────────────────────────────
# Phase 3: PDF Download
# ──────────────────────────────────────────────

def download_pdfs(content: dict, class_name: str, subject_name: str, topic_name: str) -> int:
    """Download all PDFs from a topic's content. Returns count of PDFs downloaded."""
    pdf_folder = PDF_DIR / safe_filename(class_name) / safe_filename(subject_name) / safe_filename(topic_name)
    downloaded = 0

    # Collect all PDF URLs from materials and study modules
    pdf_items = []

    # Additional materials
    materials = content.get("additional_materials", {})
    for group in materials.get("groups", []):
        for mat in group.get("materials", []):
            url = mat.get("pdf_url", "")
            if url and not mat.get("is_locked", False):
                title = f"{group['title']} - {mat['title']}"
                pdf_items.append((title, url))

    # Study modules
    modules = content.get("study_modules", {})
    for mod in modules.get("modules", []):
        url = mod.get("pdf_url", "")
        if url and not mod.get("is_locked", False):
            pdf_items.append((mod["title"], url))

    if not pdf_items:
        return 0

    # Create directory
    pdf_folder.mkdir(parents=True, exist_ok=True)

    for title, url in pdf_items:
        filename = safe_filename(title) + ".pdf"
        filepath = pdf_folder / filename

        # Skip if already downloaded
        if filepath.exists() and filepath.stat().st_size > 0:
            _update_pdf_path_in_content(content, url, str(filepath))
            downloaded += 1
            continue

        try:
            print(f"      📥 Downloading: {filename[:60]}...")
            resp = requests.get(url, timeout=60, stream=True)
            resp.raise_for_status()

            with open(filepath, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            size_kb = filepath.stat().st_size / 1024
            print(f"         ✅ {size_kb:.0f} KB")
            _update_pdf_path_in_content(content, url, str(filepath))
            downloaded += 1

        except Exception as e:
            print(f"         ❌ Failed: {e}")

    return downloaded


def _update_pdf_path_in_content(content: dict, url: str, local_path: str):
    """Add local_pdf_path to the content item matching the URL."""
    # Check additional materials
    materials = content.get("additional_materials", {})
    for group in materials.get("groups", []):
        for mat in group.get("materials", []):
            if mat.get("pdf_url") == url:
                mat["local_pdf_path"] = local_path
                return

    # Check study modules
    modules = content.get("study_modules", {})
    for mod in modules.get("modules", []):
        if mod.get("pdf_url") == url:
            mod["local_pdf_path"] = local_path
            return


# ──────────────────────────────────────────────
# Phase 4: Assembly & Main
# ──────────────────────────────────────────────

def print_summary(knowledge_base: dict):
    """Print a comprehensive summary of the extracted data."""
    print("\n" + "=" * 70)
    print("  📊  EXTRACTION SUMMARY")
    print("=" * 70)

    grand_total_videos = 0
    grand_total_pdfs = 0
    grand_total_topics = 0
    grand_total_minutes = 0

    for class_name in ["Class 11", "Class 12"]:
        class_data = knowledge_base.get(class_name, {})
        if not class_data:
            continue

        print(f"\n  ┌─ {class_name}")

        for subj_name, subj_data in class_data.items():
            topics = subj_data.get("topics", {})
            total_vids = 0
            total_pdfs = 0
            total_mins = 0

            for topic_name, topic_data in topics.items():
                vids = topic_data.get("concept_videos", {}).get("count", 0)
                mins = topic_data.get("concept_videos", {}).get("total_duration_minutes", 0)
                pdf_count = sum(
                    len(g.get("materials", []))
                    for g in topic_data.get("additional_materials", {}).get("groups", [])
                ) + len(topic_data.get("study_modules", {}).get("modules", []))
                total_vids += vids
                total_pdfs += pdf_count
                total_mins += mins

            print(f"  │  ├─ {subj_name}: {len(topics)} topics, "
                  f"{total_vids} videos ({total_mins:.0f} min), {total_pdfs} PDFs")

            grand_total_videos += total_vids
            grand_total_pdfs += total_pdfs
            grand_total_topics += len(topics)
            grand_total_minutes += total_mins

    print(f"\n  {'─'*60}")
    print(f"  TOTALS: {grand_total_topics} topics | {grand_total_videos} videos | "
          f"{grand_total_minutes:.0f} minutes ({grand_total_minutes/60:.1f} hours) | "
          f"{grand_total_pdfs} PDFs")
    print("=" * 70)


def main():
    print("=" * 70)
    print("  🚀  Allen Full-Platform Data Ripper")
    print("  📅  " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 70)

    progress = Progress()

    # ── Phase 1: Discovery ──
    discovery = discover_subjects_and_topics()

    # ── Phase 2 + 3: Extract each topic and download PDFs ──
    print("\n" + "=" * 60)
    print("  PHASE 2: EXTRACTION + PDF DOWNLOAD")
    print("=" * 60)

    knowledge_base = {
        "metadata": {
            "source": "Allen Digital (allen.in)",
            "api_endpoint": API_URL,
            "stream": STREAM,
            "course_id": COURSE_ID,
            "batch_ids": BATCH_IDS.split(","),
            "extracted_at": datetime.now().isoformat(),
        }
    }

    topic_counter = 0
    total_topics = sum(
        len(subj.get("topics", []))
        for cls in discovery.values()
        for subj in cls.values()
    )

    for class_name in ["Class 11", "Class 12"]:
        class_data = discovery.get(class_name, {})
        kb_class = {}

        for subj_name, subj_data in class_data.items():
            print(f"\n{'─'*60}")
            print(f"  📘 {class_name} > {subj_name} ({len(subj_data.get('topics', []))} topics)")
            print(f"{'─'*60}")

            kb_subject = {
                "subject_id": subj_data.get("subject_id", ""),
                "total_topics": len(subj_data.get("topics", [])),
                "topics": {},
            }

            for topic in subj_data.get("topics", []):
                topic_name = topic["name"]
                topic_key = f"{class_name}|{subj_name}|{topic_name}"
                topic_counter += 1

                # Skip if already done (resume support)
                if progress.is_done(topic_key):
                    print(f"\n  [{topic_counter}/{total_topics}] ⏭️  {topic_name} (already done)")
                    # Load from existing output if available
                    existing = _load_existing_topic(class_name, subj_name, topic_name)
                    if existing:
                        kb_subject["topics"][topic_name] = existing
                    continue

                print(f"\n  [{topic_counter}/{total_topics}] 🔍 {topic_name}")

                # Build the topic-details URL from query params
                query = topic.get("query_params", {})
                if not query:
                    print(f"      ⚠️  No query params, skipping")
                    continue

                page_url = build_topic_page_url(query)
                data = api_call(page_url)

                if not data:
                    print(f"      ❌ Failed to fetch topic data")
                    human_delay()
                    continue

                # Extract content
                content = extract_topic_content(data)
                content["topic_id"] = topic.get("topic_id", "")

                # Print quick stats
                vids = content.get("concept_videos", {}).get("count", 0)
                dur = content.get("concept_videos", {}).get("total_duration_minutes", 0)
                n_material_groups = len(content.get("additional_materials", {}).get("groups", []))
                n_modules = len(content.get("study_modules", {}).get("modules", []))
                has_fc = "flashcards" in content
                has_rn = "revision_notes" in content
                print(f"      📊 Videos: {vids} ({dur:.0f} min) | "
                      f"Material groups: {n_material_groups} | Modules: {n_modules} | "
                      f"FC: {'✓' if has_fc else '✗'} | RN: {'✓' if has_rn else '✗'}")

                # Download PDFs
                pdf_count = download_pdfs(content, class_name, subj_name, topic_name)
                if pdf_count:
                    print(f"      📄 Downloaded {pdf_count} PDFs")

                kb_subject["topics"][topic_name] = content
                progress.mark_done(topic_key)

                # Save intermediate output after every topic
                knowledge_base[class_name] = knowledge_base.get(class_name, {})
                knowledge_base[class_name][subj_name] = kb_subject
                _save_knowledge_base(knowledge_base)

                human_delay()

            kb_class[subj_name] = kb_subject

        knowledge_base[class_name] = kb_class

    # ── Phase 4: Final save ──
    knowledge_base["metadata"]["completed_at"] = datetime.now().isoformat()
    _save_knowledge_base(knowledge_base)

    print_summary(knowledge_base)

    print(f"\n  ✅ Knowledge base saved to: {Path(OUTPUT_FILE).resolve()}")
    print(f"  📂 PDFs saved to: {PDF_DIR.resolve()}")
    print(f"\n{'='*70}")
    print("  Done! Feed allen_complete_knowledge_base.json to your LLM. 🎓")
    print(f"{'='*70}")


def _save_knowledge_base(kb: dict):
    """Atomically save the knowledge base JSON."""
    tmp = Path(OUTPUT_FILE + ".tmp")
    tmp.write_text(json.dumps(kb, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(OUTPUT_FILE)


def _load_existing_topic(class_name: str, subj_name: str, topic_name: str) -> dict:
    """Try to load a previously extracted topic from the existing output file."""
    try:
        if Path(OUTPUT_FILE).exists():
            data = json.loads(Path(OUTPUT_FILE).read_text(encoding="utf-8"))
            return data.get(class_name, {}).get(subj_name, {}).get("topics", {}).get(topic_name, {})
    except Exception:
        pass
    return {}


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────

if __name__ == "__main__":
    main()
