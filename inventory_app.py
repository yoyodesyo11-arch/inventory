import streamlit as st
import requests
import json
from datetime import datetime

GAS_URL = "https://script.google.com/macros/s/AKfycbx7-ZWWZcc77PLFIKto1Tf0ZaxiwTE-W0Sk77lOU3gLJOg9USlFpm2MIbTmb9gxU9Fm/exec"

INVENTORY_HEADERS = ["id","商品名","ブランド","カテゴリ","サイズ","仕入れ値","販売予定価格","保管場所","メモ","登録日","状態"]
SALES_HEADERS = ["id","商品id","商品名","ブランド","実売価格","販売日","メモ"]
RETURNS_HEADERS = ["id","販売id","商品名","返品日","メモ"]

def gas_get(sheet):
    r = requests.get(GAS_URL, params={"action":"get","sheet":sheet})
    data = r.json()
    if len(data) <= 1:
        return []
    return [dict(zip(data[0], row)) for row in data[1:]]

def gas_append(sheet, row):
    requests.post(GAS_URL, json={"action":"append","sheet":sheet,"row":row})

def gas_update(sheet, row_index, row):
    requests.post(GAS_URL, json={"action":"update","sheet":sheet,"row_index":row_index+1,"row":row})

def gas_delete(sheet, row_index):
    requests.post(GAS_URL, json={"action":"delete","sheet":sheet,"row_index":row_index+1})

def init_headers():
    for sheet, headers in [("inventory",INVENTORY_HEADERS),("sales",SALES_HEADERS),("returns",RETURNS_HEADERS)]:
        r = requests.get(GAS_URL, params={"action":"get","sheet":sheet})
        data = r.json()
        if len(data) == 0:
            requests.post(GAS_URL, json={"action":"append","sheet":sheet,"row":headers})

st.set_page_config(page_title="古着屋在庫管理", layout="wide")
init_headers()

menu = st.sidebar.radio("画面を選択", ["ダッシュボード","商品登録","販売記録","在庫一覧・編集","販売取消・返品","CSV出力"])

if menu == "ダッシュボード":
    st.title("古着屋 在庫管理アプリ")
    inventory = gas_get("inventory")
    sales = gas_get("sales")
    active = [i for i in inventory if i.get("状態") == "在庫中"]
    this_month = datetime.now().strftime("%Y-%m")
    month_sales = [s for s in sales if str(s.get("販売日","")).startswith(this_month)]
    revenue = sum(int(s.get("実売価格",0)) for s in month_sales)
    costs = []
    for s in month_sales:
        matched = [i for i in inventory if str(i.get("id")) == str(s.get("商品id"))]
        if matched:
            costs.append(int(matched[0].get("仕入れ値",0)))
    profit = revenue - sum(costs)
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("在庫数", len(active))
    c2.metric("今月売上", f"¥{revenue:,}")
    c3.metric("今月利益", f"¥{profit:,}")
    c4.metric("今月販売点数", len(month_sales))

elif menu == "商品登録":
    st.title("商品を追加")
    with st.form("add"):
        c1,c2,c3 = st.columns(3)
        name = c1.text_input("商品名 *")
        brand = c2.text_input("ブランド")
        category = c3.text_input("カテゴリ")
        c4,c5,c6 = st.columns(3)
        size = c4.text_input("サイズ")
        buy_price = c5.number_input("仕入れ値", min_value=0)
        sell_price = c6.number_input("販売予定価格", min_value=0)
        location = st.text_input("保管場所/ラック番号")
        memo = st.text_area("メモ")
        if st.form_submit_button("登録"):
            if name:
                inventory = gas_get("inventory")
                new_id = str(int(max([int(i.get("id",0)) for i in inventory], default=0)) + 1)
                gas_append("inventory", [new_id,name,brand,category,size,buy_price,sell_price,location,memo,datetime.now().strftime("%Y-%m-%d"),"在庫中"])
                st.success("登録しました！")
            else:
                st.error("商品名は必須です")

elif menu == "販売記録":
    st.title("販売記録をつける")
    inventory = gas_get("inventory")
    active = [i for i in inventory if i.get("状態") == "在庫中"]
    if not active:
        st.info("在庫中の商品がありません")
    else:
        options = {f"{i['商品名']} ({i['ブランド']}) ¥{i['販売予定価格']}": i for i in active}
        selected = st.selectbox("商品を選択", list(options.keys()))
        item = options[selected]
        with st.form("sell"):
            price = st.number_input("実売価格", min_value=0, value=int(item.get("販売予定価格",0)))
            date = st.date_input("販売日", value=datetime.now())
            memo = st.text_area("メモ")
            if st.form_submit_button("販売記録"):
                sales = gas_get("sales")
                new_id = str(int(max([int(s.get("id",0)) for s in sales], default=0)) + 1)
                gas_append("sales", [new_id,item["id"],item["商品名"],item["ブランド"],price,str(date),memo])
                idx = next(i for i,v in enumerate(inventory) if v["id"] == item["id"])
                row = inventory[idx]
                gas_update("inventory", idx, [row["id"],row["商品名"],row["ブランド"],row["カテゴリ"],row["サイズ"],row["仕入れ値"],row["販売予定価格"],row["保管場所"],row["メモ"],row["登録日"],"販売済"])
                st.success("販売記録しました！")

elif menu == "在庫一覧・編集":
    st.title("在庫一覧")
    inventory = gas_get("inventory")
    if not inventory:
        st.info("まだ商品がありません")
    else:
        for idx, item in enumerate(inventory):
            with st.expander(f"{item.get('商品名')} / {item.get('ブランド')} / {item.get('状態')}"):
                with st.form(f"edit_{idx}"):
                    c1,c2,c3 = st.columns(3)
                    name = c1.text_input("商品名", value=str(item.get("商品名","")))
                    brand = c2.text_input("ブランド", value=str(item.get("ブランド","")))
                    category = c3.text_input("カテゴリ", value=str(item.get("カテゴリ","")))
                    c4,c5,c6 = st.columns(3)
                    size = c4.text_input("サイズ", value=str(item.get("サイズ","")))
                    buy_price = c5.number_input("仕入れ値", value=int(item.get("仕入れ値",0)))
                    sell_price = c6.number_input("販売予定価格", value=int(item.get("販売予定価格",0)))
                    location = st.text_input("保管場所", value=str(item.get("保管場所","")))
                    memo = st.text_area("メモ", value=str(item.get("メモ","")))
                    status = st.selectbox("状態", ["在庫中","販売済","返品"], index=["在庫中","販売済","返品"].index(item.get("状態","在庫中")) if item.get("状態") in ["在庫中","販売済","返品"] else 0)
                    if st.form_submit_button("更新"):
                        gas_update("inventory", idx, [item["id"],name,brand,category,size,buy_price,sell_price,location,memo,item.get("登録日",""),status])
                        st.success("更新しました！")
                        st.rerun()

elif menu == "販売取消・返品":
    st.title("販売取消 / 返品")
    sales = gas_get("sales")
    if not sales:
        st.info("販売データがありません")
    else:
        options = {f"{s['商品名']} / {s['販売日']} / ¥{s['実売価格']}": s for s in sales}
        selected = st.selectbox("対象を選択", list(options.keys()))
        item = options[selected]
        with st.form("return"):
            memo = st.text_area("返品メモ")
            if st.form_submit_button("返品処理"):
                returns = gas_get("returns")
                new_id = str(int(max([int(r.get("id",0)) for r in returns], default=0)) + 1)
                gas_append("returns", [new_id,item["id"],item["商品名"],str(datetime.now().date()),memo])
                inventory = gas_get("inventory")
                idx = next((i for i,v in enumerate(inventory) if str(v["id"]) == str(item.get("商品id"))), None)
                if idx is not None:
                    row = inventory[idx]
                    gas_update("inventory", idx, [row["id"],row["商品名"],row["ブランド"],row["カテゴリ"],row["サイズ"],row["仕入れ値"],row["販売予定価格"],row["保管場所"],row["メモ"],row["登録日"],"在庫中"])
                st.success("返品処理しました！")

elif menu == "CSV出力":
    st.title("CSVエクスポート")
    import csv, io
    inventory = gas_get("inventory")
    if inventory:
        output = io.StringIO()
        w = csv.DictWriter(output, fieldnames=INVENTORY_HEADERS)
        w.writeheader()
        w.writerows(inventory)
        st.download_button("在庫CSVをダウンロード", output.getvalue(), "inventory.csv", "text/csv")
    else:
        st.info("データがありません")
