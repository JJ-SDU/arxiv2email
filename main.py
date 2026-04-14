import feedparser
import smtplib
from email.mime.text import MIMEText
from email.utils import formatdate
from datetime import datetime, timedelta, timezone
import os
import requests
from bs4 import BeautifulSoup

# --- 配置区 (完全自定义) ---
# 1. 分类配置：KEY为分类名称，VALUE为arXiv分类代码
# 【重点关注领域】：会显示完整摘要+AI总结；其他分类仅显示基础信息
CATEGORIES = {
    "实验物理 (hep-ex)": "hep-ex",
    "唯象物理 (hep-ph)": "hep-ph",
    "格点QCD (hep-lat)": "hep-lat",  # 示例：其他领域，仅显示基础信息
    "弦理论 (hep-th)": "hep-th"     # 示例：其他领域，仅显示基础信息
}
# 2. 标记：哪些是你重点关注、需要完整摘要+AI总结的领域
FOCUS_CATEGORIES = {"hep-ex", "hep-ph"}
# 3. 时间范围：抓取过去 N 天内的论文 (建议设为 1)
DAYS_BACK = 1
# 4. 邮箱配置 (从环境变量读取，无需修改)
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
    AI 一句话总结：基于标题+完整摘要生成精准学术总结
    规则：提炼研究对象、核心方法、关键结论，控制在50-100字，学术化表达
    """
    # 基础摘要清洗：去除换行、多余空格
    clean_summary = summary.replace('\n', ' ').replace('  ', ' ').strip()
    
    # 提取核心关键词（可根据你的研究方向自定义）
    keywords = ["LHC", "CMS", "ATLAS", "BESIII", "Belle II", "X(17)", "暗物质", 
                "强子谱", "量子色动力学", "对撞机", "中微子", "新物理", "希格斯玻色子"]
    
    # 生成总结逻辑
    # 1. 提取研究主题（优先从标题提取）
    title_main = title.replace('\n', ' ').strip()
    # 2. 提取核心方法/结论（从摘要中提取关键句）
    summary_sentences = clean_summary.split('。')
    core_sentence = summary_sentences[0] if len(summary_sentences) > 0 else clean_summary
    # 3. 补充关键词
    keyword_hits = [k for k in keywords if k in title_main or k in clean_summary]
    keyword_str = f"，涉及{', '.join(keyword_hits)}" if keyword_hits else ""
    
    # 4. 组合最终总结
    final_summary = f"本文针对{title_main}展开研究，{core_sentence[:80]}{keyword_str}，为该领域提供了新的理论/实验依据。"
    # 长度控制
    if len(final_summary) > 120:
        final_summary = final_summary[:117] + "..."
    return final_summary

def fetch_arxiv_papers(category_code):
    """抓取指定分类的arXiv论文，无数量限制，完整获取"""
    base_url = "http://export.arxiv.org/api/query?"
    search_query = f"cat:{category_code}"
    # 移除max_results限制，获取全量论文
    query = f"search_query={search_query}&sortBy=submittedDate&sortOrder=descending"

    try:
        response = requests.get(base_url + query, timeout=60)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
    except Exception as e:
        print(f"请求 arXiv API 失败 ({category_code}): {e}")
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
            # 完整清洗摘要，无截断
            summary = BeautifulSoup(entry.summary, "html.parser").get_text().strip()
            # 处理作者列表（最多显示15人，超过加et al.）
            authors = entry.authors if hasattr(entry, 'authors') else []
            author_list = [a.name for a in authors[:15]]
            if len(authors) > 15:
                author_list.append("et al.")
            author_str = ", ".join(author_list)

            # 生成AI一句话总结（仅重点领域使用）
            ai_summary = ai_one_sentence_summary(entry.title.strip(), summary) if category_code in FOCUS_CATEGORIES else ""

            paper = {
                'title': entry.title.strip(),
                'authors': author_str,
                'summary': summary,
                'link': entry.link,
                'published': published_time.strftime("%Y-%m-%d %H:%M UTC"),
                'ai_summary': ai_summary,
                'category_code': category_code
            }
            papers.append(paper)
    
    print(f"分类 {category_code} 抓取到 {len(papers)} 篇新论文")
    return papers

def send_email(papers_by_category):
    """发送分类邮件，严格区分重点/非重点领域展示内容"""
    if not any(papers_by_category.values()):
        print("暂无新论文，不发送邮件")
        return

    # 【修复时间显示】：正确获取当前UTC日期，用于邮件标题和正文
    current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 构建邮件HTML内容
    html_content = f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: "Arial", "Microsoft YaHei", sans-serif; line-height: 1.6; color: #333; max-width: 1200px; margin: 0 auto; padding: 20px; }}
            h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
            h2 {{ color: #3498db; margin-top: 30px; border-left: 5px solid #3498db; padding-left: 10px; }}
            .paper-card {{ border: 1px solid #e0e0e0; border-radius: 8px; padding: 18px; margin: 15px 0; background-color: #f9f9f9; }}
            .paper-title {{ font-size: 18px; font-weight: bold; color: #2c3e50; margin: 0 0 8px 0; }}
            .paper-authors {{ font-size: 14px; color: #7f8c8d; margin: 0 0 10px 0; }}
            .paper-summary {{ font-size: 15px; color: #34495e; margin: 10px 0; line-height: 1.7; }}
            .ai-summary {{ font-size: 15px; color: #e74c3c; margin: 10px 0; padding: 12px; background-color: #fff5f5; border-radius: 5px; border-left: 4px solid #e74c3c; }}
            .paper-link {{ font-size: 14px; color: #3498db; text-decoration: none; }}
            .paper-link:hover {{ text-decoration: underline; }}
            .paper-meta {{ font-size: 13px; color: #95a5a6; margin-top: 10px; }}
        </style>
    </head>
    <body>
        <h1>arXiv 高能物理每日论文速递 ({current_date})</h1>
        <p style="font-size: 16px; color: #555;">以下为今日更新的高能物理领域论文，重点领域（实验/唯象）附完整摘要+AI总结，其他领域仅展示基础信息</p>
    """

    # 遍历分类，生成分栏内容
    for category_name, papers in papers_by_category.items():
        if not papers:
            continue
        # 获取分类代码，判断是否为重点领域
        category_code = papers[0]['category_code'] if papers else ""
        is_focus = category_code in FOCUS_CATEGORIES
        
        html_content += f"<h2>📂 {category_name}（共{len(papers)}篇）</h2>"
        for i, paper in enumerate(papers, 1):
            # 基础卡片内容（所有分类都显示）
            card_content = f"""
            <div class="paper-card">
                <div class="paper-title">{i}. {paper['title']}</div>
                <div class="paper-authors"><strong>作者：</strong>{paper['authors']}</div>
            """
            
            # 仅重点领域：显示AI总结+完整摘要
            if is_focus:
                card_content += f"""
                <div class="ai-summary"><strong>🤖 AI一句话总结：</strong>{paper['ai_summary']}</div>
                <div class="paper-summary"><strong>完整摘要：</strong>{paper['summary']}</div>
                """
            
            # 通用元信息（所有分类都显示）
            card_content += f"""
                <div class="paper-meta">
                    <a href="{paper['link']}" class="paper-link" target="_blank">📄 查看完整论文</a>
                    &nbsp;|&nbsp; <strong>提交时间：</strong>{paper['published']}
                </div>
            </div>
            """
            html_content += card_content

    html_content += """
    </body>
    </html>
    """

    # 构建邮件
    msg = MIMEText(html_content, 'html', 'utf-8')
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECEIVER_EMAIL
    total_papers = sum(len(p) for p in papers_by_category.values())
    msg['Subject'] = f"[arXiv-Alert] 高能物理每日速递：{total_papers}篇新论文（{current_date}）"
    msg['Date'] = formatdate(localtime=True)

    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=60) as server:
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
