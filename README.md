# Allen Digital Extractor 🧪

A Python pipeline that talks directly to Allen's internal `getPage` API to rip the entire JEE curriculum — every lecture, every PDF, every flashcard deck — and flatten it into one structured JSON file.

No browser automation. No Selenium. No clicking through hundreds of pages. Just raw HTTP → structured data.

---

## What this actually is

This isn't a generic web scraper. It's the **data ingestion layer** for a custom AI + ML engineering curriculum I'm building.

The idea: digitize Allen's complete Class 11 & 12 syllabus into a machine-readable format, then feed it into an LLM-powered scheduler that generates a real, day-by-day study plan — weighted by topic difficulty, video duration, and exam relevance.

**The tactical deadline:** finish extracting and completing all pending Class 12 coursework (and any remaining Class 11 backlog) by November. December is reserved purely for full-length mock tests and problem-solving. The AI scheduler can't optimize a plan it can't see, so step one is getting the raw data out.

---

## How it works

The script runs a **two-phase recursive loop** against Allen's `getPage` API:

```
Phase 1 — /subject-details
   For each subject_id (Physics=1160, Maths=1264),
   hit the subject-level endpoint and scrape the full chapter list.
   Extract every topic_id from the response.

Phase 2 — /topic-details
   For each discovered topic_id, hit the topic-level endpoint.
   Parse out:
     → Concept video metadata (title, duration, sub-topics, sequence)
     → RACE & Exercise PDFs (direct CloudFront URLs)
     → Study Module PDFs
     → Flashcard deck metadata
     → Revision notes
     → Custom practice quiz configs
```

`time.sleep(1.5)` sits between every request so we don't hammer the API.

### Resume support

Progress checkpoints to `rip_progress.json`. If the script crashes, your Wi-Fi drops, or you `Ctrl+C` — it resumes exactly where it left off. No duplicate API calls, no lost data.

### Non-destructive merge

New data gets merged into `allen_complete_knowledge_base.json` without overwriting anything already in there. You can run the script multiple times (adding subjects, re-running after a token refresh) and existing entries stay untouched.

---

## Setup

1. **Install the one dependency:**
   ```bash
   pip install requests
   ```

2. **Create `allen_token.txt`** in the project root. Paste your Bearer token inside (just the token string, no `Bearer` prefix).

   Grab it from DevTools → Network tab → any `getPage` request → `Authorization` header.

   > ⚠️ **This file is gitignored.** Don't commit it. Tokens expire — if you start getting 401s, grab a fresh one.

3. **Run it:**
   ```bash
   python allen_data_rip.py
   ```

   That's it. Sit back and watch it chew through every chapter.

---

## Current subject config

```python
SUBJECT_IDS = [
    ("Physics", "1160"),
    ("Maths", "1264"),
]
```

Chemistry and Class 11 data already lives in the knowledge base from earlier runs. These two IDs cover the remaining Class 12 Physics and Maths chapters.

To add more subjects later, intercept the `/subject-details` network request in DevTools and grab the `subject_id` from the request body.

---

## Output files

| File | What it is |
|------|-----------|
| `allen_complete_knowledge_base.json` | The whole curriculum — every topic, video, PDF link, organized by subject → chapter |
| `rip_progress.json` | Checkpoint state for resume support |
| `allen_token.txt` | Your auth token (gitignored, never committed) |

### JSON shape

```json
{
  "metadata": {
    "source": "Allen Digital (allen.in)",
    "stream": "STREAM_JEE_MAIN_ADVANCED",
    "last_updated": "2026-04-13T..."
  },
  "Physics": {
    "total_topics": 22,
    "topics": {
      "Mechanics": {
        "concept_videos": { "count": 30, "total_duration_minutes": 720.0, "lectures": [...] },
        "additional_materials": { "groups": [...] },
        "study_modules": { "modules": [...] },
        "flashcards": { ... },
        "revision_notes": { ... }
      }
    }
  }
}
```

---

## Other scripts

| Script | What it does |
|--------|-------------|
| `allen_data_rip.py` | **The main pipeline** — two-phase subject→topic extraction loop |
| `allen_full_rip.py` | Earlier version with baked-in PDF downloading and Class 11/12 auto-discovery |
| `api_probe.py` | Diagnostic tool — hits a few endpoints and dumps raw JSON for manual inspection |
| `generate_roadmap.py` | Takes the knowledge base and feeds it to an LLM for study schedule generation |

---

## Stats from previous runs

- **~1,600+ concept videos** indexed with durations and sub-topic breakdowns
- **~430+ PDFs** catalogued (RACE sheets, exercises, study modules)
- **All Class 11 PCM** already in the knowledge base
- **Class 12 Physics + Maths** being added with this run

---

## ⚠️ Ground rules

- **Don't share your token.** It's tied to your Allen account.
- **Don't distribute the PDFs or video URLs.** Copyrighted material. Everything stays local.
- **Tokens expire.** Refresh from the browser when needed.

This is a personal data pipeline for study optimization, not a redistribution tool.

---

*Built because I got tired of the Allen app's walled garden.  
The dataset this produces is step one of a bigger play: an ML-powered curriculum planner that actually understands topic dependencies, time budgets, and exam weightage — and builds a schedule that gets everything done by November so December is pure problem-solving mode.* 🎯
