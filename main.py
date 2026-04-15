import smtplib
from email.mime.text import MIMEText
from email.utils import formatdate
from datetime import datetime, timedelta, timezone
import os
import requests
from bs4 import BeautifulSoup

# ========== 配置（完全按你要求的网址） ==========
CATEGORIES = {
    "Experiment (hep-ex)": "hep-ex",
    "Phenomenology (hep-ph)": "hep-ph"
}
# 抓取最近1天的文章（和你原来的逻辑一致，可改）
DAYS_BACK = 1

SMTP_SERVER = os.getenv('EMAIL_HOST', 'smtp.163.com')
SMTP_PORT = int(os.getenv('EMAIL_PORT', 465))
SENDER_EMAIL = os.getenv('EMAIL_USER')
APP_PASSWORD = os.getenv('EMAIL_PASSWORD')
RECEIVER_EMAIL = os.getenv('EMAIL_TO')

# ========== 时间窗口 ==========
def get_time_window(days=1):
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    return start, now

# ========== 作者精简：实验合作组优先，理论前3位+et al. ==========
def format_authors(authors_raw, category_code):
    if not authors_raw:
        return "No authors"
    # 分割作者列表
    authors = [a.strip() for a in authors_raw.split(",") if a.strip()]
    
    # hep-ex 实验文章：优先显示 Collaboration
    if category_code == "hep-ex":
        for name in authors:
            if "Collaboration" in name:
                return name
        if len(authors) > 1:
            return f"{authors[0]} et al."
        else:
            return authors[0] if authors else "No authors"
    
    # hep-ph 理论文章：最多显示前3位，超过加 et al.
    if len(authors) <= 3:
        return ", ".join(authors)
    else:
        return ", ".join(authors[:3]) + " et al."

# ========== 核心抓取：从你指定的 /new 页面完整爬取 ==========
def fetch_papers(category_code):
    # 完全按你给的网址：arxiv.org/list/hep-ph/new / hep-ex/new
    url = f"https://arxiv.org/list/{category_code}/new?skip=0&show=500"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=120)
        resp.raise_for_status()  # 捕获请求错误
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        print(f"❌ {category_code} 请求失败: {str(e)}")
        return []

    papers = []
    start, end = get_time_window(DAYS_BACK)

    # 每篇论文对应一个 <dt> 标签
    for dt in soup.find_all("dt"):
        try:
            # 1. 提取 arXiv 编号 + 全文链接
            a_abs = dt.find("a", title="Abstract")
            if not a_abs:
                continue
            arxiv_id = a_abs.text.strip()
            full_link = f"https://arxiv.org/abs/{arxiv_id}"

            # 2. 精准识别公告类型：new / cross-list / replacement
            span_id = dt.find("span", class_="list-identifier")
            announce_type = "new"
            if span_id:
                id_text = span_id.text.lower()
                if "replace" in id_text:
                    announce_type = "replacement"
                elif "cross" in id_text:
                    announce_type = "cross-list"

            # 3. 取下一个 <dd> 标签，提取标题、作者、时间
            dd = dt.find_next_sibling("dd")
            if not dd:
                continue

            # 标题
            title_tag = dd.find("div", class_="list-title")
            title = title_tag.text.replace("Title:", "").strip() if title_tag else "No title"

            # 作者
            authors_tag = dd.find("div", class_="list-authors")
            authors_raw = authors_tag.text.replace("Authors:", "").strip() if authors_tag else ""
            authors_short = format_authors(authors_raw, category_code)

            # 提交时间（精准解析）
            dateline = dd.find("div", class_="list-dateline")
            if not dateline:
                continue
            time_str = dateline.text.strip()
            try:
                # 解析 "Submitted 15 April 2026" 格式
                time_part = time_str.replace("Submitted", "").strip()
                pub_time = datetime.strptime(time_part, "%d %B %Y").replace(tzinfo=timezone.utc)
            except Exception as e:
                print(f"⚠️ 时间解析失败: {time_str}, 跳过")
                continue

            # 4. 时间过滤：只保留最近 DAYS_BACK 天的文章
            if not (start <= pub_time <= end):
                continue

            # 5. 存入结果
            papers.append({
                "title": title,
                "arxiv": arxiv_id,
                "announcement_type": announce_type,
                "link": full_link,
                "time": pub_time.strftime("%Y-%m-%d %H:%M UTC"),
                "authors": authors_short
            })
        except Exception as e:
            print(f"⚠️ 单篇论文解析失败: {str(e)}")
            continue

    print(f"✅ {category_code} 抓取完成: {len(papers)} 篇 (new/cross/replace 全覆盖)")
    return papers

# ========== 发送邮件（完全沿用你原来可用的逻辑，保证能发） ==========
def send_email(papers_by_cat):
    total = sum(len(ps) for ps in papers_by_cat.values())
    if total == 0:
        print("ℹ️ 最近1天无新论文，不发送邮件")
        return

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    html = f'''
<html>
<head>
<meta charset="utf-8">
<style>
body {{ font-family: Arial, sans-serif; max-width: 960px; margin: 0 auto; padding: 20px; }}
h1 {{ border-bottom: 2px solid #36c; padding-bottom: 10px; }}
h2 {{ color: #24a; margin-top: 30px; }}
.paper {{
    background: #f7f7f7;
    border-radius: 8px;
    padding: 14px 16px;
    margin: 12px 0;
}}
.title {{ font-size: 16px; font-weight: bold; margin-bottom: 8px; }}
.meta {{ font-size: 13px; color: #555; line-height: 1.5; margin-bottom: 8px; }}
.authors {{ font-size: 14px; color: #222; }}
a {{ color: #0066cc; text-decoration: none; }}
</style>
</head>
<body>
<h1>arXiv High Energy Physics Daily Update {today}</h1>
<p>Source: <a href="https://arxiv.org/list/hep-ph/new" target="_blank">hep-ph/new</a> + <a href="https://arxiv.org/list/hep-ex/new" target="_blank">hep-ex/new</a> (all new/cross/replacement)</p>
'''

    for cat_name, papers in papers_by_cat.items():
        html += f"<h2>{cat_name} • {len(papers)} papers</h2>"
        for idx, p in enumerate(papers, 1):
            html += f'''
<div class="paper">
<div class="title">{idx}. {p['title']}</div>
<div class="meta">
arXiv:{p['arxiv']} &nbsp;|&nbsp; Type: {p['announcement_type']} &nbsp;|&nbsp; <a href="{p['link']}" target="_blank">Full text</a><br>
Submitted: {p['time']}
</div>
<div class="authors">Authors: {p['authors']}</div>
</div>
'''

    html += "</body></html>"

    msg = MIMEText(html, 'html', 'utf-8')
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECEIVER_EMAIL
    msg['Subject'] = f"[arXiv] {today} hep-ex + hep-ph ({total} papers)"
    msg['Date'] = formatdate(localtime=True)

    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=120) as server:
            server.login(SENDER_EMAIL, APP_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        print("✅ 邮件发送成功！")
    except Exception as e:
        print(f"❌ 邮件发送失败: {str(e)}")

# ========== 主入口 ==========
if __name__ == "__main__":
    print("🚀 开始从 arXiv /new 页面抓取论文...")
    result = {name: fetch_papers(code) for name, code in CATEGORIES.items()}
    send_email(result)
    print("🏁 任务完成")
