import feedparser
import email
import smtplib
from email.mime.text import MIMEText
from email.utils import formatdate
from datetime import datetime, timedelta, timezone
import os
import requests
from bs4 import BeautifulSoup

# --- 配置区 (请根据需要修改) ---
# 1. arXiv 分类订阅 (可添加多个，如 'cs.AI', 'hep-th', 'q-bio' 等)
CATEGORIES = ['hep-ph', 'hep-ex', 'hep-lat', 'hep-th']
# 2. 时间范围：抓取过去 N 天内的论文 (建议设为 1 或 2，避免邮件过长)
DAYS_BACK = 1
# 3. 邮箱配置 (从环境变量读取，无需修改)
SMTP_SERVER = os.getenv('EMAIL_HOST', 'smtp.163.com')
SMTP_PORT = int(os.getenv('EMAIL_PORT', 465))
SENDER_EMAIL = os.getenv('EMAIL_USER')
APP_PASSWORD = os.getenv('EMAIL_PASSWORD')
RECEIVER_EMAIL = os.getenv('EMAIL_TO')

# --- 核心修复：统一时区处理 ---
def get_time_window(days=1):
    """
    获取时间窗口的起始和结束时间，并强制带上时区信息 (UTC)。
    修复了原代码无时区导致的对比错误。
    """
    # 获取当前 UTC 时间
    now = datetime.now(timezone.utc)
    # 计算起始时间 (N天前的同一时刻)
    start_time = now - timedelta(days=days)
    # arXiv API 返回的时间格式通常是 RFC 822，需解析为 aware datetime
    return start_time, now

def fetch_arxiv_papers():
    base_url = "http://export.arxiv.org/api/query?"
    # 构建搜索查询：搜索多个分类
    search_query = " OR ".join([f"cat:{cat}" for cat in CATEGORIES])
    # 排序方式：最后提交时间
    query = f"search_query={search_query}&sortBy=submittedDate&sortOrder=descending&max_results=200"

    try:
        # 设置超时时间，防止卡死
        response = requests.get(base_url + query, timeout=30)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
    except Exception as e:
        print(f"请求 arXiv API 失败: {e}")
        return []

    papers = []
    start_time, end_time = get_time_window(DAYS_BACK)

    for entry in feed.entries:
        # 关键修复：统一将 published 解析为带时区的 datetime
        try:
            # arXiv published 时间通常是 UTC，解析时强制指定 tzinfo
            published_time = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        except AttributeError:
            # 备用方案，如果没有 published_parsed，尝试解析字符串
            published_time = datetime.strptime(entry.published, "%a, %d %b %Y %H:%M:%S %z").replace(tzinfo=timezone.utc)

        # 现在两边都是 offset-aware 时间，可以安全对比
        if start_time <= published_time <= end_time:
            # 清洗摘要 (去除 HTML 标签)
            summary = BeautifulSoup(entry.summary, "html.parser").get_text().strip()
            
            paper = {
                'title': entry.title.strip(),
                'authors': entry.author if hasattr(entry, 'author') else ', '.join([a.name for a in entry.authors]),
                'summary': summary,
                'link': entry.link,
                'published': published_time.strftime("%Y-%m-%d %H:%M UTC")
            }
            papers.append(paper)
    
    print(f"共抓取到 {len(papers)} 篇新论文")
    return papers

def send_email(papers):
    if not papers:
        print("暂无新论文，不发送邮件")
        return

    # 构建邮件内容
    html_content = "<html><body style='font-family: Arial, sans-serif;'>"
    html_content += f"<h2>arXiv 高能物理领域新论文速递 ({datetime.now().strftime('%Y-%m-%d')})</h2>"
    
    for i, paper in enumerate(papers, 1):
        html_content += f"""
        <div style='border: 1px solid #e0e0e0; margin: 15px 0; padding: 15px; border-radius: 8px; background-color: #f9f9f9;'>
            <h3 style='color: #2c3e50; margin-top: 0;'>{i}. {paper['title']}</h3>
            <p style='color: #7f8c8d; font-size: 14px;'><strong>作者:</strong> {paper['authors']}</p>
            <p style='color: #34495e; font-size: 15px;'><strong>摘要:</strong> {paper['summary']}</p>
            <p style='font-size: 14px;'><a href='{paper['link']}' style='color: #3498db; text-decoration: none;'>📄 链接</a> | <strong>提交时间:</strong> {paper['published']}</p>
        </div>
        """
    html_content += "</body></html>"

    msg = MIMEText(html_content, 'html', 'utf-8')
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECEIVER_EMAIL
    msg['Subject'] = f"[arXiv-Alert] 发现 {len(papers)} 篇高能物理新论文"
    msg['Date'] = formatdate(localtime=True)

    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
            server.login(SENDER_EMAIL, APP_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        print("邮件发送成功！")
    except Exception as e:
        print(f"邮件发送失败: {e}")

if __name__ == "__main__":
    papers = fetch_arxiv_papers()
    send_email(papers)
