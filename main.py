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
            pub_time = datetime.strptime(entry.published, "%a, %d %b %Y %H:%M:%S %z").replace(tzinfo=timezone.utc)

        if not (start <= pub_time <= end):
            continue

        # 提取 arXiv 号
        arxiv_id = entry.id.split('/abs/')[-1] if '/abs/' in entry.id else ""

        # 作者
        authors = [a.name for a in entry.authors] if hasattr(entry, 'authors') else []
        author_str = ", ".join(authors)

        # 摘要
        summary = BeautifulSoup(entry.summary, "html.parser").get_text(strip=True).replace("\n", " ")

        papers.append({
            "title": entry.title.strip(),
            "authors": author_str,
            "summary": summary,
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
.meta {{ font-size: 13px; color: #555; margin-bottom: 10px; }}
.toggle {{
    color: #0066cc;
    cursor: pointer;
    font-size: 14px;
    margin: 4px 0;
    display: inline-block;
}}
.box {{
    margin-top: 6px;
    display: none;
    font-size: 14px;
    line-height: 1.6;
}}
.authors {{ color: #222; }}
.summary {{ color: #222; white-space: pre-wrap; }}
a {{ color: #0066cc; text-decoration: none; }}
</style>

<script type="text/javascript">
function toggle(id) {{
    var el = document.getElementById(id);
    if (el.style.display === 'none' || el.style.display === '') {{
        el.style.display = 'block';
    }} else {{
        el.style.display = 'none';
    }}
}}
</script>
</head>

<body>
<h1>arXiv High Energy Physics Daily Update {today}</h1>
<p>All papers in hep-ex + hep-ph, no filtering.</p>
'''

    for cat_name, papers in papers_by_cat.items():
        html += f"<h2>{cat_name} • {len(papers)} papers</h2>"
        for idx, p in enumerate(papers, 1):
            id_auth = f"a_{idx}_{hash(p['arxiv']) % 99999}"
            id_abst = f"b_{idx}_{hash(p['arxiv']) % 99999}"

            html += f'''
<div class="paper">
<div class="title">{idx}. {p['title']}</div>
<div class="meta">
arXiv:{p['arxiv']} | <a href="{p['link']}" target="_blank">Full text</a> &nbsp;|&nbsp; {p['time']}
</div>

<div class="toggle" onclick="toggle('{id_auth}')">▼ Authors</div>
<div class="box" id="{id_auth}">
<div class="authors">{p['authors']}</div>
</div>

<div style="height:6px;"></div>

<div class="toggle" onclick="toggle('{id_abst}')">▼ Abstract</div>
<div class="box" id="{id_abst}">
<div class="summary">{p['summary']}</div>
</div>

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
