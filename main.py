import feedparser
import smtplib
from email.mime.text import MIMEText
from email.utils import formatdate
from datetime import datetime, timedelta, timezone
import os
import requests
from bs4 import BeautifulSoup

# ========== 配置区 ==========
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

# ========== 时间函数 ==========
def get_time_window(days=1):
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(days=days)
    return start_time, now

# ========== 抓取论文 ==========
def fetch_papers(category_code):
    url = f"http://export.arxiv.org/api/query?search_query=cat:{category_code}&sortBy=submittedDate&sortOrder=descending"
    try:
        resp = requests.get(url, timeout=60)
        feed = feedparser.parse(resp.content)
    except:
        return []

    papers = []
    start, end = get_time_window(DAYS_BACK)

    for entry in feed.entries:
        try:
            pub_time = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        except:
            pub_time = datetime.strptime(entry.published, "%a, %d %b %Y %H:%M:%S %z").replace(tzinfo=timezone.utc)

        if not (start <= pub_time <= end):
            continue

        authors = entry.authors if hasattr(entry, "authors") else []
        author_names = [a.name for a in authors]
        author_str = ", ".join(author_names)

        summary = BeautifulSoup(entry.summary, "html.parser").get_text(strip=True).replace("\n", " ")

        papers.append({
            "title": entry.title.strip(),
            "authors": author_str,
            "summary": summary,
            "link": entry.link,
            "time": pub_time.strftime("%Y-%m-%d %H:%M UTC")
        })

    print(f"{category_code} → {len(papers)} 篇")
    return papers

# ========== 发送邮件 ==========
def send_email(papers_by_cat):
    total = sum(len(p) for p in papers_by_cat.values())
    if total == 0:
        print("无新论文")
        return

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    html = f"""
<html>
<head>
<meta charset="utf-8">
<style>
body {{ font-family: Arial, sans-serif; max-width: 1000px; margin: 0 auto; padding: 20px; }}
h1 {{ border-bottom: 2px solid #44a; padding-bottom: 10px; }}
h2 {{ color: #2255aa; margin-top: 30px; }}
.paper {{
    background: #f8f8f8;
    border-radius: 8px;
    padding: 14px 16px;
    margin: 12px 0;
}}
.title {{ font-size: 16px; font-weight: bold; margin-bottom: 6px; }}
.meta {{ font-size: 13px; color: #666; margin-bottom: 8px; }}
.toggle {{
    color: #0066cc;
    cursor: pointer;
    font-size: 14px;
    user-select: none;
    margin: 4px 0;
    display: inline-block;
}}
.extra {{
    margin-top: 6px;
    display: none;
    font-size: 14px;
    line-height: 1.6;
}}
.authors {{ color: #333; margin-bottom: 8px; }}
.summary {{ color: #222; white-space: pre-wrap; }}
a {{ color: #0066cc; text-decoration: none; }}
</style>

<script>
function toggle(id) {{
    var e = document.getElementById(id);
    e.style.display = e.style.display === 'none' ? 'block' : 'none';
}}
</script>
</head>

<body>
<h1>arXiv High Energy Physics Daily Update {today}</h1>
<p>Experiment (hep-ex) & Phenomenology (hep-ph) only.</p>
"""

    for cat_name, papers in papers_by_cat.items():
        html += f"<h2>{cat_name}  •  {len(papers)} papers</h2>"
        for i, p in enumerate(papers, 1):
            uid_auth = f"auth_{i}_{hash(p['link']) % 99999}"
            uid_abst = f"abst_{i}_{hash(p['link']) % 99999}"

            html += f'''
<div class="paper">
<div class="title">{i}. {p['title']}</div>
<div class="meta">
  <a href="{p['link']}" target="_blank">Full text</a> &nbsp;|&nbsp; {p['time']}
</div>

<div class="toggle" onclick="toggle('{uid_auth}')">▼ Authors</div>
<div class="extra" id="{uid_auth}">
  <div class="authors">{p['authors']}</div>
</div>

<div style="margin-top:6px;"></div>

<div class="toggle" onclick="toggle('{uid_abst}')">▼ Abstract</div>
<div class="extra" id="{uid_abst}">
  <div class="summary">{p['summary']}</div>
</div>

</div>
'''

    html += "</body></html>"

    msg = MIMEText(html, 'html', 'utf-8')
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECEIVER_EMAIL
    msg['Subject'] = f"[arXiv] {today}  hep-ex + hep-ph  ({total} papers)"
    msg['Date'] = formatdate(localtime=True)

    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=60) as s:
            s.login(SENDER_EMAIL, APP_PASSWORD)
            s.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        print("✅ 邮件发送成功")
    except Exception as e:
        print("❌ 发送失败", e)

# ========== 主程序 ==========
if __name__ == "__main__":
    result = {name: fetch_papers(code) for name, code in CATEGORIES.items()}
    send_email(result)
