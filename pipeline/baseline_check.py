import os
import pandas as pd
from datetime import timedelta
from dotenv import load_dotenv

NOTION_VERSION = "2022-06-28"

def notion_query_today_by_type(type_name: str):
    """Return today's page for a given Insight Type (or None)."""
    url = f"https://api.notion.com/v1/databases/{DB_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }
    today = pd.Timestamp.utcnow().strftime("%Y-%m-%d")  # YYYY-MM-DD
    body = {
        "filter": {
            "and": [
                {"property": "Insight Type", "select": {"equals": type_name}},
                {"property": "Date", "date": {"equals": today}},
            ]
        },
        "page_size": 1
    }
    r = requests.post(url, headers=headers, data=json.dumps(body))
    if r.status_code >= 300:
        print(f"⚠️ Notion query error for {type_name}:", r.status_code, r.text)
        return None
    data = r.json()
    return data.get("results", [None])[0]

def notion_update(page_id, properties):
    url = f"https://api.notion.com/v1/pages/{page_id}"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }
    r = requests.patch(url, headers=headers, data=json.dumps({"properties": properties}))
    if r.status_code >= 300:
        print("❌ Notion update error:", r.status_code, r.text)
    else:
        print("✅ Weekly Pulse card updated.")

load_dotenv()

CSV_PATH = os.getenv("HC_INPUT_CSV", "latest_posts.csv")
BASELINE_ER = float(os.getenv("BASELINE_ER_MEDIAN", "0.0"))
BASELINE_IVR = float(os.getenv("BASELINE_IVR_MEDIAN", "0.0"))
FALLBACK_FOLLOWERS = float(os.getenv("HC_FOLLOWERS", "0"))

if not os.path.exists(CSV_PATH):
    raise FileNotFoundError(f"CSV not found: {CSV_PATH}")

df = pd.read_csv(CSV_PATH)

# ---- column picking ----
cols = {c.lower().strip(): c for c in df.columns}
def pick(*cands, required=False):
    for c in cands:
        if c.lower() in cols:
            return cols[c.lower()]
    if required:
        raise ValueError(f"CSV missing required column: {cands}")
    return None

DATE_COL      = pick("date_v4","date_v3","date", required=True)
LIKES_COL     = pick("total_likes_v4","total_likes_v3","likes")
COMMENTS_COL  = pick("total_comments_v4","total_comments_v3","comments")
VIEWS_COL     = pick("total_views_v4","total_views_v3","views")
ER_COL        = pick("er_v4","er_v3","er")
IVR_COL       = pick("ivr_v4","ivr_v3","ivr")
URL_COL       = pick("url","permalink","link")
FOLLOWERS_COL = pick("followers","follower_count")

print("Columns used ->",
      "DATE:", DATE_COL,
      "| LIKES:", LIKES_COL,
      "| COMMENTS:", COMMENTS_COL,
      "| VIEWS:", VIEWS_COL,
      "| FOLLOWERS:", FOLLOWERS_COL,
      "| ER:", ER_COL,
      "| IVR:", IVR_COL,
      "| URL:", URL_COL or "—")

def to_num(x):
    try:
        if isinstance(x,str):
            x=x.replace(",","").replace("%","").strip()
        return float(x)
    except:
        return float("nan")

# ---- parse dates ----
dt_series = pd.to_datetime(df[DATE_COL], utc=True, errors="coerce")
valid = dt_series.notna()
df = df.loc[valid].copy()
dt_series = dt_series.loc[valid]

# ---- compute metrics ----
df["likes"]    = df[LIKES_COL].apply(to_num)    if LIKES_COL else 0.0
df["comments"] = df[COMMENTS_COL].apply(to_num) if COMMENTS_COL else 0.0
if VIEWS_COL: df["views"] = df[VIEWS_COL].apply(to_num)

if FOLLOWERS_COL:
    df["followers"] = df[FOLLOWERS_COL].apply(to_num)
else:
    df["followers"] = FALLBACK_FOLLOWERS

if ER_COL:
    df["ER"] = df[ER_COL].apply(to_num)
else:
    df["ER"] = ((df["likes"]+df["comments"])/df["followers"].replace(0,pd.NA))*100

if IVR_COL:
    df["IVR"] = df[IVR_COL].apply(to_num)
elif "views" in df.columns:
    df["IVR"] = ((df["likes"]+df["comments"])/df["views"].replace(0,pd.NA))*100

# ---- 30-day window ----
cutoff = pd.Timestamp.utcnow().tz_convert("UTC") - pd.Timedelta(days=30)
mask = dt_series >= cutoff
latest = df.loc[mask].copy()
if latest.empty:
    print("No posts in the last 30 days.")
    raise SystemExit(0)

latest["__date"] = dt_series.loc[mask].dt.strftime("%Y-%m-%d")

# ---- medians and deltas ----
# ---- outlier guard (drop extreme ER outliers above 95th percentile) ----
er_p95 = latest["ER"].quantile(0.95)
latest_no_outliers = latest[latest["ER"] <= er_p95].copy()

er_med = float(latest_no_outliers["ER"].median(skipna=True))
ivr_med = float(latest_no_outliers["IVR"].median(skipna=True)) if "IVR" in latest_no_outliers.columns else float("nan")

er_delta = er_med - BASELINE_ER
ivr_delta = ivr_med - BASELINE_IVR if pd.notna(ivr_med) else float("nan")

def fmt(x): return "—" if pd.isna(x) else f"{x:.2f}"

print("\nMAS+ Instagram — Movement vs Baseline (last 30 days)\n")
print(f"Baseline: ER {BASELINE_ER:.2f}% | IVR {BASELINE_IVR:.2f}%")
print(f"Latest 30 d: ER {fmt(er_med)}% | IVR {fmt(ivr_med)}%")
print(f"Δ vs baseline: ER {fmt(er_delta)} pts | IVR {fmt(ivr_delta)} pts\n")

# ---- top/bottom posts ----
latest["ER_uplift_pts"] = latest["ER"] - BASELINE_ER
def show(rows,title):
    print(title)
    for _,r in rows.iterrows():
        print(f" - {r['__date']} | ER {fmt(r['ER'])}% | Δ {fmt(r['ER_uplift_pts'])} pts | {r.get(URL_COL,'')}")
    print()

show(latest.sort_values("ER_uplift_pts",ascending=False).head(3),"Top by ER uplift:")
show(latest.sort_values("ER_uplift_pts",ascending=True).head(3),"Bottom by ER uplift:")

# ---- Notion writer (Weekly Pulse card + Predictive Test) ----
import requests, json

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DB_ID = os.getenv("NOTION_DB_MASPLUS")
NOTION_VERSION = "2022-06-28"

def rt(text):  # rich_text
    return {"rich_text": [{"type": "text", "text": {"content": str(text)[:1900]}}]}

def ttl(text):  # title
    return {"title": [{"type": "text", "text": {"content": str(text)[:200]}}]}

def sel(name):
    return {"select": {"name": name}}

def notion_create(properties):
    if not NOTION_TOKEN or not DB_ID:
        print("⚠️  Missing NOTION_TOKEN or NOTION_DB_MASPLUS in .env — skipping Notion write.")
        return
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }
    payload = {"parent": {"database_id": DB_ID}, "properties": properties}
    r = requests.post(url, headers=headers, data=json.dumps(payload))
    if r.status_code >= 300:
        print("❌ Notion create error:", r.status_code, r.text)
    else:
        print("✅ Notion page created.")

def notion_update(page_id, properties):
    url = f"https://api.notion.com/v1/pages/{page_id}"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }
    r = requests.patch(url, headers=headers, data=json.dumps({"properties": properties}))
    if r.status_code >= 300:
        print("❌ Notion update error:", r.status_code, r.text)
    else:
        print("✅ Notion page updated.")

def notion_query_today_by_type(type_name: str):
    """Return today's page for a given Insight Type (or None)."""
    url = f"https://api.notion.com/v1/databases/{DB_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }
    today = pd.Timestamp.utcnow().strftime("%Y-%m-%d")
    body = {
        "filter": {
            "and": [
                {"property": "Insight Type", "select": {"equals": type_name}},
                {"property": "Date", "date": {"on_or_after": today}},
                {"property": "Date", "date": {"on_or_before": today}},
            ]
        },
        "page_size": 1,
        "sorts": [{"property": "Date", "direction": "descending"}],
    }
    r = requests.post(url, headers=headers, data=json.dumps(body))
    if r.status_code >= 300:
        print(f"⚠️ Notion query error for {type_name}:", r.status_code, r.text)
        return None
    data = r.json()
    return data.get("results", [None])[0]

# -------- Build Weekly Pulse content --------
headline_line = f"ER {fmt(er_delta)} pts vs baseline | IVR {fmt(ivr_delta)} pts"
detail_line   = f"ER {fmt(er_med)}% (base {BASELINE_ER:.2f}%) • IVR {fmt(ivr_med)}% (base {BASELINE_IVR:.2f}%)"

# summary based on movement
if er_delta > 0 and ivr_delta < 0:
    summary = "Broader reach but lower depth — test 12–15s Reels with stronger first-frame hook."
elif er_delta > 0:
    summary = "Positive lift; maintain momentum on current creative focus."
else:
    summary = "Engagement softness; review hook clarity and emotional framing."

# outlier transparency
summary += " (95th-percentile outliers removed for the ER median)."

# top territories (if available)
if "Assigned_Territory_v4" in df.columns:
    tcol = "Assigned_Territory_v4"
    latest_no = latest_no_outliers if "latest_no_outliers" in locals() else latest
    g = latest_no.groupby(tcol)["ER"].median().sort_values(ascending=False).head(3)
    top_terr = "; ".join([f"{k}: {v:.2f}%" for k, v in g.items()])
    summary += f" Top territories (ER median, 30 d): {top_terr}."

pulse_props = {
    "Date": {"date": {"start": pd.Timestamp.utcnow().strftime("%Y-%m-%d")}},
    "Insight Type": sel("Weekly Pulse"),
    "Headline": rt(headline_line),
    "Metric": rt(f"{fmt(er_delta)} pts"),
    "Confidence": sel("High" if abs(er_delta) >= 0.20 else "Medium"),
    "Status": sel("Published"),
    "Action": rt(f"{detail_line}\n{summary}"),
    "Title": ttl("Weekly Pulse"),
}

existing_pulse = notion_query_today_by_type("Weekly Pulse")
if existing_pulse and existing_pulse.get("id"):
    notion_update(existing_pulse["id"], pulse_props)
else:
    notion_create(pulse_props)

# -------- Predictive Test (idempotent) --------
if pd.notna(ivr_delta) and ivr_delta < 0:
    pred_props = {
        "Date": {"date": {"start": pd.Timestamp.utcnow().strftime("%Y-%m-%d")}},
        "Insight Type": sel("Predictive Test"),
        "Headline": rt("Predictive Test — Lift IVR via first-frame hook + 12–15s"),
        "Metric": rt("10–15%"),
        "Confidence": sel("Medium"),
        "Status": sel("Published"),
        "Action": rt(f"IVR {fmt(ivr_med)}% vs base {BASELINE_IVR:.2f}%. Test: macro first frame, motion in 0.5s, question opener; 12–15s."),
        "Title": ttl("Predictive Test"),
    }
    existing_pred = notion_query_today_by_type("Predictive Test")
    if existing_pred and existing_pred.get("id"):
        notion_update(existing_pred["id"], pred_props)
    else:
        notion_create(pred_props)
