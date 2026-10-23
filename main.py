# -*- coding: utf-8 -*-
"""模块5：主流程入口。"""

import sys

import common
import gen_keywords
import llm_rank
import local_pages
import make_report
import push_wechat
import resume_parse
import search_fetch

STEP = "主流程"


def _collection_queries(city: str) -> list:
    data = common.load_json(common.DATA_DIR / "keywords.json", default={}) or {}
    mapping = data.get("search_keywords") or {}
    terms, seen = [], set()
    for values in mapping.values():
        for term in values or []:
            term = str(term).strip()
            if term and term.lower() not in seen:
                seen.add(term.lower())
                terms.append(term)
    return [f"{city} {term} 招聘" for term in terms]


def _print_collection_guide(city: str):
    queries = _collection_queries(city)
    print("\npages/ 目录为空。最简采集流程（约1-2分钟）：")
    print("1. 浏览器登录招聘网站")
    if queries:
        print(f"2. 从以下 {len(queries)} 个查询中挑选 2-4 个最相关的搜索（不必全部采集）：")
        for query in queries:
            print(f"   - {query}")
    else:
        print("2. 搜索目标岗位（关键词文件缺失）")
    print("3. 优先保存搜索结果列表页（每页通常含多个岗位）；保存类型先试“网页，完整”，")
    print("   或“网页，仅HTML”（保存后确认页面里有岗位卡片）。")
    print("4. 把 HTML 放到 pages/{站点}/ 目录，不必逐条保存详情页。")
    print("5. 保存完成后回到网页点击“开始匹配”（或重新运行本程序）。\n")


def _search_auto_available(config: dict) -> bool:
    provider = str(config.get("search_api_provider") or "").strip().lower()
    if provider == "deepseek":
        return bool(str(config.get("deepseek_api_key") or "").strip())
    if provider in ("bocha", "bing"):
        return bool(str(config.get("search_api_key") or "").strip())
    return False


def _ask_city(default_city: str) -> str:
    try:
        value = input(f"目标城市（回车默认 {default_city}）：").strip()
    except EOFError:
        value = ""
    return value or default_city


def _ask_continue(step_name: str, error: Exception) -> bool:
    try:
        answer = input(
            f"{step_name} 失败：{error}\n是否继续后续步骤？(y/n，默认 n)："
        ).strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes", "是", "继续")


def run() -> dict:
    """执行完整流程，返回各步骤结果摘要。"""
    common.log("启动", "岗位匹配推送程序")
    config = common.load_config()
    common.ensure_dirs()
    city = _ask_city(config.get("default_city", "深圳"))
    common.log("启动", f"目标城市：{city}")

    steps = [
        ("简历解析", resume_parse.run),
        ("关键词生成", gen_keywords.run),
        ("本地页面提取", local_pages.run),
        ("搜索快照", search_fetch.run),
        ("LLM精评", llm_rank.run),
        ("报告生成", make_report.run),
        ("微信推送", push_wechat.run),
    ]

    results = {}
    report_path = ""
    aborted = False

    for step_name, entry in steps:
        try:
            result = entry(city)
            results[step_name] = result
            common.log(STEP, f"{step_name}完成：{result}")
            if step_name == "本地页面提取" and isinstance(result, dict):
                if int(result.get("pages_found") or 0) == 0:
                    if _search_auto_available(config):
                        common.log(
                            STEP,
                            "本地页面为空，将自动使用搜索 API 补充岗位；"
                            "也可保存 2-4 个列表页提高质量",
                        )
                    else:
                        _print_collection_guide(city)
            if step_name == "报告生成" and isinstance(result, dict):
                report_path = result.get("report_path", "")
        except Exception as e:
            common.log(STEP, f"{step_name}失败：{e}")
            if not _ask_continue(step_name, e):
                common.log(STEP, f"流程在「{step_name}」终止")
                aborted = True
                break

    if not aborted:
        common.log(STEP, f"全流程完成，报告：{report_path or '未生成'}")
    return {
        "city": city,
        "results": results,
        "report_path": report_path,
        "aborted": aborted,
    }


if __name__ == "__main__":
    outcome = run()
    if outcome["aborted"]:
        sys.exit(1)
