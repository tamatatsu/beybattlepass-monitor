import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

MAX_PRICE = 3300
NTFY_TOPIC = os.environ["NTFY_TOPIC"]
STATE_FILE = Path("state.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/152.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
}

# v4:
# 商品詳細ページに固執せず、各店で比較的軽い検索結果・一覧ページ等を優先。
# 「価格」と「在庫」の両方が取れた時だけ判定し、曖昧なら unknown にして通知しない。
TARGETS = [
    {
        "id": "biccamera",
        "name": "ビックカメラ",
        "click_url": "https://www.biccamera.com/bc/item/11344352/",
        "sources": [
            "https://www.biccamera.com/bc/category/?q=beyblade+x",
            "https://www.biccamera.com/bc/item/11344352/",
        ],
        "anchors": ["ベイブレードX BX-09 ベイバトルパス"],
        "price_patterns": [r"([0-9,]+)円"],
        "out_words": ["販売休止中です", "販売休止中", "在庫がなくなりました", "ご購入できません"],
        "in_words": ["在庫あり", "カートに入れる", "お取り寄せ"],
        "floor": 2500,
    },
    {
        "id": "takaratomy",
        "name": "タカラトミーモール",
        "click_url": "https://takaratomymall.jp/shop/goods/search.aspx?category=Beyblade&search=true",
        "sources": [
            "https://takaratomymall.jp/shop/goods/search.aspx?category=Beyblade&p=2&search=true",
            "https://takaratomymall.jp/shop/goods/search.aspx?all=0&category=Beyblade&ismodesmartphone=on&keyword=BX-09&search=true",
        ],
        "anchors": ["BEYBLADE X BX-09 ベイバトルパス", "BX-09 ベイバトルパス"],
        "price_patterns": [r"([0-9,]+)円"],
        "out_words": ["在庫なし", "入荷案内申込", "品切れ"],
        "in_words": ["カートに入れる", "購入する", "在庫あり"],
        "floor": 2500,
    },
    {
        "id": "amazon",
        "name": "Amazon",
        "click_url": "https://www.amazon.co.jp/s?k=4904810905240",
        "sources": [
            "https://www.amazon.co.jp/dp/B0D7D9JR71",
            "https://www.amazon.co.jp/s?k=4904810905240",
        ],
        "anchors": ["BX-09 ベイバトルパス", "ベイバトルパス"],
        "price_patterns": [r"￥\s*([0-9,]+)", r"([0-9,]+)円"],
        "out_words": ["現在在庫切れです", "一時的に在庫切れ", "在庫切れ"],
        "in_words": ["在庫あり", "カートに入れる", "今すぐ買う"],
        "floor": 2500,
        "note": "Amazonは購入前に販売元・発送元と送料を確認してください。",
    },
    {
        "id": "joshin",
        "name": "Joshin web",
        "click_url": "https://joshinweb.jp/toy/67304/4904810905240.html",
        "sources": [
            "https://joshinweb.jp/toy/67304/4904810905240.html",
        ],
        "anchors": ["ベイブレードX BX-09 ベイバトルパス"],
        "price_patterns": [r"([0-9,]+)円", r"￥\s*([0-9,]+)"],
        "out_words": ["完売いたしました", "売り切れ", "在庫なし"],
        "in_words": ["在庫あり", "カートに入れる", "お取り寄せ"],
        "floor": 2500,
    },
    {
        "id": "edion",
        "name": "エディオン",
        "click_url": "https://www.edion.com/detail.html?p_cd=00075806569",
        "sources": [
            "https://www.edion.com/item_list.html?c_cd=001025502005",
            "https://www.edion.com/item_list.html?c_cd=001039022001",
        ],
        "anchors": ["BEYBLADE X BX-09 ベイバトルパス", "BX-09 ベイバトルパス"],
        "price_patterns": [r"￥\s*([0-9,]+)\s*\(税込\)", r"￥\s*([0-9,]+)"],
        "out_words": ["売り切れ", "在庫数0台", "在庫なし"],
        "in_words": ["在庫数", "最短翌日出荷", "カートに入れる"],
        "floor": 2500,
    },
    {
        "id": "toysrus",
        "name": "トイザらス",
        "click_url": "https://www.toysrus.co.jp/ja-jp/7652429-765242900.html",
        "sources": [
            "https://www.toysrus.co.jp/ja-jp/7652429-765242900.html",
            "https://www.toysrus.co.jp/search/?q=%E3%83%99%E3%82%A4%E3%83%96%E3%83%AC%E3%83%BC%E3%83%89",
        ],
        "anchors": ["BX-09 ベイバトルパス"],
        "price_patterns": [r"¥\s*([0-9,]+)", r"￥\s*([0-9,]+)"],
        "out_words": ["在庫なし", "Out of Stock", "売り切れ"],
        "in_words": ["在庫あり", "Add to Cart", "カートに入れる"],
        "floor": 2500,
    },
    {
        "id": "yamada",
        "name": "ヤマダウェブコム",
        "click_url": "https://www.yamada-denkiweb.com/6885552016/",
        "sources": [
            "https://www.yamada-denkiweb.com/category/215/005/006/?maker=791",
            "https://www.yamada-denkiweb.com/6885552016/?q=%E3%83%99%E3%82%A4%E3%83%96%E3%83%AC%E3%83%BC%E3%83%89%E3%82%A8%E3%83%83%E3%82%AF%E3%82%B9",
        ],
        "anchors": ["BX－09 ベイバトルパス", "BX-09 ベイバトルパス"],
        "price_patterns": [r"¥\s*([0-9,]+)", r"￥\s*([0-9,]+)", r"([0-9,]+)円"],
        "out_words": ["好評につき売り切れました", "売り切れました", "次回入荷待ち", "在庫なし"],
        "in_words": ["在庫あり", "カートに入れる", "お取り寄せ"],
        "floor": 2500,
    },
    {
        "id": "yodobashi",
        "name": "ヨドバシ.com",
        "click_url": "https://www.yodobashi.com/product/100000001007832087/",
        "sources": [
            "https://www.yodobashi.com/community/product/100000001007832087/all/02/review.html",
            "https://www.yodobashi.com/product/100000001007832087/",
        ],
        "anchors": ["BX-09 ベイバトルパス"],
        "price_patterns": [r"￥\s*([0-9,]+)", r"¥\s*([0-9,]+)"],
        "out_words": ["販売を終了しました", "予定数の販売を終了", "在庫なし"],
        "in_words": ["在庫あり", "カートに入れる", "在庫残少"],
        "floor": 2500,
    },
    {
        "id": "rakuten",
        "name": "楽天市場",
        "click_url": "https://product.rakuten.co.jp/product/-/bca3ff418ad8972ac7ae92107879ef28/",
        "sources": [
            "https://product.rakuten.co.jp/product/-/bca3ff418ad8972ac7ae92107879ef28/",
        ],
        "anchors": ["ＢＥＹＢＬＡＤＥ　Ｘ　ＢＸ−０９　ベイバトルパス", "BX-09 ベイバトルパス"],
        "price_patterns": [
            r"最安値\s*([0-9,]+)\s*円",
            r"新品[^0-9]{0,20}([0-9,]+)\s*円",
        ],
        "out_words": ["新品(0)", "該当する商品がありません"],
        # 価格比較ページに新品ショップが存在すれば在庫候補と扱う。
        "in_words": ["新品(", "購入する", "ショップページ"],
        "floor": 2500,
        "note": "楽天はショップ・送料・新品かどうかを購入前に確認してください。",
    },
    {
        "id": "shimamura",
        "name": "しまむらオンラインストア（バースデイ）",
        "click_url": "https://www.shop-shimamura.com/",
        "sources": [
            "https://www.shop-shimamura.com/disp/itemlist/?popular_tag=7%2F8%E8%B2%A9%E5%A3%B2&sortKey=02",
            "https://www.shop-shimamura.com/disp/itemlist/?b=birthday&page=10&popular_tag=6%2F8%E9%80%B1%E8%B2%A9%E5%A3%B2%3A6%2F15%E9%80%B1%E8%B2%A9%E5%A3%B2%3A6%2F22%E9%80%B1%E8%B2%A9%E5%A3%B2&sortKey=03",
        ],
        "anchors": ["BEYBLADE X BX-09 ベイバトルパス"],
        "price_patterns": [
            r"([0-9,]+)円\s*＋税",
            r"([0-9,]+)円",
        ],
        "out_words": ["在庫なし", "売り切れ"],
        "in_words": ["在庫あり", "カートに入れる", "店舗受取"],
        "floor": 2000,
        "plus_tax": True,
    },
]


def fetch_text(url):
    r = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
    r.raise_for_status()
    if not r.encoding or r.encoding.lower() == "iso-8859-1":
        r.encoding = r.apparent_encoding
    soup = BeautifulSoup(r.text, "html.parser")
    return " ".join(soup.stripped_strings)


def get_segment(text, anchors, before=120, after=700):
    for anchor in anchors:
        idx = text.find(anchor)
        if idx != -1:
            return text[max(0, idx - before): idx + len(anchor) + after]
    return None


def extract_price(segment, target):
    prices = []
    for pattern in target["price_patterns"]:
        for m in re.finditer(pattern, segment, flags=re.S | re.I):
            try:
                price = int(m.group(1).replace(",", ""))
                if target.get("plus_tax") and "＋税" in m.group(0):
                    price = int(round(price * 1.10))
                if target.get("floor", 500) <= price <= 30000:
                    prices.append(price)
            except Exception:
                pass
    return min(prices) if prices else None


def judge_stock(segment, target):
    lowered = segment.lower()

    # 売り切れ系を最優先
    for word in target["out_words"]:
        if word.lower() in lowered:
            # Edionの「在庫数」のような一般語があっても、売り切れ表記があればFalse
            return False

    for word in target["in_words"]:
        if word.lower() in lowered:
            # Edion: 「在庫数0台」はoutで先に弾く。
            # 「在庫数123台」のような場合はTrue。
            if word == "在庫数":
                m = re.search(r"在庫数\s*([0-9,]+)\s*台", segment)
                if m:
                    return int(m.group(1).replace(",", "")) > 0
                continue
            return True

    return None


def inspect_target(target):
    attempts = []

    for url in target["sources"]:
        try:
            text = fetch_text(url)
        except Exception as e:
            attempts.append(f"{urlparse(url).netloc}: {type(e).__name__} {e}")
            continue

        segment = get_segment(text, target["anchors"])
        if not segment:
            attempts.append(f"{urlparse(url).netloc}: product-not-found")
            continue

        price = extract_price(segment, target)
        stock = judge_stock(segment, target)

        if price is None or stock is None:
            attempts.append(
                f"{urlparse(url).netloc}: parsed price={price} stock={stock}"
            )
            continue

        if stock is True and price <= MAX_PRICE:
            status = "hit"
        else:
            status = "not_target"

        return {
            "status": status,
            "price": price,
            "stock": stock,
            "source": url,
            "detail": None,
        }

    return {
        "status": "unknown",
        "price": None,
        "stock": None,
        "source": None,
        "detail": " | ".join(attempts[-4:]) if attempts else "no source",
    }


def load_state():
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state):
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def notify(title, message, click_url):
    r = requests.post(
        "https://ntfy.sh/",
        json={
            "topic": NTFY_TOPIC,
            "title": title,
            "message": message,
            "priority": 4,
            "tags": ["tada", "shopping_cart"],
            "click": click_url,
        },
        timeout=20,
    )
    r.raise_for_status()


def main():
    previous = load_state()
    new_state = dict(previous)

    for target in TARGETS:
        result = inspect_target(target)
        old_status = previous.get(target["id"], {}).get("status")

        print(
            f'{target["name"]}: status={result["status"]}, '
            f'price={result["price"]}, stock={result["stock"]}, '
            f'source={result["source"]}'
        )

        if result.get("detail"):
            print(f'  DETAIL: {result["detail"]}', file=sys.stderr)

        # unknownは誤通知防止のため前回状態を保持
        if result["status"] == "unknown":
            continue

        new_state[target["id"]] = {
            "status": result["status"],
            "price": result["price"],
        }

        # 前回hitではない → 今回hit の瞬間だけ通知
        if result["status"] == "hit" and old_status != "hit":
            body = (
                f'{target["name"]}でBX-09 ベイバトルパスを'
                f'税込{result["price"]:,}円で在庫ありと検知しました。'
            )
            if target.get("note"):
                body += " " + target["note"]

            notify(
                "ベイバトルパス在庫あり！",
                body,
                target["click_url"],
            )
            print(f'  NOTIFIED: {target["name"]}')

    save_state(new_state)


if __name__ == "__main__":
    main()
