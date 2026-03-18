
import os
import re
import sqlite3
from datetime import date, datetime
from typing import Optional

import pandas as pd
import streamlit as st

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "inventory.db")
IMG_DIR = os.path.join(APP_DIR, "images")
os.makedirs(IMG_DIR, exist_ok=True)

st.set_page_config(page_title="Vintage Inventory Pro", layout="wide")


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_code TEXT,
            name TEXT NOT NULL,
            brand TEXT,
            category TEXT,
            size TEXT,
            cost REAL DEFAULT 0,
            list_price REAL DEFAULT 0,
            actual_sale_price REAL,
            expected_profit REAL,
            actual_profit REAL,
            location TEXT,
            notes TEXT,
            image_path TEXT,
            status TEXT DEFAULT '在庫中',
            created_at TEXT,
            sold_date TEXT,
            sold_channel TEXT,
            return_flag INTEGER DEFAULT 0
        )
        """
    )
    conn.commit()
    conn.close()


def safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", name.strip())
    return cleaned[:60] or "item"


def next_item_code(conn) -> str:
    yy_mm = datetime.now().strftime("%y%m")
    prefix = f"NM-{yy_mm}-"
    cur = conn.cursor()
    cur.execute("SELECT item_code FROM inventory WHERE item_code LIKE ? ORDER BY id DESC LIMIT 1", (prefix + "%",))
    row = cur.fetchone()
    if not row or not row[0]:
        num = 1
    else:
        try:
            num = int(str(row[0]).split("-")[-1]) + 1
        except Exception:
            num = 1
    return f"{prefix}{num:03d}"


def save_uploaded_image(uploaded_file, item_code: str) -> Optional[str]:
    if uploaded_file is None:
        return None
    ext = os.path.splitext(uploaded_file.name)[1].lower() or ".jpg"
    filename = f"{safe_filename(item_code)}{ext}"
    path = os.path.join(IMG_DIR, filename)
    with open(path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return path


def load_df() -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query("SELECT * FROM inventory ORDER BY id DESC", conn)
    conn.close()
    if df.empty:
        return df
    for col in ["cost", "list_price", "actual_sale_price", "expected_profit", "actual_profit"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "created_at" in df.columns:
        df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
    if "sold_date" in df.columns:
        df["sold_date"] = pd.to_datetime(df["sold_date"], errors="coerce")
    if "created_at" in df.columns and "sold_date" in df.columns:
        df["rotation_days"] = (df["sold_date"] - df["created_at"]).dt.days
    else:
        df["rotation_days"] = None
    today = pd.Timestamp.today().normalize()
    if "created_at" in df.columns:
        df["stock_days"] = (today - df["created_at"].dt.normalize()).dt.days
    else:
        df["stock_days"] = None
    return df


def update_expected_profit(conn, item_id: int):
    cur = conn.cursor()
    cur.execute("SELECT cost, list_price FROM inventory WHERE id=?", (item_id,))
    row = cur.fetchone()
    if row:
        cost = float(row[0] or 0)
        list_price = float(row[1] or 0)
        expected_profit = list_price - cost
        cur.execute("UPDATE inventory SET expected_profit=? WHERE id=?", (expected_profit, item_id))
        conn.commit()


def add_item(data, uploaded_file):
    conn = get_conn()
    item_code = next_item_code(conn)
    img_path = save_uploaded_image(uploaded_file, item_code)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO inventory (
            item_code, name, brand, category, size, cost, list_price,
            expected_profit, location, notes, image_path, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '在庫中', ?)
        """,
        (
            item_code,
            data["name"],
            data["brand"],
            data["category"],
            data["size"],
            data["cost"],
            data["list_price"],
            float(data["list_price"] or 0) - float(data["cost"] or 0),
            data["location"],
            data["notes"],
            img_path,
            datetime.now().strftime("%Y-%m-%d"),
        ),
    )
    conn.commit()
    conn.close()


def record_sale(item_id: int, sold_date: str, channel: str, sale_price: float):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT cost FROM inventory WHERE id=?", (item_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return False
    cost = float(row[0] or 0)
    actual_profit = float(sale_price or 0) - cost
    cur.execute(
        """
        UPDATE inventory
        SET status='販売済み', sold_date=?, sold_channel=?, actual_sale_price=?, actual_profit=?, return_flag=0
        WHERE id=?
        """,
        (sold_date, channel, sale_price, actual_profit, item_id),
    )
    conn.commit()
    conn.close()
    return True


def undo_sale(item_id: int, mark_return: bool = False):
    conn = get_conn()
    cur = conn.cursor()
    new_status = '返品' if mark_return else '在庫中'
    return_flag = 1 if mark_return else 0
    cur.execute(
        """
        UPDATE inventory
        SET status=?, sold_date=NULL, sold_channel=NULL, actual_sale_price=NULL,
            actual_profit=NULL, return_flag=?
        WHERE id=?
        """,
        (new_status, return_flag, item_id),
    )
    conn.commit()
    conn.close()


def delete_item(item_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT image_path FROM inventory WHERE id=?", (item_id,))
    row = cur.fetchone()
    if row and row[0] and os.path.exists(row[0]):
        try:
            os.remove(row[0])
        except OSError:
            pass
    cur.execute("DELETE FROM inventory WHERE id=?", (item_id,))
    conn.commit()
    conn.close()


def update_item(item_id: int, values: dict, uploaded_file):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT item_code, image_path FROM inventory WHERE id=?", (item_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return
    item_code = row[0]
    image_path = row[1]
    new_image_path = image_path
    if uploaded_file is not None:
        new_image_path = save_uploaded_image(uploaded_file, item_code)
    cur.execute(
        """
        UPDATE inventory
        SET name=?, brand=?, category=?, size=?, cost=?, list_price=?,
            expected_profit=?, location=?, notes=?, image_path=?
        WHERE id=?
        """,
        (
            values["name"], values["brand"], values["category"], values["size"],
            values["cost"], values["list_price"], float(values["list_price"] or 0) - float(values["cost"] or 0),
            values["location"], values["notes"], new_image_path, item_id
        )
    )
    conn.commit()
    conn.close()


def render_thumb(path: Optional[str]):
    if path and os.path.exists(path):
        st.image(path, width=90)
    else:
        st.caption("画像なし")


init_db()
st.title("古着屋 在庫管理アプリ 完全版")
st.caption("商品画像つき / 販売記録 / 販売取消 / 商品編集 / 回転率 / 売れ残りチェック")

with st.sidebar:
    st.header("メニュー")
    page = st.radio(
        "画面を選択",
        ["ダッシュボード", "商品登録", "販売記録", "在庫一覧・編集", "販売取消・返品", "CSV出力"],
    )


df = load_df()

if page == "ダッシュボード":
    current_month = datetime.now().strftime("%Y-%m")
    sold_df = df[df["status"] == "販売済み"].copy() if not df.empty else pd.DataFrame()
    month_df = sold_df[sold_df["sold_date"].dt.strftime("%Y-%m") == current_month] if not sold_df.empty else pd.DataFrame()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("在庫数", int((df["status"] == "在庫中").sum()) if not df.empty else 0)
    c2.metric("今月売上", f"¥{int(month_df['actual_sale_price'].fillna(0).sum()):,}" if not month_df.empty else "¥0")
    c3.metric("今月利益", f"¥{int(month_df['actual_profit'].fillna(0).sum()):,}" if not month_df.empty else "¥0")
    c4.metric("今月販売点数", int(len(month_df)))

    st.subheader("売れたブランドランキング（今月）")
    if not month_df.empty:
        rank = month_df.groupby("brand", dropna=False).size().reset_index(name="販売点数").sort_values("販売点数", ascending=False)
        rank["brand"] = rank["brand"].fillna("未入力")
        st.dataframe(rank, width='stretch')
    else:
        st.info("今月の販売データがまだありません。")

    st.subheader("売れ残りアラート")
    if not df.empty:
        in_stock = df[df["status"] == "在庫中"].copy()
        alert = in_stock[in_stock["stock_days"].fillna(0) >= 30][["item_code", "name", "brand", "category", "stock_days", "location"]].sort_values("stock_days", ascending=False)
        if alert.empty:
            st.success("30日以上売れていない在庫はありません。")
        else:
            st.dataframe(alert, width='stretch')
    else:
        st.info("在庫データがまだありません。")

elif page == "商品登録":
    st.subheader("商品を追加")
    with st.form("add_item_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        name = c1.text_input("商品名 *")
        brand = c2.text_input("ブランド")
        category = c3.text_input("カテゴリ")
        c4, c5, c6 = st.columns(3)
        size = c4.text_input("サイズ")
        cost = c5.number_input("仕入れ値", min_value=0, step=100)
        list_price = c6.number_input("販売予定価格", min_value=0, step=100)
        c7, c8 = st.columns(2)
        location = c7.text_input("保管場所 / ラック番号")
        notes = c8.text_input("メモ")
        image = st.file_uploader("商品画像", type=["jpg", "jpeg", "png", "webp"])
        submitted = st.form_submit_button("登録")
        if submitted:
            if not name.strip():
                st.error("商品名は必須です。")
            else:
                add_item({
                    "name": name.strip(), "brand": brand.strip(), "category": category.strip(), "size": size.strip(),
                    "cost": cost, "list_price": list_price, "location": location.strip(), "notes": notes.strip()
                }, image)
                st.success("商品を登録しました。左のメニューから在庫一覧で確認できます。")

elif page == "販売記録":
    st.subheader("販売記録をつける")
    if df.empty or (df["status"] == "在庫中").sum() == 0:
        st.info("販売記録をつけられる在庫中の商品がありません。")
    else:
        in_stock = df[df["status"] == "在庫中"].copy()
        search = st.text_input("販売した商品を検索", placeholder="商品名・ブランド・カテゴリで検索")
        if search:
            mask = (
                in_stock["name"].fillna("").str.contains(search, case=False, na=False)
                | in_stock["brand"].fillna("").str.contains(search, case=False, na=False)
                | in_stock["category"].fillna("").str.contains(search, case=False, na=False)
                | in_stock["item_code"].fillna("").str.contains(search, case=False, na=False)
            )
            in_stock = in_stock[mask]
        if in_stock.empty:
            st.warning("該当する商品が見つかりません。")
        else:
            in_stock["label"] = in_stock.apply(lambda r: f"{r['item_code']} | {r['brand'] or '-'} | {r['name']} | {r['size'] or '-'}", axis=1)
            selected_label = st.selectbox("販売した商品", in_stock["label"].tolist())
            selected_row = in_stock[in_stock["label"] == selected_label].iloc[0]
            st.write(f"予定価格: ¥{int(selected_row['list_price'] or 0):,} / 仕入れ: ¥{int(selected_row['cost'] or 0):,}")
            with st.form("sale_form"):
                c1, c2, c3 = st.columns(3)
                sold_date = c1.date_input("売れた日", value=date.today())
                channel = c2.selectbox("販売場所", ["店頭", "メルカリ", "BASE", "eBay", "その他"])
                sale_price = c3.number_input("実際の販売額", min_value=0, step=100, value=int(selected_row['list_price'] or 0))
                submitted = st.form_submit_button("販売記録を保存")
                if submitted:
                    record_sale(int(selected_row["id"]), sold_date.strftime("%Y-%m-%d"), channel, float(sale_price))
                    st.success("販売記録を保存しました。商品データにも反映されています。")

elif page == "在庫一覧・編集":
    st.subheader("在庫一覧")
    if df.empty:
        st.info("まだ商品がありません。")
    else:
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        keyword = c1.text_input("キーワード")
        brand_filter = c2.selectbox("ブランド", ["全部"] + sorted([x for x in df["brand"].dropna().unique().tolist() if x]))
        size_filter = c3.selectbox("サイズ", ["全部"] + sorted([x for x in df["size"].dropna().unique().tolist() if x]))
        category_filter = c4.selectbox("カテゴリ", ["全部"] + sorted([x for x in df["category"].dropna().unique().tolist() if x]))
        status_filter = c5.selectbox("状態", ["全部", "在庫中", "販売済み", "返品"])
        sort_by = c6.selectbox("並び替え", ["登録順", "ブランド順", "価格順", "利益順", "回転率順"])

        filtered = df.copy()
        if keyword:
            mask = (
                filtered["name"].fillna("").str.contains(keyword, case=False, na=False)
                | filtered["brand"].fillna("").str.contains(keyword, case=False, na=False)
                | filtered["category"].fillna("").str.contains(keyword, case=False, na=False)
                | filtered["item_code"].fillna("").str.contains(keyword, case=False, na=False)
            )
            filtered = filtered[mask]
        if brand_filter != "全部":
            filtered = filtered[filtered["brand"] == brand_filter]
        if size_filter != "全部":
            filtered = filtered[filtered["size"] == size_filter]
        if category_filter != "全部":
            filtered = filtered[filtered["category"] == category_filter]
        if status_filter != "全部":
            filtered = filtered[filtered["status"] == status_filter]

        if sort_by == "ブランド順":
            filtered = filtered.sort_values(["brand", "id"], ascending=[True, False], na_position="last")
        elif sort_by == "価格順":
            filtered = filtered.sort_values(["list_price", "id"], ascending=[False, False], na_position="last")
        elif sort_by == "利益順":
            filtered = filtered.sort_values(["expected_profit", "id"], ascending=[False, False], na_position="last")
        elif sort_by == "回転率順":
            filtered = filtered.sort_values(["rotation_days", "id"], ascending=[True, False], na_position="last")
        else:
            filtered = filtered.sort_values("id", ascending=False)

        st.write(f"表示件数: {len(filtered)}件")
        for _, row in filtered.iterrows():
            with st.expander(f"{row['item_code']} | {row['brand'] or '-'} | {row['name']} | {row['status']}"):
                a, b = st.columns([1, 2])
                with a:
                    render_thumb(row.get("image_path"))
                with b:
                    info = {
                        "商品コード": row.get("item_code"),
                        "ブランド": row.get("brand"),
                        "カテゴリ": row.get("category"),
                        "サイズ": row.get("size"),
                        "仕入れ": row.get("cost"),
                        "販売予定価格": row.get("list_price"),
                        "予定利益": row.get("expected_profit"),
                        "保管場所": row.get("location"),
                        "状態": row.get("status"),
                        "売れた日": row.get("sold_date"),
                        "販売場所": row.get("sold_channel"),
                        "実際の販売額": row.get("actual_sale_price"),
                        "実利益": row.get("actual_profit"),
                        "回転日数": row.get("rotation_days"),
                        "在庫日数": row.get("stock_days"),
                        "メモ": row.get("notes"),
                    }
                    pretty = pd.DataFrame(list(info.items()), columns=["項目", "内容"])
                    st.dataframe(pretty, width='stretch', hide_index=True)

                st.markdown("### 商品編集")
                with st.form(f"edit_{int(row['id'])}"):
                    e1, e2, e3 = st.columns(3)
                    name = e1.text_input("商品名", value=row.get("name") or "")
                    brand = e2.text_input("ブランド", value=row.get("brand") or "")
                    category = e3.text_input("カテゴリ", value=row.get("category") or "")
                    e4, e5, e6 = st.columns(3)
                    size = e4.text_input("サイズ", value=row.get("size") or "")
                    cost = e5.number_input("仕入れ値", min_value=0, step=100, value=int(row.get("cost") or 0), key=f"cost_{int(row['id'])}")
                    list_price = e6.number_input("販売予定価格", min_value=0, step=100, value=int(row.get("list_price") or 0), key=f"list_{int(row['id'])}")
                    e7, e8 = st.columns(2)
                    location = e7.text_input("保管場所", value=row.get("location") or "")
                    notes = e8.text_input("メモ", value=row.get("notes") or "")
                    new_image = st.file_uploader("画像差し替え", type=["jpg", "jpeg", "png", "webp"], key=f"img_{int(row['id'])}")
                    submitted = st.form_submit_button("更新")
                    if submitted:
                        update_item(int(row["id"]), {
                            "name": name.strip(), "brand": brand.strip(), "category": category.strip(), "size": size.strip(),
                            "cost": cost, "list_price": list_price, "location": location.strip(), "notes": notes.strip()
                        }, new_image)
                        st.success("商品情報を更新しました。")

                if st.button("この商品を削除", key=f"delete_{int(row['id'])}"):
                    delete_item(int(row["id"]))
                    st.warning("商品を削除しました。ページを再読込すると一覧に反映されます。")

elif page == "販売取消・返品":
    st.subheader("販売取消 / 返品")
    sold_like = df[df["status"].isin(["販売済み", "返品"])].copy() if not df.empty else pd.DataFrame()
    if sold_like.empty:
        st.info("対象データがありません。")
    else:
        sold_like["label"] = sold_like.apply(lambda r: f"{r['item_code']} | {r['brand'] or '-'} | {r['name']} | {r['status']} | {str(r['sold_date'])[:10] if pd.notna(r['sold_date']) else '-'}", axis=1)
        selected = st.selectbox("対象商品", sold_like["label"].tolist())
        row = sold_like[sold_like["label"] == selected].iloc[0]
        c1, c2 = st.columns(2)
        if c1.button("販売取消して在庫に戻す"):
            undo_sale(int(row["id"]), mark_return=False)
            st.success("在庫中に戻しました。")
        if c2.button("返品として記録する"):
            undo_sale(int(row["id"]), mark_return=True)
            st.success("返品ステータスに変更しました。")

elif page == "CSV出力":
    st.subheader("CSVエクスポート")
    if df.empty:
        st.info("出力できるデータがありません。")
    else:
        export_df = df.copy()
        if "created_at" in export_df.columns:
            export_df["created_at"] = export_df["created_at"].astype(str)
        if "sold_date" in export_df.columns:
            export_df["sold_date"] = export_df["sold_date"].astype(str)
        csv_data = export_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button("在庫データをCSVで保存", data=csv_data, file_name="inventory_export.csv", mime="text/csv")
        sold_df = export_df[export_df["status"] == "販売済み"].copy()
        if not sold_df.empty:
            sold_csv = sold_df.to_csv(index=False).encode("utf-8-sig")
            st.download_button("販売データだけCSVで保存", data=sold_csv, file_name="sales_export.csv", mime="text/csv")
