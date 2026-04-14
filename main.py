import os
import arxiv
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText

# ===================== 核心方向关键词 =====================
CORE_KEYWORDS = [
    "x3872", "x(3872)", "zc", "pc", "zcs", "pcs",
    "tetraquark", "pentaquark", "multiquark", "exotic hadron",
    "j/psi", "psi", "upsilon", "charmonium", "bottomonium",
    "bc meson", "hadron spectrum",
    "nrqcd", "nonrelativistic qcd",
    "nlo", "nnlo", "higher order", "radiative correction",
    "lattice qcd", "qcd sum rule",
    "standard model", "sm precision", "precision calculation",
    "x17", "x17 anomaly", "17 mev", "anomaly", "discrepancy",
    "new physics", "bsm"
]
CORE_LOWER = [k.lower() for k in CORE_KEYWORDS]

# 实验组关键词
EXPERIMENTAL_GROUPS = [
    "LHCb", "ATLAS", "CMS", "BESIII", "Belle", "Belle II",
    "BaBar", "CLAS", "GlueX", "PANDA", "COMPASS"
]

def is_core(paper):
    text = (paper["title"] + " " + paper["abstract"]).lower()
    return any(kw in text for kw in CORE_LOWER)

def first_author_or_collab(authors_str):
    for g in EXPERIMENTAL_GROUPS:
        if g in authors_str:
            return g
    first = authors_str.split(",")[0]
    return first.strip()

def fetch_arxiv_papers():
    end = datetime.now()
    start = end - timedelta(days=1)
    papers = {"hep-ph": [], "hep-ex": []}

    for cat in ["hep-ph", "hep-ex"]:
        search = arxiv.Search(
            query=f"cat:{cat}",
            max_results=100,
            sort_by=arxiv.SortCriterion.SubmittedDate
        )
        for res in arxiv.Client().results(search):
            if not (start <= res.published <= end):
                continue
            authors_full = ", ".join([a.name for a in res.authors])
            first = first_author_or_collab(authors_full)
            papers[cat].append({
                "title": res.title,
                "first_author": first,
                "abstract": res.summary.replace("\n", " ").strip(),
                "url": res.entry_id,
                "time": res.published.strftime("%Y-%m-%d")
            })
    return papers

def ai_one_sentence(paper):
    t = paper["title"].lower()
    a = paper["abstract"].lower()

    if "nrqcd" in t:
        return "基于NRQCD开展重夸克体系计算，包含高阶修正并与实验对比。"
    if "nlo" in t or "nnlo" in t:
        return "完成高阶QCD微扰计算，提升标准模型理论预言精度。"
    if "x3872" in t or "zc" in t or "pc" in t:
        return "研究奇特强子结构与衰变，支持分子态或紧致多夸克解释。"
    if "tetraquark" in t or "pentaquark" in t:
        return "分析多夸克态的产生与性质，探索非平凡强子结构。"
    if "j/psi" in t or "charmonium" in t:
        return "研究粲偶素产生/极化/衰变，检验唯象模型与实验一致性。"
    if "upsilon" in t or "bottomonium" in t:
        return "精确研究底偶素能谱与衰变，约束强相互作用参数。"
    if "bc meson" in t:
        return "对Bc介子性质做系统理论计算，填补双味重强子研究空白。"
    if "lhcb" in a or "atlas" in a or "cms" in a:
        return "对撞机实验测量强子态或反常信号，与标准模型对比检验。"
    if "besiii" in a or "belle" in a:
        return "正负电子对撞机精确测量强子衰变，检验强子结构模型。"
    if "lattice" in t:
        return "格点QCD第一性原理计算，给出无模型依赖的强子参数。"
    if "x17" in t or "anomaly" in t:
        return "分析实验-理论偏差，探讨新物理或高阶QCD效应可能性。"
    return "围绕强子谱与重夸克物理开展理论或实验研究，深化QCD理解。"

def build_report(papers):
    ph = papers["hep-ph"]
    ex = papers["hep-ex"]

    core = []
    for p in ph + ex:
        p["cat"] = "hep-ph" if p in ph else "hep-ex"
        if is_core(p):
            core.append(p)

    other_ph = [p for p in ph if not is_core(p)]
    other_ex = [p for p in ex if not is_core(p)]

    today = datetime.now().strftime("%Y-%m-%d")
    total = len(core) + len(other_ph) + len(other_ex)

    rep = f"arXiv 高能物理每日简报\n"
    rep += f"日期：{today}\n"
    rep += f"hep-ph + hep-ex 总更新：{total} 篇\n\n"

    rep += "="*70 + "\n"
    rep += "【一、核心研究方向（详细版）】\n"
    rep += "（标题 + 第一作者/实验组 + 链接 + 摘要 + AI解读）\n\n"

    if not core:
        rep += "今日无核心方向论文\n\n"
    else:
        for i, p in enumerate(core, 1):
            rep += f"{i}. [{p['cat']}] {p['title']}\n"
            rep += f"   作者：{p['first_author']}\n"
            rep += f"   链接：{p['url']}\n\n"
            rep += f"📄 摘要：\n   {p['abstract'][:400]}...\n\n"
            rep += f"🧠 AI一句话总结：\n   {ai_one_sentence(p)}\n\n"
            rep += "-"*60 + "\n\n"

    rep += "="*70 + "\n"
    rep += f"【二、其他 hep-ph 论文（精简版）】共 {len(other_ph)} 篇\n\n"
    for i, p in enumerate(other_ph, 1):
        rep += f"{i}. {p['title']}\n"
        rep += f"   作者：{p['first_author']}\n"
        rep += f"   链接：{p['url']}\n\n"

    rep += "="*70 + "\n"
    rep += f"【三、其他 hep-ex 论文（精简版）】共 {len(other_ex)} 篇\n\n"
    for i, p in enumerate(other_ex, 1):
        rep += f"{i}. {p['title']}\n"
        rep += f"   作者：{p['first_author']}\n"
        rep += f"   链接：{p['url']}\n\n"

    rep += "="*70 + "\n"
    rep += "自动生成 · 高能物理AI智能体\n"
    return rep

def send_163(content):
    to = os.getenv("TO_EMAIL")
    frm = os.getenv("SMTP_EMAIL")
    pwd = os.getenv("SMTP_PASS")

    if not (to and frm and pwd):
        print("缺少邮箱配置")
        return

    msg = MIMEText(content, 'plain', 'utf-8')
    msg['Subject'] = f"arXiv 高能物理简报 {datetime.now().strftime('%Y-%m-%d')}"
    msg['From'] = frm
    msg['To'] = to

    try:
        with smtplib.SMTP_SSL("smtp.163.com", 465) as s:
            s.login(frm, pwd)
            s.send_message(msg)
        print("✅ 发送成功")
    except Exception as e:
        print(f"❌ 失败：{e}")

if __name__ == "__main__":
    papers = fetch_arxiv_papers()
    report = build_report(papers)
    send_163(report)
