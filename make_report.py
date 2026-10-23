# -*- coding: utf-8 -*-
"""模块4a：生成单文件 HTML 岗位推荐报告。"""

import html
from datetime import date

import common

STEP = "HTML报告"


def _e(value) -> str:
    """HTML 转义。"""
    return html.escape(str(value if value is not None else ""))


def _load_stats() -> dict:
    """从 job_pages.json 汇总 local/ext/snapshot 统计。"""
    pages = common.load_json(common.DATA_DIR / "job_pages.json", default=[])
    page_count = len(pages) if isinstance(pages, list) else 0
    local_count = ext_count = snapshot_count = 0
    if isinstance(pages, list):
        for page in pages:
            if not isinstance(page, dict):
                continue
            source_type = page.get("source_type")
            if source_type == "local":
                local_count += 1
            elif source_type == "ext":
                ext_count += 1
            elif source_type == "snapshot":
                snapshot_count += 1
    return {
        "pages": page_count,
        "local": local_count,
        "ext": ext_count,
        "snapshot": snapshot_count,
    }


def _job_card(job: dict, index: int) -> str:
    score = int(job.get("total_score") or 0)
    if score >= 80:
        score_class = "high"
    elif score >= 60:
        score_class = "mid"
    else:
        score_class = "low"

    reasons = job.get("reasons") or []
    if not isinstance(reasons, list):
        reasons = [reasons]
    reasons_html = "".join(f"<li>{_e(reason)}</li>" for reason in reasons if str(reason).strip())

    url = str(job.get("url") or "").strip()
    if url.startswith("http"):
        link_html = (
            f'<a class="apply" href="{_e(url)}" target="_blank" rel="noopener">'
            "查看原岗位</a>"
        )
    else:
        link_html = '<span class="no-link">原链接缺失</span>'

    source_type = str(job.get("source_type") or "")
    source_labels = {"local": "本地页面", "ext": "扩展采集", "snapshot": "搜索快照"}
    source_label = source_labels.get(source_type, "来源未知")
    source_class = source_type if source_type in source_labels else "unknown"

    meta_parts = []
    if job.get("salary_text"):
        meta_parts.append(f"薪资 {_e(job.get('salary_text'))}")
    if job.get("city"):
        meta_parts.append(f"城市 {_e(job.get('city'))}")
    if job.get("work_year_text"):
        meta_parts.append(f"年限 {_e(job.get('work_year_text'))}")
    if job.get("degree_text"):
        meta_parts.append(f"学历 {_e(job.get('degree_text'))}")
    if job.get("publish_date"):
        meta_parts.append(f"发布 {_e(job.get('publish_date'))}")
    if job.get("source"):
        meta_parts.append(f"来源 {_e(job.get('source'))}")
    meta_html = (
        f'<span class="source-badge {source_class}">{source_label}</span>'
        + (" · " + " · ".join(meta_parts) if meta_parts else "")
    )

    summary = str(job.get("jd_summary") or "").strip()
    summary_html = f'<p class="summary">{_e(summary)}</p>' if summary else ""

    return f"""
    <article class="card">
      <div class="card-head">
        <div class="head-left">
          <span class="rank">#{_e(job.get('rank') or index)}</span>
          <div>
            <h2 class="job-title">{_e(job.get('title') or '未命名岗位')}</h2>
            <div class="company">{_e(job.get('company') or '公司信息未提供')}</div>
          </div>
        </div>
        <div class="score {score_class}"><strong>{score}</strong><span>匹配分</span></div>
      </div>
      <div class="meta">{meta_html}</div>
      {summary_html}
      <ul class="reasons">{reasons_html or '<li>暂无匹配理由</li>'}</ul>
      <div class="card-foot">{link_html}</div>
    </article>
    """


def run(city: str) -> dict:
    """模块入口：生成 output/report_YYYYMMDD.html。"""
    common.log(STEP, "开始生成 HTML 报告")
    common.ensure_dirs()

    profile = common.load_json(common.DATA_DIR / "profile.json", default={}) or {}
    jobs = common.load_json(common.DATA_DIR / "top30.json", default=[])
    if not isinstance(jobs, list):
        jobs = []
    stats = _load_stats()

    today = date.today()
    skills = profile.get("skills") or []
    top_skills = "、".join(str(item) for item in skills[:5]) if skills else "未提供"
    expected_salary = profile.get("expected_salary_k") or "未知"
    expected_city = profile.get("expected_city") or "未知"
    preferences = str(profile.get("preferences") or "").strip()
    preferences_html = (
        f'<p>求职偏好：{_e(preferences)}</p>' if preferences else ""
    )

    cards_html = "".join(_job_card(job, index) for index, job in enumerate(jobs, 1))
    if not cards_html:
        cards_html = """
        <div class="empty">
          <h2>今日暂无推荐岗位</h2>
          <p>请检查 pages/ 采集、搜索 API key、关键词或目标城市，或稍后重试。</p>
        </div>
        """
    avg_score = (
        round(sum(int(job.get("total_score") or 0) for job in jobs) / len(jobs), 1)
        if jobs
        else 0
    )

    html_text = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>岗位推荐报告 {today.isoformat()}</title>
<style>
  :root {{
    --bg: #f5f6f8;
    --card: #ffffff;
    --text: #1f2937;
    --muted: #6b7280;
    --line: #e5e7eb;
    --brand: #2563eb;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
    line-height: 1.6;
  }}
  .container {{ max-width: 980px; margin: 0 auto; padding: 36px 20px 64px; }}
  header {{ margin-bottom: 22px; }}
  h1 {{ margin: 0 0 8px; font-size: 30px; letter-spacing: .5px; }}
  .subtitle {{ color: var(--muted); font-size: 14px; }}
  .profile {{
    background: linear-gradient(135deg, #eff6ff, #ffffff);
    border: 1px solid #dbeafe;
    border-radius: 14px;
    padding: 18px 20px;
    margin: 20px 0;
  }}
  .profile h2 {{ margin: 0 0 8px; font-size: 17px; }}
  .profile p {{ margin: 4px 0; color: #374151; }}
  .stats {{
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 10px;
    margin: 18px 0 26px;
  }}
  .stat {{
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 12px;
    padding: 14px 12px;
    text-align: center;
  }}
  .stat strong {{ display: block; font-size: 22px; color: var(--brand); }}
  .stat span {{ color: var(--muted); font-size: 12px; }}
  .card {{
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 16px;
    padding: 22px;
    margin: 16px 0;
    box-shadow: 0 4px 14px rgba(15, 23, 42, .04);
  }}
  .card-head {{ display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }}
  .head-left {{ display: flex; gap: 12px; align-items: flex-start; min-width: 0; }}
  .rank {{
    flex: 0 0 auto;
    font-weight: 700;
    color: var(--brand);
    background: #eff6ff;
    border-radius: 8px;
    padding: 4px 9px;
    font-size: 14px;
  }}
  .job-title {{ margin: 0; font-size: 20px; line-height: 1.4; word-break: break-word; }}
  .company {{ color: var(--muted); margin-top: 4px; font-size: 14px; }}
  .score {{
    flex: 0 0 auto;
    min-width: 70px;
    text-align: center;
    border-radius: 12px;
    padding: 8px 10px;
  }}
  .score strong {{ display: block; font-size: 24px; line-height: 1.1; }}
  .score span {{ font-size: 11px; }}
  .score.high {{ background: #dcfce7; color: #166534; }}
  .score.mid {{ background: #fef3c7; color: #92400e; }}
  .score.low {{ background: #f1f5f9; color: #475569; }}
  .meta {{ color: var(--muted); font-size: 14px; margin-top: 12px; }}
  .source-badge {{
    display: inline-block;
    padding: 1px 9px;
    border-radius: 999px;
    font-size: 12px;
    margin-right: 6px;
  }}
  .source-badge.local {{ background: #dcfce7; color: #166534; }}
  .source-badge.ext {{ background: #dbeafe; color: #1d4ed8; }}
  .source-badge.snapshot {{ background: #fef3c7; color: #92400e; }}
  .source-badge.unknown {{ background: #f1f5f9; color: #475569; }}
  .no-link {{ color: var(--muted); font-size: 13px; }}
  .summary {{ margin: 12px 0 0; color: #374151; font-size: 14px; }}
  .reasons {{ margin: 14px 0 0; padding-left: 20px; color: #374151; font-size: 14px; }}
  .reasons li {{ margin: 3px 0; }}
  .card-foot {{ margin-top: 14px; }}
  .apply {{
    display: inline-block;
    color: #fff;
    background: var(--brand);
    text-decoration: none;
    padding: 8px 14px;
    border-radius: 9px;
    font-size: 14px;
  }}
  .apply:hover {{ background: #1d4ed8; }}
  .empty {{
    background: var(--card);
    border: 1px dashed #cbd5e1;
    border-radius: 16px;
    text-align: center;
    padding: 46px 20px;
    color: var(--muted);
  }}
  .empty h2 {{ margin: 0 0 8px; color: var(--text); }}
  footer {{ color: var(--muted); font-size: 12px; margin-top: 30px; text-align: center; }}
  @media (max-width: 720px) {{
    .stats {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .card-head {{ flex-direction: column; }}
    .score {{ align-self: flex-start; }}
  }}
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>岗位推荐报告 {today.isoformat()}</h1>
    <div class="subtitle">目标城市：{_e(city)} · 数据来自本地页面采集与搜索快照</div>
  </header>

  <section class="profile">
    <h2>简历画像</h2>
    <p>{_e(profile.get('name') or '姓名未提供')} · {_e(profile.get('years_of_experience') or 0)} 年经验 · {_e(profile.get('degree') or '学历未知')}</p>
    <p>期望：{_e(expected_city)} · {_e(expected_salary)}K · 技能：{_e(top_skills)}</p>
    <p>{_e(profile.get('summary') or '')}</p>
    {preferences_html}
  </section>

  <section class="stats">
    <div class="stat"><strong>{stats['local'] + stats['ext']}</strong><span>本地/扩展岗位</span></div>
    <div class="stat"><strong>{stats['snapshot']}</strong><span>快照岗位</span></div>
    <div class="stat"><strong>{stats['pages']}</strong><span>岗位总数</span></div>
    <div class="stat"><strong>{len(jobs)}</strong><span>推荐（过滤后）</span></div>
    <div class="stat"><strong>{avg_score}</strong><span>平均匹配分</span></div>
  </section>

  <main>{cards_html}</main>

  <footer>
    信息来自本地保存页面与搜索快照，可能存在滞后或缺失；投递前请点开原链接确认岗位状态。
  </footer>
</div>
</body>
</html>
"""

    out_path = common.OUTPUT_DIR / f"report_{today:%Y%m%d}.html"
    out_path.write_text(html_text, encoding="utf-8")
    relative = out_path.relative_to(common.ROOT_DIR).as_posix()
    common.log(STEP, f"报告已生成：{relative}，推荐 {len(jobs)} 个岗位")
    return {"report_path": relative, "jobs": len(jobs)}


if __name__ == "__main__":
    config = common.load_config()
    print("运行结果：", run(config.get("default_city", "深圳")))
