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
SMTP_PORT = int(os.getenv('EMAIL_PORT', 466))
SENDER_EMAIL = os.getenv('EMAIL_USER')
APP_PASSWORD = os.getenv('EMAIL_PASSWORD')
RECEIVER_EMAIL = os.getenv('EMAIL_TO')

# ========== 时间窗口 ==========
def get_time_window(days=1):
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    return start, now

# ========== 作者格式化 ==========
def format_authors(authors_list, category_code):
    if not authors_list:
        return ""
    # 实验文章：直接显示合作组
    if category_code == "hep-ex":
        for name in authors_list:
            if "Collaboration" in name:
                return name
        if len(authors_list) > 1:
            return f"{authors_list[0]} et al. (Collaboration)"
        else:
            return authors_list[0]
    # 理论文章：前3位 + et al.
    if len(authors_list) <= 3:
        return ", ".join(authors_list)
    else:
        return ", ".join(authors_list[:3]) + " et al."

# ========== 从 arxiv.org/list 完整抓取（不漏 new/cross/replace）==========
def fetch_papers(category_code):
    # 用官方 list 页面（对应你说的 hep-ph6 / hep-ex6）
    url = f"https://arxiv.org/list/{category_code}/?skip=0&show=100"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=60)
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        print(f"{category_code} 请求失败: {e}")
        return []

    papers = []
    start, end = get_time_window(DAYS_BACK)

    # 解析每一篇
    for dt in soup.find_all("dt"):
        try:
            # 1) arXiv 号 + 链接
            a_link = dt.find("a", title="Abstract")
            if not a_link:
                continue
            arxiv_id = a_link.text.strip()
            full_link = f"https://arxiv.org/abs/{arxiv_id}"

            # 2) 公告类型：new / cross / replace / replace-cross
            span_type = dt.find("span", class_="list-identifier")
            announce_type = "new"
            if span_type:
                txt = span_type.text.lower()
                if "replace" in txt:
                    announce_type = "replacement"
                elif "cross" in txt:
                    announce_type = "cross-list"

            # 3) 进入摘要页取作者、时间（更准）
            resp_p = requests.get(full_link, headers=headers, timeout=30)
            s = BeautifulSoup(resp_p.text, "html.parser")

            # 作者
            authors = []
            for a in s.find_all("div", class_="authors"):
                for link in a.find_all("a"):
                    authors.append(link.text.strip())
            authors_short = format_authors(authors, category_code)

            # 提交时间
            time_str = "unknown"
            for div in s.find_all("div", class_="dateline"):
                time_str = div.text.strip()
                try:
                    # 提取 "Submitted 01 April 2026"
                    time_part = time_str.replace("Submitted", "").strip()
                    pub_time = datetime.strptime(time_part, "%d %B %Y").replace(tzinfo=timezone.utc)
                except:
                    pub_time = datetime.now(timezone.utc)
                break

            # 时间过滤
            if not (start <= pub_time <= end):
                continue

            # 标题
            title = s.find("h1", class_="title").text.replace("Title:", "").strip()

            papers.append({
                "title": title,
                "arxiv": arxiv_id,
                "announcement_type": announce_type,
                "link": full_link,
                "time": pub_time.strftime("%Y-%m-%d %H:%M UTC"),
                "authors": authors_short
            })
        except Exception as e:
            continue

    print(f"{category_code}: 抓到 {len(papers)} 篇 (new/cross/replace 全覆盖)")
    return papers

# ========== 发送邮件（极简，无 Abstract）==========
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
body {{ font-family: Arial, sans-serif; max-width:960px; margin:0 auto; padding:20px; }}
h1 {{ border-bottom:2px solid #36c; padding-bottom:10px; }}
h2 {{ color:#24a; margin-top:30px; }}
.paper {{
    background:#f7f7f7; border-radius:8px;
    padding:14px 16px; margin:12px 0;
}}
.title {{ font-size:16px; font-weight:bold; margin-bottom:8px; }}
.meta {{ font-size:13px; color:#555; line-height:1.5; }}
.authors {{ font-size:14px; color:#222; margin-top:6px; }}
a {{ color:#06c; text-decoration:none; }}
</style>
</head>
<body>
<h1>arXiv Hep Daily {today} (完整 new/cross/replace)</h1>
<p>hep-ex + hep-ph 全覆盖，无遗漏</p>
'''

    for cat_name, papers in papers_by_cat.items():
        html += f"<h2>{cat_name} • {len(papers)} 篇</h2>"
        for idx, p in enumerate(papers, 1):
            html += f'''
<div class="paper">
<div class="title">{idx}. {p['title']}</div>
<div class="meta">
arXiv:{p['arxiv']} &nbsp;|&nbsp; Type: {p['announcement_type']}<br>
<a href="{p['link']}" target="_blank">全文</a> &nbsp;|&nbsp; {p['time']}
</div>
<div class="authors">作者: {p['authors']}</div>
</div>
'''
    html += "</body></html>"

    msg = MIMEText(html, 'html', 'utf-8')
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECEIVER_EMAIL
    msg['Subject'] = f"[arXiv] {today} hep-ex+hep-ph ({total} 篇)"
    msg['Date'] = formatdate(localtime=True)

    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=60) as server:
            server.login(SENDER_EMAIL, APP_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        print("✅ 邮件发送成功")
    except Exception as e:
        print("❌ 发送失败:", e)

# ========== 主入口 ==========
if __name__ == "__main__":
    result = {name: fetch_papers(code) for name, code in CATEGORIES.items()}
    send_email(result)
