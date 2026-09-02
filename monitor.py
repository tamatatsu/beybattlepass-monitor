import os
import re
import sys
import requests
from bs4 import BeautifulSoup

MAX_PRICE = 3300
NTFY_TOPIC = os.environ["NTFY_TOPIC"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/152.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

# JAN: 4904810905240
# 価格は税込3,300円以下を通知対象にする
TARGETS = [
    {
        "name": "ビックカメラ",
        "url": "https://www.biccamera.com/bc/item/11344352/",
        "focus": "ベイバトルパス",
        "price_patterns": [r"([0-9,]+)円"],
        "out": ["販売休止中", "販売を終了しました", "在庫なし"],
        "in": ["カートに入れる", "在庫あり"],
    },
    {
        "name": "タカラトミーモール",
        "url": "https://takaratomymall.jp/shop/goods/search.aspx?search=true&keyword=BX-09",
        "focus": "BX-09",
        "price_patterns": [r"販売価格\s*[:：]?\s*([0-9,]+)円", r"([0-9,]+)円"],
        "out": ["在庫なし", "入荷案内申込", "品切れ"],
        "in": ["在庫あり", "カートに入れる", "残りわずか"],
    },
    {
        "name": "Amazon",
        "url": "https://www.amazon.co.jp/s?k=4904810905240",
        "focus": "BX-09",
        "price_patterns": [r"￥\s*([0-9,]+)", r"([0-9,]+)円"],
        "out": ["現在在庫切れです", "一時的に在庫切れ", "在庫切れ"],
        "in": ["カートに入れる", "在庫あり", "通常"],
        # Amazon検索結果はマーケットプレイスが混ざるので通知文で販売元確認を促す
        "note": "Amazonは通知後に販売元・発送元がAmazon.co.jpか確認してください。",
    },
    {
        "name": "Joshin web",
        "url": "https://joshinweb.jp/toy/67304/4904810905240.html",
        "focus": "ベイバトルパス",
        "price_patterns": [r"([0-9,]+)円", r"￥\s*([0-9,]+)"],
        "out": ["完売いたしました", "売り切れ", "在庫なし"],
        "in": ["カートに入れる", "在庫あり", "お取り寄せ"],
    },
    {
        "name": "エディオン",
        "url": "https://www.edion.com/item_list.html?c_cd=001039022001",
        "focus": "BX-09 ベイバトルパス",
        "price_patterns": [r"￥\s*([0-9,]+)\s*\(税込\)", r"￥\s*([0-9,]+)"],
        "out": ["売り切れ", "在庫なし"],
        "in": ["在庫数", "カートに入れる", "最短翌日出荷"],
    },
    {
        "name": "トイザらス",
        "url": "https://www.toysrus.co.jp/ja-jp/7652429-765242900.html",
        "focus": "BX-09 ベイバトルパス",
        "price_patterns": [r"¥\s*([0-9,]+)", r"￥\s*([0-9,]+)"],
        "out": ["在庫なし", "Out of Stock"],
        "in": ["カートに入れる", "在庫あり", "Add to Cart"],
    },
    {
        "name": "ヤマダウェブコム",
        "url": "https://www.yamada-denkiweb.com/6885552016/",
        "focus": "BX－09 ベイバトルパス",
        "price_patterns": [r"¥\s*([0-9,]+)", r"￥\s*([0-9,]+)"],
        "out": ["好評につき売り切れました", "売り切れ", "在庫なし"],
        "in": ["カートに入れる", "在庫あり", "お取り寄せ"],
    },
    {
        "name": "ヨドバシ.com",
        "url": "https://www.yodobashi.com/?word=4904810905240",
        "focus": "ベイバトルパス",
        "price_patterns": [r"￥\s*([0-9,]+)", r"([0-9,]+)円"],
        "out": ["販売終了", "予定数の販売を終了", "在庫なし"],
        "in": ["カートに入れる", "在庫あり", "在庫残少"],
    },
    {
        "name": "楽天市場",
        "url": "https://search.rakuten.co.jp/search/mall/4904810905240/",
        "focus": "ベイバトルパス",
        "price_patterns": [r"([0-9,]+)円"],
        "out": ["売り切れ", "在庫なし", "入荷待ち"],
        "in": ["在庫あり", "発送予定", "お届け", "買い物かご"],
        "note": "楽天はショップごとに送料・販売者が異なるため、通知後に商品ページで最終確認してください。",
    },
    {
        "name": "しまむらオンラインストア",
        "url": "https://www.shop-shimamura.com/?b=shimamura&keyword=4904810905240",
        "focus": "ベイバトルパス",
        "price_patterns": [r"￥\s*([0-9,]+)", r"([0-9,]+)円"],
        "out": ["在庫なし", "売り切れ", "販売終了"],
        "in": ["カートに入れる", "在庫あり", "店舗受取"],
    },
]

def fetch_text(url):
    r = requests.get(url, headers=HEADERS, timeout=25)
    r.raise_for_status()
    if not r.encoding or r.encoding.lower() == "iso-8859-1":
        r.encoding = r.apparent_encoding
    soup = BeautifulSoup(r.text, "html.parser")
    return " ".join(soup.stripped_strings)

def focus_text(text, keyword=None, radius=1800):
    if not keyword:
        return text
    # 表記揺れを少し吸収
    candidates = [
        keyword,
        keyword.replace("－", "-"),
        keyword.replace("-", "－"),
        "4904810905240",
        "BX-09",
        "ベイバトルパス",
    ]
    for k in candidates:
        i = text.find(k)
        if i != -1:
            return text[max(0, i-radius): i+radius]
    return text[:5000]

def extract_price(text, patterns):
    prices = []
    for pattern in patterns:
        for m in re.finditer(pattern, text, flags=re.S):
            try:
                prices.append(int(m.group(1).replace(",", "")))
            except Exception:
                pass
    # 商品周辺に複数価格がある場合、定価以下候補の最小値を採用
    sensible = [p for p in prices if 500 <= p <= 30000]
    return min(sensible) if sensible else None

def judge_stock(area, target):
    # 売切表記を優先。商品周辺に在庫表記がある時だけtrue
    if any(word in area for word in target["out"]):
        return False
    if any(word in area for word in target["in"]):
        return True
    return None

def notify(title, message, click_url):
    r = requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=message.encode("utf-8"),
        headers={
            "Title": title,
            "Priority": "high",
            "Tags": "tada,shopping_cart",
            "Click": click_url,
        },
        timeout=20,
    )
    r.raise_for_status()

def main():
    if os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
        notify(
            "ベイバトルパス監視・テスト",
            "GitHub Actions → Python → ntfy → iPhone の通知テスト成功！",
            "https://github.com/"
        )

    hits = []

    for target in TARGETS:
        try:
            text = fetch_text(target["url"])
            area = focus_text(text, target.get("focus"))
            price = extract_price(area, target["price_patterns"])
            stock = judge_stock(area, target)

            print(f'{target["name"]}: price={price}, in_stock={stock}')

            if price is not None and price <= MAX_PRICE and stock is True:
                hits.append((target, price))

        except Exception as e:
            # 1店舗がbot対策等で取得失敗しても他店舗の監視は継続
            print(f'ERROR {target["name"]}: {type(e).__name__}: {e}', file=sys.stderr)

    for target, price in hits:
        note = target.get("note", "")
        body = f'{target["name"]}で税込{price:,}円以下の在庫候補を検知。タップして確認！'
        if note:
            body += f" {note}"
        notify("ベイバトルパス在庫候補！", body, target["url"])

if __name__ == "__main__":
    main()
