# Allen Digital Extractor 🧪

A precision data-ingestion pipeline that communicates directly with Allen's internal `getPage` API to extract, structure, and serialize the complete JEE Advanced curriculum into a single, machine-readable JSON file.

No browser automation. No Selenium. No Playwright. Just authenticated HTTP requests hitting the same endpoints the webapp uses internally — except instead of rendering React components, we parse the raw payload and keep moving.

---

## Why this exists

Allen's platform is designed for one thing: watching one video at a time inside their app. It's not designed for answering questions like:

- *"Across all 3 subjects, how many hours of lecture content do I have left?"*
- *"Which chapters have exercises uploaded but no study modules?"*
- *"If I have 200 days until my exam, how many minutes of content do I need to cover per day, accounting for my gym schedule and weekends?"*

You can't answer those questions by clicking around a webapp. You answer them by **extracting the entire dataset, structuring it, and feeding it to a system that can reason over it.**

That system is an LLM. This repo is the data layer that makes it possible.

---

## Architecture: The Two-Phase Extraction Loop

The script (`allen_data_rip.py`) executes a recursive two-phase loop against Allen's `getPage` API:

```
Phase 1 — /subject-details
   For each subject_id in [1160, 746, 1264] (Physics, Chemistry, Maths):
     → Hit the subject-level endpoint
     → Parse the chapter list from the response widgets
     → Extract every topic_id

Phase 2 — /topic-details
   For each discovered topic_id:
     → Hit the topic-level endpoint
     → Extract structured content:
         • Concept videos (title, duration, sub-topics, sequence order)
         • RACE & Exercise PDFs (direct signed CloudFront URLs)
         • Study Module PDFs
         • Flashcard deck metadata
         • Revision notes URIs
         • Custom practice quiz configurations
     → Merge into the knowledge base
     → Checkpoint progress
     → Sleep 1.5s before the next request
```

### Resume support

Every completed topic is checkpointed to `rip_progress.json`. Kill the process, lose internet, reboot your machine — the script resumes exactly where it left off. Zero duplicate API calls.

### Non-destructive merge

New data is merged into `allen_complete_knowledge_base.json` without overwriting existing entries. The Class 11 data from earlier extraction runs is preserved. You can re-run the script after a token refresh or after adding new subject IDs, and nothing gets clobbered.

---

## Current extraction status

| Scope | Subjects | Status |
|-------|----------|--------|
| **Class 11** | Physics, Chemistry, Mathematics | ✅ Fully extracted |
| **Class 12** | Physics (`1160`) | ✅ Extracted |
| **Class 12** | Chemistry (`746`) | ✅ Extracted |
| **Class 12** | Mathematics (`1264`) | ✅ Extracted |

### Aggregate stats

- **~1,600+ concept videos** indexed with per-lecture durations and sub-topic breakdowns
- **~430+ PDFs** catalogued (RACE sheets, exercise solutions, study modules)
- **Full PCM coverage** across both Class 11 and Class 12

---

## The Ultimate Goal: RAG-Powered Study Intelligence

This repository is **Phase 1: Data Ingestion** of a larger system.

### Phase 1 — Data Ingestion (this repo)

Extract Allen's entire curriculum into `allen_complete_knowledge_base.json` — a structured, hierarchical dataset containing every video, every PDF, every topic dependency, and every duration metric across all subjects and classes.

### Phase 2 — LLM-as-Reasoning-Engine (RAG Architecture)

The JSON file produced by Phase 1 becomes the **context window payload** for a frontier LLM — Claude 3 Opus, Gemini 1.5 Pro, or equivalent. The full knowledge base (~1MB of structured JSON) fits comfortably within modern context windows (200K+ tokens), enabling the model to reason over the *entire* curriculum simultaneously.

This is not a simple chatbot integration. It's a **Retrieval-Augmented Generation architecture** where the retrieval layer is the complete, pre-extracted curriculum graph, and the generation layer is a frontier model operating with full visibility into:

- Every chapter across all 6 subject-class combinations
- Total video hours remaining per subject
- Which topics have supplementary materials vs. video-only coverage
- The sequential dependency ordering within each chapter

### Phase 3 — The AI Study Coach

With the full curriculum loaded as context, the LLM acts as a **dynamic, context-aware study planner**. Concretely, it can:

- **Generate daily study schedules** — not generic templates, but plans derived from the actual video durations and topic counts in the dataset
- **Calculate required daily throughput** — "You have 847 hours of content remaining. At 4.5 hours/day with weekends off, you need to start by [date] to finish by November 1st."
- **Track completion state** — mark topics as done, recalculate the remaining workload, and dynamically rebalance the schedule
- **Adapt to fixed constraints** — account for gym sessions, school hours, energy levels (heavier subjects in the morning, lighter review in the evening)
- **Prioritize by exam weightage** — surface high-yield chapters first based on JEE Advanced topic distribution patterns
- **Flag gaps** — identify chapters where you have videos but haven't downloaded the exercise PDFs, or topics with no flashcard coverage

The hard deadline: **all coursework complete by November 1st.** December is reserved exclusively for full-length mock tests and targeted problem-solving. The AI scheduler's job is to make that timeline mathematically achievable and dynamically adjust when life inevitably disrupts the plan.

---

## Setup

1. **Install dependencies:**
   ```bash
   pip install requests
   ```

2. **Create `allen_token.txt`** in the project root with your Bearer token inside (just the token, no `Bearer` prefix).

   Grab it: DevTools → Network → any `getPage` call → `Authorization` header → copy the token after `Bearer `.

   > ⚠️ Gitignored. Never committed. Tokens expire — refresh from the browser when you hit 401s.

3. **Run the extractor:**
   ```bash
   python allen_data_rip.py
   ```

---

## Subject configuration

```python
SUBJECT_IDS = [
    ("Physics", "1160"),
    ("Chemistry", "746"),
    ("Maths", "1264"),
]
```

To add more subjects: open Allen in the browser → navigate to the subject → DevTools Network tab → find the `getPage` request → copy the `subject_id` from the request body.

---

## Output

| File | Purpose |
|------|---------|
| `allen_complete_knowledge_base.json` | Complete structured curriculum — the payload for the LLM context window |
| `rip_progress.json` | Extraction checkpoint state (resume support) |
| `allen_token.txt` | Auth token (gitignored) |

---

## Other scripts

| Script | Purpose |
|--------|---------|
| `allen_data_rip.py` | Main pipeline — two-phase subject→topic extraction loop |
| `allen_full_rip.py` | Earlier version with integrated PDF downloading and Class 11/12 auto-discovery |
| `api_probe.py` | Diagnostic — hits endpoints and dumps raw JSON for manual inspection |
| `generate_roadmap.py` | Feeds the knowledge base to an LLM to generate study schedules |

---

## ⚠️ Operational notes

- **Tokens are account-bound.** Don't share `allen_token.txt`.
- **Content is copyrighted.** PDFs and video URLs stay local. This is a personal optimization tool, not a distribution mechanism.
- **Rate limiting is built in.** 1.5s between requests. Don't remove it.
- **Token expiry.** If the script starts returning 401s or non-200 statuses, grab a fresh token from the browser.

---

*This is infrastructure, not a toy. The JSON file this script produces is the foundation for a system that turns a massive, unstructured ed-tech platform into a programmable, AI-optimized learning pipeline — one that adapts to my schedule, respects my constraints, and keeps me accountable to a hard November 1st deadline.* 🎯
