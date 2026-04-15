import feedparser
import smtplib
from email.mime.text import MIMEText
from email.utils import formatdate
from datetime import datetime, timedelta, timezone
import os
import requests
from bs4 import BeautifulSoup

# ========== 配置 ==========
CATEGORIES = {
    "Experiment (hep-ex)": "hep-ex",
    "Phenomenology (hep-ph)": "hep-ph"
}
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

# ========== 格式化作者列表：前3位 + et al.，实验合作组直接显示 ==========
def format_authors(authors_list, category_code):
    if not authors_list:
        return ""
    
    # 实验类文章 → 直接按合作组显示
    if category_code == "hep-ex":
        if len(authors_list) > 1:
            return f"{authors_list[0]} et al. (Collaboration)"
        else:
            return authors_list[0]
    
    # 理论类：最多显示前3位，超过加 et al.
    if len(authors_list) <= 3:
        return ", ".join(authors_list)
    else:
        return ", ".join(authors_list[:3]) + " et al."

# ========== 抓取论文 ==========
def fetch_papers(category_code):
    url = f"http://export.arxiv.org/api/query?search_query=cat:{category_code}&sortBy=submittedDate&sortOrder=descending"
    try:
        resp = requests.get(url, timeout=60)
        feed = feedparser.parse(resp.content)
    except Exception as e:
        print(e)
        return []

    papers = []
    start, end = get_time_window(DAYS_BACK)

    for entry in feed.entries:
        try:
            pub_time = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        except:
            pub_time = datetime.strptime(entry.published, "%a, %d %b %Y %:%M:%S %z").replace(tzinfo=timezone.utc)

        if not (start <= pub_time <= end):
            continue

        # arXiv 编号
        arxiv_id = entry.id.split('/abs/')[-1] if '/abs/' in entry.id else ""

        # 作者列表
        authors_raw = [a.name for a in entry.authors] if hasattr(entry, 'authors') else []
        authors_short = format_authors(authors_raw, category_code)

        # 公告类型：new / cross-list / replacement
        announcement_type = "new"
        if hasattr(entry, 'arxiv_announcement_type'):
            announcement_type = entry.arxiv_announcement_type
        elif hasattr(entry, 'title_detail') and 'replacement' in entry.title_detail.value.lower():
            announcement_type = "replacement"
        elif hasattr(entry, 'title_detail') and 'cross-list' in entry.title_detail.value.lower():
            announcement_type = "cross-list"

        # 不再获取摘要
        papers.append({
            "title": entry.title.strip(),
            "authors": authors_short,
            "announcement_type": announcement_type,
            "link": entry.link,
            "arxiv": arxiv_id,
            "time": pub_time.strftime("%Y-%m-%d %H:%M UTC")
        })

    print(f"{category_code}: {len(papers)} papers")
    return papers

# ========== 发送邮件 ==========
def send_email(papers_by_cat):
    total = sum(len(ps) for ps in papers_by_cat.values())
    if total == 0:
        print("No new papers.")
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
.meta {{ font-size: 13px; color: #555; margin-bottom: 10px; line-height:1.5; }}
.authors {{ font-size:14px; color:#222; margin-top:6px; }}
a {{ color: #0066cc; text-decoration: none; }}
</style>
</head>

<body>
<h1>arXiv High Energy Physics Daily Update {today}</h1>
<p>All papers in hep-ex + hep-ph, no filtering.</p>
'''

    for cat_name, papers in papers_by_cat.items():
        html += f"<h2>{cat_name} • {len(papers)} papers</h2>"
        for idx, p in enumerate(papers, 1):
            html += f'''
<div class="paper">
<div class="title">{idx}. {p['title']}</div>
<div class="meta">
arXiv:{p['arxiv']} &nbsp;|&nbsp; Type: {p['announcement_type']} &nbsp;|&nbsp; <a href="{p['link']}" target="_blank">Full text</a><br>
Updated: {p['time']}
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
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=60) as server:
            server.login(SENDER_EMAIL, APP_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        print("✅ Email sent successfully")
    except Exception as e:
        print("❌ Failed:", e)

# ========== 主入口 ==========
if __name__ == "__main__":
    result = {name: fetch_papers(code) for name, code in CATEGORIES.items()}
    send_email(result)
