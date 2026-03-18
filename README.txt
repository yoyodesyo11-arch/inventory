# inventory_complete_fresh

Macでの起動方法

1. ターミナルを開く
2. 次の3行を順番に実行

cd ~/Downloads/inventory_complete_fresh
python3 -m pip install --user -r requirements.txt
python3 -m streamlit run inventory_app.py

3. ブラウザで http://localhost:8501 を開く

入っている機能
- 商品画像つき在庫登録
- 商品コード自動発番
- 商品検索 / 並び替え
- 商品編集 / 削除
- 販売記録
- 実売価格と実利益の反映
- 販売取消 / 返品
- 今月売上 / 今月利益 / ブランドランキング
- 回転率 / 売れ残りアラート
- CSV出力
