import datetime

import streamlit as st
import pandas as pd
import gspread
from gspread.exceptions import APIError

st.set_page_config(page_title="我的记账本", page_icon="💰", layout="centered")

# ── 密码保护 ──────────────────────────────────────────────
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    st.title("🔐 请输入密码")
    password = st.text_input("密码", type="password")
    if st.button("登录"):
        if password == st.secrets["APP_PASSWORD"]:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("密码错误")
    st.stop()

EXPECTED_HEADERS = ["timestamp", "date", "type", "category", "amount", "payment_method", "note"]

# ── 连接 Google Sheets ─────────────────────────────────────
@st.cache_resource
def get_worksheet():
    service_account = dict(st.secrets["gcp_service_account"])
    gc = gspread.service_account_from_dict(service_account)
    sheet = gc.open_by_key(st.secrets["SHEET_ID"])
    ws = sheet.sheet1
    all_values = ws.get_all_values()
    if not all_values:
        ws.append_row(EXPECTED_HEADERS)
    elif all_values[0] != EXPECTED_HEADERS:
        ws.insert_row(EXPECTED_HEADERS, index=1)
    return ws

@st.cache_resource
def get_settings_ws():
    service_account = dict(st.secrets["gcp_service_account"])
    gc = gspread.service_account_from_dict(service_account)
    sheet = gc.open_by_key(st.secrets["SHEET_ID"])
    try:
        settings = sheet.worksheet("settings")
    except gspread.exceptions.WorksheetNotFound:
        settings = sheet.add_worksheet("settings", rows=2, cols=2)
        settings.append_row(["key", "value"])
    return settings

ws = get_worksheet()
settings_ws = get_settings_ws()

def load_setting(key, default):
    try:
        all_rows = settings_ws.get_all_records()
        for row in all_rows:
            if row["key"] == key:
                return row["value"]
    except (APIError, KeyError):
        pass
    return default

def save_setting(key, value):
    all_rows = settings_ws.get_all_values()
    for i, row in enumerate(all_rows):
        if row[0] == key:
            settings_ws.update(f"B{i + 1}", [[value]])
            return
    settings_ws.append_row([key, value])

# ── 读取全部数据 ───────────────────────────────────────────
@st.cache_data(ttl=10)
def load_data():
    records = ws.get_all_records()
    if not records:
        return pd.DataFrame(columns=["timestamp", "date", "type", "category", "amount", "payment_method", "note"])
    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    return df

df = load_data()

# ── 侧边栏设置 ─────────────────────────────────────────────
st.sidebar.title("⚙️ 设置")

if "start_day" not in st.session_state:
    saved = load_setting("start_day", 1)
    st.session_state["start_day"] = int(saved)

def on_start_day_change():
    save_setting("start_day", st.session_state["start_day"])

start_day = st.sidebar.number_input(
    "记账周期起始日",
    min_value=1, max_value=28,
    step=1,
    key="start_day",
    on_change=on_start_day_change,
)

today = datetime.date.today()
default_month = today.strftime("%Y-%m")
available_months = pd.date_range(end=today, periods=24, freq="MS").strftime("%Y-%m").tolist()[::-1]
billing_month = st.sidebar.selectbox("选择记账月", available_months, index=0)

# 计算实际日期范围
year, month = int(billing_month[:4]), int(billing_month[5:7])
range_start = datetime.date(year, month, start_day)
if month == 12:
    range_end = datetime.date(year + 1, 1, start_day)
else:
    range_end = datetime.date(year, month + 1, start_day)
range_display_end = range_end - datetime.timedelta(days=1)

st.sidebar.info(f"**当前统计范围**\n\n{range_start} 至 {range_display_end}")

# ── 筛选当前周期数据 ───────────────────────────────────────
if not df.empty:
    mask = (df["date"] >= pd.Timestamp(range_start)) & (df["date"] < pd.Timestamp(range_end))
    period_df = df[mask]
else:
    period_df = df

period_income = period_df[period_df["type"] == "income"]["amount"].sum()
period_expense = period_df[period_df["type"] == "expense"]["amount"].sum()
period_balance = period_income - period_expense

# ── 主页面 ─────────────────────────────────────────────────
st.title("💰 我的记账本")

# ── 统计概览 ───────────────────────────────────────────────
st.subheader(f"📊 {billing_month} 记账月概览")
col1, col2, col3 = st.columns(3)
col1.metric("收入", f"¥{period_income:,.2f}")
col2.metric("支出", f"¥{period_expense:,.2f}")
col3.metric("结余", f"¥{period_balance:,.2f}")

st.divider()

# ── 新增记录 ───────────────────────────────────────────────
st.subheader("✏️ 新增记录")
with st.form("new_record", clear_on_submit=True):
    c1, c2 = st.columns(2)
    record_type = c1.selectbox("类型", ["expense", "income"], format_func=lambda x: "支出" if x == "expense" else "收入")
    record_date = c2.date_input("日期", value=today)

    categories = ["餐饮", "交通", "学习", "娱乐", "购物", "住宿", "其他"]
    c3, c4 = st.columns(2)
    record_category = c3.selectbox("分类", categories)
    record_amount = c4.number_input("金额", min_value=0.01, step=0.01, format="%.2f")

    payment_methods = ["微信", "支付宝", "现金", "银行卡"]
    c5, c6 = st.columns(2)
    record_payment = c5.selectbox("支付方式", payment_methods)
    record_note = c6.text_input("备注", placeholder="选填")

    submitted = st.form_submit_button("保存记录", use_container_width=True)
    if submitted:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            ws.append_row([
                timestamp,
                record_date.strftime("%Y-%m-%d"),
                record_type,
                record_category,
                record_amount,
                record_payment,
                record_note,
            ])
            st.cache_data.clear()
            st.success("记录已保存！")
            st.rerun()
        except APIError as e:
            st.error(f"保存失败：{e}")

st.divider()

# ── 分类支出统计 ───────────────────────────────────────────
st.subheader("📈 分类支出统计")
if not period_df.empty:
    expense_by_cat = period_df[period_df["type"] == "expense"].groupby("category")["amount"].sum().sort_values(ascending=True)
    if not expense_by_cat.empty:
        st.bar_chart(expense_by_cat)
    else:
        st.caption("当前周期暂无支出记录")
else:
    st.caption("暂无数据")

st.divider()

# ── 最近记录 ───────────────────────────────────────────────
st.subheader("📋 最近记录")
show_mode = st.radio("显示范围", ["全部最近记录", "当前记账周期内的记录"], horizontal=True, label_visibility="collapsed")

if show_mode == "当前记账周期内的记录":
    display_df = period_df.sort_values("date", ascending=False)
    desc = f"当前周期（{range_start} 至 {range_display_end}）内的记录"
else:
    display_df = df.sort_values("date", ascending=False) if not df.empty else df
    desc = "全部最近记录（最多 50 条）"

st.caption(desc)

if not display_df.empty:
    display_df = display_df.head(50).copy()
    display_df["date"] = display_df["date"].dt.strftime("%Y-%m-%d")
    display_df["type"] = display_df["type"].map({"income": "收入", "expense": "支出"})
    display_df["amount"] = display_df["amount"].apply(lambda x: f"¥{x:,.2f}")
    show_cols = ["date", "type", "category", "amount", "payment_method", "note"]
    st.dataframe(
        display_df[show_cols].rename(columns={
            "date": "日期", "type": "类型", "category": "分类",
            "amount": "金额", "payment_method": "支付方式", "note": "备注"
        }),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.caption("暂无记录")
