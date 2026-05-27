import datetime

import streamlit as st
import pandas as pd
import gspread
from gspread.exceptions import APIError

st.set_page_config(page_title="我的记账本", page_icon="💰", layout="centered")

st.markdown("""
<style>
    header[data-testid="stHeader"] { display: none; }
    html { font-size: 14px; }
    .block-container { padding: 0.5rem 0.75rem 1rem 0.75rem; max-width: 640px; }
    [data-testid="stMetric"] { background: none !important; padding: 4px 0 !important; }
    [data-testid="stMetricLabel"] { font-size: 0.7rem !important; }
    [data-testid="stMetricValue"] { font-size: 1.1rem !important; font-weight: 600 !important; }
    h2 { font-size: 0.9rem !important; margin: 0 0 0.25rem 0 !important; font-weight: 600 !important; }
    hr { margin: 0.4rem 0 !important; opacity: 0.12; }
    .stButton > button { border-radius: 10px !important; font-weight: 500 !important; font-size: 0.9rem !important; }
    [data-testid="stForm"] { border: none !important; padding: 0 !important; }
    [data-testid="stSidebar"] { min-width: 200px !important; max-width: 240px !important; }
    [data-testid="stSidebar"] .block-container { padding: 0.5rem 0.5rem; }
    .stRadio [role="radiogroup"] { gap: 4px; }
    .stRadio label { font-size: 0.85rem !important; }
</style>
""", unsafe_allow_html=True)

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
    all_values = ws.get_all_values()
    if len(all_values) < 2:
        return pd.DataFrame(columns=["timestamp", "date", "type", "category", "amount", "payment_method", "note", "_row"])
    df = pd.DataFrame(all_values[1:], columns=all_values[0])
    df["_row"] = range(2, len(all_values) + 1)
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
EXPENSE_CATEGORIES = ["餐饮", "交通", "学习", "娱乐", "购物", "住宿", "其他", "小金库支出"]
INCOME_CATEGORIES = ["奖学金", "生活费", "兼职", "工资", "红包", "投资", "其他收入", "小金库存入"]
FUND_CATEGORIES = ["小金库存入", "小金库支出"]

if not df.empty:
    mask = (df["date"] >= pd.Timestamp(range_start)) & (df["date"] < pd.Timestamp(range_end))
    period_df = df[mask]
else:
    period_df = df

regular_df = period_df[~period_df["category"].isin(FUND_CATEGORIES)]
period_income = regular_df[regular_df["type"] == "income"]["amount"].sum()
period_expense = regular_df[regular_df["type"] == "expense"]["amount"].sum()
period_balance = period_income - period_expense

period_fund_in = period_df[(period_df["type"] == "income") & (period_df["category"] == "小金库存入")]["amount"].sum()
period_fund_out = period_df[(period_df["type"] == "expense") & (period_df["category"] == "小金库支出")]["amount"].sum()
total_fund = df[(df["type"] == "income") & (df["category"] == "小金库存入")]["amount"].sum() - df[(df["type"] == "expense") & (df["category"] == "小金库支出")]["amount"].sum()
all_regular = df[~df["category"].isin(FUND_CATEGORIES)] if not df.empty else df
total_balance_all = all_regular[all_regular["type"] == "income"]["amount"].sum() - all_regular[all_regular["type"] == "expense"]["amount"].sum()

st.sidebar.divider()
st.sidebar.metric("🏦 小金库余额", f"¥{total_fund:,.2f}")
st.sidebar.caption(f"本期存入 ¥{period_fund_in:,.2f} ｜ 本期支出 ¥{period_fund_out:,.2f}")
col_s1, col_s2 = st.sidebar.columns(2)
if col_s1.button("＋ 存入", use_container_width=True):
    st.session_state["show_form"] = True
    st.session_state["fund_quick"] = "deposit"
    st.rerun()
if col_s2.button("－ 支出", use_container_width=True):
    st.session_state["show_form"] = True
    st.session_state["fund_quick"] = "expense"
    st.rerun()

# ── 主页面 ─────────────────────────────────────────────────
# 当前总余额
st.markdown(f"<h1 style='text-align:center;font-size:2.2rem;margin:0.25rem 0 0 0;font-weight:700;'>¥{total_balance_all:,.2f}</h1>", unsafe_allow_html=True)
st.markdown(f"<p style='text-align:center;color:#8e8e93;margin:0 0 0.5rem 0;font-size:0.8rem;'>当前总余额</p>", unsafe_allow_html=True)

# 本月概览
col1, col2, col3 = st.columns(3)
col1.metric("本月收入", f"¥{period_income:,.2f}")
col2.metric("本月支出", f"¥{period_expense:,.2f}")
col3.metric("本月结余", f"¥{period_balance:,.2f}")

st.divider()

# ── 最近记录 ──
st.subheader("📋 最近记录")
show_mode = st.radio("显示范围", ["全部最近记录", "当前记账周期内的记录"], horizontal=True, label_visibility="collapsed")

if show_mode == "当前记账周期内的记录":
    display_df = period_df.sort_values("date", ascending=False)
    desc = f"当前周期（{range_start} 至 {range_display_end}）内的记录"
else:
    display_df = df.sort_values("date", ascending=False) if not df.empty else df
    desc = "全部最近记录（最多 50 条）"

st.caption(desc)

type_filter = st.radio("类型筛选", ["全部", "仅支出", "仅收入"], horizontal=True, key="type_filter", label_visibility="collapsed")

if not display_df.empty:
    display_df = display_df.head(50).copy()
    if type_filter == "仅支出":
        display_df = display_df[display_df["type"] == "expense"]
    elif type_filter == "仅收入":
        display_df = display_df[display_df["type"] == "income"]
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

# ── ＋ 记一笔 ──
if "show_form" not in st.session_state:
    st.session_state["show_form"] = False

_, btn_col, _ = st.columns([1, 2, 1])
if btn_col.button("＋ 记一笔", use_container_width=True, type="primary"):
    st.session_state["show_form"] = not st.session_state["show_form"]

if st.session_state["show_form"]:
    st.divider()
    st.subheader("✏️ 新增记录")
    quick = st.session_state.pop("fund_quick", None)
    if quick:
        st.session_state["record_type"] = "income" if quick == "deposit" else "expense"
    if "record_type" not in st.session_state:
        st.session_state["record_type"] = "expense"
    record_type = st.selectbox(
        "类型", ["expense", "income"],
        format_func=lambda x: "支出" if x == "expense" else "收入",
        key="record_type",
    )
    categories = EXPENSE_CATEGORIES if record_type == "expense" else INCOME_CATEGORIES
    preset_cat = "小金库存入" if quick == "deposit" else ("小金库支出" if quick == "expense" else None)
    cat_index = categories.index(preset_cat) if preset_cat and preset_cat in categories else 0
    with st.form("new_record", clear_on_submit=True):
        c1, c2 = st.columns(2)
        record_date = c1.date_input("日期", value=today)
        record_category = c2.selectbox("分类", categories, index=cat_index)
        c3, c4 = st.columns(2)
        record_amount = c3.number_input("金额", min_value=0.01, step=0.01, format="%.2f")
        payment_methods = ["微信", "支付宝", "现金", "银行卡"]
        record_payment = c4.selectbox("支付方式", payment_methods)
        record_note = st.text_input("备注", placeholder="选填")
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
                st.session_state["show_form"] = False
                st.success("记录已保存！")
                st.rerun()
            except APIError as e:
                st.error(f"保存失败：{e}")

# ── 分类统计 ──
with st.expander("📈 分类统计"):
    if not regular_df.empty:
        expense_by_cat = regular_df[regular_df["type"] == "expense"].groupby("category")["amount"].sum().sort_values(ascending=True)
        if not expense_by_cat.empty:
            st.bar_chart(expense_by_cat)
        else:
            st.caption("当前周期暂无支出记录")
    else:
        st.caption("暂无数据")

# ── 删除记录 ──
with st.expander("🗑️ 删除记录"):
    if not df.empty:
        del_candidates = df.sort_values("date", ascending=False).head(50)
        del_labels = del_candidates.apply(
            lambda r: f"行{int(r['_row'])} - {r['date'].strftime('%Y-%m-%d')} - {'收入' if r['type']=='income' else '支出'} - {r['category']} - ¥{r['amount']:,.2f}",
            axis=1,
        ).tolist()
        del_selected = st.selectbox("选择要删除的记录", del_labels, key="del_select")
        if st.button("删除选中记录", type="primary", key="del_btn"):
            row_num = int(del_selected.split(" - ")[0].replace("行", ""))
            try:
                ws.delete_rows(row_num)
                st.cache_data.clear()
                st.success("已删除")
                st.rerun()
            except APIError as e:
                st.error(f"删除失败：{e}")
    else:
        st.caption("暂无记录可删除")
