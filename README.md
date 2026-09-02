# ベイバトルパス 5分在庫監視 v2

対象:
- ビックカメラ
- タカラトミーモール
- Amazon
- Joshin web
- エディオン
- トイザらス
- ヤマダウェブコム
- ヨドバシ.com
- 楽天市場
- しまむらオンラインストア

条件:
- BX-09 ベイバトルパス
- 税込3,300円以下
- 在庫ありと判定した場合にntfyへ通知

JAN:
4904810905240

## 導入

1. iPhoneにntfyをインストール
2. 推測されにくいTopic名を作って購読
3. GitHubでPublicリポジトリを作成
4. このフォルダの中身をアップロード
5. Settings → Secrets and variables → Actions
6. Repository secret `NTFY_TOPIC` にTopic名を保存
7. Actions → ベイバトルパス在庫監視 → Run workflow でテスト

## 実行周期

cron:
`2-59/5 * * * *`

おおむね5分ごとです。GitHub Actionsのscheduleは遅延する場合があります。

## 大事な注意

通販サイトはHTML構造やbot対策を変更することがあります。
その場合、GitHub Actionsのログに `ERROR 店名:` が出ます。
Amazon・楽天は複数販売者が混ざるため、通知後に販売元・送料を最終確認してください。

このv2は「対象店舗を広く見張ること」を優先した初期版です。
誤通知・連続通知を減らす改良は後から追加できます。
