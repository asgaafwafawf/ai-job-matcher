# -*- coding: utf-8 -*-
"""模块3b：搜索 API 通道（DeepSeek Search / 博查 / Bing）。

读 keywords.json，调用搜索服务获取岗位结果，转换成 job_pages.json 的
snapshot 条目并追加合并。DeepSeek Search 可同时返回网页正文，作为自动化的
主搜索通道；本模块不直接请求任何招聘网站。
"""

import time
from datetime import date
from urllib.parse import urlparse

import common

STEP = "搜索快照"
DEEPSEEK_SEARCH_URL = "https://api.deepseek.com/v1/tools/search"
BOCHA_URL = "https://api.bochaai.com/v1/web-search"
BING_URL = "https://api.bing.microsoft.com/v7.0/search"
QUERY_SUFFIXES = ["", " 薪资", " 最新", " 岗位"]

# 仅允许这五家招聘官网；每个站点最终最多保留 10 个岗位
JOB_SITES = [
    {"key": "boss", "name": "BOSS直聘", "domain": "zhipin.com"},
    {"key": "liepin", "name": "猎聘", "domain": "liepin.com"},
    {"key": "51job", "name": "51job", "domain": "51job.com"},
    {"key": "zhilian", "name": "智联招聘", "domain": "zhaopin.com"},
    {"key": "guopin", "name": "国聘", "domain": "iguopin.com"},
]
MAX_JOBS_PER_SITE = 10
EXPIRED_MARKERS = (
    "职位已过期",
    "已下架",
    "该职位已关闭",
    "已停止招聘",
    "已下线",
    "已失效",
    "招聘已结束",
    "该职位不存在",
    "页面不存在",
    "404 not found",
)


def _load_search_terms() -> list:
    data = common.load_json(common.DATA_DIR / "keywords.json", default={}) or {}
    mapping = data.get("search_keywords") or {}
    terms, seen = [], set()
    for values in mapping.values():
        for term in values or []:
            term = str(term).strip()
            key = term.lower()
            if term and key not in seen:
                seen.add(key)
                terms.append(term)
    if not terms:
        raise RuntimeError("data/keywords.json 中没有可搜索的关键词，请先运行模块2")
    return terms


def _build_site_queries(city: str, terms: list, per_keyword: int) -> list:
    """每个搜索词 × 每个官网生成查询，使用 site: 限定官方域名。"""
    per_keyword = max(1, int(per_keyword))
    queries, seen = [], set()
    for term in terms:
        base = f"{city} {term} 招聘"
        for index in range(per_keyword):
            suffix = QUERY_SUFFIXES[index] if index < len(QUERY_SUFFIXES) else " 最新"
            for site in JOB_SITES:
                query = f"{base}{suffix} site:{site['domain']}".strip()
                key = (query, site["key"])
                if key not in seen:
                    seen.add(key)
                    queries.append({"query": query, "site": site})
    return queries


def _match_site(url: str):
    """URL 是否属于五家招聘官网之一；返回站点配置或 None。"""
    host = (urlparse(str(url or "")).hostname or "").lower()
    if not host:
        return None
    for site in JOB_SITES:
        domain = site["domain"]
        if host == domain or host.endswith("." + domain):
            return site
    return None


def _is_expired(item: dict, days_limit: int) -> bool:
    """按方案设计的过期规则做搜索层预过滤。"""
    text = f"{item.get('content') or ''} {item.get('summary') or ''} {item.get('snippet') or ''}"
    text_lower = text.lower()
    if any(marker in text for marker in EXPIRED_MARKERS) or "404 not found" in text_lower:
        return True
    date_text = str(item.get("date") or "").strip()
    if not date_text:
        return False  # 日期缺失留给精评阶段按硬排除规则处理
    try:
        days_ago = (date.today() - date.fromisoformat(date_text)).days
    except ValueError:
        return False
    return days_ago > max(1, int(days_limit))


def _extract_values(payload) -> list:
    """兼容博查/Bing 常见结构，取出结果数组。"""
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if isinstance(data, dict):
        pages = data.get("webPages")
        if isinstance(pages, dict) and isinstance(pages.get("value"), list):
            return pages["value"]
        if isinstance(data.get("value"), list):
            return data["value"]
    pages = payload.get("webPages")
    if isinstance(pages, dict) and isinstance(pages.get("value"), list):
        return pages["value"]
    if isinstance(payload.get("results"), list):
        return payload["results"]
    if isinstance(payload.get("items"), list):
        return payload["items"]
    return []


def _check_api_error(payload, provider: str):
    if not isinstance(payload, dict):
        raise RuntimeError(f"{provider} 返回内容不是 JSON 对象")
    if isinstance(payload.get("error"), dict):
        raise RuntimeError(f"{provider} 返回错误：{str(payload.get('error'))[:200]}")
    code = payload.get("code")
    if code is not None and str(code) not in ("0", "200"):
        message = payload.get("msg") or payload.get("message") or ""
        raise RuntimeError(f"{provider} 业务错误 code={code}：{str(message)[:200]}")


def _map_item(item: dict):
    if not isinstance(item, dict):
        return None
    url = str(item.get("url") or item.get("link") or "").strip()
    if not url.startswith("http"):
        return None
    title = str(item.get("name") or item.get("title") or "").strip() or url
    raw_snippet = item.get("snippet") or item.get("description") or ""
    summary = str(item.get("summary") or "").strip()
    content = str(item.get("content") or "").strip()
    snippet = str(raw_snippet or summary).strip()
    date = common.normalize_date(
        item.get("dateLastCrawled")
        or item.get("datePublished")
        or item.get("date")
        or ""
    )
    site_name = str(item.get("siteName") or item.get("site_name") or "").strip()
    if not site_name:
        site_name = urlparse(url).netloc
    return {
        "title": title,
        "url": url,
        "snippet": snippet,
        "summary": summary,
        "content": content,
        "date": date,
        "site_name": site_name,
        "rerank_score": item.get("rerank_score"),
    }


def _map_results(payload, provider: str) -> list:
    _check_api_error(payload, provider)
    results = []
    for value in _extract_values(payload):
        if provider == "deepseek" and isinstance(value, dict):
            try:
                score = float(value.get("rerank_score"))
            except (TypeError, ValueError):
                score = None
            if score is not None and score < 1.0:
                continue
        mapped = _map_item(value)
        if mapped:
            results.append(mapped)
    return results


def _call_deepseek_search(query: str, key: str, count: int) -> list:
    body = {"query": query, "count": count, "need_content": True}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    resp = common.http_post(
        DEEPSEEK_SEARCH_URL, json=body, headers=headers, timeout=90, retries=0
    )
    if resp.status_code != 200:
        raise RuntimeError(f"DeepSeek Search HTTP {resp.status_code}：{resp.text[:200]}")
    try:
        payload = resp.json()
    except ValueError as e:
        raise RuntimeError(f"DeepSeek Search 返回非 JSON：{e}；原文前 200 字：{resp.text[:200]}")
    return _map_results(payload, "deepseek")


def _call_bocha(query: str, key: str, count: int) -> list:
    body = {"query": query, "freshness": "oneMonth", "summary": True, "count": count}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    resp = common.http_post(BOCHA_URL, json=body, headers=headers, timeout=30, retries=0)
    if resp.status_code != 200:
        raise RuntimeError(f"博查 HTTP {resp.status_code}：{resp.text[:200]}")
    try:
        payload = resp.json()
    except ValueError as e:
        raise RuntimeError(f"博查返回非 JSON：{e}；原文前 200 字：{resp.text[:200]}")
    return _map_results(payload, "bocha")


def _call_bing(query: str, key: str, count: int) -> list:
    params = {"q": query, "freshness": "Month", "count": count, "mkt": "zh-CN"}
    headers = {"Ocp-Apim-Subscription-Key": key}
    resp = common.http_get(BING_URL, headers=headers, params=params, timeout=20, retries=0)
    if resp.status_code != 200:
        raise RuntimeError(f"Bing HTTP {resp.status_code}：{resp.text[:200]}")
    try:
        payload = resp.json()
    except ValueError as e:
        raise RuntimeError(f"Bing 返回非 JSON：{e}；原文前 200 字：{resp.text[:200]}")
    return _map_results(payload, "bing")


def _request_with_retry(provider: str, query: str, key: str, count: int) -> list:
    last_error = None
    for attempt in range(2):
        try:
            if provider == "deepseek":
                return _call_deepseek_search(query, key, count)
            if provider == "bocha":
                return _call_bocha(query, key, count)
            if provider == "bing":
                return _call_bing(query, key, count)
            raise RuntimeError(f"不支持的搜索源：{provider}")
        except Exception as e:
            last_error = e
            if attempt == 0:
                common.log(STEP, f"{provider} 查询失败，2 秒后重试一次：{e}")
                time.sleep(2)
    raise RuntimeError(f"{provider} 查询失败：{last_error}")


def _search_query(
    query: str, state: dict, backup_provider: str, backup_key: str, count: int
) -> tuple:
    """查询单个关键词；失败时尝试备选源。返回 (结果, 是否失败)。"""
    provider, key = state["provider"], state["key"]
    try:
        results = _request_with_retry(provider, query, key, count)
        if provider not in state["providers_used"]:
            state["providers_used"].append(provider)
        return results, False
    except Exception as e:
        common.log(STEP, f"搜索源 {provider} 不可用：{e}")

    if backup_key and backup_provider != provider:
        common.log(STEP, f"切换备选搜索源：{backup_provider}")
        try:
            results = _request_with_retry(backup_provider, query, backup_key, count)
            state["provider"] = backup_provider
            state["key"] = backup_key
            if backup_provider not in state["providers_used"]:
                state["providers_used"].append(backup_provider)
            return results, False
        except Exception as e:
            common.log(STEP, f"备选搜索源也失败：{e}")
    return [], True


def run(city: str) -> dict:
    """模块入口：只在五家招聘官网搜索，每站最多 10 条，追加到 job_pages.json。"""
    common.log(STEP, f"开始获取搜索快照，城市：{city}")
    common.ensure_dirs()
    config = common.load_config()
    terms = _load_search_terms()
    per_keyword = int(config.get("queries_per_keyword", 2) or 2)
    queries = _build_site_queries(city, terms, per_keyword)
    count = max(1, int(config.get("results_per_query", 20) or 20))
    days_limit = max(1, int(config.get("publish_days_limit", 30) or 30))

    primary = str(config.get("search_api_provider") or "deepseek").strip().lower()
    if primary == "deepseek":
        primary_key = str(config.get("deepseek_api_key") or "").strip()
    else:
        primary_key = str(config.get("search_api_key") or "").strip()
    backup_key = str(config.get("search_api_backup_key") or "").strip()
    backup_provider = "bing" if primary != "bing" else "bocha"

    if primary not in ("deepseek", "bocha", "bing"):
        common.log(STEP, f"警告：不支持的 search_api_provider={primary}，跳过搜索通道")
        return {"queries": 0, "fetched": 0, "added": 0, "providers_used": []}

    if not primary_key and backup_key:
        common.log(STEP, f"主搜索 key 为空，改用备选源 {backup_provider}")
        provider, key = backup_provider, backup_key
    else:
        provider, key = primary, primary_key

    if not key:
        key_name = "deepseek_api_key" if primary == "deepseek" else "search_api_key"
        common.log(STEP, f"未配置 {key_name}，跳过搜索通道")
        return {"queries": 0, "fetched": 0, "added": 0, "providers_used": []}

    job_pages_path = common.DATA_DIR / "job_pages.json"
    existing = common.load_json(job_pages_path, default=[])
    if not isinstance(existing, list):
        existing = []
    existing_urls = set()
    for entry in existing:
        if isinstance(entry, dict):
            url = str(entry.get("url") or "").strip().rstrip("/")
            if url:
                existing_urls.add(url)

    common.log(
        STEP,
        f"共 {len(terms)} 个搜索词，生成 {len(queries)} 条官网查询"
        f"（{len(JOB_SITES)} 个站点），每查询 {count} 条，每站最多保留 {MAX_JOBS_PER_SITE} 条，"
        f"搜索源 {provider}",
    )
    state = {"provider": provider, "key": key, "providers_used": []}
    site_candidates = {site["key"]: [] for site in JOB_SITES}
    candidate_urls = set()
    fetched = 0
    queries_run = 0
    off_site_count = 0
    expired_count = 0
    consecutive_failures = 0

    for index, query_item in enumerate(queries, 1):
        query = query_item["query"]
        target_site = query_item["site"]
        queries_run += 1
        results, failed = _search_query(query, state, backup_provider, backup_key, count)
        consecutive_failures = consecutive_failures + 1 if failed else 0
        fetched += len(results)
        valid_this_query = 0

        for item in results:
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            key_url = url.rstrip("/")
            if key_url in candidate_urls or key_url in existing_urls:
                continue
            site = _match_site(url)
            if not site:
                off_site_count += 1
                continue
            if _is_expired(item, days_limit):
                expired_count += 1
                continue
            candidate_urls.add(key_url)
            candidate = dict(item)
            candidate["query"] = query
            candidate["search_provider"] = state["provider"]
            site_candidates[site["key"]].append(candidate)
            valid_this_query += 1

        common.log(
            STEP,
            f"[{index}/{len(queries)}] {target_site['name']} | {query}："
            f"{len(results)} 条，五站内新增 {valid_this_query} 条",
        )
        if consecutive_failures >= 2:
            common.log(STEP, "连续 2 条查询失败，停止搜索通道；请检查搜索 key、额度或网络")
            break
        time.sleep(0.5)

    added_entries = []
    for site in JOB_SITES:
        items = site_candidates[site["key"]]
        items.sort(
            key=lambda item: (
                float(item.get("rerank_score") or 0),
                item.get("date") or "",
            ),
            reverse=True,
        )
        kept = items[:MAX_JOBS_PER_SITE]
        if items:
            common.log(
                STEP,
                f"{site['name']}：候选 {len(items)} 条，按每站上限保留 {len(kept)} 条",
            )
        for item in kept:
            content = str(item.get("content") or "").strip()
            summary = str(item.get("summary") or "").strip()
            snippet = str(item.get("snippet") or "").strip()
            page_text = content or summary or snippet
            added_entries.append(
                {
                    "url": str(item.get("url") or "").strip(),
                    "query": item.get("query") or "",
                    "title": item.get("title") or item.get("url") or "",
                    "company": "",
                    "snippet": snippet or summary,
                    "date": item.get("date") or "",
                    "site_name": site["name"],
                    "site_key": site["key"],
                    "source_type": "snapshot",
                    "provider": item.get("search_provider") or provider,
                    "rerank_score": item.get("rerank_score"),
                    "page_text": page_text,
                    "fetch_status": "ok" if content else "snapshot",
                    "fallback": not bool(content),
                }
            )

    merged = existing + added_entries
    common.save_json(merged, job_pages_path)
    common.log(
        STEP,
        f"完成：执行 {queries_run}/{len(queries)} 条官网查询，原始 {fetched} 条，"
        f"站外过滤 {off_site_count} 条，过期过滤 {expired_count} 条，写入 {len(added_entries)} 条",
    )
    return {
        "queries": queries_run,
        "fetched": fetched,
        "added": len(added_entries),
        "providers_used": state["providers_used"],
    }


if __name__ == "__main__":
    config = common.load_config()
    print("运行结果：", run(config.get("default_city", "深圳")))
