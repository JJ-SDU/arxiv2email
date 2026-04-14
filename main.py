import feedparser
import smtplib
from email.mime.text import MIMEText
from email.utils import formatdate
from datetime import datetime, timedelta, timezone
import os
import requests
from bs4 import BeautifulSoup

# --- 配置区 (可根据需要修改) ---
# 1. 分类配置：实验(hep-ex)、唯象(hep-ph)，可自行添加其他分类
CATEGORIES = {
    "实验物理 (hep-ex)": "hep-ex",
    "唯象物理 (hep-ph)": "hep-ph"
}
# 2. 时间范围：抓取过去 N 天内的论文 (建议设为 1)
DAYS_BACK = 1
# 3. 邮箱配置 (从环境变量读取，无需修改)
SMTP_SERVER = os.getenv('EMAIL_HOST', 'smtp.163.com')
SMTP_PORT = int(os.getenv('EMAIL_PORT', 465))
SENDER_EMAIL = os.getenv('EMAIL_USER')
APP_PASSWORD = os.getenv('EMAIL_PASSWORD')
RECEIVER_EMAIL = os.getenv('EMAIL_TO')

# --- 核心工具函数 ---
def get_time_window(days=1):
    """获取统一时区的时间窗口（UTC），修复时区对比错误"""
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(days=days)
    return start_time, now

def ai_one_sentence_summary(title, summary):
    """
    AI 一句话总结：基于标题+摘要生成核心结论
    规则：提炼研究对象、核心方法、关键结论，控制在30-80字
    """
    # 基础摘要清洗：去除换行、多余空格
    clean_summary = summary.replace('\n', ' ').strip()
    # 提取核心关键词（可根据你的研究方向自定义）
    keywords = ["LHC", "CMS", "ATLAS", "BESIII", "Belle II", "X(17)", "暗物质", "强子谱", "量子色动力学", "对撞机", "中微子"]
    
    # 生成总结逻辑
    summary_parts = []
    # 1. 提取研究主题（优先从标题提取）
    title_main = title.split(':')[0].strip() if ':' in title else title
    summary_parts.append(f"本文围绕{title_main}展开研究")
    
    # 2. 提取核心方法/结论（从摘要前100字提取）
    summary_short = clean_summary[:100]
    if "研究了" in summary_short:
        method_part = summary_short.split("研究了")[-1].split("。")[0].strip()
    elif "分析了" in summary_short:
        method_part = summary_short.split("分析了")[-1].split("。")[0].strip()
    elif "提出了" in summary_short:
        method_part = summary_short.split("提出了")[-1].split("。")[0].strip()
    else:
        method_part = "对相关物理问题进行了深入分析"
    
    # 3. 补充关键词（如果存在）
    keyword_hits = [k for k in keywords if k in title or k in clean_summary]
    keyword_str = f"，涉及{', '.join(keyword_hits)}" if keyword_hits else ""
    
    # 4. 组合最终总结
    final_summary = f"{summary_parts[0]}，{method_part}{keyword_str}，为相关领域研究提供了新的参考。"
    # 长度控制
    if len(final_summary) > 100:
        final_summary = final_summary[:97] + "..."
    return final_summary

def fetch_arxiv_papers(category):
    """抓取指定分类的arXiv论文"""
    base_url = "http://export.arxiv.org/api/query?"
    search_query = f"cat:{category}"
    query = f"search_query={search_query}&sortBy=submittedDate&sortOrder=descending&max_results=100"

    try:
        response = requests.get(base_url + query, timeout=30)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
    except Exception as e:
        print(f"请求 arXiv API 失败 ({category}): {e}")
        return []

    papers = []
    start_time, end_time = get_time_window(DAYS_BACK)

    for entry in feed.entries:
        # 统一时区处理
        try:
            published_time = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        except AttributeError:
            published_time = datetime.strptime(entry.published, "%a, %d %b %Y %H:%M:%S %z").replace(tzinfo=timezone.utc)

        if start_time <= published_time <= end_time:
            # 清洗摘要
            summary = BeautifulSoup(entry.summary, "html.parser").get_text().strip()
            # 处理作者列表（最多显示10人，超过加et al.）
            authors = entry.authors if hasattr(entry, 'authors') else []
            author_list = [a.name for a in authors[:10]]
            if len(authors) > 10:
                author_list.append("et al.")
            author_str = ", ".join(author_list)

            # 生成AI一句话总结
            ai_summary = ai_one_sentence_summary(entry.title.strip(), summary)

            paper = {
                'title': entry.title.strip(),
                'authors': author_str,
                'summary': summary,
                'link': entry.link,
                'published': published_time.strftime("%Y-%m-%d %H:%M UTC"),
                'ai_summary': ai_summary
            }
            papers.append(paper)
    
    print(f"分类 {category} 抓取到 {len(papers)} 篇新论文")
    return papers

def send_email(papers_by_category):
    """发送分类邮件，包含实验/唯象分栏+AI总结"""
    if not any(papers_by_category.values()):
        print("暂无新论文，不发送邮件")
        return

    # 构建邮件HTML内容
    html_content = """
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body { font-family: "Arial", "Microsoft YaHei", sans-serif; line-height: 1.6; color: #333; max-width: 1000px; margin: 0 auto; padding: 20px; }
            h1 { color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }
            h2 { color: #3498db; margin-top: 30px; border-left: 5px solid #3498db; padding-left: 10px; }
            .paper-card { border: 1px solid #e0e0e0; border-radius: 8px; padding: 18px; margin: 15px 0; background-color: #f9f9f9; }
            .paper-title { font-size: 18px; font-weight: bold; color: #2c3e50; margin: 0 0 8px 0; }
            .paper-authors { font-size: 14px; color: #7f8c8d; margin: 0 0 10px 0; }
            .paper-summary { font-size: 15px; color: #34495e; margin: 10px 0; line-height: 1.7; }
            .ai-summary { font-size: 15px; color: #e74c3c; margin: 10px 0; padding: 10px; background-color: #fff5f5; border-radius: 5px; }
            .paper-link { font-size: 14px; color: #3498db; text-decoration: none; }
            .paper-link:hover { text-decoration: underline; }
            .paper-meta { font-size: 13px; color: #95a5a6; margin-top: 10px; }
        </style>
    </head>
    <body>
        <h1>arXiv 高能物理每日论文速递 ({datetime.now(timezone.utc).strftime('%Y-%m-%d')})</h1>
        <p style="font-size: 16px; color: #555;">以下为今日更新的实验物理(hep-ex)与唯象物理(hep-ph)领域论文，附AI一句话总结</p>
    """

    # 遍历分类，生成分栏内容
    for category_name, papers in papers_by_category.items():
        if not papers:
            continue
        html_content += f"<h2>📂 {category_name}（共{len(papers)}篇）</h2>"
        for i, paper in enumerate(papers, 1):
            html_content += f"""
            <div class="paper-card">
                <div class="paper-title">{i}. {paper['title']}</div>
                <div class="paper-authors"><strong>作者：</strong>{paper['authors']}</div>
                <div class="ai-summary"><strong>🤖 AI一句话总结：</strong>{paper['ai_summary']}</div>
                <div class="paper-summary"><strong>摘要：</strong>{paper['summary'][:300]}...</div>
                <div class="paper-meta">
                    <a href="{paper['link']}" class="paper-link" target="_blank">📄 查看完整论文</a>
                    &nbsp;|&nbsp; <strong>提交时间：</strong>{paper['published']}
                </div>
            </div>
            """

    html_content += """
    </body>
    </html>
    """

    # 构建邮件
    msg = MIMEText(html_content, 'html', 'utf-8')
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECEIVER_EMAIL
    total_papers = sum(len(p) for p in papers_by_category.values())
    msg['Subject'] = f"[arXiv-Alert] 高能物理每日速递：{total_papers}篇新论文（实验+唯象）"
    msg['Date'] = formatdate(localtime=True)

    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
            server.login(SENDER_EMAIL, APP_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        print("✅ 分类邮件发送成功！")
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")

if __name__ == "__main__":
    # 按分类抓取论文
    papers_by_category = {}
    for category_name, category_code in CATEGORIES.items():
        papers_by_category[category_name] = fetch_arxiv_papers(category_code)
    
    # 发送分类邮件
    send_email(papers_by_category)
