import streamlit as st
import requests
from datetime import datetime
import csv, io
from collections import Counter

GAS_URL = "https://script.google.com/macros/s/AKfycbzvGHwizg3fNi8Rae1_hUp9Nzoxc3U24iv8FpuivdWFf2lVqyId1JOzgHne--1A97oX/exec"
INVENTORY_HEADERS = ["id","商品名","ブランド","カテゴリ","サイズ","仕入れ値","販売予定価格","保管場所","メモ","登録日","仕入れ日","状態"]
SALES_HEADERS = ["id","商品id","商品名","ブランド","実売価格","販売日","メモ"]
RETURNS_HEADERS = ["id","販売id","商品名","返品日","メモ"]

STATUS_ICON = {"在庫中": "🟢", "販売済": "⚫", "返品": "🟠"}

STATUS_VALUES = {"在庫中", "販売済", "返品"}

@st.cache_data(ttl=300)
def gas_get(sheet):
    try:
        r = requests.get(GAS_URL, params={"action": "get", "sheet": sheet}, timeout=15)
        data = r.json()
        if len(data) <= 1:
            return []
        rows = [dict(zip(data[0], row)) for row in data[1:]]
        # 仕入れ日が空で登録された行は状態が1列左にズレる → 自動補正
        if sheet == "inventory":
            for row in rows:
                if row.get("状態") not in STATUS_VALUES and str(row.get("仕入れ日", "")) in STATUS_VALUES:
                    row["状態"] = row["仕入れ日"]
                    row["仕入れ日"] = ""
        return rows
    except Exception as e:
        st.error(f"データ取得エラー: {e}")
        return []

def gas_append(sheet, row):
    try:
        r = requests.post(GAS_URL, json={"action": "append", "sheet": sheet, "row": row}, timeout=15)
        st.cache_data.clear()
        try:
            resp = r.json()
            if isinstance(resp, dict) and resp.get("status") == "ok":
                return True
            st.error(f"GAS保存エラー: {resp}")
            return False
        except Exception:
            st.error(f"GASレスポンス異常(append): {r.text[:300]}")
            return False
    except Exception as e:
        st.error(f"保存エラー: {e}")
        return False

def gas_update(sheet, row_index, row):
    try:
        r = requests.post(GAS_URL, json={"action": "update", "sheet": sheet, "row_index": row_index + 1, "row": row}, timeout=15)
        st.cache_data.clear()
        try:
            resp = r.json()
            if isinstance(resp, dict) and resp.get("status") == "ok":
                return True
            st.error(f"GAS更新エラー: {resp}")
            return False
        except Exception:
            st.error(f"GASレスポンス異常(update): {r.text[:300]}")
            return False
    except Exception as e:
        st.error(f"更新エラー: {e}")
        return False

def search_filter(items, keyword, keys):
    if not keyword:
        return items
    kw = keyword.lower()
    return [i for i in items if any(kw in str(i.get(k, "")).lower() for k in keys)]

def update_inventory_status(inventory, item_id, status):
    """在庫のステータスを更新する共通関数"""
    real_idx = next((i for i, v in enumerate(inventory) if str(v["id"]) == str(item_id)), None)
    if real_idx is None:
        st.error("対象の商品が見つかりませんでした")
        return False
    row = inventory[real_idx]
    return gas_update("inventory", real_idx, [
        row["id"], row["商品名"], row["ブランド"], row["カテゴリ"],
        row["サイズ"], row["仕入れ値"], row["販売予定価格"], row["保管場所"],
        row["メモ"], row["登録日"], row.get("仕入れ日", ""), status
    ])

# ── ページ設定 ────────────────────────────────────────────────────────
st.set_page_config(page_title="古着屋在庫管理", layout="wide", page_icon="👕")

st.markdown("""
<style>
div[data-testid="metric-container"] {
    background: #f8f9fa;
    border: 1px solid #e0e0e0;
    padding: 16px;
    border-radius: 10px;
}
div[data-testid="stExpander"] {
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    margin-bottom: 6px;
}
</style>
""", unsafe_allow_html=True)

# ── サイドバー ────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 👕 古着屋 在庫管理")
    st.divider()
    menu = st.radio("メニュー", [
        "📊 ダッシュボード",
        "➕ 商品登録",
        "💰 販売記録",
        "📦 在庫一覧・編集",
        "↩️ 販売取消・返品",
        "📥 CSV出力",
    ], label_visibility="collapsed")

# ── ダッシュボード ────────────────────────────────────────────────────
if menu == "📊 ダッシュボード":
    st.title("📊 ダッシュボード")

    with st.spinner("データ読み込み中..."):
        inventory = gas_get("inventory")
        sales = gas_get("sales")

    active = [i for i in inventory if i.get("状態") == "在庫中"]
    this_month = datetime.now().strftime("%Y-%m")
    month_sales = [s for s in sales if str(s.get("販売日", "")).startswith(this_month)]
    revenue = sum(int(s.get("実売価格", 0)) for s in month_sales)
    inv_map = {str(i["id"]): i for i in inventory}
    costs = sum(int(inv_map.get(str(s.get("商品id")), {}).get("仕入れ値", 0)) for s in month_sales)
    profit = revenue - costs

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📦 在庫数", f"{len(active)} 点")
    c2.metric("💰 今月売上", f"¥{revenue:,}")
    c3.metric("📈 今月利益", f"¥{profit:,}")
    c4.metric("🛍️ 今月販売", f"{len(month_sales)} 点")

    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("🏆 今月ブランドランキング")
        if month_sales:
            medals = ["🥇", "🥈", "🥉", "4位", "5位"]
            for rank, (brand, cnt) in enumerate(Counter(s.get("ブランド", "不明") for s in month_sales).most_common(5)):
                st.write(f"{medals[rank]}  **{brand}** — {cnt} 点")
        else:
            st.info("今月の販売データがありません")

    with col_right:
        st.subheader("⚠️ 売れ残りアラート（30日以上）")
        today = datetime.now().date()
        alerts = []
        for i in active:
            try:
                reg = datetime.strptime(str(i.get("仕入れ日", ""))[:10], "%Y-%m-%d").date()
                days = (today - reg).days
                if days >= 30:
                    alerts.append((days, i))
            except Exception:
                pass
        if not alerts:
            st.success("✅ 売れ残りはありません")
        else:
            alerts.sort(reverse=True)
            for days, i in alerts:
                st.warning(f"**{i.get('商品名')}** / {i.get('ブランド')} — **{days}日** 経過  |  仕入れ ¥{int(i.get('仕入れ値', 0)):,}")

# ── 商品登録 ──────────────────────────────────────────────────────────
elif menu == "➕ 商品登録":
    st.title("➕ 商品を登録")

    with st.form("add", clear_on_submit=True):
        st.subheader("基本情報")
        c1, c2, c3 = st.columns(3)
        name = c1.text_input("商品名 *", placeholder="例：リーバイス 501")
        brand = c2.text_input("ブランド", placeholder="例：Levi's")
        category = c3.text_input("カテゴリ", placeholder="例：デニム")

        st.subheader("サイズ・価格")
        c4, c5, c6 = st.columns(3)
        size = c4.text_input("サイズ", placeholder="例：M / W32L30")
        buy_price = c5.number_input("仕入れ値 (¥)", min_value=0, step=100)
        sell_price = c6.number_input("販売予定価格 (¥)", min_value=0, step=100)

        st.subheader("その他")
        c7, c8 = st.columns(2)
        buy_date = c7.date_input("仕入れ日", value=datetime.now())
        location = c8.text_input("保管場所 / ラック番号", placeholder="例：ラック A-3")
        memo = st.text_area("メモ", placeholder="状態・特記事項など")

        if st.form_submit_button("✅ 登録する", use_container_width=True, type="primary"):
            if not name:
                st.error("⚠️ 商品名は必須です")
            else:
                inventory = gas_get("inventory")
                new_id = str(int(max([int(i.get("id", 0)) for i in inventory], default=0)) + 1)
                ok = gas_append("inventory", [
                    new_id, name, brand, category, size,
                    buy_price, sell_price, location, memo,
                    datetime.now().strftime("%Y-%m-%d"), str(buy_date), "在庫中"
                ])
                if ok:
                    st.success(f"✅ **{name}** を登録しました！（ID: {new_id}）")

# ── 販売記録 ──────────────────────────────────────────────────────────
elif menu == "💰 販売記録":
    st.title("💰 販売記録")

    inventory = gas_get("inventory")
    ov = st.session_state.get("status_ov", {})
    active = [i for i in inventory if ov.get(str(i["id"]), i.get("状態")) == "在庫中"]

    if not active:
        st.info("在庫中の商品がありません")
    else:
        keyword = st.text_input("🔍 検索（商品名・ブランド・カテゴリ）", placeholder="検索キーワード")
        filtered = search_filter(active, keyword, ["商品名", "ブランド", "カテゴリ"])

        if not filtered:
            st.warning("該当する商品がありません")
        else:
            options = {
                f"{i['商品名']}  ({i.get('ブランド', '—')})  [{i.get('サイズ', '—')}]  ¥{int(i.get('販売予定価格', 0)):,}": i
                for i in filtered
            }
            selected = st.selectbox("商品を選択", list(options.keys()))
            item = options[selected]

            # 商品プレビュー
            st.markdown("---")
            pc1, pc2, pc3, pc4 = st.columns(4)
            pc1.info(f"**カテゴリ**\n\n{item.get('カテゴリ', '—')}")
            pc2.info(f"**サイズ**\n\n{item.get('サイズ', '—')}")
            pc3.info(f"**仕入れ値**\n\n¥{int(item.get('仕入れ値', 0)):,}")
            pc4.info(f"**保管場所**\n\n{item.get('保管場所', '—')}")
            if item.get("メモ"):
                st.caption(f"メモ: {item.get('メモ')}")
            st.markdown("---")

            with st.form("sell", clear_on_submit=True):
                col1, col2 = st.columns(2)
                price = col1.number_input("実売価格 (¥)", min_value=0, value=int(item.get("販売予定価格", 0)), step=100)
                date = col2.date_input("販売日", value=datetime.now())

                profit_preview = price - int(item.get("仕入れ値", 0))
                if profit_preview >= 0:
                    st.success(f"💹 見込み利益: **¥{profit_preview:,}**")
                else:
                    st.error(f"⚠️ 見込み損失: **¥{abs(profit_preview):,}**")

                memo = st.text_area("メモ")

                if st.form_submit_button("💰 販売記録する", use_container_width=True, type="primary"):
                    # 1. 販売記録を追加
                    sales = gas_get("sales")
                    new_id = str(int(max([int(s.get("id", 0)) for s in sales], default=0)) + 1)
                    ok1 = gas_append("sales", [new_id, item["id"], item["商品名"], item["ブランド"], price, str(date), memo])

                    if ok1:
                        # 2. 在庫ステータスを「販売済」に更新
                        ok2 = update_inventory_status(inventory, item["id"], "販売済")
                        if ok2:
                            st.session_state.setdefault("status_ov", {})[str(item["id"])] = "販売済"
                            st.success(f"✅ **{item['商品名']}** を販売記録しました！")
                            st.rerun()
                        else:
                            st.error("⚠️ 販売記録は保存しましたが、在庫ステータスの更新に失敗しました。在庫一覧から手動で「販売済」に変更してください。")

# ── 在庫一覧・編集 ────────────────────────────────────────────────────
elif menu == "📦 在庫一覧・編集":
    st.title("📦 在庫一覧")

    inventory = gas_get("inventory")

    if not inventory:
        st.info("まだ商品がありません")
    else:
        # サマリー
        cnt_all = len(inventory)
        cnt_active = sum(1 for i in inventory if i.get("状態") == "在庫中")
        cnt_sold = sum(1 for i in inventory if i.get("状態") == "販売済")
        cnt_return = sum(1 for i in inventory if i.get("状態") == "返品")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("全商品", cnt_all)
        c2.metric("🟢 在庫中", cnt_active)
        c3.metric("⚫ 販売済", cnt_sold)
        c4.metric("🟠 返品", cnt_return)

        st.divider()

        # フィルター
        filter_status = st.radio("表示", ["すべて", "在庫中", "販売済", "返品"], horizontal=True)
        keyword = st.text_input("🔍 検索（商品名・ブランド・カテゴリ）")

        filtered = [i for i in inventory if filter_status == "すべて" or i.get("状態") == filter_status]
        filtered = search_filter(filtered, keyword, ["商品名", "ブランド", "カテゴリ"])
        st.caption(f"{len(filtered)} 件表示")

        ov = st.session_state.get("status_ov", {})
        for idx, item in enumerate(filtered):
            real_idx = inventory.index(item)
            status = ov.get(str(item.get("id")), item.get("状態", "在庫中"))
            icon = STATUS_ICON.get(status, "")

            with st.expander(f"{icon} **{item.get('商品名')}**  /  {item.get('ブランド', '—')}  /  {item.get('サイズ', '—')}  /  ¥{int(item.get('販売予定価格', 0)):,}"):
                with st.form(f"edit_{idx}"):
                    c1, c2, c3 = st.columns(3)
                    name = c1.text_input("商品名", value=str(item.get("商品名", "")))
                    brand = c2.text_input("ブランド", value=str(item.get("ブランド", "")))
                    category = c3.text_input("カテゴリ", value=str(item.get("カテゴリ", "")))
                    c4, c5, c6 = st.columns(3)
                    size = c4.text_input("サイズ", value=str(item.get("サイズ", "")))
                    buy_price = c5.number_input("仕入れ値", value=int(item.get("仕入れ値", 0)), step=100)
                    sell_price = c6.number_input("販売予定価格", value=int(item.get("販売予定価格", 0)), step=100)
                    c7, c8 = st.columns(2)
                    try:
                        bd = datetime.strptime(str(item.get("仕入れ日", ""))[:10], "%Y-%m-%d").date()
                    except Exception:
                        bd = datetime.now().date()
                    buy_date = c7.date_input("仕入れ日", value=bd, key=f"bd_{idx}")
                    location = c8.text_input("保管場所", value=str(item.get("保管場所", "")))
                    memo = st.text_area("メモ", value=str(item.get("メモ", "")))
                    if st.form_submit_button("💾 更新する", type="primary"):
                        ok = gas_update("inventory", real_idx, [
                            item["id"], name, brand, category, size,
                            buy_price, sell_price, location, memo,
                            item.get("登録日", ""), str(buy_date), item.get("状態", "在庫中")
                        ])
                        if ok:
                            st.success("✅ 更新しました！")
                            st.rerun()

                st.write("**状態を変更**")
                col1, col2, col3 = st.columns(3)
                if col1.button("🟢 在庫中", key=f"s1_{idx}", type="primary" if status == "在庫中" else "secondary"):
                    st.session_state.setdefault("status_ov", {})[str(item["id"])] = "在庫中"
                    gas_update("inventory", real_idx, [item["id"], item.get("商品名"), item.get("ブランド"), item.get("カテゴリ"), item.get("サイズ"), item.get("仕入れ値"), item.get("販売予定価格"), item.get("保管場所"), item.get("メモ"), item.get("登録日"), item.get("仕入れ日", ""), "在庫中"])
                    st.rerun()
                if col2.button("⚫ 販売済", key=f"s2_{idx}", type="primary" if status == "販売済" else "secondary"):
                    st.session_state.setdefault("status_ov", {})[str(item["id"])] = "販売済"
                    gas_update("inventory", real_idx, [item["id"], item.get("商品名"), item.get("ブランド"), item.get("カテゴリ"), item.get("サイズ"), item.get("仕入れ値"), item.get("販売予定価格"), item.get("保管場所"), item.get("メモ"), item.get("登録日"), item.get("仕入れ日", ""), "販売済"])
                    st.rerun()
                if col3.button("🟠 返品", key=f"s3_{idx}", type="primary" if status == "返品" else "secondary"):
                    st.session_state.setdefault("status_ov", {})[str(item["id"])] = "返品"
                    gas_update("inventory", real_idx, [item["id"], item.get("商品名"), item.get("ブランド"), item.get("カテゴリ"), item.get("サイズ"), item.get("仕入れ値"), item.get("販売予定価格"), item.get("保管場所"), item.get("メモ"), item.get("登録日"), item.get("仕入れ日", ""), "返品"])
                    st.rerun()

# ── 販売取消・返品 ────────────────────────────────────────────────────
elif menu == "↩️ 販売取消・返品":
    st.title("↩️ 販売取消 / 返品")

    sales = gas_get("sales")
    keyword = st.text_input("🔍 検索（商品名・ブランド）")
    filtered_sales = search_filter(sales, keyword, ["商品名", "ブランド"])

    if not filtered_sales:
        st.info("対象データがありません")
    else:
        options = {
            f"{s['商品名']}  /  {s.get('販売日', '')}  /  ¥{int(s.get('実売価格', 0)):,}": s
            for s in filtered_sales
        }
        selected = st.selectbox("返品する販売記録を選択", list(options.keys()))
        item = options[selected]

        st.info(f"**{item['商品名']}** / {item.get('ブランド', '')} / 販売日: {item.get('販売日', '')} / ¥{int(item.get('実売価格', 0)):,}")

        with st.form("return"):
            memo = st.text_area("返品メモ", placeholder="返品理由など")
            if st.form_submit_button("↩️ 返品処理する", type="primary", use_container_width=True):
                returns = gas_get("returns")
                new_id = str(int(max([int(r.get("id", 0)) for r in returns], default=0)) + 1)
                gas_append("returns", [new_id, item["id"], item["商品名"], str(datetime.now().date()), memo])

                inventory = gas_get("inventory")
                ok = update_inventory_status(inventory, item.get("商品id"), "在庫中")
                if ok:
                    st.session_state.setdefault("status_ov", {})[str(item.get("商品id"))] = "在庫中"
                    st.success("✅ 返品処理しました！在庫に戻しました。")
                else:
                    st.warning("⚠️ 返品記録は保存しましたが、在庫ステータスの更新に失敗しました。在庫一覧から手動で「在庫中」に変更してください。")

# ── CSV出力 ───────────────────────────────────────────────────────────
elif menu == "📥 CSV出力":
    st.title("📥 CSVエクスポート")

    inventory = gas_get("inventory")
    sales = gas_get("sales")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("在庫データ")
        if inventory:
            output = io.StringIO()
            csv.DictWriter(output, fieldnames=INVENTORY_HEADERS, extrasaction="ignore").writeheader()
            csv.DictWriter(output, fieldnames=INVENTORY_HEADERS, extrasaction="ignore").writerows(inventory)
            st.download_button("📥 在庫CSVをダウンロード", output.getvalue(), "inventory.csv", "text/csv", use_container_width=True)
        else:
            st.info("データがありません")

    with col2:
        st.subheader("販売データ")
        if sales:
            output = io.StringIO()
            csv.DictWriter(output, fieldnames=SALES_HEADERS, extrasaction="ignore").writeheader()
            csv.DictWriter(output, fieldnames=SALES_HEADERS, extrasaction="ignore").writerows(sales)
            st.download_button("📥 販売CSVをダウンロード", output.getvalue(), "sales.csv", "text/csv", use_container_width=True)
        else:
            st.info("データがありません")
