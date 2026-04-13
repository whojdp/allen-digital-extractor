"""
Quick probe to discover Allen's API navigation endpoints.
Tests: library-web, subject-details, and explore pages.
"""
import json
import requests

API_URL = "https://api.allen-live.in/api/v1/pages/getPage"

HEADERS = {
    "accept": "application/json",
    "accept-language": "en-US,en;q=0.6",
    "authorization": (
        "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJhdWQiOiJhVVNzVzhHSTAzZHlRMEFJRlZuOTIiLCJjYW1wdXMiOiIiLCJjZW50ZXIiOiIiLCJkX3R5cGUiOiJ3ZWIiLCJkaWQiOiIxZDM3YzhiMC1kZjZiLTQ4NDMtOWYyYS1hNzA4YzZjYjE2MGYiLCJlX2lkIjoiNjcyOTczODY2IiwiZXhwIjoxNzc2MzQzMjUzLCJpYXQiOiIyMDI2LTA0LTA5VDEyOjQwOjUzLjUwNTA3NjAxOFoiLCJpc3MiOiJhdXRoZW50aWNhdGlvbi5hbGxlbi1wcm9kIiwiaXN1IjoiZmFsc2UiLCJwdCI6IlNUVURFTlQiLCJzaWQiOiI5ZTJlMmU1ZS03NzY3LTRmNmItOWYwNy1lOGJmNGVlNjA2OTQiLCJzdHJlYW0iOiIiLCJ0aWQiOiJhVVNzVzhHSTAzZHlRMEFJRlZuOTIiLCJ0eXBlIjoiYWNjZXNzIiwidWlkIjoiUjVpRHhuUmFkZU01WUszRjFmcFhPIn0."
        "4mPCSTeA8x48wI03V4AgeYxMw9nVE3TK7uyct7hI4A4"
    ),
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

def probe(name, page_url):
    print(f"\n{'='*60}")
    print(f"PROBING: {name}")
    print(f"page_url: {page_url}")
    print(f"{'='*60}")
    
    resp = requests.post(API_URL, headers=HEADERS, json={"page_url": page_url}, timeout=30)
    data = resp.json()
    
    # Save raw response
    fname = f"probe_{name.replace(' ', '_').lower()}.json"
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"Status: {data.get('status')} {data.get('reason')}")
    
    # Print widget types
    widgets = data.get("data", {}).get("page_content", {}).get("widgets", [])
    print(f"Widget count: {len(widgets)}")
    for w in widgets:
        wtype = w.get("type", "?")
        wdata = w.get("data", {})
        
        # Try to get title or translation_key
        title = wdata.get("title", "")
        tkey = wdata.get("translation_key", "")
        inner_title = wdata.get("data", {}).get("title", "") if isinstance(wdata.get("data"), dict) else ""
        
        desc = title or tkey or inner_title or ""
        print(f"  [{wtype}] {desc[:80]}")
        
        # If it has tabs, print them
        if "tabs" in wdata:
            for tab in wdata["tabs"][:10]:
                tab_title = tab.get("title", tab.get("label", "?"))
                print(f"    TAB: {tab_title}")
                
        # If it has items/cards/contents, show count
        for key in ["items", "cards", "contents_list", "subjects", "chapters", "topics"]:
            items = wdata.get(key, [])
            if not items and isinstance(wdata.get("data"), dict):
                items = wdata.get("data", {}).get(key, [])
            if items:
                print(f"    {key}: {len(items)} items")
                for item in items[:5]:
                    item_name = item.get("title", item.get("name", item.get("label", item.get("card_title", ""))))
                    item_id = item.get("id", item.get("subject_id", item.get("topic_id", "")))
                    action_data = (item.get("action") or item.get("card_action") or item.get("cta_action") or {}).get("data", {})
                    query = action_data.get("query", {})
                    uri = action_data.get("uri", "")
                    print(f"      - {item_name} (id={item_id}) -> {uri}")
                    if query:
                        print(f"        query: {json.dumps(query, indent=0)[:200]}")
                if len(items) > 5:
                    print(f"      ... and {len(items) - 5} more")
    
    print(f"Saved to: {fname}")
    return data

# 1. Library page (Study tab)
probe("library", "/library-web?batch_id=bt_dGHnem4IjNtEOVQjfmW26%2Cbt_Ez5lOBgnoJadUVdL7IaXM%2Cbt_Lk86uKMqqav23yczHJHJh&selected_batch_list=bt_dGHnem4IjNtEOVQjfmW26%2Cbt_Ez5lOBgnoJadUVdL7IaXM%2Cbt_Lk86uKMqqav23yczHJHJh&selected_course_id=cr_cpTLbkqWLu96FPkmfoREz&stream=STREAM_JEE_MAIN_ADVANCED")

# 2. Subject details (Chemistry, Class 11)
probe("subject_chem_11", "/subject-details?batch_id=bt_dGHnem4IjNtEOVQjfmW26%2Cbt_Ez5lOBgnoJadUVdL7IaXM%2Cbt_Lk86uKMqqav23yczHJHJh&class_12_subject_id=746&class_12_taxonomy_id=1739171216OJ&revision_class=CLASS_11&selected_batch_list=bt_dGHnem4IjNtEOVQjfmW26%2Cbt_Ez5lOBgnoJadUVdL7IaXM%2Cbt_Lk86uKMqqav23yczHJHJh&selected_course_id=cr_cpTLbkqWLu96FPkmfoREz&stream=STREAM_JEE_MAIN_ADVANCED&subject_id=2&taxonomy_id=1739171216OJ")

# 3. Subject details (Chemistry, Class 12 — try subject_id=746)  
probe("subject_chem_12", "/subject-details?batch_id=bt_dGHnem4IjNtEOVQjfmW26%2Cbt_Ez5lOBgnoJadUVdL7IaXM%2Cbt_Lk86uKMqqav23yczHJHJh&selected_batch_list=bt_dGHnem4IjNtEOVQjfmW26%2Cbt_Ez5lOBgnoJadUVdL7IaXM%2Cbt_Lk86uKMqqav23yczHJHJh&selected_course_id=cr_cpTLbkqWLu96FPkmfoREz&stream=STREAM_JEE_MAIN_ADVANCED&subject_id=746&taxonomy_id=1739171216OJ")

# 4. Explore page
probe("explore", "/explore")

print("\n\nDone! Check the probe_*.json files for full responses.")
