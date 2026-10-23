# -*- coding: utf-8 -*-
"""公共模块：配置读取、日志、HTTP 请求、JSON 读写。其他模块统一 import 本模块。"""

import json
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests

# 项目根目录：源码运行时取 common.py 所在目录；PyInstaller 打包后取 exe 所在目录
if getattr(sys, "frozen", False):
    ROOT_DIR = Path(sys.executable).resolve().parent
else:
    ROOT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = ROOT_DIR / "config.json"
DATA_DIR = ROOT_DIR / "data"
OUTPUT_DIR = ROOT_DIR / "output"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def load_config() -> dict:
    """读取 config.json 返回 dict；文件不存在则抛 FileNotFoundError 并提示。"""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"配置文件不存在：{CONFIG_PATH}，请先创建 config.json")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_dirs():
    """创建 data/ 和 output/ 目录（已存在则跳过）。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def log(step: str, msg: str):
    """统一日志：[2026-10-22 10:00:00] [步骤名] 消息内容。"""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{step}] {msg}", flush=True)


def _merge_headers(headers=None) -> dict:
    """默认带 User-Agent，允许调用方覆盖。"""
    final = {"User-Agent": UA}
    if headers:
        final.update(headers)
    return final


def http_get(url, headers=None, params=None, timeout=15, retries=2) -> requests.Response:
    """GET 请求，失败自动重试 retries 次，每次间隔 2 秒；最终失败抛 RuntimeError（带 url 信息）。"""
    last_err = None
    for attempt in range(retries + 1):
        try:
            return requests.get(url, headers=_merge_headers(headers), params=params, timeout=timeout)
        except requests.RequestException as e:
            last_err = e
            if attempt < retries:
                log("HTTP", f"GET 请求失败（第 {attempt + 1} 次），2 秒后重试：{url}")
                time.sleep(2)
    raise RuntimeError(f"GET 请求失败：{url}，错误：{last_err}")


def http_post(url, data=None, json=None, headers=None, timeout=30, retries=1) -> requests.Response:
    """POST 请求，失败自动重试 retries 次，每次间隔 2 秒；最终失败抛 RuntimeError（带 url 信息）。"""
    last_err = None
    for attempt in range(retries + 1):
        try:
            return requests.post(
                url, data=data, json=json, headers=_merge_headers(headers), timeout=timeout
            )
        except requests.RequestException as e:
            last_err = e
            if attempt < retries:
                log("HTTP", f"POST 请求失败（第 {attempt + 1} 次），2 秒后重试：{url}")
                time.sleep(2)
    raise RuntimeError(f"POST 请求失败：{url}，错误：{last_err}")


def save_json(obj, path):
    """写入 JSON 文件（ensure_ascii=False, indent=2），自动创建父目录。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def load_json(path, default=None):
    """读取 JSON 文件；文件不存在返回 default。"""
    path = Path(path)
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_salary(text: str):
    """薪资文本转 (min_k, max_k)，单位千元/月；面议或解析失败返回 (0, 0)。"""
    raw = str(text or "").strip()
    if not raw or "面议" in raw:
        return 0, 0

    # 去掉 “·14薪”“×13薪” 等，避免把薪数当成月薪
    cleaned = re.split(r"[·×xX]\s*\d+\s*薪", raw)[0]
    cleaned = re.sub(r"\d+\s*薪", "", cleaned)
    cleaned = cleaned.replace("～", "-").replace("—", "-").replace("–", "-").replace("至", "-")
    annual = ("年薪" in cleaned) or bool(re.search(r"/\s*年", cleaned))

    def to_k(num: str, unit: str) -> float:
        value = float(num)
        unit = (unit or "").lower()
        if unit == "万":
            value *= 10
        elif unit == "元":
            value /= 1000
        elif unit in ("千", "k"):
            pass
        elif value >= 1000:
            value /= 1000
        if annual:
            value /= 12
        return value

    # 区间：如 15-25K、8千-1.2万、1.5-2万·14薪
    range_match = re.search(
        r"(\d+(?:\.\d+)?)\s*([万千Kk元]?)\s*-\s*(\d+(?:\.\d+)?)\s*([万千Kk元]?)",
        cleaned,
    )
    if range_match:
        low_num, low_unit, high_num, high_unit = range_match.groups()
        # “1.5-2万”这种写法，单位只出现在后一个数字上
        if not low_unit and high_unit:
            low_unit = high_unit
        if not high_unit and low_unit:
            high_unit = low_unit
        low = to_k(low_num, low_unit)
        high = to_k(high_num, high_unit)
        if low > high:
            low, high = high, low
        return int(round(low)), int(round(high))

    # 单值：如 20K以上、15K
    single = re.search(r"(\d+(?:\.\d+)?)\s*([万千Kk元]?)", cleaned)
    if not single:
        return 0, 0
    value = to_k(*single.groups())
    if "以上" in cleaned or "+" in cleaned:
        return int(round(value)), int(round(value * 1.75))
    if "以下" in cleaned:
        return 0, int(round(value))
    return int(round(value)), int(round(value))


def parse_work_year(text: str):
    """工作年限文本转 (min, max)；经验不限/应届生返回 (0, 0)。"""
    raw = str(text or "").strip()
    if not raw or "不限" in raw or "应届" in raw or "无经验" in raw or "无需经验" in raw:
        return 0, 0
    nums = [int(float(x)) for x in re.findall(r"\d+(?:\.\d+)?", raw)]
    if not nums:
        return 0, 0
    if len(nums) >= 2:
        low, high = nums[0], nums[1]
        if low > high:
            low, high = high, low
        return low, high
    low = nums[0]
    if "以上" in raw or "及以上" in raw:
        if low >= 10:
            return low, 20
        if low >= 5:
            return low, 12
        return low, low + 7
    if "以下" in raw or "以内" in raw:
        return 0, low
    return low, low


def degree_rank(text: str) -> int:
    """学历文本转统一等级：不限=0，大专=1，本科=2，硕士=3，博士=4。"""
    raw = str(text or "")
    if not raw or "不限" in raw or "无要求" in raw:
        return 0
    if "博士" in raw:
        return 4
    if "硕士" in raw or "研究生" in raw or "MBA" in raw:
        return 3
    if "本科" in raw or "学士" in raw:
        return 2
    if "大专" in raw or "专科" in raw:
        return 1
    return 0


def normalize_date(text: str) -> str:
    """把绝对/相对时间统一成 YYYY-MM-DD；无法识别返回空字符串。"""
    raw = str(text or "").strip()
    if not raw:
        return ""
    today = date.today()
    match = re.search(r"(\d{4})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})", raw)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3))).isoformat()
        except ValueError:
            return ""
    if "今天" in raw or "刚刚" in raw or "分钟前" in raw or "小时前" in raw:
        return today.isoformat()
    if "昨天" in raw:
        return (today - timedelta(days=1)).isoformat()
    if "前天" in raw:
        return (today - timedelta(days=2)).isoformat()
    match = re.search(r"(\d+)\s*天前", raw)
    if match:
        return (today - timedelta(days=int(match.group(1)))).isoformat()
    match = re.search(r"(\d+)\s*周前", raw)
    if match:
        return (today - timedelta(weeks=int(match.group(1)))).isoformat()
    match = re.search(r"(\d+)\s*个?月前", raw)
    if match:
        return (today - timedelta(days=30 * int(match.group(1)))).isoformat()
    match = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日", raw)
    if match:
        try:
            return date(today.year, int(match.group(1)), int(match.group(2))).isoformat()
        except ValueError:
            return ""
    match = re.search(r"(\d{1,2})\s*[-/]\s*(\d{1,2})", raw)
    if match:
        try:
            return date(today.year, int(match.group(1)), int(match.group(2))).isoformat()
        except ValueError:
            return ""
    return ""


def call_deepseek(
    system_prompt: str, user_prompt: str, config: dict, json_mode: bool = True
) -> str:
    """调用 DeepSeek 返回 message.content；失败重试 1 次，仍失败抛 RuntimeError。

    json_mode 默认开启 JSON 输出；交互式提问等场景可传 False。
    """
    api_key = str(config.get("deepseek_api_key") or "").strip()
    if not api_key or api_key == "sk-xxxx":
        raise RuntimeError("未配置 deepseek_api_key")

    body = {
        "model": str(config.get("deepseek_model") or "deepseek-chat").strip(),
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    last_error = None
    for attempt in range(2):
        try:
            resp = http_post(
                "https://api.deepseek.com/chat/completions",
                json=body,
                headers=headers,
                timeout=120,
                retries=0,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"DeepSeek HTTP {resp.status_code}：{resp.text[:200]}")
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise RuntimeError("DeepSeek 返回内容不是文本")
            return content
        except Exception as e:
            last_error = e
            if attempt == 0:
                log("LLM", f"DeepSeek 调用失败，2 秒后重试一次：{str(e)[:200]}")
                time.sleep(2)
    raise RuntimeError(f"DeepSeek 调用失败：{str(last_error)[:200]}")
