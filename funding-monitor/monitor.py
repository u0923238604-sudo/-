#!/usr/bin/env python3
"""xyz:SOXL 資金費率監控：抓取 → 年化 → 與 state.json 比較 → 輸出 Markdown 報表。"""
import json, time, os, urllib.request
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "state.json")
TPE = timezone(timedelta(hours=8))
HL = "https://api.hyperliquid.xyz/info"
PX = "https://api.pionex.com/api/v1/market/fundingRates?symbol={}&limit=2"
COIN = "xyz:SOXL"


def req(url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "User-Agent": "funding-monitor/1.0"})
    with urllib.request.urlopen(r, timeout=20) as f:
        return json.load(f)


def safe(fn):
    try:
        return fn()
    except Exception:
        return None


def hl_ctx():
    meta, ctxs = req(HL, {"type": "metaAndAssetCtxs", "dex": "xyz"})
    i = [u["name"] for u in meta["universe"]].index(COIN)
    c = ctxs[i]
    return {k: float(c[k]) for k in ("funding", "premium", "openInterest", "markPx")}


def hl_hist():
    start = int(time.time() * 1000) - 3 * 3600 * 1000
    h = req(HL, {"type": "fundingHistory", "coin": COIN, "startTime": start})
    return [{"time": x["time"], "rate": float(x["fundingRate"])} for x in h[-3:]] or None


def px(sym):
    r = req(PX.format(sym))["data"]["rates"]
    return {"rate": float(r[0]["fundingRate"]), "time": r[0]["fundingTime"],
            "prev": float(r[1]["fundingRate"]) if len(r) > 1 else None}


def pct(x, d=4):
    return "取不到" if x is None else f"{x*100:.{d}f}%"


def main():
    now = datetime.now(TPE)
    ctx, hist = safe(hl_ctx), safe(hl_hist)
    soxl, soxs = safe(lambda: px("SOXLX_USDT_PERP")), safe(lambda: px("SOXSX_USDT_PERP"))
    prev = safe(lambda: json.load(open(STATE))) or {}

    cur = {
        "ts": now.isoformat(timespec="minutes"),
        "funding": ctx and ctx["funding"],
        "funding_ann": ctx and ctx["funding"] * 24 * 365,
        "recent": hist and [h["rate"] for h in hist],
        "oi": ctx and ctx["openInterest"],
        "markPx": ctx and ctx["markPx"],
        "premium": ctx and ctx["premium"],
        "soxlx": soxl and soxl["rate"],
        "soxlx_ann": soxl and soxl["rate"] * 3 * 365,
        "soxsx": soxs and soxs["rate"],
        "soxsx_ann": soxs and soxs["rate"] * 3 * 365,
        "soxsx_prev": soxs and soxs["prev"],
    }
    oi_chg = (cur["oi"] / prev["oi"] - 1) if cur["oi"] is not None and prev.get("oi") else None
    cur["oi_chg"] = oi_chg

    def p(k, f):
        v = prev.get(k)
        return "無紀錄" if v is None else f(v)

    rec = lambda r: "取不到" if r is None else " / ".join(pct(x) for x in r)
    oi_fmt = lambda v: "取不到" if v is None else f"{v:,.2f}"
    rows = [
        ("預估費率 (1h / 年化)",
         "取不到" if cur["funding"] is None else f"{pct(cur['funding'])} / {pct(cur['funding_ann'],2)}",
         p("funding", lambda v: f"{pct(v)} / {pct(v*24*365,2)}")),
        ("最近 3 筆實收 (舊→新)", rec(cur["recent"]), p("recent", rec)),
        ("OI (變化)",
         "取不到" if cur["oi"] is None else oi_fmt(cur["oi"]) + ("" if oi_chg is None else f" ({oi_chg*100:+.2f}%)"),
         p("oi", oi_fmt)),
        ("標記價 markPx", oi_fmt(cur["markPx"]), p("markPx", oi_fmt)),
        ("溢價 premium", pct(cur["premium"]), p("premium", pct)),
        ("Pionex SOXLX (8h / 年化)",
         "取不到" if cur["soxlx"] is None else f"{pct(cur['soxlx'])} / {pct(cur['soxlx_ann'],2)}",
         p("soxlx", lambda v: f"{pct(v)} / {pct(v*3*365,2)}")),
        ("Pionex SOXSX (8h / 年化)",
         "取不到" if cur["soxsx"] is None else f"{pct(cur['soxsx'])} / {pct(cur['soxsx_ann'],2)}",
         p("soxsx", lambda v: f"{pct(v)} / {pct(v*3*365,2)}")),
        ("Pionex SOXSX 前一期 (8h)", pct(cur["soxsx_prev"]), p("soxsx_prev", pct)),
    ]

    def chk(ok):  # None = 取不到
        return "⚪ 取不到" if ok is None else ("🟢" if ok else "🔴")

    c1 = None if cur["funding"] is None else cur["funding"] > 0
    c2 = None if cur["oi"] is None else (True if oi_chg is None else oi_chg > -0.15)
    # 連續 2 期為正才算紅
    c3 = None if cur["soxsx"] is None or cur["soxsx_prev"] is None else not (cur["soxsx"] > 0 and cur["soxsx_prev"] > 0)
    fm = safe(lambda: json.load(open(os.path.join(HERE, "formation.json")))) or {}
    fs, fi = fm.get("SOXX.US"), fm.get(".IXIC.US")
    c4 = None if not fs else fs["state"] != "red"
    zh = {"green": "多頭排列", "yellow": "整理", "red": "跌破月線"}
    checks = [("費率為正", c1), ("OI 無驟減 15%", c2), ("SOXS 費率非連續 2 期為正", c3), ("陣型（費半 SOXX）", c4)]
    red = any(v is False for _, v in checks)
    unknown = any(v is None for _, v in checks)

    out = [f"**xyz:SOXL 資金費率監控｜{now:%Y-%m-%d %H:%M} 台北**",
           f"(上次：{prev.get('ts','無紀錄')})", "",
           "| 項目 | 本次 | 上次 |", "|---|---|---|"]
    out += [f"| {a} | {b} | {c} |" for a, b, c in rows]
    out += ["", "| 檢查項目 | 狀態 |", "|---|---|"]
    out += [f"| {'**'+n+'**' if v is False else n} | {'**🔴**' if v is False else chk(v)} |" for n, v in checks]
    fd = lambda f: "取不到" if not f else f"{zh[f['state']]}（{f['date']} 收 {f['close']:,.2f}／MA5 {f['ma5']:,.2f}／MA20 {f['ma20']:,.2f}／MA60 {f['ma60']:,.2f}）"
    out += ["", f"陣型・費半 SOXX：{fd(fs)}", f"陣型・那斯達克：{fd(fi)}", ""]
    if red:
        out.append("**⚠️ 檢查表翻紅 → 減 1/3**")
    elif unknown:
        out.append("部分資料取不到，無法判定全綠。")
    else:
        out.append("四格全綠 → **續抱**")
    if prev.get("oi") is None:
        out.append("_首次執行或無上次 OI，變化率無法計算。_")

    h = now.hour + now.minute / 60
    us = h >= 22.5 or h < 5
    print(f"<!-- US_SESSION={int(us)} RED={int(red)} -->")
    print("\n".join(out))

    run = dict(cur, c1=c1, c2=c2, c3=c3, c4=c4, red=red,
               f_soxx=fs and fs["state"], f_ixic=fi and fi["state"])
    json.dump(run, open(os.path.join(HERE, "last_run.json"), "w"), ensure_ascii=False)

    # 只用實際取到的值更新 state，取不到的欄位保留上次值供下次比較，但報表本次一律寫「取不到」
    new = dict(prev)
    new.update({k: v for k, v in cur.items() if v is not None})
    new["ts"] = cur["ts"]
    json.dump(new, open(STATE, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
