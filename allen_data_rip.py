"""
Allen Data Ripper v3.0 — Universal Two-Phase Extractor
=======================================================
Hits the Allen getPage API in two passes:

  Phase 1 (/subject-details)
      For each subject_id in SUBJECT_IDS, fetch the full chapter list
      and extract every topic_id.

  Phase 2 (/topic-details)
      For every discovered topic_id, pull concept-video metadata,
      lecture durations, PDF links, flashcards, revision notes, and
      custom-practice configs.

All data is appended into allen_complete_knowledge_base.json without
destroying existing entries that already live there.

Usage:
    python allen_data_rip.py
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, unquote

# Fix Windows console encoding for emoji / unicode
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
REQUEST_DELAY = 1.5  # seconds between requests

# Read token from secure file (never hardcoded)
try:
    with open("allen_token.txt", "r") as f:
        auth_token = f.read().strip()
except FileNotFoundError:
    print("FATAL: 'allen_token.txt' not found.")
    print("       Create the file and paste your Bearer token inside.")
    sys.exit(1)

# ── Shared request plumbing ──
BATCH_IDS = "bt_dGHnem4IjNtEOVQjfmW26,bt_Ez5lOBgnoJadUVdL7IaXM,bt_Lk86uKMqqav23yczHJHJh"
COURSE_ID = "cr_cpTLbkqWLu96FPkmfoREz"
STREAM = "STREAM_JEE_MAIN_ADVANCED"
TAXONOMY_ID = "1739171216OJ"

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
    "x-selected-batch-list": BATCH_IDS,
    "x-selected-course-id": COURSE_ID,
    "x-visitor-id": "d5f1d6c0-ebf5-40e7-8448-f103cba77f6a",
}

# ── Subject definitions ──
# Each entry: (label, subject_id)
# Confirmed IDs from intercepted /subject-details cURLs.
SUBJECT_IDS = [
    ("Physics", "1160"),
    ("Maths", "1264"),
]


# ──────────────────────────────────────────────
# Low-level helpers
# ──────────────────────────────────────────────

def _build_qs(params: dict) -> str:
    """Encode a dict into a URL query string."""
    return "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params.items())


def api_call(page_url: str, retries: int = 3) -> dict:
    """POST to getPage with automatic retries."""
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
            print(f"    ⚠️  API status {data.get('status')}: {data.get('reason')}")
            if attempt < retries:
                time.sleep(3)
        except requests.exceptions.RequestException as e:
            print(f"    ❌ Request error (attempt {attempt}/{retries}): {e}")
            if attempt < retries:
                time.sleep(5)
    return {}


def get_widgets_by_type(data: dict) -> dict:
    """Index page_content.widgets by their widget type."""
    widgets = data.get("data", {}).get("page_content", {}).get("widgets", [])
    index: dict = {}
    for w in widgets:
        index.setdefault(w.get("type", "UNKNOWN"), []).append(w)
    return index


def throttle():
    """Be nice to the API."""
    time.sleep(REQUEST_DELAY)


# ──────────────────────────────────────────────
# Progress (resume support)
# ──────────────────────────────────────────────

class Progress:
    """Simple checkpoint file so you can kill & restart safely."""

    def __init__(self):
        self.path = Path(PROGRESS_FILE)
        self.completed: set = set()
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.completed = set(data.get("completed", []))
                print(f"   📂 Resumed — {len(self.completed)} topics already done")
            except Exception:
                pass

    def mark_done(self, key: str):
        self.completed.add(key)
        self._save()

    def is_done(self, key: str) -> bool:
        return key in self.completed

    def _save(self):
        payload = {
            "completed": sorted(self.completed),
            "last_updated": datetime.now().isoformat(),
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# ──────────────────────────────────────────────
# Phase 1:  /subject-details  →  discover topics
# ──────────────────────────────────────────────

def build_subject_url(subject_id: str) -> str:
    """Build the page_url for /subject-details."""
    params = {
        "batch_id": BATCH_IDS,
        "selected_batch_list": BATCH_IDS,
        "selected_course_id": COURSE_ID,
        "stream": STREAM,
        "subject_id": subject_id,
        "taxonomy_id": TAXONOMY_ID,
    }
    return "/subject-details?" + _build_qs(params)


def extract_topics_from_subject(data: dict) -> list[dict]:
    """
    Parse the /subject-details response and return a list of topic dicts:
        [{"name": "...", "topic_id": "...", "query_params": {...}}, ...]
    """
    widgets = get_widgets_by_type(data)
    topics: list[dict] = []
    seen: set = set()

    for w in widgets.get("POLYMORPHIC_WIDGET", []):
        inner = w.get("data", {}).get("data", {})
        chapters = inner.get("chapters_list", {}).get("chapters", [])

        for ch in chapters:
            name = ch.get("name", "Unknown")
            if name in seen:
                continue
            seen.add(name)

            action_data = (ch.get("action") or {}).get("data", {})
            query = action_data.get("query", {})
            tracking = (
                (ch.get("action") or {})
                .get("tracking_params", {})
                .get("current", {})
            )

            topics.append({
                "name": name,
                "topic_id": query.get("topic_id", tracking.get("topic_id", "")),
                "subject_id": query.get("subject_id", ""),
                "query_params": query,
            })

    return topics


def run_phase_1() -> dict:
    """
    Hit /subject-details for every subject and collect topics.
    Returns: {"Chemistry": [topic_dict, ...], ...}
    """
    print("\n" + "=" * 60)
    print("  PHASE 1 — Discovering topics via /subject-details")
    print("=" * 60)

    discovered: dict = {}

    for label, subject_id in SUBJECT_IDS:
        if subject_id.startswith("<"):
            print(f"\n  ⏭️  {label}: skipped (placeholder ID)")
            continue

        print(f"\n  📡 Fetching {label} (subject_id={subject_id}) ...")
        url = build_subject_url(subject_id)
        data = api_call(url)

        if not data:
            print(f"    ❌ Failed to fetch {label}. Skipping.")
            throttle()
            continue

        topics = extract_topics_from_subject(data)
        discovered[label] = topics
        print(f"    ✅ {label}: {len(topics)} topics found")
        for t in topics:
            print(f"       • {t['name']}  (topic_id={t['topic_id']})")

        throttle()

    total = sum(len(v) for v in discovered.values())
    print(f"\n  {'─' * 50}")
    print(f"  📊 Total topics discovered: {total}")
    print(f"  {'─' * 50}")
    return discovered


# ──────────────────────────────────────────────
# Phase 2:  /topic-details  →  extract content
# ──────────────────────────────────────────────

def build_topic_url(query_params: dict) -> str:
    """Build the page_url for /topic-details."""
    return "/topic-details?" + _build_qs(query_params)


# ── Individual widget extractors ──

def _extract_videos(widget: dict) -> dict:
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
        action_data = (item.get("content_action") or {}).get("data", {})
        if action_data:
            lecture["content_id"] = action_data.get("content_id", "")
        lectures.append(lecture)

    lectures.sort(key=lambda x: x.get("sequence", 0))

    # Total duration in minutes
    total_minutes = 0.0
    for lec in lectures:
        dur = lec.get("duration", "")
        if ":" in dur:
            parts = dur.split(":")
            if len(parts) == 2:
                total_minutes += int(parts[0]) + int(parts[1]) / 60
            elif len(parts) == 3:
                total_minutes += int(parts[0]) * 60 + int(parts[1]) + int(parts[2]) / 60

    return {
        "section_title": inner.get("title", "Concept Videos"),
        "count": len(lectures),
        "total_duration_minutes": round(total_minutes, 1),
        "lectures": lectures,
    }


def _extract_materials(widget: dict) -> dict:
    inner = widget.get("data", {}).get("data", {})
    cards = inner.get("cards", [])

    groups = []
    for card in cards:
        group = {
            "title": card.get("card_title", "Untitled"),
            "subtitle": card.get("subtitle", ""),
            "materials": [],
        }
        popup = card.get("card_action", {}).get("data", {})
        contents = popup.get("content", {}).get("data", {}).get("contents_list", [])

        for item in contents:
            mat = {
                "title": item.get("content_title", "Untitled"),
                "description": item.get("description", ""),
                "content_type": item.get("type", ""),
                "is_locked": item.get("is_locked", False),
            }
            action_data = (item.get("content_action") or {}).get("data", {})
            if action_data:
                mat["content_id"] = action_data.get("content_id", "")
                mat["pdf_url"] = action_data.get("uri", "")
            group["materials"].append(mat)

        groups.append(group)

    return {
        "section_title": inner.get("title", "Additional Materials"),
        "groups": groups,
    }


def _extract_study_modules(widget: dict) -> dict:
    inner = widget.get("data", {}).get("data", {})
    contents = inner.get("contents_list", [])

    modules = []
    for item in contents:
        mod = {
            "title": item.get("content_title", "Untitled"),
            "description": item.get("description", ""),
            "content_type": item.get("type", ""),
            "is_locked": item.get("is_locked", False),
        }
        action_data = (item.get("content_action") or {}).get("data", {})
        if action_data:
            mod["content_id"] = action_data.get("content_id", "")
            mod["pdf_url"] = action_data.get("uri", "")
        modules.append(mod)

    return {
        "section_title": inner.get("title", "Study Modules"),
        "modules": modules,
    }


def _extract_flashcards(widget: dict) -> dict:
    inner = widget.get("data", {}).get("data", {})
    card = inner.get("card", {})
    return {
        "section_title": inner.get("title", "Flashcards"),
        "subtitle": inner.get("sub_title", ""),
        "card_title": card.get("title", ""),
        "card_subtitle": card.get("subtitle", ""),
        "uri": (
            (card.get("cta") or {}).get("action") or {}
        ).get("data", {}).get("uri", ""),
    }


def _extract_revision_notes(widget: dict) -> dict:
    inner = widget.get("data", {}).get("data", {})
    return {
        "section_title": inner.get("title", "Revision Notes"),
        "subtitle": inner.get("sub_title", ""),
        "uri": (
            (inner.get("cta") or {}).get("action") or {}
        ).get("data", {}).get("uri", ""),
    }


def _extract_custom_practice(widget: dict) -> dict:
    wd = widget.get("data", {})
    options = wd.get("options", [])
    return {
        "section_title": wd.get("title", "Custom Practice"),
        "subtitle": wd.get("subtitle", ""),
        "options": [
            {
                "key": opt.get("key", ""),
                "label": opt.get("label", ""),
                "default": (opt.get("default") or {}).get("display_value", ""),
                "choices": [i.get("display_value", "") for i in opt.get("list", [])],
            }
            for opt in options
        ],
    }


def extract_topic_content(data: dict) -> dict:
    """Parse a /topic-details response into a clean content dict."""
    widgets = get_widgets_by_type(data)
    content: dict = {}

    # Header
    for w in widgets.get("APP_GENERIC_HEADER_V2", []):
        wd = w.get("data", {})
        content["header"] = {
            "title": wd.get("title", ""),
            "subtitles": [s.get("text", "") for s in wd.get("subtitles", [])],
        }

    # Polymorphic content blocks
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

    # Custom practice
    for w in widgets.get("SELECTION_CARD", []):
        content["custom_practice"] = _extract_custom_practice(w)

    return content


def run_phase_2(discovered: dict, progress: Progress) -> dict:
    """
    For every topic found in Phase 1, call /topic-details and extract content.
    Returns the dict that gets merged into the knowledge base.
    """
    print("\n" + "=" * 60)
    print("  PHASE 2 — Extracting topic content via /topic-details")
    print("=" * 60)

    results: dict = {}  # {subject_label: {topic_name: content}}
    total = sum(len(v) for v in discovered.values())
    counter = 0

    for subject_label, topics in discovered.items():
        print(f"\n{'─' * 55}")
        print(f"  📘 {subject_label} ({len(topics)} topics)")
        print(f"{'─' * 55}")

        subject_data: dict = {}

        for topic in topics:
            topic_name = topic["name"]
            topic_key = f"{subject_label}|{topic_name}"
            counter += 1

            # Resume support
            if progress.is_done(topic_key):
                print(f"\n  [{counter}/{total}] ⏭️  {topic_name} (already done)")
                existing = _load_existing_topic(subject_label, topic_name)
                if existing:
                    subject_data[topic_name] = existing
                continue

            print(f"\n  [{counter}/{total}] 🔍 {topic_name}")

            query = topic.get("query_params", {})
            if not query:
                print("      ⚠️  No query params — skipping")
                continue

            url = build_topic_url(query)
            data = api_call(url)

            if not data:
                print("      ❌ Failed")
                throttle()
                continue

            content = extract_topic_content(data)
            content["topic_id"] = topic.get("topic_id", "")

            # Quick progress line
            vids = content.get("concept_videos", {}).get("count", 0)
            dur = content.get("concept_videos", {}).get("total_duration_minutes", 0)
            n_groups = len(content.get("additional_materials", {}).get("groups", []))
            n_mods = len(content.get("study_modules", {}).get("modules", []))
            print(
                f"      📊 Videos: {vids} ({dur:.0f} min) | "
                f"Material groups: {n_groups} | Modules: {n_mods}"
            )

            subject_data[topic_name] = content
            progress.mark_done(topic_key)

            throttle()

        results[subject_label] = subject_data

    return results


# ──────────────────────────────────────────────
# Persistence — merge without destroying
# ──────────────────────────────────────────────

def load_knowledge_base() -> dict:
    """Load the existing knowledge base, or start fresh."""
    path = Path(OUTPUT_FILE)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_knowledge_base(kb: dict):
    """Atomic write: tmp → rename."""
    tmp = Path(OUTPUT_FILE + ".tmp")
    tmp.write_text(json.dumps(kb, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(OUTPUT_FILE)


def merge_results(kb: dict, results: dict):
    """
    Merge newly extracted subject→topic data into the knowledge base
    without overwriting existing entries that weren't re-fetched.
    """
    # Ensure top-level metadata
    if "metadata" not in kb:
        kb["metadata"] = {}

    kb["metadata"].update({
        "source": "Allen Digital (allen.in)",
        "api_endpoint": API_URL,
        "stream": STREAM,
        "course_id": COURSE_ID,
        "batch_ids": BATCH_IDS.split(","),
        "last_updated": datetime.now().isoformat(),
    })

    for subject_label, topics_dict in results.items():
        if not topics_dict:
            continue

        # Find or create the subject bucket.
        # The existing KB nests under class names, but since the new
        # /subject-details call doesn't distinguish class, we merge
        # at the subject level, preserving existing class structure.
        # If the subject already exists somewhere, add topics there;
        # otherwise create a new top-level entry.
        target = _find_subject_bucket(kb, subject_label)

        if target is None:
            # Create a fresh top-level entry
            kb[subject_label] = {
                "total_topics": len(topics_dict),
                "topics": {},
            }
            target = kb[subject_label]

        existing_topics = target.setdefault("topics", {})
        for topic_name, content in topics_dict.items():
            existing_topics[topic_name] = content

        target["total_topics"] = len(existing_topics)


def _find_subject_bucket(kb: dict, subject_label: str) -> dict | None:
    """
    Walk the existing KB structure to find where this subject lives.
    Handles both flat (`kb["Chemistry"]`) and nested (`kb["Class 11"]["Chemistry"]`).
    """
    # Direct key match
    if subject_label in kb and isinstance(kb[subject_label], dict) and "topics" in kb[subject_label]:
        return kb[subject_label]

    # Nested under class names
    for key, val in kb.items():
        if not isinstance(val, dict):
            continue
        if subject_label in val and isinstance(val[subject_label], dict):
            return val[subject_label]

    return None


def _load_existing_topic(subject_label: str, topic_name: str) -> dict:
    """Load a single previously-extracted topic from the output file."""
    try:
        kb = load_knowledge_base()
        bucket = _find_subject_bucket(kb, subject_label)
        if bucket:
            return bucket.get("topics", {}).get(topic_name, {})
    except Exception:
        pass
    return {}


# ──────────────────────────────────────────────
# Summary printer
# ──────────────────────────────────────────────

def print_summary(results: dict):
    print("\n" + "=" * 60)
    print("  📊 EXTRACTION SUMMARY")
    print("=" * 60)

    grand_vids = 0
    grand_pdfs = 0
    grand_mins = 0.0

    for subject, topics in results.items():
        subj_vids = 0
        subj_pdfs = 0
        subj_mins = 0.0

        for _, content in topics.items():
            v = content.get("concept_videos", {})
            subj_vids += v.get("count", 0)
            subj_mins += v.get("total_duration_minutes", 0)
            subj_pdfs += sum(
                len(g.get("materials", []))
                for g in content.get("additional_materials", {}).get("groups", [])
            )
            subj_pdfs += len(content.get("study_modules", {}).get("modules", []))

        print(
            f"\n  {subject}: {len(topics)} topics | "
            f"{subj_vids} videos ({subj_mins:.0f} min / {subj_mins / 60:.1f} hr) | "
            f"{subj_pdfs} PDFs"
        )

        grand_vids += subj_vids
        grand_pdfs += subj_pdfs
        grand_mins += subj_mins

    print(f"\n  {'─' * 50}")
    print(
        f"  TOTAL: {grand_vids} videos | "
        f"{grand_mins:.0f} min ({grand_mins / 60:.1f} hr) | {grand_pdfs} PDFs"
    )
    print("=" * 60)


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  🚀  Allen Data Ripper v3.0")
    print(f"  📅  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    progress = Progress()

    # Phase 1: discover topic_ids from /subject-details
    discovered = run_phase_1()

    if not discovered:
        print("\n  ❌ No subjects returned data. Check your token / subject IDs.")
        sys.exit(1)

    # Phase 2: extract content from /topic-details
    results = run_phase_2(discovered, progress)

    # Merge into existing knowledge base
    kb = load_knowledge_base()
    merge_results(kb, results)
    save_knowledge_base(kb)

    # Summary
    print_summary(results)

    print(f"\n  ✅ Knowledge base saved → {Path(OUTPUT_FILE).resolve()}")
    print(f"\n{'=' * 60}")
    print("  Done. Feed allen_complete_knowledge_base.json to your LLM. 🎓")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
