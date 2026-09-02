import json, os, re, sys, time
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options

MAX_PRICE = 3300
MIN_REALISTIC_PRICE = 2500
NTFY_TOPIC = os.environ["NTFY_TOPIC"]
STATE_FILE = Path("state.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/152.0 Safari/537.36",
    "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
}

TARGETS = [
    {"id":"biccamera","name":"ビックカメラ","url":"https://www.biccamera.com/bc/item/11344352/","focus":"BX-09","price_patterns":[r"([0-9,]+)円"],"out":["販売休止中","販売を終了しました","在庫なし","予定数終了"],"in":["カートに入れる","在庫あり"]},
    {"id":"takaratomy","name":"タカラトミーモール","url":"https://takaratomymall.jp/shop/goods/search.aspx?search=true&keyword=BX-09","focus":"BX-09","price_patterns":[r"販売価格\s*[:：]?\s*([0-9,]+)円",r"([0-9,]+)円"],"out":["在庫なし","入荷案内申込","品切れ","販売終了"],"in":["在庫あり","カートに入れる","残りわずか"]},
    {"id":"amazon","name":"Amazon","url":"https://www.amazon.co.jp/s?k=4904810905240","focus":"ベイバトルパス","price_patterns":[r"￥\s*([0-9,]+)",r"([0-9,]+)円"],"out":["現在在庫切れです","一時的に在庫切れ","在庫切れ"],"in":["カートに入れる","在庫あり"],"note":"販売元・発送元がAmazon.co.jpか、送料を含め3,300円以下か購入前に確認してください。"},
    {"id":"joshin","name":"Joshin web","url":"https://joshinweb.jp/toy/67304/4904810905240.html","focus":"ベイバトルパス","price_patterns":[r"([0-9,]+)円",r"￥\s*([0-9,]+)"],"out":["完売いたしました","売り切れ","在庫なし","販売終了"],"in":["カートに入れる","在庫あり","お取り寄せ"]},
    {"id":"edion","name":"エディオン","url":"https://www.edion.com/detail.html?p_cd=00075806569","focus":"ベイバトルパス","price_patterns":[r"￥\s*([0-9,]+)",r"([0-9,]+)円"],"out":["選択された商品は、存在しません","売り切れ","在庫なし","販売終了"],"in":["カートに入れる","在庫あり","出荷目安"]},
    {"id":"toysrus","name":"トイザらス","url":"https://www.toysrus.co.jp/ja-jp/7652429-765242900.html","focus":"BX-09","price_patterns":[r"¥\s*([0-9,]+)",r"￥\s*([0-9,]+)",r"([0-9,]+)円"],"out":["在庫なし","Out of Stock","売り切れ"],"in":["カートに入れる","在庫あり","Add to Cart"]},
    {"id":"yamada","name":"ヤマダウェブコム","url":"https://www.yamada-denkiweb.com/6885552016/?q=BEYBLADE","focus":"BX－09","price_patterns":[r"¥\s*([0-9,]+)",r"￥\s*([0-9,]+)",r"([0-9,]+)円"],"out":["好評につき売り切れました","売り切れました","売り切れ","在庫なし"],"in":["カートに入れる","在庫あり","お取り寄せ"]},
    {"id":"yodobashi","name":"ヨドバシ.com","url":"https://www.yodobashi.com/?word=4904810905240","focus":"ベイバトルパス","price_patterns":[r"￥\s*([0-9,]+)",r"([0-9,]+)円"],"out":["販売終了","予定数の販売を終了","在庫なし"],"in":["カートに入れる","在庫あり","在庫残少"]},
    {"id":"rakuten","name":"楽天市場","url":"https://search.rakuten.co.jp/search/mall/4904810905240/","focus":"ベイバトルパス","price_patterns":[r"([0-9,]+)円"],"out":["検索結果がありません"],"in":["発送","お届け","在庫あり","買い物かご","翌日配送"],"strict_price_floor":2500,"note":"ショップ・送料・新品かどうかを購入前に確認してください。"},
    {"id":"shimamura","name":"しまむらオンラインストア","url":"https://www.shop-shimamura.com/?b=shimamura&keyword=4904810905240","focus":"ベイバトルパス","price_patterns":[r"￥\s*([0-9,]+)",r"([0-9,]+)円"],"out":["在庫なし","売り切れ","販売終了","商品が見つかりません"],"in":["カートに入れる","在庫あり","店舗受取"]},
]

def html_to_text(html):
    return " ".join(BeautifulSoup(html, "html.parser").stripped_strings)

def fetch_requests(url):
    r = requests.get(url, headers=HEADERS, timeout=10)
    r.raise_for_status()
    if not r.encoding or r.encoding.lower() == "iso-8859-1":
        r.encoding = r.apparent_encoding
    return html_to_text(r.text), "requests"

def make_driver():
    o=Options()
    for a in ["--headless=new","--no-sandbox","--disable-dev-shm-usage","--window-size=1440,2000","--lang=ja-JP"]:
        o.add_argument(a)
    o.add_argument(f"--user-agent={HEADERS['User-Agent']}")
    o.page_load_strategy="eager"
    d=webdriver.Chrome(options=o); d.set_page_load_timeout(18)
    return d

def fetch_browser(driver,url):
    try: driver.get(url)
    except TimeoutException: pass
    time.sleep(2)
    return html_to_text(driver.page_source),"chrome"

def focus_text(text,keyword=None,radius=1200):
    for key in [keyword or "","4904810905240","BX-09","BX－09","ベイバトルパス"]:
        if key:
            i=text.find(key)
            if i!=-1: return text[max(0,i-radius):i+radius]
    return text[:3000]

def extract_price(text,patterns, floor=500):
    prices=[]
    for p in patterns:
        for m in re.finditer(p,text,re.S|re.I):
            try:
                v=int(m.group(1).replace(",",""))
                if floor <= v <= 30000: prices.append(v)
            except: pass
    return min(prices) if prices else None

def judge_stock(area,target):
    lo=area.lower()
    if any(w.lower() in lo for w in target["out"]): return False
    if any(w.lower() in lo for w in target["in"]): return True
    return None

def inspect_target(target,driver):
    errors=[]
    try: text,method=fetch_requests(target["url"])
    except Exception as e:
        errors.append(f"requests={type(e).__name__}: {e}")
        try:
            if driver is None: driver=make_driver()
            text,method=fetch_browser(driver,target["url"])
        except Exception as e2:
            return {"status":"unknown","price":None,"stock":None,"method":"failed","error":str(e2)},driver

    area=focus_text(text,target.get("focus"))
    floor=target.get("strict_price_floor",500)
    price=extract_price(area,target["price_patterns"],floor=floor)
    stock=judge_stock(area,target)

    if (price is None or stock is None) and method=="requests":
        try:
            if driver is None: driver=make_driver()
            bt,_=fetch_browser(driver,target["url"])
            ba=focus_text(bt,target.get("focus"))
            bp=extract_price(ba,target["price_patterns"],floor=floor)
            bs=judge_stock(ba,target)
            if bp is not None: price=bp
            if bs is not None: stock=bs
            method="chrome"
        except Exception as e: errors.append(str(e))

    if stock is None or price is None: status="unknown"
    elif stock is True and price <= MAX_PRICE: status="hit"
    else: status="not_target"
    return {"status":status,"price":price,"stock":stock,"method":method,"error":" | ".join(errors) if errors else None},driver

def load_state():
    if not STATE_FILE.exists(): return {}
    try: return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except: return {}

def save_state(s):
    STATE_FILE.write_text(json.dumps(s,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")

def notify(title,message,click_url):
    r=requests.post("https://ntfy.sh/",json={"topic":NTFY_TOPIC,"title":title,"message":message,"priority":4,"tags":["tada","shopping_cart"],"click":click_url},timeout=20)
    r.raise_for_status()

def main():
    previous=load_state(); new_state=dict(previous); driver=None
    try:
        for target in TARGETS:
            result,driver=inspect_target(target,driver)
            old=previous.get(target["id"],{}).get("status")
            print(f'{target["name"]}: status={result["status"]}, price={result["price"]}, stock={result["stock"]}, method={result["method"]}')
            if result["status"]=="unknown": continue
            new_state[target["id"]]={"status":result["status"],"price":result["price"]}
            if result["status"]=="hit" and old!="hit":
                body=f'{target["name"]}でBX-09 ベイバトルパスを税込{result["price"]:,}円で在庫ありと検知しました。'
                if target.get("note"): body+=" "+target["note"]
                notify("ベイバトルパス在庫あり！",body,target["url"])
                print(f'  NOTIFIED: {target["name"]}')
    finally:
        if driver:
            try: driver.quit()
            except: pass
    save_state(new_state)

if __name__=="__main__":
    main()
