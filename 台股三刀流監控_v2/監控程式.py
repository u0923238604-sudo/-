# -*- coding: utf-8 -*-
"""
台股加權指數 60分K「三刀流 (MA20/MA60/MA240) + MACD」監控程式

四個條件（每根 60分K 收完後判斷一次）：
  1. 跌破三刀流：收盤價 < MA20、MA60、MA240
  2. 站上三刀流：收盤價 > MA20、MA60、MA240
  3. MACD 柱縮短 1/4：|本根柱| <= |前一根柱| x (1 - 縮短比例)
  4. MACD 柱翻色：綠轉紅 或 紅轉綠（台股習慣：正值=紅、負值=綠）
兩段式通知（沒成立就不打擾）：
  成立 >= 強烈警示門檻（預設 3）→ 紅色強烈警示：桌面跳出視窗（按確定才關）＋提示音＋手機最高優先
  成立 >= 一般提醒門檻（預設 2）→ 黃色一般提醒：桌面右下角通知＋手機一般優先

用法：
  python 監控程式.py            盤中自動監控（一鍵啟動.bat 就是執行這行）
  python 監控程式.py --回測     用過去約一年的 60分K 找出歷史觸發點，輸出 CSV
  python 監控程式.py --測試通知  發一則測試通知到桌面與手機
"""
import configparser, csv, os, re, secrets, sys, time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

TW = timezone(timedelta(hours=8))
BASE = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(BASE, "設定.ini")
LOG_PATH = os.path.join(BASE, "警示紀錄.csv")
NAMES = ["跌破三刀流", "站上三刀流", "MACD柱縮短1/4", "MACD柱翻色"]


# ---------------- 設定 ----------------
def load_cfg():
    c = configparser.ConfigParser(inline_comment_prefixes=(";",))
    c.read(CFG_PATH, encoding="utf-8-sig")   # 相容記事本存檔的 BOM
    m, d, p = c["監控"], c["桌面通知"], c["手機通知"]
    yes = lambda v: str(v).strip() in ("是", "1", "true", "True", "yes")
    nums = lambda v: [int(x) for x in v.split(",")]
    cfg = dict(
        symbol=m.get("標的", "^TWII").strip(), name=m.get("標的名稱", "加權指數").strip(),
        ma=nums(m.get("均線", "20,60,240")), ma_all=m.get("均線判斷", "全部").strip() != "任一",
        macd=nums(m.get("MACD", "12,26,9")), shrink=float(m.get("縮短比例", "0.25")),
        strong=int(m.get("強烈警示門檻", "3")), normal=int(m.get("一般提醒門檻", "2")),
        every=max(1, int(m.get("檢查間隔分鐘", "3"))),
        desk=yes(d.get("啟用", "是")), beep=yes(d.get("提示音", "是")),
        mode=p.get("方式", "ntfy").strip().lower(), topic=p.get("ntfy頻道", "").strip(),
        server=p.get("ntfy伺服器", "https://ntfy.sh").strip().rstrip("/"),
        tg_token=p.get("telegram_token", "").strip(), tg_chat=p.get("telegram_chat_id", "").strip(),
    )
    if cfg["mode"] == "ntfy" and not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", cfg["topic"]):
        cfg["topic"] = "twii-" + secrets.token_hex(6)       # 自動產生頻道並寫回設定檔
        txt = open(CFG_PATH, encoding="utf-8-sig").read()
        txt = re.sub(r"(?m)^ntfy頻道\s*=.*$", "ntfy頻道 = " + cfg["topic"], txt)
        open(CFG_PATH, "w", encoding="utf-8").write(txt)
        print(f"★ 已自動產生 ntfy 頻道：{cfg['topic']}（請在手機 ntfy App 訂閱這個名稱）")
    return cfg


# ---------------- 資料 ----------------
def fetch_60m(symbol, rng="6mo"):
    """向 Yahoo Finance 取 60分K，回傳台灣時間索引的 DataFrame（只含已收完的 K 棒）"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(symbol)}"
    r = requests.get(url, params={"interval": "60m", "range": rng},
                     headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    df = pd.DataFrame({k: q[k] for k in ("open", "high", "low", "close")},
                      index=pd.to_datetime(res["timestamp"], unit="s", utc=True).tz_convert("Asia/Taipei"))
    df = df.dropna(subset=["close"])
    # 只留 09:00~13:00 整點開始的 60分K（排除 Yahoo 偶爾附帶的非整點即時報價）
    df = df[(df.index.minute == 0) & (df.index.hour >= 9) & (df.index.hour <= 13)]
    df = df[~df.index.duplicated(keep="last")]
    return df[[bar_done(t) for t in df.index]]


def bar_done(t, now=None):
    """K 棒是否已收完：結束時間 = 開始+60分，最後一根到 13:30 為止"""
    now = now or datetime.now(TW)
    end = min(t + timedelta(hours=1), t.replace(hour=13, minute=30, second=0))
    return now >= end + timedelta(minutes=1)


# ---------------- 指標與條件 ----------------
def evaluate(df, cfg):
    """回傳加上指標與四個條件欄位的 DataFrame"""
    c = df["close"]
    out = df.copy()
    for n in cfg["ma"]:
        out[f"MA{n}"] = c.rolling(n).mean()
    f, s, sig = cfg["macd"]
    dif = c.ewm(span=f, adjust=False).mean() - c.ewm(span=s, adjust=False).mean()
    out["DIF"], out["DEA"] = dif, dif.ewm(span=sig, adjust=False).mean()
    out["柱"] = h = out["DIF"] - out["DEA"]
    mas = out[[f"MA{n}" for n in cfg["ma"]]]
    lo, hi = mas.min(axis=1), mas.max(axis=1)
    ok = mas.notna().all(axis=1)                       # MA240 需滿 240 根才開始判斷
    hp = h.shift(1)
    # 全部：低於最低那條才算跌破、高於最高那條才算站上；任一：碰到一條就算
    out[NAMES[0]] = ok & (c < (lo if cfg["ma_all"] else hi))
    out[NAMES[1]] = ok & (c > (hi if cfg["ma_all"] else lo))
    out[NAMES[2]] = (hp.abs() > 0) & (h.abs() <= hp.abs() * (1 - cfg["shrink"]))
    out[NAMES[3]] = (h * hp) < 0
    out["成立數"] = out[NAMES].sum(axis=1)
    return out


def color(v):
    return "紅" if v > 0 else "綠" if v < 0 else "平"


def describe(row, cfg, t):
    hit = [n for n in NAMES if row[n]]
    ma = "  ".join(f"MA{n}={row[f'MA{n}']:.0f}" for n in cfg["ma"])
    return (f"{cfg['name']} {t:%m/%d %H:%M} 60分K 收 {row['close']:.2f}\n{ma}\n"
            f"MACD柱 {row['柱']:+.2f}（{color(row['柱'])}）\n"
            f"成立 {len(hit)}/4：{'、'.join(hit) if hit else '無'}")


# ---------------- 通知 ----------------
def notify(cfg, title, msg, urgent=True):
    if cfg["desk"]:
        desktop(title, msg, cfg["beep"], sticky=urgent)
    try:
        if cfg["mode"] == "ntfy":
            requests.post(cfg["server"], json={"topic": cfg["topic"], "title": title, "message": msg,
                                               "priority": 5 if urgent else 3,
                                               "tags": ["rotating_light" if urgent else "chart_with_upwards_trend"]},
                          timeout=15).raise_for_status()
        elif cfg["mode"] == "telegram" and cfg["tg_token"]:
            requests.post(f"https://api.telegram.org/bot{cfg['tg_token']}/sendMessage",
                          data={"chat_id": cfg["tg_chat"], "text": f"{title}\n{msg}"}, timeout=15).raise_for_status()
    except Exception as e:
        print(f"[手機通知失敗] {e}")


def desktop(title, msg, beep, sticky=False):
    """右下角通知；sticky=True（強烈警示）時另外跳出置頂視窗，按確定才會關"""
    if beep and os.name == "nt":
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONHAND if sticky else winsound.MB_ICONASTERISK)
        except Exception:
            pass
    toast = False
    try:
        from plyer import notification
        notification.notify(title=title, message=msg[:250], app_name="三刀流監控", timeout=20)
        toast = True
    except Exception:
        pass
    if os.name == "nt" and (sticky or not toast):       # 置頂視窗（另開執行緒，不會卡住監控）
        import ctypes, threading
        icon = 0x30 if sticky else 0x40                   # 驚嘆號 / 資訊
        threading.Thread(target=ctypes.windll.user32.MessageBoxW,
                         args=(0, msg, title, icon | 0x40000 | 0x1000), daemon=True).start()
    elif not toast:
        print(f"[桌面通知] {title}\n{msg}")


def write_log(t, row, level):
    new = not os.path.exists(LOG_PATH)
    with open(LOG_PATH, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["K棒時間", "收盤", "MACD柱", "柱色"] + NAMES + ["成立數", "通知等級"])
        w.writerow([f"{t:%Y-%m-%d %H:%M}", f"{row['close']:.2f}", f"{row['柱']:.2f}", color(row["柱"])]
                   + ["V" if row[n] else "" for n in NAMES] + [int(row["成立數"]), level])


# ---------------- 主流程 ----------------
def alert_level(hit, cfg):
    if hit >= cfg["strong"]:
        return "強烈警示"
    if cfg["normal"] and hit >= cfg["normal"]:
        return "一般提醒"
    return ""


def in_session(now):
    return now.weekday() < 5 and (8, 55) <= (now.hour, now.minute) <= (13, 45)


def run():
    cfg = load_cfg()
    print(f"=== {cfg['name']} 60分K 三刀流監控啟動（強烈警示 {cfg['strong']}/4、一般提醒 "
          f"{cfg['normal'] or '關閉'}{'/4' if cfg['normal'] else ''}，均線判斷：{'全部' if cfg['ma_all'] else '任一'}）===")
    print(f"手機通知：{cfg['mode']} {cfg['topic'] if cfg['mode'] == 'ntfy' else ''}　關閉請按 Ctrl+C 或直接關視窗\n")
    last = None
    while True:
        now = datetime.now(TW)
        try:
            if in_session(now) or last is None:
                df = evaluate(fetch_60m(cfg["symbol"]), cfg)
                t = df.index[-1]
                if last is None or t > last:
                    row = df.iloc[-1]
                    hit = int(row["成立數"])
                    info = describe(row, cfg, t)
                    print(f"[{now:%H:%M:%S}] {info}\n")
                    if last is not None:                     # 啟動當下只顯示，不重複通知舊 K 棒
                        level = alert_level(hit, cfg)
                        if level == "強烈警示":
                            notify(cfg, f"🔴 強烈警示｜{cfg['name']}（{hit}/4 成立）", info, urgent=True)
                        elif level == "一般提醒":
                            notify(cfg, f"🟡 一般提醒｜{cfg['name']}（{hit}/4 成立）", info, urgent=False)
                        write_log(t, row, level)
                    last = t
        except Exception as e:
            print(f"[{now:%H:%M:%S}] 取資料失敗，稍後重試：{e}")
        time.sleep(cfg["every"] * 60 if in_session(datetime.now(TW)) else 300)


def backtest():
    cfg = load_cfg()
    df = evaluate(fetch_60m(cfg["symbol"], "1y"), cfg).dropna(subset=[f"MA{max(cfg['ma'])}"])
    path = os.path.join(BASE, f"回測結果_{datetime.now(TW):%Y%m%d_%H%M}.csv")
    keep = ["close"] + [f"MA{n}" for n in cfg["ma"]] + ["DIF", "DEA", "柱"] + NAMES + ["成立數"]
    out = df[keep].round(2)
    out.index = out.index.strftime("%Y-%m-%d %H:%M")
    print(f"回測區間：{out.index[0]} ~ {out.index[-1]}，共 {len(out)} 根 60分K")
    for n in NAMES:
        print(f"  {n}：{int(df[n].sum())} 次")
    for k in range(4, 0, -1):
        print(f"  成立 {k} 個以上：{int((df['成立數'] >= k).sum())} 次")
    out["通知等級"] = [alert_level(int(h), cfg) for h in df["成立數"]]
    out.to_csv(path, encoding="utf-8-sig", index_label="K棒時間")
    days = df.index.normalize().nunique()
    for lv in ("強烈警示", "一般提醒"):
        n = int((out["通知等級"] == lv).sum())
        print(f"\n【{lv}】共 {n} 次，平均每個交易日 {n / days:.2f} 次")
        if lv == "強烈警示":
            for t, r in df[out["通知等級"].values == lv].iterrows():
                print(f"  {t:%Y-%m-%d %H:%M}  收 {r['close']:.0f}  " + "、".join(x for x in NAMES if r[x]))
    print(f"\n完整明細已存到：{path}")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "--回測":
        backtest()
    elif arg == "--測試通知":
        c = load_cfg()
        notify(c, "✅ 三刀流監控 測試通知", f"看到這則訊息代表通知設定成功！\n{datetime.now(TW):%Y-%m-%d %H:%M:%S}")
        print("已送出測試通知，請確認桌面與手機都有收到。")
    else:
        try:
            run()
        except KeyboardInterrupt:
            print("\n已停止監控。")
