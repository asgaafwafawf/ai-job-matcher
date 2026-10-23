# -*- coding: utf-8 -*-
"""模块4b：通过 Server酱推送到微信。"""

from datetime import date

import requests

import common

STEP = "微信推送"
SERVERCHAN_URL = "https://sctapi.ftqq.com/{sendkey}.send"


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


def _clean(text) -> str:
    """压缩成适合 Markdown 单行的文本。"""
    value = str(text if text is not None else "")
    value = value.replace("\r", " ").replace("\n", " ").replace("|", "｜")
    return " ".join(value.split()).strip()


def _report_path() -> str:
    out = common.OUTPUT_DIR / f"report_{date.today():%Y%m%d}.html"
    if out.exists():
        return out.relative_to(common.ROOT_DIR).as_posix()
    return "未生成"


def _build_desp(profile: dict, jobs: list, stats: dict) -> str:
    years = profile.get("years_of_experience") or 0
    degree = profile.get("degree") or "学历未知"
    salary = profile.get("expected_salary_k") or "未知"
    report_path = _report_path()

    lines = [
        "## 匹配概况",
        f"- 本地/扩展岗位 {stats['local'] + stats['ext']} 个 / 快照 {stats['snapshot']} 条 → "
        f"岗位 {stats['pages']} 条 → 推荐 {len(jobs)} 条",
        f"- 简历画像：{years}年经验 · {degree} · 期望 {salary}K",
        "",
        "## Top 10 推荐",
    ]

    if not jobs:
        lines.append("今日暂无匹配岗位，请检查 pages/ 采集、搜索 key、关键词或目标城市。")
    else:
        for index, job in enumerate(jobs[:10], 1):
            title = _clean(job.get("title") or "未命名岗位")
            company = _clean(job.get("company") or "公司未提供")
            salary_text = _clean(job.get("salary_text") or "薪资未知")
            city = _clean(job.get("city") or "城市未知")
            score = job.get("total_score") or 0
            reasons = job.get("reasons") or []
            if not isinstance(reasons, list):
                reasons = [reasons]
            first_reason = _clean(reasons[0]) if reasons else "暂无匹配理由"
            url = str(job.get("url") or "").strip()

            lines.append(f"{index}. **{title}** | {company} | {salary_text} | {city}")
            lines.append(f"   匹配 {score} 分：{first_reason}")
            if url.startswith("http"):
                lines.append(f"   [查看详情]({url})")
            lines.append("")

    lines.append(f"（更多见完整报告 {report_path}）")
    return "\n".join(lines)


def _post_serverchan(sendkey: str, title: str, desp: str):
    """发送 Server酱消息，返回 (是否成功, 失败原因)。"""
    url = SERVERCHAN_URL.format(sendkey=sendkey)
    masked_url = SERVERCHAN_URL.format(sendkey="***")
    try:
        resp = requests.post(
            url,
            data={"title": title, "desp": desp},
            headers={"User-Agent": common.UA},
            timeout=30,
        )
    except requests.RequestException as e:
        common.log(STEP, f"推送请求失败（{masked_url}）：{type(e).__name__}")
        return False, f"网络错误：{type(e).__name__}"

    if resp.status_code != 200:
        common.log(STEP, f"推送失败：HTTP {resp.status_code}")
        return False, f"HTTP {resp.status_code}"

    try:
        payload = resp.json()
    except ValueError:
        common.log(STEP, "推送失败：返回内容不是 JSON")
        return False, "返回内容不是 JSON"

    code = payload.get("code")
    if str(code) == "0":
        common.log(STEP, f"推送成功：{title}")
        return True, ""

    message = payload.get("message") or payload.get("msg") or ""
    common.log(STEP, f"推送失败：code={code}，{str(message)[:200]}")
    return False, f"code={code}，{str(message)[:100]}"


def send_test(config: dict) -> dict:
    """发送一条测试推送，供网页设置页验证 SendKey。"""
    sendkey = str(config.get("serverchan_sendkey") or "").strip()
    if not sendkey:
        common.log(STEP, "未配置 serverchan_sendkey，无法测试推送")
        return {"pushed": False, "reason": "未配置 serverchan_sendkey"}
    title = "岗位匹配助手测试推送"
    desp = "## 测试推送\n如果你收到这条消息，说明 Server酱推送配置成功。"
    ok, reason = _post_serverchan(sendkey, title, desp)
    return {"pushed": True} if ok else {"pushed": False, "reason": reason}


def run(city: str) -> dict:
    """模块入口：推送 Top 10 到微信。"""
    common.log(STEP, "开始微信推送")
    common.ensure_dirs()
    config = common.load_config()
    sendkey = str(config.get("serverchan_sendkey") or "").strip()
    if not sendkey:
        common.log(STEP, "未配置 serverchan_sendkey，跳过推送")
        return {"pushed": False, "reason": "未配置 serverchan_sendkey"}

    profile = common.load_json(common.DATA_DIR / "profile.json", default={}) or {}
    jobs = common.load_json(common.DATA_DIR / "top30.json", default=[])
    if not isinstance(jobs, list):
        jobs = []
    stats = _load_stats()

    today = date.today().isoformat()
    title = f"岗位推送 {today} | 今日推荐 {len(jobs)} 个岗位"
    desp = _build_desp(profile, jobs, stats)
    ok, reason = _post_serverchan(sendkey, title, desp)
    return {"pushed": True} if ok else {"pushed": False, "reason": reason}


if __name__ == "__main__":
    config = common.load_config()
    print("运行结果：", run(config.get("default_city", "深圳")))
