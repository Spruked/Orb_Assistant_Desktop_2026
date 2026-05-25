import sys
import os
import json
import urllib.request
import datetime
from typing import Optional

USGS_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"
RESULTS_DIRS = [
    os.path.join("R:/R_Drive_Substrate/orb_mesh/results/research_executor"),
    os.path.join(os.path.dirname(__file__), "../research_results")
]

SCHEMA = {
    "ok": False,
    "source_id": "usgs_earthquake_all_day",
    "source_name": "USGS Earthquake Feed - All Day",
    "source_url": USGS_URL,
    "query": None,
    "fetched_at": None,
    "event_count": 0,
    "largest_event": {
        "magnitude": None,
        "place": None,
        "time": None,
        "url": None
    },
    "summary": "",
    "raw_saved_path": None,
    "normalized_saved_path": None,
    "error": None
}

KEYWORDS = ("earthquake", "quakes", "seismic", "usgs")

def _ensure_dir(path):
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except Exception:
        return False

def _get_results_dir():
    for d in RESULTS_DIRS:
        if _ensure_dir(d):
            return d
    return None

def run_research(query: str) -> dict:
    result = SCHEMA.copy()
    result["query"] = query
    result["fetched_at"] = datetime.datetime.utcnow().isoformat() + "Z"
    result["source_url"] = USGS_URL
    result["ok"] = False
    result["error"] = None
    result["raw_saved_path"] = None
    result["normalized_saved_path"] = None
    
    if not any(k in query.lower() for k in KEYWORDS):
        result["error"] = "Query does not match supported keywords."
        return result
    
    # Fetch data
    try:
        with urllib.request.urlopen(USGS_URL, timeout=15) as resp:
            raw = resp.read()
            data = json.loads(raw)
    except Exception as e:
        result["error"] = f"Network or JSON error: {e}"
        return result
    
    # Save raw JSON
    results_dir = _get_results_dir()
    ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    raw_path = None
    norm_path = None
    if results_dir:
        try:
            raw_path = os.path.join(results_dir, f"usgs_raw_{ts}.json")
            with open(raw_path, "wb") as f:
                f.write(raw)
            result["raw_saved_path"] = os.path.abspath(raw_path)
        except Exception as e:
            result["error"] = f"Failed to save raw JSON: {e}"
    
    # Normalize
    features = data.get("features", []) if isinstance(data, dict) else []
    result["event_count"] = len(features)
    largest = None
    for f in features:
        try:
            mag = f["properties"].get("mag")
            if mag is not None and (largest is None or mag > largest["magnitude"]):
                largest = {
                    "magnitude": mag,
                    "place": f["properties"].get("place"),
                    "time": datetime.datetime.utcfromtimestamp(f["properties"].get("time",0)/1000).isoformat()+"Z" if f["properties"].get("time") else None,
                    "url": f["properties"].get("url")
                }
        except Exception:
            continue
    result["largest_event"] = largest or {"magnitude": None, "place": None, "time": None, "url": None}
    result["summary"] = (
        f"{result['event_count']} events. "
        + (f"Largest: M{largest['magnitude']} at {largest['place']} on {largest['time']}" if largest and largest["magnitude"] is not None else "No magnitude data.")
    )
    result["ok"] = True if result["event_count"] > 0 else False
    
    # Save normalized JSON
    if results_dir:
        try:
            norm_path = os.path.join(results_dir, f"usgs_normalized_{ts}.json")
            with open(norm_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            result["normalized_saved_path"] = os.path.abspath(norm_path)
        except Exception as e:
            result["error"] = f"Failed to save normalized JSON: {e}"
    return result

if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "earthquake"
    result = run_research(query)
    print(json.dumps(result, ensure_ascii=False, indent=2))
