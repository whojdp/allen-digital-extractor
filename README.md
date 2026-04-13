# Allen Digital Universal Knowledge Base Extractor 🚀

An autonomous, API-driven Python extraction engine designed to fully map, scrape, and download the entire curriculum from the Allen Digital platform. 

This script bypasses slow visual UI browser-crawling by communicating directly with Allen's backend `getPage` API, resulting in lighting-fast, incredibly robust full-platform extraction.

## 🎯 What This Does

When run, the script autonomously performs the following operations:
1. **API Discovery:** Discovers the exact UUIDs and query parameters for every single Subject (Physics, Chemistry, Maths) across Class 11 and Class 12.
2. **Deep Metadata Extraction:** Mines the payload of every chapter to extract:
   - 📺 **Concept Videos:** Titles, descriptions, exact durations, and optimal viewing sequences.
   - 🃏 **Flashcards & Revision Notes:** Full metadata URIs.
   - 📝 **Practice Tests:** Extracted configs, tags, and difficulty bounds.
3. **Mass PDF Downloader:** Automatically scans for RACE modules, Exercise sheets, and massive Study Modules, downloading the authentic secure PDFs directly to organized folders on your hard drive.
4. **Resiliency:** Progress is safely check-pointed. If your internet dies or power goes out, the script perfectly resumes exactly where it left off without duplicating downloads.
5. **The Ultimate Master File:** Compiles all 1,500+ videos and hundreds of chapters into one single, massive `allen_complete_knowledge_base.json`.

## 🧠 Why? (The LLM Roadmap Vision)

This extractor was fundamentally built to decouple you from the restrictive Allen app. By structuring the entirety of Allen's curriculum into a granular JSON format, you can feed `allen_complete_knowledge_base.json` directly into an LLM (like Claude or GPT-4).

The AI can then instantly calculate hundreds of hours of video lengths against your specific exam timeline, dynamically generating the ultimate, day-by-day, perfectly-paced JEE study roadmap.

## 📊 Extraction Stats (Example Run)
*   **Total Concept Videos Indexed:** ~1,600+
*   **Total Official PDFs Downloaded:** ~430+ 
*   **Topics Fully Mapped:** All Physics, Chemistry, and Maths topics across both 11th and 12th standards.

## ⚙️ How to Use

*(Note: Ensure you do NOT share your authentication token or upload the massive `allen_pdfs/` folder as it contains vast amounts of copyrighted material. Keep the PDFs localized to your machine!)*

1. Install requirements:
   ```bash
   pip install requests
   ```
2. Paste your Allen platform explicit `Bearer` token inside `allen_token.txt`.
3. Run the ripper!
   ```bash
   python allen_full_rip.py
   ```
4. Sit back. The script will securely download gigabytes of PDFs and generate the JSON brain output.

---
*Disclaimer: Created for personal, offline study optimization and data structural mapping. Respect the copyright policies of the educational platform and do not distribute the downloaded lecture matrices or PDF documents.*
