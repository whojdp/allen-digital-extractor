"""
Allen Data Ripper v2.0
======================
Replicates the intercepted getPage API call for the Allen curriculum,
parses the JSON response, and extracts:
  - Chapter / Topic Names (from breadcrumbs & header)
  - Concept Video Lectures (titles, durations, descriptions, sub-topics, HLS URLs)
  - Additional Materials (RACE PDFs, Exercise Solutions PDFs)
  - Study Module PDFs
  - Flashcard & Revision Notes metadata
  - Custom Practice quiz configuration

Output: final_syllabus.json  --  a beautiful, hierarchical JSON file.

Usage:
    python allen_data_rip.py
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

import requests


# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────

API_URL = "https://api.allen-live.in/api/v1/pages/getPage"
OUTPUT_FILE = "final_syllabus.json"
RAW_RESPONSE_FILE = "raw_api_response.json"

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

PAYLOAD = {
    "page_url": (
        "/topic-details?"
        "batch_id=bt_dGHnem4IjNtEOVQjfmW26%2Cbt_Ez5lOBgnoJadUVdL7IaXM%2Cbt_Lk86uKMqqav23yczHJHJh"
        "&class_12_subject_id=746"
        "&class_12_taxonomy_id=1739171216OJ"
        "&revision_class=CLASS_11"
        "&selected_batch_list=bt_dGHnem4IjNtEOVQjfmW26%2Cbt_Ez5lOBgnoJadUVdL7IaXM%2Cbt_Lk86uKMqqav23yczHJHJh"
        "&selected_course_id=cr_cpTLbkqWLu96FPkmfoREz"
        "&stream=STREAM_JEE_MAIN_ADVANCED"
        "&subject_id=2"
        "&taxonomy_id=1739171216OJ"
        "&topic_id=89"
    )
}


# ──────────────────────────────────────────────
# API call
# ──────────────────────────────────────────────

def fetch_page_data() -> dict:
    """Make the getPage API call and return the parsed JSON response."""
    print("[*] Calling Allen getPage API...")
    print(f"    URL: {API_URL}")

    try:
        resp = requests.post(API_URL, headers=HEADERS, json=PAYLOAD, timeout=30)
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        print(f"[!] HTTP Error: {e}")
        print(f"    Status: {resp.status_code}")
        print(f"    Body:   {resp.text[:500]}")
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"[!] Request failed: {e}")
        sys.exit(1)

    data = resp.json()
    print(f"[+] Response received ({len(resp.content):,} bytes)")

    Path(RAW_RESPONSE_FILE).write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[+] Raw response saved to {RAW_RESPONSE_FILE}")
    return data


# ──────────────────────────────────────────────
# Extraction helpers
# ──────────────────────────────────────────────

def get_widgets_by_type(data: dict) -> dict:
    """
    Index page_content.widgets by their type.
    Returns {type_string: [widget, ...]} for easy lookup.
    """
    widgets = data.get("data", {}).get("page_content", {}).get("widgets", [])
    index = {}
    for w in widgets:
        wtype = w.get("type", "UNKNOWN")
        index.setdefault(wtype, []).append(w)
    return index


def extract_breadcrumbs(widget: dict) -> list[dict]:
    """Extract the breadcrumb trail from a BREADCRUMBS widget."""
    crumbs = widget.get("data", {}).get("breadcrumbs", [])
    return [
        {
            "id": bc.get("id"),
            "label": bc.get("label", ""),
            "is_active": bc.get("isActive", False),
            "uri": (bc.get("action") or {}).get("data", {}).get("uri", ""),
        }
        for bc in crumbs
    ]


def extract_header(widget: dict) -> dict:
    """Extract topic header metadata from APP_GENERIC_HEADER_V2."""
    wd = widget.get("data", {})
    subtitles = wd.get("subtitles", [])
    return {
        "title": wd.get("title", ""),
        "subtitles": [s.get("text", "") for s in subtitles],
        "background_image": (wd.get("background_image") or {}).get("url", ""),
    }


def extract_concept_videos(widget: dict) -> dict:
    """
    Extract all concept video lectures from a POLYMORPHIC_WIDGET
    with translation_key = LIBRARY_VIDEOS_WEB.

    Each video item has:
      content_title, duration, description, sub_topics, sequence,
      is_locked, type, and content_action.data with video URI.
    """
    inner = widget.get("data", {}).get("data", {})
    section_title = inner.get("title", "Concept Videos")
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
            "thumbnail": (item.get("image_data") or {}).get("url", ""),
            "is_new": bool(item.get("new")),
        }

        # Extract video playback URL from content_action
        action_data = (item.get("content_action") or {}).get("data", {})
        if action_data:
            lecture["content_id"] = action_data.get("content_id", "")
            lecture["video_url"] = action_data.get("uri", "")
            lecture["batch_id"] = action_data.get("batch_id", "")

            # Extract watch progress if available
            progress = action_data.get("progress_info")
            if progress:
                lecture["progress"] = {
                    "completion": round(progress.get("completion_factor", 0) * 100, 2),
                    "elapsed_seconds": progress.get("elapsed_duration", 0),
                    "total_seconds": progress.get("total_duration", 0),
                }

        lectures.append(lecture)

    # Sort by sequence
    lectures.sort(key=lambda x: x.get("sequence", 0))

    return {
        "section_title": section_title,
        "total_count": len(lectures),
        "lectures": lectures,
    }


def extract_additional_materials(widget: dict) -> dict:
    """
    Extract Additional Materials from a POLYMORPHIC_WIDGET
    with translation_key = LIBRARY_ADDITIONAL_MATERIAL_WEB.

    Each card (e.g. 'RACE & Solutions', 'Exercises & Solutions') contains
    a nested contents_list with PDF links.
    """
    inner = widget.get("data", {}).get("data", {})
    section_title = inner.get("title", "Additional Materials")
    cards = inner.get("cards", [])

    material_groups = []
    for card in cards:
        group = {
            "title": card.get("card_title", "Untitled"),
            "subtitle": card.get("subtitle", ""),
            "is_new": bool(card.get("new")),
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
                material["action_type"] = (item.get("content_action") or {}).get("type", "")

            group["materials"].append(material)

        material_groups.append(group)

    return {
        "section_title": section_title,
        "groups": material_groups,
    }


def extract_study_modules(widget: dict) -> dict:
    """
    Extract Study Modules from a POLYMORPHIC_WIDGET
    with translation_key = LIBRARY_STUDY_MODULES_WEB.
    """
    inner = widget.get("data", {}).get("data", {})
    section_title = inner.get("title", "Study Modules")
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
        "section_title": section_title,
        "modules": modules,
    }


def extract_flashcards(widget: dict) -> dict:
    """Extract Flashcards metadata from LIBRARY_FLASHCARDS_CONTAINER_B1_WEB."""
    inner = widget.get("data", {}).get("data", {})
    card = inner.get("card", {})
    return {
        "section_title": inner.get("title", "Flashcards"),
        "subtitle": inner.get("sub_title", ""),
        "card_title": card.get("title", ""),
        "card_subtitle": card.get("subtitle", ""),
        "progress": card.get("progress", ""),
        "remaining": card.get("number_of_topics_remaining", ""),
        "image": (inner.get("image_data") or {}).get("url", ""),
        "uri": ((card.get("cta") or {}).get("action") or {}).get("data", {}).get("uri", ""),
    }


def extract_revision_notes(widget: dict) -> dict:
    """Extract Revision Notes metadata from LIBRARY_REVISION_NOTES_WEB."""
    inner = widget.get("data", {}).get("data", {})
    return {
        "section_title": inner.get("title", "Revision Notes"),
        "subtitle": inner.get("sub_title", ""),
        "image": (inner.get("image_data") or {}).get("url", ""),
        "uri": ((inner.get("cta") or {}).get("action") or {}).get("data", {}).get("uri", ""),
    }


def extract_custom_practice(widget: dict) -> dict:
    """Extract Custom Practice quiz config from SELECTION_CARD."""
    wd = widget.get("data", {})
    options = wd.get("options", [])
    parsed_options = []
    for opt in options:
        parsed_options.append({
            "key": opt.get("key", ""),
            "label": opt.get("label", ""),
            "default": (opt.get("default") or {}).get("display_value", ""),
            "choices": [
                item.get("display_value", "")
                for item in opt.get("list", [])
            ],
        })
    return {
        "section_title": wd.get("title", "Custom Practice"),
        "subtitle": wd.get("subtitle", ""),
        "options": parsed_options,
    }


# ──────────────────────────────────────────────
# Build the final hierarchical output
# ──────────────────────────────────────────────

TRANSLATION_KEY_MAP = {
    "LIBRARY_VIDEOS_WEB": "concept_videos",
    "LIBRARY_ADDITIONAL_MATERIAL_WEB": "additional_materials",
    "LIBRARY_STUDY_MODULES_WEB": "study_modules",
    "LIBRARY_FLASHCARDS_CONTAINER_B1_WEB": "flashcards",
    "LIBRARY_REVISION_NOTES_WEB": "revision_notes",
}


def build_syllabus(raw_data: dict) -> dict:
    """Build the final_syllabus.json structure from the raw API response."""

    widget_index = get_widgets_by_type(raw_data)

    # ── Breadcrumbs ──
    breadcrumbs = []
    for w in widget_index.get("BREADCRUMBS", []):
        breadcrumbs = extract_breadcrumbs(w)

    # ── Header / Topic info ──
    header = {}
    for w in widget_index.get("APP_GENERIC_HEADER_V2", []):
        header = extract_header(w)

    # ── Custom Practice ──
    custom_practice = {}
    for w in widget_index.get("SELECTION_CARD", []):
        custom_practice = extract_custom_practice(w)

    # ── Polymorphic Widgets (main content) ──
    concept_videos = {}
    additional_materials = {}
    study_modules = {}
    flashcards = {}
    revision_notes = {}

    for w in widget_index.get("POLYMORPHIC_WIDGET", []):
        tkey = w.get("data", {}).get("translation_key", "")

        if tkey == "LIBRARY_VIDEOS_WEB":
            concept_videos = extract_concept_videos(w)
        elif tkey == "LIBRARY_ADDITIONAL_MATERIAL_WEB":
            additional_materials = extract_additional_materials(w)
        elif tkey == "LIBRARY_STUDY_MODULES_WEB":
            study_modules = extract_study_modules(w)
        elif tkey == "LIBRARY_FLASHCARDS_CONTAINER_B1_WEB":
            flashcards = extract_flashcards(w)
        elif tkey == "LIBRARY_REVISION_NOTES_WEB":
            revision_notes = extract_revision_notes(w)

    # ── Parse URL parameters for metadata ──
    page_url = PAYLOAD.get("page_url", "")
    params = {}
    if "?" in page_url:
        for param in page_url.split("?", 1)[1].split("&"):
            if "=" in param:
                k, v = param.split("=", 1)
                params[k] = unquote(v)

    # ── Statistics ──
    total_videos = concept_videos.get("total_count", 0)
    total_pdfs = sum(
        len(g.get("materials", []))
        for g in additional_materials.get("groups", [])
    ) + len(study_modules.get("modules", []))

    total_resources = total_pdfs
    if flashcards:
        total_resources += 1
    if revision_notes:
        total_resources += 1

    # ── Assemble the final structure ──
    syllabus = {
        "metadata": {
            "source": "Allen Digital (allen.in)",
            "api_endpoint": API_URL,
            "extracted_at": datetime.now().isoformat(),
            "stream": params.get("stream", "N/A"),
            "subject_id": params.get("subject_id", "N/A"),
            "topic_id": params.get("topic_id", "N/A"),
            "taxonomy_id": params.get("taxonomy_id", "N/A"),
            "revision_class": params.get("revision_class", "N/A"),
            "course_id": params.get("selected_course_id", "N/A"),
            "batch_ids": params.get("batch_id", "N/A").split(","),
        },
        "navigation": {
            "breadcrumbs": breadcrumbs,
        },
        "topic": {
            "name": header.get("title", ""),
            "class": next((s for s in header.get("subtitles", []) if "Class" in s), ""),
            "subject": next(
                (s for s in header.get("subtitles", []) if "Class" not in s), ""
            ),
            "background_image": header.get("background_image", ""),
        },
        "statistics": {
            "total_concept_videos": total_videos,
            "total_pdfs": total_pdfs,
            "total_resources": total_resources,
            "has_flashcards": bool(flashcards),
            "has_revision_notes": bool(revision_notes),
            "has_custom_practice": bool(custom_practice),
        },
        "content": {
            "concept_videos": concept_videos,
            "additional_materials": additional_materials,
            "study_modules": study_modules,
            "flashcards": flashcards,
            "revision_notes": revision_notes,
            "custom_practice": custom_practice,
        },
    }

    return syllabus


# ──────────────────────────────────────────────
# Pretty printing
# ──────────────────────────────────────────────

def print_syllabus_summary(syllabus: dict):
    """Print a beautiful console summary of the extracted syllabus."""
    topic = syllabus["topic"]
    stats = syllabus["statistics"]
    nav = syllabus["navigation"]
    content = syllabus["content"]

    print()
    print("=" * 70)
    print("  EXTRACTED SYLLABUS SUMMARY")
    print("=" * 70)

    # Breadcrumb path
    crumb_path = " > ".join(bc["label"] for bc in nav["breadcrumbs"])
    print(f"  Path: {crumb_path}")
    print(f"  Topic: {topic['name']}")
    print(f"  Class: {topic['class']}  |  Subject: {topic['subject']}")
    print("-" * 70)
    print(f"  Concept Videos : {stats['total_concept_videos']}")
    print(f"  PDFs           : {stats['total_pdfs']}")
    print(f"  Flashcards     : {'Yes' if stats['has_flashcards'] else 'No'}")
    print(f"  Revision Notes : {'Yes' if stats['has_revision_notes'] else 'No'}")
    print(f"  Custom Practice: {'Yes' if stats['has_custom_practice'] else 'No'}")
    print("-" * 70)

    # Concept Videos
    videos = content.get("concept_videos", {})
    if videos.get("lectures"):
        print(f"\n  [{videos['section_title']}] ({videos['total_count']} videos)")
        for lec in videos["lectures"]:
            seq = lec.get("sequence", "?")
            title = lec.get("title", "Untitled")
            dur = lec.get("duration", "N/A")
            locked = " [LOCKED]" if lec.get("is_locked") else ""
            progress_str = ""
            if lec.get("progress"):
                pct = lec["progress"]["completion"]
                progress_str = f" ({pct:.1f}% watched)"

            print(f"    {seq:>2}. {title}")
            print(f"        Duration: {dur}{locked}{progress_str}")

            if lec.get("sub_topics"):
                for st in lec["sub_topics"]:
                    print(f"        Sub-topic: {st}")

            if lec.get("video_url"):
                url_preview = lec["video_url"][:80] + "..."
                print(f"        Video: {url_preview}")

    # Additional Materials
    materials = content.get("additional_materials", {})
    if materials.get("groups"):
        print(f"\n  [{materials['section_title']}]")
        for group in materials["groups"]:
            print(f"    >> {group['title']} ({group['subtitle']})")
            for mat in group.get("materials", []):
                print(f"       - {mat['title']}")
                if mat.get("pdf_url"):
                    print(f"         PDF: {mat['pdf_url'][:80]}...")

    # Study Modules
    mods = content.get("study_modules", {})
    if mods.get("modules"):
        print(f"\n  [{mods['section_title']}]")
        for mod in mods["modules"]:
            print(f"    - {mod['title']}")
            if mod.get("pdf_url"):
                print(f"      PDF: {mod['pdf_url'][:80]}...")

    # Flashcards
    fc = content.get("flashcards", {})
    if fc and fc.get("section_title"):
        print(f"\n  [{fc['section_title']}] {fc.get('subtitle', '')}")
        if fc.get("uri"):
            print(f"    URI: {fc['uri']}")

    # Revision Notes
    rn = content.get("revision_notes", {})
    if rn and rn.get("section_title"):
        print(f"\n  [{rn['section_title']}] {rn.get('subtitle', '')}")
        if rn.get("uri"):
            print(f"    URI: {rn['uri']}")

    # Custom Practice
    cp = content.get("custom_practice", {})
    if cp and cp.get("options"):
        print(f"\n  [{cp['section_title']}] {cp.get('subtitle', '')}")
        for opt in cp["options"]:
            choices = ", ".join(opt["choices"][:5])
            print(f"    {opt['label']}: {opt['default']} (choices: {choices})")

    print()
    print("=" * 70)


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def main():
    print("=" * 70)
    print("  Allen Data Ripper v2.0")
    print("=" * 70)

    # Step 1: Fetch data from the API
    raw_data = fetch_page_data()

    # Step 2: Quick structure check
    status = raw_data.get("status")
    reason = raw_data.get("reason")
    print(f"[+] API Status: {status} {reason}")

    if status != 200:
        print("[!] Non-200 status. Check raw_api_response.json for details.")
        sys.exit(1)

    # Step 3: Extract & build syllabus
    print("[*] Extracting curriculum data...")
    syllabus = build_syllabus(raw_data)

    # Step 4: Save to file
    output_path = Path(OUTPUT_FILE)
    output_path.write_text(
        json.dumps(syllabus, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[+] Syllabus saved to: {output_path.resolve()}")

    # Step 5: Print human-readable summary
    print_syllabus_summary(syllabus)

    print(f"[+] Done! Total content sections extracted: "
          f"{sum(1 for v in syllabus['content'].values() if v)}")


if __name__ == "__main__":
    main()
