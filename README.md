# 我的记账本

一个基于 Streamlit 的个人在线记账小程序，使用 Google Sheets 作为数据库。

## 功能

- 记录收入 / 支出，保存到 Google Sheets
- 自定义记账周期（方便按发薪日统计）
- 按记账月查看收入、支出、结余
- 分类支出统计图表
- 适合手机和电脑使用
- 简单密码保护

## 本地运行

1. 克隆项目，安装依赖：
   ```bash
   pip install -r requirements.txt
   ```

2. 配置密钥：
   ```bash
   cp .streamlit/secrets.toml.example .streamlit/secrets.toml
   ```
   编辑 `.streamlit/secrets.toml`，填入真实值：
   - `APP_PASSWORD`：登录密码
   - `SHEET_ID`：Google Sheets 的 ID（从表格 URL 中获取）
   - `gcp_service_account`：Google Cloud 服务账号的 JSON 凭据

3. 在 Google Sheets 中创建表格，第一行表头：`timestamp, date, type, category, amount, payment_method, note`

4. 将服务账号邮箱添加为表格的编辑者。

5. 启动：
   ```bash
   streamlit run app.py
   ```

## 部署到 Streamlit Community Cloud

1. 将项目推送到 GitHub。
2. 在 [Streamlit Community Cloud](https://streamlit.io/cloud) 中连接仓库。
3. 在 App Settings → Secrets 中粘贴 `.streamlit/secrets.toml` 的内容。
4. 部署即可。
