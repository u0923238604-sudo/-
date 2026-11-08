#!/usr/bin/env python3
"""把 last_run.json 追加到 history.json（看板用），並判斷翻紅項目是否有變化（推播用）。"""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
H, L = os.path.join(HERE, "history.json"), os.path.join(HERE, "last_run.json")
NAMES = {"c1": "費率為正", "c2": "OI 無驟減 15%", "c3": "SOXS 連續 2 期為正", "c4": "陣型（費半）跌破月線"}
run = json.load(open(L))
try:
    rows = json.load(open(H))
except Exception:
    rows = []
prev = rows[-1] if rows else None
row = {"ts": run["ts"], "funding": run["funding"], "funding_ann": run["funding_ann"],
       "r1": None, "r2": None, "r3": None, "oi": run["oi"], "oi_chg": run["oi_chg"],
       "markPx": run["markPx"], "premium": run["premium"],
       "soxlx": run["soxlx"], "soxlx_ann": run["soxlx_ann"],
       "soxsx": run["soxsx"], "soxsx_ann": run["soxsx_ann"], "soxsx_prev": run.get("soxsx_prev"),
       "c1": run["c1"], "c2": run["c2"], "c3": run["c3"], "c4": run.get("c4"), "f_soxx": run.get("f_soxx"), "f_ixic": run.get("f_ixic"), "red": run["red"]}
rec = run.get("recent") or []
for i, v in enumerate(rec[-3:]):
    row[f"r{i+1}"] = v
if not (prev and prev["ts"] == row["ts"]):
    rows.append(row)
rows = rows[-720:]
json.dump(rows, open(H, "w"), ensure_ascii=False)
red_now = sorted(k for k in NAMES if row[k] is False)
red_prev = sorted(k for k in NAMES if prev and prev.get(k) is False)
changed = red_now != red_prev
print(f"PUSH={int(changed and bool(red_now))} RECOVERED={int(changed and not red_now)}")
print("RED_ITEMS=" + "、".join(NAMES[k] for k in red_now))
print(f"ROWS={len(rows)}")
