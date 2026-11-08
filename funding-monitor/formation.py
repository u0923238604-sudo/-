#!/usr/bin/env python3
"""由 us_daily.json（日收盤）算 5/20/60 日均線陣型，寫入 formation.json。
綠：收盤 > MA5 > MA20 > MA60（多頭排列）；紅：收盤 < MA20（跌破月線）；其餘為黃。"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
src = json.load(open(os.path.join(HERE, "us_daily.json")))
out = {"fetched": src.get("fetched")}
for sym in ("SOXX.US", ".IXIC.US"):
    bars = src.get(sym) or []
    cs = [b["c"] for b in bars]
    if len(cs) < 60:
        out[sym] = None
        continue
    ma = lambda n: sum(cs[-n:]) / n
    c, m5, m20, m60 = cs[-1], ma(5), ma(20), ma(60)
    state = "green" if c > m5 > m20 > m60 else ("red" if c < m20 else "yellow")
    out[sym] = {"date": bars[-1]["d"], "close": c, "ma5": m5, "ma20": m20, "ma60": m60, "state": state}
json.dump(out, open(os.path.join(HERE, "formation.json"), "w"), ensure_ascii=False)
for k in ("SOXX.US", ".IXIC.US"):
    v = out[k]
    print(k, "資料不足" if v is None else f"{v['date']} 收{v['close']:.2f} MA5 {v['ma5']:.2f} MA20 {v['ma20']:.2f} MA60 {v['ma60']:.2f} → {v['state']}")
