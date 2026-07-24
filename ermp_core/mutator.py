"""
ermp_core.mutator – univerzální AI generátor výstupů pomocí Ollama.

Podporované typy výstupů (automatická detekce z popisu):
  - game       → HTML/JS hra
  - web        → Landing page / web
  - tool       → Interaktivní nástroj (kalkulačka, generátor, konvertor)
  - pwa        → Progressive Web App (instalovatelná na mobil)
  - script     → Python / Bash skript (ke stažení)
  - document   → HTML dokument / šablona
  - quiz       → Kvíz / test
  - dashboard  → Dashboard / admin panel

Vyžaduje běžící lokální Ollama (http://localhost:11434) s modelem mistral.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests

# ---------------------------------------------------------------------------
# Konfigurace
# ---------------------------------------------------------------------------
OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "mistral"
TELEGRAPH_API = "https://api.telegra.ph"
DB_PATH       = "db.json"
TEMPLATES_PATH = os.path.join(os.path.dirname(__file__), "templates.py")

# ---------------------------------------------------------------------------
# Detekce typu výstupu
# ---------------------------------------------------------------------------

OUTPUT_KEYWORDS: Dict[str, List[str]] = {
    "game": [
        "hra", "game", "hraj", "hráč", "level", "score", "skóre", "puzzle",
        "arkáda", "platformer", "RPG", "tetris", "had", "snake", "clicker",
        "střílečka", "závodní", "piškvorky", "šachy", "minecraft", "mario",
    ],
    "web": [
        "web", "stránka", "stránky", "landing", "portfolio", "prezentace",
        "blog", "e-shop", "obchod", "web app", "website", "homepage",
        "firemní", "vizitka", "restaurace", "kavárna", "produktová",
    ],
    "tool": [
        "nástroj", "tool", "kalkulačka", "kalkulátor", "konvertor",
        "generátor", "převodník", "checker", "validator", "timer",
        "stopky", "odpočet", "countdown", "heslo", "password",
        "qr kód", "qr code", "šifrování", "encode", "decode",
    ],
    "pwa": [
        "pwa", "aplikace", "app", "mobilní", "instalovat", "offline",
        "push notifikace", "service worker",
    ],
    "script": [
        "skript", "script", "python", "bash", "automatizace", "automate",
        "bot", "scraper", "stažení", "download", "api", "cli",
    ],
    "document": [
        "dokument", "document", "smlouva", "šablona", "template",
        "faktura", "invoice", "životopis", "cv", "report", "zpráva",
    ],
    "quiz": [
        "kvíz", "quiz", "test", "otázky", "otázka", "odpovědi",
        "zkouška", "trivia", "vědomostní",
    ],
    "dashboard": [
        "dashboard", "panel", "admin", "statistiky", "analytics",
        "grafy", "chart", "monitoring", "přehled",
    ],
}

def detect_output_type(description: str) -> str:
    """Detekuje typ výstupu z popisu uživatele. Vrátí string typ."""
    desc_lower = description.lower()
    scores: Dict[str, int] = {t: 0 for t in OUTPUT_KEYWORDS}
    for output_type, keywords in OUTPUT_KEYWORDS.items():
        for kw in keywords:
            if kw in desc_lower:
                scores[output_type] += 1
    best = max(scores, key=lambda t: scores[t])
    # Pokud žádné klíčové slovo nesedí, výchozí je "tool"
    return best if scores[best] > 0 else "tool"

# ---------------------------------------------------------------------------
# Self-mutating wrapper (kosmetický JS pro hry/weby)
# ---------------------------------------------------------------------------

MUTATING_WRAPPER_JS = r"""
<script>
(function () {
  'use strict';
  var KEY = 'ermp_first_run';
  var firstRun = localStorage.getItem(KEY);
  var now = Date.now();
  if (!firstRun) { firstRun = now.toString(); localStorage.setItem(KEY, firstRun); }
  var elapsed = now - parseInt(firstRun, 10);
  var MUTATION_MS = 24 * 60 * 60 * 1000;
  var MUTATIONS = [
    function() { document.documentElement.style.filter = 'hue-rotate(180deg) invert(0.06)'; },
    function() {
      var badge = document.createElement('div');
      badge.textContent = '⭐ NEW UPDATE';
      badge.style.cssText = 'position:fixed;top:10px;right:10px;background:linear-gradient(135deg,#ff6b6b,#feca57);color:#fff;padding:8px 16px;border-radius:20px;font-family:sans-serif;font-weight:bold;font-size:13px;z-index:99999;box-shadow:0 2px 12px rgba(0,0,0,.3);';
      document.body.appendChild(badge);
    },
    function() {
      var s = document.createElement('style');
      s.textContent = 'body{animation:ermp-bg 8s ease infinite}@keyframes ermp-bg{0%,100%{filter:none}50%{filter:brightness(1.08) saturate(1.2)}}';
      document.head.appendChild(s);
    }
  ];
  function applyMutation() {
    var idx = Math.floor(Math.random() * MUTATIONS.length);
    try { MUTATIONS[idx](); } catch(e) {}
  }
  if (elapsed >= MUTATION_MS) { applyMutation(); }
  else { setTimeout(applyMutation, MUTATION_MS - elapsed); }
})();
</script>
"""

# ---------------------------------------------------------------------------
# Prompty pro jednotlivé typy výstupů
# ---------------------------------------------------------------------------

def _build_prompt(
    description: str,
    output_type: str,
    ton_address: str,
    referral_code: str,
) -> str:
    """Sestaví specializovaný prompt pro daný typ výstupu."""

    ton_btn = (
        f"<div style='text-align:center;margin:20px 0;'>"
        f"<a href='ton://transfer/{ton_address}?amount=3000000000&text={referral_code}' "
        f"style='background:#0088cc;color:#fff;padding:12px 24px;border-radius:8px;"
        f"text-decoration:none;font-weight:bold;font-size:15px;'>⚡ Podpořit tvůrce (3 TON)</a>"
        f"</div>"
        f"<p style='text-align:center;font-size:11px;color:#aaa;'>ref: {referral_code}</p>"
    )

    base = (
        "Jsi expert vývojář. Vygeneruj KOMPLETNÍ, funkční self-contained HTML soubor.\n"
        "PRAVIDLA (MUSÍŠ dodržet):\n"
        "1. Vše v jednom HTML souboru. Žádné externí soubory.\n"
        "2. Moderní, responzivní design (mobile-first).\n"
        "3. Kód musí fungovat okamžitě po otevření v prohlížeči.\n"
        "4. Těsně před </body> vlož PŘESNĚ tento HTML blok:\n"
        f"   {ton_btn}\n"
        "5. Vrať POUZE HTML bez vysvětlení, bez markdown obalů.\n\n"
    )

    TYPE_INSTRUCTIONS = {
        "game": (
            "Vytvoř plně hratelnou HROU. Musí mít:\n"
            "- Herní smyčku (game loop), skóre, game over stav\n"
            "- Ovládání klávesnicí i dotykem (mobilní tlačítka)\n"
            "- Hezký UI s animacemi\n"
            "- Canvas nebo DOM-based rendering\n\n"
        ),
        "web": (
            "Vytvoř profesionální WEB / LANDING PAGE. Musí mít:\n"
            "- Hero sekci s nadpisem a CTA tlačítkem\n"
            "- Sekci funkcí / výhod (features)\n"
            "- Responzivní navigaci (hamburger menu na mobilu)\n"
            "- Footer s kontaktem\n"
            "- Smooth scroll animace\n\n"
        ),
        "tool": (
            "Vytvoř praktický INTERAKTIVNÍ NÁSTROJ. Musí mít:\n"
            "- Přehledné vstupní formuláře\n"
            "- Okamžité výsledky bez reloadu stránky\n"
            "- Jasné instrukce pro uživatele\n"
            "- Možnost kopírovat / stáhnout výsledek\n\n"
        ),
        "pwa": (
            "Vytvoř PROGRESSIVE WEB APP. Musí mít:\n"
            "- Manifest meta tagy pro instalaci\n"
            "- Offline-ready (localStorage fallback)\n"
            "- Add to Home Screen prompt\n"
            "- App-like UI (bez scrollbaru, full-height)\n\n"
        ),
        "script": (
            "Vytvoř HTML stránku s:\n"
            "- Zobrazeným a zvýrazněným kódem skriptu (syntax highlight)\n"
            "- Tlačítkem 'Stáhnout skript'\n"
            "- Návodem jak skript použít\n"
            "- Kopírovat do schránky funkcí\n\n"
        ),
        "document": (
            "Vytvoř HTML DOKUMENT / ŠABLONU. Musí mít:\n"
            "- Profesionální typografii\n"
            "- Editovatelné pole (contenteditable) pro klíčové části\n"
            "- Tlačítko pro tisk (window.print())\n"
            "- Čistý, formální vzhled\n\n"
        ),
        "quiz": (
            "Vytvoř interaktivní KVÍZ. Musí mít:\n"
            "- Alespoň 5 otázek s možnostmi A/B/C/D\n"
            "- Průběžné skóre a finální výsledek\n"
            "- Barevný feedback (správně = zelená, špatně = červená)\n"
            "- Animace přechodu mezi otázkami\n\n"
        ),
        "dashboard": (
            "Vytvoř DASHBOARD / ADMIN PANEL. Musí mít:\n"
            "- Sidebar navigaci\n"
            "- Stat karty s čísly a trendy\n"
            "- Alespoň jeden interaktivní graf (Chart.js z CDN)\n"
            "- Tmavý nebo světlý moderní design\n\n"
        ),
    }

    instructions = TYPE_INSTRUCTIONS.get(output_type, TYPE_INSTRUCTIONS["tool"])
    return base + instructions + f"POPIS OD UŽIVATELE:\n{description}\n"


# ---------------------------------------------------------------------------
# Ollama volání
# ---------------------------------------------------------------------------

def _call_ollama(prompt: str, timeout: int = 180) -> str:
    """Zavolá lokální Ollama API a vrátí vygenerovaný text."""
    payload: Dict[str, Any] = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.75, "num_predict": 6000},
    }
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json().get("response", "")
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            "Nelze se připojit k Ollama na http://localhost:11434. "
            "Spusť Ollama příkazem: ollama serve"
        )
    except requests.exceptions.Timeout:
        raise RuntimeError(f"Ollama nestihla odpovědět za {timeout}s.")


def _extract_html(text: str) -> str:
    """Extrahuje čistý HTML kód z odpovědi LLM."""
    fence = re.search(r"```(?:html)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1)
    start = re.search(r"(<!DOCTYPE html|<html)", text, re.IGNORECASE)
    if start:
        text = text[start.start():]
    end = re.search(r"</html>\s*$", text, re.IGNORECASE)
    if end:
        text = text[: end.end()]
    return text.strip()


def _inject_mutation(html: str) -> str:
    """Vloží self-mutating wrapper před </body>."""
    target = html.lower().rfind("</body>")
    if target != -1:
        return html[:target] + MUTATING_WRAPPER_JS + "\n" + html[target:]
    target = html.lower().rfind("</html>")
    if target != -1:
        return html[:target] + MUTATING_WRAPPER_JS + "\n" + html[target:]
    return html + "\n" + MUTATING_WRAPPER_JS


# ---------------------------------------------------------------------------
# Telegraph API
# ---------------------------------------------------------------------------

def _telegraph_create_account() -> str:
    """Vytvoří anonymní Telegraph účet a vrátí access_token."""
    resp = requests.post(
        f"{TELEGRAPH_API}/createAccount",
        json={"short_name": "NullEngine", "author_name": "NULL ENGINE Bot"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegraph createAccount selhal: {data}")
    return data["result"]["access_token"]


def _telegraph_create_page(token: str, title: str, html_content: str) -> str:
    """Nahraje obsah na Telegraph a vrátí URL stránky."""
    # Telegraph DOM node formát – obalíme do <pre> pro raw HTML
    content_nodes = [{"tag": "p", "children": [html_content[:10000]]}]
    resp = requests.post(
        f"{TELEGRAPH_API}/createPage",
        json={
            "access_token": token,
            "title": title[:255],
            "content": content_nodes,
            "return_content": False,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegraph createPage selhal: {data}")
    return data["result"]["url"]


# ---------------------------------------------------------------------------
# Hlavní veřejná funkce
# ---------------------------------------------------------------------------

def generate_ermp_app(
    description: str,
    ton_address: str = "",
    referral_code: str = "NULL",
) -> Tuple[str, str]:
    """
    Vygeneruje self-contained HTML aplikaci pomocí Ollama a nahraje na Telegraph.

    Args:
        description:   Popis aplikace od uživatele (přirozený jazyk).
        ton_address:   TON adresa vlastníka pro platební tlačítko.
        referral_code: Unikátní kód uživatele pro sledování pozvánek.

    Returns:
        Tuple (telegraph_url, output_type) – URL výsledku a typ výstupu.
    """
    # 1) Detekce typu
    output_type = detect_output_type(description)

    # 2) Sestavení promptu
    prompt = _build_prompt(description, output_type, ton_address, referral_code)

    # 3) Generování přes Ollama
    raw = _call_ollama(prompt)

    # 4) Extrakce HTML
    html = _extract_html(raw)
    if not html:
        raise RuntimeError("Ollama nevrátila validní HTML kód. Zkus jiný popis.")

    # 5) Inject mutating wrapperu (pouze pro hry/weby)
    if output_type in ("game", "web", "pwa", "dashboard"):
        html = _inject_mutation(html)

    # 5b) Inject virálního watermarku (do všech výstupů)
    html = _inject_viral_watermark(html, ton_address, referral_code)

    # 6) Nahrání na Telegraph
    try:
        token = _telegraph_create_account()
        title = f"NULL ENGINE – {output_type.upper()} – {description[:50]}"
        url = _telegraph_create_page(token, title, html)
    except Exception as e:
        raise RuntimeError(f"Telegraph upload selhal: {e}")

    return url, output_type


# ---------------------------------------------------------------------------
# Autonomní generování šablon (spouštěno periodicko úlohou)
# ---------------------------------------------------------------------------

def _load_db() -> Dict[str, Any]:
    if not os.path.exists(DB_PATH):
        return {}
    with open(DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _analyze_requests(db: Dict[str, Any]) -> List[str]:
    """Najde nejčastější slova v požadavcích uživatelů (stoplist odfiltruje běžná slova)."""
    STOPLIST = {
        "a", "i", "s", "v", "na", "do", "to", "je", "že", "se", "co",
        "pro", "jak", "kde", "ale", "nebo", "chci", "chce", "vytvor",
        "udělej", "udelej", "potřebuju", "prosím", "prosim", "please",
    }
    words: List[str] = []
    for user_data in db.values():
        for req in user_data.get("requests", []):
            words.extend([
                w.lower() for w in re.findall(r"\b\w{3,}\b", req)
                if w.lower() not in STOPLIST
            ])
    counter = Counter(words)
    return [w for w, _ in counter.most_common(5)]


def _append_template_to_file(template: Dict[str, Any]) -> None:
    """Přidá novou šablonu do templates.py."""
    with open(TEMPLATES_PATH, "a", encoding="utf-8") as f:
        f.write(f"\n# Auto-generated template – {datetime.now().isoformat()}\n")
        f.write(f"TEMPLATES.append({json.dumps(template, ensure_ascii=False, indent=2)})\n")


def auto_generate_template() -> None:
    """
    Analyzuje požadavky uživatelů a vygeneruje novou šablonu přes Ollama.
    Šablonu uloží do templates.py.
    """
    db = _load_db()
    if not db:
        return

    top_words = _analyze_requests(db)
    if not top_words:
        return

    topic = ", ".join(top_words)
    prompt = (
        f"Na základě populárních témat ({topic}) vygeneruj jednu novou HTML hru nebo nástroj. "
        "Vrať pouze čistý HTML kód bez komentářů."
    )

    try:
        raw = _call_ollama(prompt, timeout=120)
        html = _extract_html(raw)
        if html:
            template = {
                "name": f"Auto: {topic[:40]}",
                "description": f"Automaticky vygenerovaná šablona. Témata: {topic}",
                "html_skeleton": html[:5000],
            }
            _append_template_to_file(template)
    except Exception as e:
        # Autonomní úloha – chyby logujeme, ale nepadáme
        print(f"[auto_generate_template] Chyba: {e}")


def publish_html(html: str, title: str = "NULL ENGINE") -> str:
    """
    Publikuje HTML na Telegraph a vrátí URL.
    Používá se pro IPTV a další standalone HTML výstupy.
    """
    token = _telegraph_create_account()
    if not token:
        raise RuntimeError("Telegraph účet nelze vytvořit")
    url = _telegraph_create_page(token, html, title)
    return url
