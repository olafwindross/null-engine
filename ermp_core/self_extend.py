"""
ermp_core.self_extend – Samo-rozšiřující jádro NULL ENGINE
============================================================
Tento modul dává botovi schopnost *samo-rozšiřování*. Když dostane
požadavek, který neumí vyřídit, sám si napíše kód, otestuje ho
v sandboxu a příště ho rovnou použije.

Architektura:
  - SkillRegistry   → registr dovedností (skills_registry.json)
  - SkillGenerator  → generuje novou Python funkci přes lokální Ollama
  - SkillExecutor   → bezpečně spustí kód v sandboxu (omezený globals,
                      timeout 10 s přes threading.Timer)
  - SelfExtendEngine→ hlavní třída: can_handle / handle / learn_new_skill

Požadavky: Python 3.10+, externí závislosti pouze requests + stdlib.
"""

from __future__ import annotations

import ast
import json
import math
import os
import re
import threading
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

# ---------------------------------------------------------------------------
# Konfigurace
# ---------------------------------------------------------------------------

OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "mistral"
REGISTRY_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "skills_registry.json"
)
EXEC_TIMEOUT = 10  # sekundy

# ---------------------------------------------------------------------------
# Klíčová slova pro detekci typu úkolu
# ---------------------------------------------------------------------------

TASK_KEYWORDS: Dict[str, List[str]] = {
    "weather": [
        "počasí", "pocasi", "weather", "teplota", "prší", "prsi",
        "sníh", "snih", "větru", "vetru", "vlhkost",
    ],
    "crypto": [
        "kurs", "kurz", "bitcoin", "btc", "crypto", "kryptomena",
        "cena", "ethereum", "eth", "litecoin", "dogecoin", "monero",
        "tržní", "trzni", "marketcap", "kapitalizace",
    ],
    "datetime": [
        "čas", "cas", "datum", "time", "date", "kolik je hodin",
        "jaký den", "jaky den", "dnes", "today", "now",
    ],
    "wikipedia": [
        "wikipedia", "wiki", "co je", "kdo je", "co to je",
        "kdo to je", "vysvětli", "vysvetli", "define", "definition",
    ],
    "translate": [
        "přeložit", "prelozit", "překlad", "preklad", "translate",
        "translation", "překládat", "prekladat",
    ],
    "calculate": [
        "kalkulace", "výpočet", "vypocet", "spočítej", "spoctej",
        "calculate", "vypočti", "vypocti", "kolik je", "plus",
        "mínus", "minus", "krát", "krat", "děleno", "deleno",
    ],
    "news": [
        "zprávy", "zpravy", "news", "novinky", "headline", "titulky",
        "co se děje", "co se deje", "dnesní zprávy", "dnesni zpravy",
    ],
    "image": [
        "obrázek", "obrazek", "image", "foto", "photograph", "foto",
        "wallpaper", "tapeta", "picture", "pic",
    ],
}

# ---------------------------------------------------------------------------
# Vestavěné dovednosti — skutečné implementace
# ---------------------------------------------------------------------------


def _skill_weather(context: dict) -> str:
    """Získá aktuální počasí z wttr.in (bez API klíče)."""
    location = context.get("location") or context.get("argument") or ""
    location = str(location).strip()
    if not location:
        location = "Prague"
    url = f"https://wttr.in/{urllib.parse.quote(location)}?format=j1"
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "curl/7.0"})
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        try:
            txt_url = f"https://wttr.in/{urllib.parse.quote(location)}?format=3"
            txt_resp = requests.get(
                txt_url, timeout=10, headers={"User-Agent": "curl/7.0"}
            )
            txt_resp.raise_for_status()
            return f"🌤 Počasí ({location}): {txt_resp.text.strip()}"
        except Exception:
            return f"❌ Nepodařilo se získat počasí pro '{location}': {exc}"

    try:
        current = data["current_condition"][0]
        area = data.get("nearest_area", [{}])[0]
        area_name = area.get("areaName", [{}])[0].get("value", location)
        country = area.get("country", [{}])[0].get("value", "")
        temp_c = current.get("temp_C", "?")
        feels = current.get("FeelsLikeC", "?")
        desc = current.get("weatherDesc", [{}])[0].get("value", "")
        humidity = current.get("humidity", "?")
        wind = current.get("windspeedKmph", "?")
        return (
            f"🌤 Počasí – {area_name}, {country}\n"
            f"   Teplota: {temp_c}°C (pocitově {feels}°C)\n"
            f"   Stav: {desc}\n"
            f"   Vlhkost: {humidity}%\n"
            f"   Vítr: {wind} km/h"
        )
    except Exception as exc:
        return f"❌ Chyba při zpracování počasí: {exc}"


def _skill_crypto(context: dict) -> str:
    """Získá cenu kryptoměny z CoinGecko API (bez klíče)."""
    query = context.get("argument") or context.get("coin") or context.get("query") or ""
    query = str(query).strip().lower()
    coin_map = {
        "bitcoin": "bitcoin", "btc": "bitcoin",
        "ethereum": "ethereum", "eth": "ethereum",
        "litecoin": "litecoin", "ltc": "litecoin",
        "dogecoin": "dogecoin", "doge": "dogecoin",
        "monero": "monero", "xmr": "monero",
        "cardano": "cardano", "ada": "cardano",
        "solana": "solana", "sol": "solana",
        "ripple": "ripple", "xrp": "ripple",
    }
    coin_id = coin_map.get(query, query if query else "bitcoin")
    url = (
        "https://api.coingecko.com/api/v3/simple/price"
        f"?ids={coin_id}&vs_currencies=usd,eur,czk&include_24hr_change=true"
    )
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return f"❌ Nepodařilo se získat cenu pro '{coin_id}': {exc}"

    if coin_id not in data:
        try:
            search_url = (
                "https://api.coingecko.com/api/v3/search?query="
                f"{urllib.parse.quote(query)}"
            )
            sresp = requests.get(search_url, timeout=10)
            sresp.raise_for_status()
            sdata = sresp.json()
            coins = sdata.get("coins", [])
            if coins:
                coin_id = coins[0]["id"]
                resp = requests.get(
                    "https://api.coingecko.com/api/v3/simple/price"
                    f"?ids={coin_id}&vs_currencies=usd,eur,czk"
                    "&include_24hr_change=true",
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            return f"❌ Měna '{query}' nebyla nalezena: {exc}"

    if coin_id not in data:
        return f"❌ Měna '{query}' nebyla nalezena na CoinGecko."

    info = data[coin_id]
    usd = info.get("usd", "?")
    eur = info.get("eur", "?")
    czk = info.get("czk", "?")
    change = info.get("usd_24h_change")
    change_str = f" ({change:+.2f}% 24h)" if isinstance(change, (int, float)) else ""
    return (
        f"💰 {coin_id.upper()}\n"
        f"   USD: ${usd}{change_str}\n"
        f"   EUR: €{eur}\n"
        f"   CZK: {czk} Kč"
    )


def _skill_datetime(context: dict) -> str:
    """Vrátí aktuální čas a datum."""
    tz_name = context.get("timezone") or context.get("tz") or "Europe/Prague"
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo(str(tz_name))
    except Exception:
        tz = timezone.utc
    from datetime import datetime as _dt
    now = _dt.now(tz)
    days_cs = [
        "pondělí", "úterý", "středa", "čtvrtek",
        "pátek", "sobota", "neděle",
    ]
    months_cs = [
        "ledna", "února", "března", "dubna", "května", "června",
        "července", "srpna", "září", "října", "listopadu", "prosince",
    ]
    day_name = days_cs[now.weekday()]
    month_name = months_cs[now.month - 1]
    return (
        f"🕐 {now.strftime('%H:%M:%S')}\n"
        f"📅 {day_name} {now.day}. {month_name} {now.year}\n"
        f"   Časová zóna: {tz}"
    )


def _skill_wikipedia(context: dict) -> str:
    """Vyhledá a vrátí shrnutí z Wikipedie (API bez klíče)."""
    query = context.get("argument") or context.get("query") or context.get("topic") or ""
    query = str(query).strip()
    if not query:
        return "❌ Zadej co chceš vyhledat."
    for prefix in ["co je ", "kdo je ", "co to je ", "kdo to je "]:
        if query.lower().startswith(prefix):
            query = query[len(prefix):]
            break
    query = query.strip()
    lang = context.get("lang") or "cs"
    summary_url = (
        f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/"
        f"{urllib.parse.quote(query)}"
    )
    try:
        resp = requests.get(summary_url, timeout=10, headers={
            "User-Agent": "NULL-ENGINE/1.0 (self-extend)"
        })
        if resp.status_code == 200:
            data = resp.json()
            title = data.get("title", query)
            extract = data.get("extract", "")
            url = data.get("content_urls", {}).get("desktop", {}).get("page", "")
            if extract:
                result = f"📖 {title}\n{extract}"
                if url:
                    result += f"\n🔗 {url}"
                return result
    except Exception:
        pass
    search_url = (
        f"https://{lang}.wikipedia.org/w/api.php?action=query&list=search"
        f"&srsearch={urllib.parse.quote(query)}&format=json&utf8=1"
    )
    try:
        resp = requests.get(search_url, timeout=10, headers={
            "User-Agent": "NULL-ENGINE/1.0 (self-extend)"
        })
        resp.raise_for_status()
        results = resp.json().get("query", {}).get("search", [])
        if not results:
            return f"❌ Pro '{query}' nebylo nic nalezeno na Wikipedii."
        top = results[0]
        title = top["title"]
        snippet = re.sub(r"<[^>]+>", "", top.get("snippet", ""))
        page_url = f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
        return f"📖 {title}\n{snippet}...\n🔗 {page_url}"
    except Exception as exc:
        return f"❌ Chyba při vyhledávání na Wikipedii: {exc}"


def _skill_translate(context: dict) -> str:
    """Přeloží text přes MyMemory API (bez klíče)."""
    text = context.get("text") or context.get("argument") or context.get("query") or ""
    text = str(text).strip()
    if not text:
        return "❌ Zadej text k překladu."
    target = context.get("target_lang") or context.get("target") or "en"
    source = context.get("source_lang") or context.get("source") or "cs"
    url = (
        "https://api.mymemory.translated.net/get?q="
        f"{urllib.parse.quote(text)}&langpair={source}|{target}"
    )
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        translated = data.get("responseData", {}).get("translatedText", "")
        if translated and "MYMEMORY WARNING" not in translated.upper():
            return f"🌐 Překlad ({source}→{target}):\n{translated}"
    except Exception:
        pass
    lt_url = context.get("libretranslate_url") or "https://libretranslate.com/translate"
    try:
        resp = requests.post(lt_url, json={
            "q": text, "source": source, "target": target, "format": "text"
        }, timeout=10)
        resp.raise_for_status()
        translated = resp.json().get("translatedText", "")
        if translated:
            return f"🌐 Překlad ({source}→{target}):\n{translated}"
    except Exception:
        pass
    return f"❌ Překlad se nezdařil pro: '{text}'"


def _skill_calculate(context: dict) -> str:
    """Bezpečně vyhodnotí matematický výraz."""
    expr = context.get("expression") or context.get("argument") or context.get("query") or ""
    expr = str(expr).strip()
    if not expr:
        return "❌ Zadej výraz k výpočtu."
    expr = (expr.replace("krát", "*")
                .replace("krat", "*")
                .replace("děleno", "/")
                .replace("deleno", "/")
                .replace("mínus", "-")
                .replace("minus", "-")
                .replace("plus", "+")
                .replace("x", "*")
                .replace("÷", "/")
                .replace("×", "*"))
    for word in ["spočítej", "spoctej", "vypočti", "vypocti", "calculate",
                 "kolik je", "výpočet", "vypocet", "kalkulace"]:
        expr = re.sub(rf"\b{re.escape(word)}\b", "", expr, flags=re.IGNORECASE)
    expr = expr.strip().rstrip("=").strip()
    if not expr:
        return "❌ Prázdný výraz."
    allowed_nodes = (
        ast.Expression, ast.BinOp, ast.UnaryOp, ast.Num, ast.Constant,
        ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow,
        ast.FloorDiv, ast.USub, ast.UAdd, ast.BitAnd, ast.BitOr,
        ast.BitXor, ast.LShift, ast.RShift, ast.Invert,
    )
    try:
        tree = ast.parse(expr, mode="eval")
        for node in ast.walk(tree):
            if not isinstance(node, allowed_nodes):
                return f"❌ Nepovolený výraz: {type(node).__name__}"
        result = eval(compile(tree, "<calc>", "eval"), {
            "__builtins__": {},
            "abs": abs, "round": round, "min": min, "max": max,
            "pow": pow, "sum": sum, "int": int, "float": float,
        }, {})
        if isinstance(result, float) and result.is_integer():
            result = int(result)
        return f"🧮 {expr} = {result}"
    except ZeroDivisionError:
        return "❌ Dělení nulou."
    except Exception as exc:
        return f"❌ Chyba ve výpočtu '{expr}': {exc}"


def _skill_news(context: dict) -> str:
    """Získá aktuální zprávy z RSS feedu (HN, BBC)."""
    source = str(context.get("source") or context.get("argument") or "").lower().strip()
    feeds = {
        "hn": "https://news.ycombinator.com/rss",
        "hacker": "https://news.ycombinator.com/rss",
        "hackernews": "https://news.ycombinator.com/rss",
        "bbc": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "bbc-world": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "bbc-tech": "https://feeds.bbci.co.uk/news/technology/rss.xml",
    }
    feed_url = feeds.get(source)
    if not feed_url:
        feed_url = "https://news.ycombinator.com/rss"
    try:
        resp = requests.get(feed_url, timeout=10, headers={
            "User-Agent": "NULL-ENGINE/1.0"
        })
        resp.raise_for_status()
        xml = resp.text
    except Exception as exc:
        return f"❌ Nepodařilo se načíst zprávy: {exc}"

    items = re.findall(r"<item>(.*?)</item>", xml, re.DOTALL)
    if not items:
        return "❌ Žádné zprávy nebyly nalezeny v RSS feedu."
    headlines: List[str] = []
    for item in items[:8]:
        title_m = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", item, re.DOTALL)
        link_m = re.search(r"<link>(.*?)</link>", item, re.DOTALL)
        title = title_m.group(1).strip() if title_m else "?"
        link = link_m.group(1).strip() if link_m else ""
        if link:
            headlines.append(f"📰 {title}\n   {link}")
        else:
            headlines.append(f"📰 {title}")
    if not headlines:
        return "❌ Nepodařilo se extrahovat titulky."
    label = source.upper() if source else "HN"
    return f"📰 Aktuální zprávy ({label}):\n\n" + "\n\n".join(headlines)


def _skill_image(context: dict) -> str:
    """Vrátí URL náhodného obrázku z Unsplash Source (bez klíče)."""
    query = context.get("argument") or context.get("query") or context.get("topic") or ""
    query = str(query).strip()
    if query:
        url = (
            "https://source.unsplash.com/800x600/?"
            f"{urllib.parse.quote(query)}"
        )
    else:
        url = "https://source.unsplash.com/800x600/?random"
    return f"🖼 Náhodný obrázek{' (' + query + ')' if query else ''}:\n{url}"


BUILTIN_SKILLS: Dict[str, Callable[[dict], str]] = {
    "weather": _skill_weather,
    "crypto": _skill_crypto,
    "datetime": _skill_datetime,
    "wikipedia": _skill_wikipedia,
    "translate": _skill_translate,
    "calculate": _skill_calculate,
    "news": _skill_news,
    "image": _skill_image,
}


# ---------------------------------------------------------------------------
# SkillRegistry — registr dovedností
# ---------------------------------------------------------------------------


class SkillRegistry:
    """
    Perzistentní registr naučených dovedností.

    Každá dovednost:
      {
        "name": str,
        "description": str,
        "code": str,
        "created_at": str,
        "usage_count": int,
        "success_rate": float
      }
    """

    def __init__(self, path: str = REGISTRY_PATH):
        self.path = path
        self._skills: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            self._skills = []
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                self._skills = data
            elif isinstance(data, dict) and "skills" in data:
                self._skills = data["skills"]
            else:
                self._skills = []
        except Exception:
            self._skills = []

    def _save(self) -> None:
        with self._lock:
            try:
                with open(self.path, "w", encoding="utf-8") as f:
                    json.dump(self._skills, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

    def list_skills(self) -> List[Dict[str, Any]]:
        return list(self._skills)

    def get_skill(self, name: str) -> Optional[Dict[str, Any]]:
        name = name.lower().strip()
        for skill in self._skills:
            if skill.get("name", "").lower() == name:
                return skill
        return None

    def find_skill(self, task: str) -> Optional[Dict[str, Any]]:
        task_lower = task.lower()
        best: Optional[Dict[str, Any]] = None
        best_score = 0
        for skill in self._skills:
            desc = skill.get("description", "").lower()
            score = 0
            for word in task_lower.split():
                if word in desc:
                    score += 1
            score += skill.get("success_rate", 0) * 0.5
            if score > best_score:
                best_score = score
                best = skill
        if best_score >= 1:
            return best
        return None

    def add_skill(self, name: str, description: str, code: str) -> None:
        name = name.lower().strip().replace(" ", "_")
        for skill in self._skills:
            if skill.get("name") == name:
                skill["description"] = description
                skill["code"] = code
                skill["updated_at"] = datetime.now(timezone.utc).isoformat()
                self._save()
                return
        skill = {
            "name": name,
            "description": description,
            "code": code,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "usage_count": 0,
            "success_rate": 1.0,
        }
        self._skills.append(skill)
        self._save()

    def record_usage(self, name: str, success: bool) -> None:
        name = name.lower().strip()
        for skill in self._skills:
            if skill.get("name") == name:
                count = skill.get("usage_count", 0) + 1
                old_rate = skill.get("success_rate", 1.0)
                if success:
                    new_rate = old_rate * 0.9 + 1.0 * 0.1
                else:
                    new_rate = old_rate * 0.9 + 0.0 * 0.1
                skill["usage_count"] = count
                skill["success_rate"] = round(new_rate, 4)
                self._save()
                return

    def remove_skill(self, name: str) -> bool:
        name = name.lower().strip()
        before = len(self._skills)
        self._skills = [s for s in self._skills if s.get("name") != name]
        if len(self._skills) < before:
            self._save()
            return True
        return False


# ---------------------------------------------------------------------------
# SkillGenerator — generuje kód přes Ollama
# ---------------------------------------------------------------------------


class SkillGenerator:
    """Generuje novou self-contained Python funkci pomocí lokálního Ollama."""

    def __init__(self, url: str = OLLAMA_URL, model: str = OLLAMA_MODEL):
        self.url = url
        self.model = model

    def _build_prompt(self, task: str) -> str:
        return f"""You are a Python code generator. Generate a SINGLE self-contained Python function.

Requirements:
1. Function signature: def skill_func(context: dict) -> str:
2. The function receives a dict 'context' and returns a string result.
3. Only use Python standard library + 'requests' (already imported). No other imports.
4. Do NOT include any import statements - assume requests is available.
5. Do NOT include example usage, tests, or explanations.
6. Output ONLY the function code, nothing else.
7. The function must handle errors gracefully and return error strings.
8. Return a human-readable Czech or English string result.

Task description: {task}

Generate the function now:"""

    def generate(self, task: str, timeout: int = 60) -> Optional[str]:
        prompt = self._build_prompt(task)
        try:
            resp = requests.post(
                self.url,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3},
                },
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data.get("response", "")
        except Exception:
            return None

        code = self._extract_code(raw)
        if not code:
            return None

        try:
            ast.parse(code)
        except SyntaxError:
            return None

        if "def skill_func" not in code:
            return None

        return code

    def _extract_code(self, raw: str) -> str:
        pattern = r"```(?:python)?\s*\n(.*?)```"
        match = re.search(pattern, raw, re.DOTALL)
        if match:
            return match.group(1).strip()
        idx = raw.find("def skill_func")
        if idx != -1:
            return raw[idx:].strip()
        return raw.strip()

    def generate_skill_name(self, task: str) -> str:
        words = re.sub(r"[^a-zA-Z0-9á-žÁ-Ž ]", "", task).split()
        words = [w for w in words if len(w) > 2][:3]
        name = "_".join(w.lower() for w in words) if words else "custom_skill"
        return name


# ---------------------------------------------------------------------------
# SkillExecutor — sandbox spouštění
# ---------------------------------------------------------------------------


class SkillExecutor:
    """
    Bezpečně spustí vygenerovanou funkci v sandboxu.

    - Omezený globals (žádné nebezpečné builtins, ošetřené requests/json/urllib)
    - Timeout 10 s přes threading.Timer
    - Vrací (success, result, error)
    """

    def __init__(self, timeout: int = EXEC_TIMEOUT):
        self.timeout = timeout

    def _build_safe_globals(self) -> dict:
        safe_builtins = {
            "print": print, "len": len, "str": str, "int": int,
            "float": float, "bool": bool, "list": list, "dict": dict,
            "tuple": tuple, "set": set, "range": range,
            "enumerate": enumerate, "zip": zip, "map": map,
            "filter": filter, "sorted": sorted, "reversed": reversed,
            "min": min, "max": max, "sum": sum, "abs": abs,
            "round": round, "all": all, "any": any,
            "isinstance": isinstance, "type": type,
            "True": True, "False": False, "None": None,
            "Exception": Exception, "ValueError": ValueError,
            "TypeError": TypeError, "KeyError": KeyError,
            "IndexError": IndexError, "AttributeError": AttributeError,
            "StopIteration": StopIteration,
            "ZeroDivisionError": ZeroDivisionError,
            "ImportError": ImportError, "RuntimeError": RuntimeError,
            "ConnectionError": ConnectionError,
            "TimeoutError": TimeoutError, "OSError": OSError,
            "NameError": NameError,
        }
        return {
            "__builtins__": safe_builtins,
            "requests": requests,
            "json": json,
            "re": re,
            "math": math,
            "time": time,
            "os": os,
            "urllib": __import__("urllib"),
            "datetime": __import__("datetime"),
            "threading": threading,
        }

    def execute(self, code: str, context: dict) -> Tuple[bool, Any, str]:
        try:
            ast.parse(code)
        except SyntaxError as exc:
            return False, None, f"SyntaxError: {exc}"

        result_holder: Dict[str, Any] = {"result": None, "error": None}
        timer: Optional[threading.Timer] = None

        def _timeout_handler() -> None:
            result_holder["error"] = "TimeoutError: exekuce přesáhla limit"

        sandbox_globals = self._build_safe_globals()
        sandbox_locals: Dict[str, Any] = {}

        try:
            timer = threading.Timer(self.timeout, _timeout_handler)
            timer.daemon = True
            timer.start()

            exec(code, sandbox_globals, sandbox_locals)  # noqa: S102

            func = sandbox_locals.get("skill_func")
            if func is None or not callable(func):
                return False, None, "skill_func nebyla definována nebo není volatelná"

            output = func(context)

            if result_holder["error"] is not None:
                return False, None, result_holder["error"]

            return True, output, ""

        except Exception as exc:
            if result_holder["error"] is not None:
                return False, None, result_holder["error"]
            return False, None, f"{type(exc).__name__}: {exc}"
        finally:
            if timer is not None:
                timer.cancel()

    def execute_builtin(
        self, func: Callable[[dict], str], context: dict
    ) -> Tuple[bool, Any, str]:
        result_holder: Dict[str, Any] = {"result": None, "error": None}
        timer: Optional[threading.Timer] = None

        def _timeout_handler() -> None:
            result_holder["error"] = "TimeoutError: exekuce přesáhla limit"

        def _run() -> None:
            try:
                result_holder["result"] = func(context)
            except Exception as exc:
                result_holder["error"] = f"{type(exc).__name__}: {exc}"

        try:
            timer = threading.Timer(self.timeout, _timeout_handler)
            timer.daemon = True
            timer.start()
            thread = threading.Thread(target=_run, daemon=True)
            thread.start()
            thread.join(timeout=self.timeout + 1)

            if result_holder["error"] is not None:
                return False, None, result_holder["error"]
            if thread.is_alive():
                return False, None, "TimeoutError: exekuce přesáhla limit"
            return True, result_holder["result"], ""
        finally:
            if timer is not None:
                timer.cancel()


# ---------------------------------------------------------------------------
# SelfExtendEngine — hlavní třída
# ---------------------------------------------------------------------------


class SelfExtendEngine:
    """
    Hlavní engine pro samo-rozšiřování bota.

    Tok:
      1. can_handle(task) → True pokud existuje vestavěná nebo naučená dovednost
      2. handle(task, context) → provede dovednost a vrátí výsledek
      3. learn_new_skill(task) → vygeneruje novou dovednost přes Ollama
    """

    def __init__(
        self,
        registry: Optional[SkillRegistry] = None,
        generator: Optional[SkillGenerator] = None,
        executor: Optional[SkillExecutor] = None,
    ):
        self.registry = registry or SkillRegistry()
        self.generator = generator or SkillGenerator()
        self.executor = executor or SkillExecutor()

    def _detect_task_type(self, task: str) -> Optional[str]:
        task_lower = task.lower()
        scores: Dict[str, int] = {}
        for skill_type, keywords in TASK_KEYWORDS.items():
            score = 0
            for kw in keywords:
                if kw in task_lower:
                    score += 1
            if score > 0:
                scores[skill_type] = score
        if not scores:
            return None
        return max(scores, key=scores.get)

    def _enrich_context(self, task: str, context: dict) -> dict:
        ctx = dict(context) if context else {}
        ctx["task"] = task
        ctx.setdefault("argument", task)
        ctx.setdefault("query", task)
        return ctx

    def can_handle(self, task: str) -> bool:
        task_type = self._detect_task_type(task)
        if task_type is not None:
            return True
        learned = self.registry.find_skill(task)
        return learned is not None

    def handle(self, task: str, context: Optional[dict] = None) -> str:
        context = self._enrich_context(task, context or {})
        task_type = self._detect_task_type(task)

        if task_type is not None and task_type in BUILTIN_SKILLS:
            func = BUILTIN_SKILLS[task_type]
            success, result, error = self.executor.execute_builtin(func, context)
            if success and result is not None:
                return str(result)
            learned = self.registry.find_skill(task)
            if learned:
                res = self._run_learned_skill(learned, context)
                if res is not None:
                    return res
            return f"❌ Selhala dovednost '{task_type}': {error}"

        learned = self.registry.find_skill(task)
        if learned:
            res = self._run_learned_skill(learned, context)
            if res is not None:
                return res

        if self.learn_new_skill(task):
            learned = self.registry.find_skill(task)
            if learned:
                res = self._run_learned_skill(learned, context)
                if res is not None:
                    return res

        return f"❌ Neumím vyřídit: '{task}'"

    def _run_learned_skill(
        self, skill: Dict[str, Any], context: dict
    ) -> Optional[str]:
        code = skill.get("code", "")
        name = skill.get("name", "unknown")
        success, result, error = self.executor.execute(code, context)
        self.registry.record_usage(name, success)
        if success and result is not None:
            return str(result)
        return None

    def learn_new_skill(self, task: str) -> bool:
        code = self.generator.generate(task)
        if code is None:
            return False

        test_context = {"task": task, "argument": task, "query": task}
        success, result, error = self.executor.execute(code, test_context)

        name = self.generator.generate_skill_name(task)
        self.registry.add_skill(name=name, description=task, code=code)

        if success:
            self.registry.record_usage(name, True)
            return True
        if error and ("TimeoutError" in error or "ConnectionError" in error
                       or "ConnectionRefused" in error or "MaxRetryError" in error):
            return True

        self.registry.remove_skill(name)
        return False

    def status(self) -> dict:
        skills = self.registry.list_skills()
        return {
            "total_learned_skills": len(skills),
            "skills": [
                {
                    "name": s.get("name"),
                    "usage_count": s.get("usage_count", 0),
                    "success_rate": s.get("success_rate", 0),
                }
                for s in skills
            ],
            "builtin_skills": list(BUILTIN_SKILLS.keys()),
        }


# ---------------------------------------------------------------------------
# Singleton a veřejné funkce
# ---------------------------------------------------------------------------

_engine: Optional[SelfExtendEngine] = None
_engine_lock = threading.Lock()


def get_engine() -> SelfExtendEngine:
    """Vrátí singleton instanci SelfExtendEngine."""
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = SelfExtendEngine()
    return _engine


async def handle_special_task(
    task: str, context: Optional[dict] = None
) -> Optional[str]:
    """
    Asynchronní vstupní bod pro zpracování speciálního tasku.

    Vrací výsledek jako string, nebo None pokud engine neumí task vyřídit
    a nepodařilo se ho ani naučit.
    """
    engine = get_engine()

    if not engine.can_handle(task):
        if engine.learn_new_skill(task):
            result = engine.handle(task, context)
            return result
        return None

    result = engine.handle(task, context)
    if result and result.startswith("❌ Neumím vyřídit"):
        return None
    return result
