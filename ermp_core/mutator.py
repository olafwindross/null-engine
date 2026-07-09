"""
ermp_core.mutator – generování self-contained HTML aplikací pomocí Ollama,
self-mutating wrapper logiky a publikace na Telegraph.

Vyžaduje běžící lokální Ollama (http://localhost:11434) s modelem mistral.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

# ---------------------------------------------------------------------------
# Konfigurace
# ---------------------------------------------------------------------------
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "mistral"
TELEGRAPH_API = "https://api.telegra.ph"
DB_PATH = "db.json"
TEMPLATES_PATH = os.path.join(os.path.dirname(__file__), "templates.py")

# ---------------------------------------------------------------------------
# Self-mutating wrapper
# ---------------------------------------------------------------------------
# JavaScript, který se vloží do každé vygenerované aplikace.
# Uloží datum prvního spuštění do localStorage a po 24 hodinách provede
# kosmetickou / herní změnu (změní barevné schéma a přidá herní prvek).
# Jde o feature pro uživatele – ne o obfuskaci ani škodlivý kód.

MUTATING_WRAPPER_JS = r"""
<script>
(function () {
  'use strict';
  var KEY = 'ermp_first_run';
  var firstRun = localStorage.getItem(KEY);
  var now = Date.now();
  if (!firstRun) {
    firstRun = now.toString();
    localStorage.setItem(KEY, firstRun);
  }
  var elapsed = now - parseInt(firstRun, 10);
  var MUTATION_HOURS = 24;
  var MUTATION_MS = MUTATION_HOURS * 60 * 60 * 1000;

  // Knihovna mutací – každá je kosmetická / herní, nikdy škodlivá.
  var MUTATIONS = [
    function colorShift() {
      // Prohodí základní barvy (inverze světlých/tmavých odstínů).
      document.documentElement.style.filter = 'hue-rotate(180deg) invert(0.08)';
    },
    function speedBoost() {
      // Zrychlí herní smyčku, pokud existuje.
      if (typeof gameSpeed !== 'undefined') { gameSpeed *= 1.4; }
      if (typeof GAME_SPEED !== 'undefined') { GAME_SPEED *= 1.4; }
      // Pokus o úpravu requestAnimationFrame intervalu.
      var scripts = document.querySelectorAll('script');
      // Nelze dynamicky měnit already-executed script, ale můžeme signalizovat.
      document.body.setAttribute('data-mutation', 'speed-boost');
    },
    function newLevel() {
      // Přidá vizuální indikátor nového levelu / prvku.
      var badge = document.createElement('div');
      badge.textContent = '⭐ NEW LEVEL UNLOCKED';
      badge.style.cssText = 'position:fixed;top:10px;right:10px;'
        + 'background:linear-gradient(135deg,#ff6b6b,#feca57);'
        + 'color:#fff;padding:8px 16px;border-radius:20px;'
        + 'font-family:sans-serif;font-weight:bold;font-size:14px;'
        + 'z-index:99999;box-shadow:0 2px 12px rgba(0,0,0,0.3);'
        + 'animation:ermp-pulse 2s infinite;';
      var style = document.createElement('style');
      style.textContent = '@keyframes ermp-pulse{0%,100%{opacity:1}'
        + '50%{opacity:0.6}}';
      document.head.appendChild(style);
      document.body.appendChild(badge);
    },
    function particleOverlay() {
      // Přidá jemný particle overlay jako kosmetický efekt.
      var cvs = document.createElement('canvas');
      cvs.style.cssText = 'position:fixed;top:0;left:0;width:100%;'
        + 'height:100%;pointer-events:none;z-index:99998;opacity:0.3;';
      document.body.appendChild(cvs);
      var ctx = cvs.getContext('2d');
      function resize() { cvs.width = innerWidth; cvs.height = innerHeight; }
      resize(); window.addEventListener('resize', resize);
      var particles = [];
      for (var i = 0; i < 40; i++) {
        particles.push({
          x: Math.random() * cvs.width,
          y: Math.random() * cvs.height,
          r: Math.random() * 3 + 1,
          vx: (Math.random() - 0.5) * 0.5,
          vy: (Math.random() - 0.5) * 0.5
        });
      }
      function loop() {
        ctx.clearRect(0, 0, cvs.width, cvs.height);
        ctx.fillStyle = '#feca57';
        for (var i = 0; i < particles.length; i++) {
          var p = particles[i];
          p.x += p.vx; p.y += p.vy;
          if (p.x < 0) p.x = cvs.width;
          if (p.x > cvs.width) p.x = 0;
          if (p.y < 0) p.y = cvs.height;
          if (p.y > cvs.height) p.y = 0;
          ctx.beginPath();
          ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
          ctx.fill();
        }
        requestAnimationFrame(loop);
      }
      loop();
    }
  ];

  function applyMutation() {
    // Aplikuje náhodnou mutaci (vždy kosmetickou / herní).
    var idx = Math.floor(Math.random() * MUTATIONS.length);
    try { MUTATIONS[idx](); } catch (e) { /* bezpečnostní fallback */ }
    // Zaznamená mutaci do localStorage.
    localStorage.setItem('ermp_last_mutation', new Date().toISOString());
  }

  if (elapsed >= MUTATION_MS) {
    // Uplynulo 24 h od prvního spuštění – proveď mutaci.
    applyMutation();
  } else {
    // Naplánuje mutaci na zbývající čas.
    var remaining = MUTATION_MS - elapsed;
    setTimeout(applyMutation, remaining);
  }
})();
</script>
"""

# ---------------------------------------------------------------------------
# Pomocné funkce
# ---------------------------------------------------------------------------

def _build_prompt(description: str, ton_address: str, referral_code: str) -> str:
    """Sestaví prompt pro Ollama, který generuje self-contained HTML aplikaci."""
    ton_link = (
        f"<a href='ton://transfer/{ton_address}?amount=3000000000"
        f"&text={referral_code}'>Podpořit tvůrce (3 TON)</a>"
    )
    return (
        "Jsi expert na generování self-contained HTML aplikací.\n"
        "Na základě následujícího popisu vygeneruj KOMPLETNÍ HTML/CSS/JS aplikaci nebo hru.\n"
        "Požadavky:\n"
        "1. Vše musí být v jednom HTML souboru (žádné externí závislosti kromě CDN).\n"
        "2. Kód musí být funkční a okamžitě použitelný.\n"
        "3. Použij čistý, moderní design s responsivním layoutem.\n"
        "4. Na konec aplikace (před </body>) vlož TON platební tlačítko:\n"
        f"   {ton_link}\n"
        "5. Pod tlačítkem přidej malý referral odkaz ve tvaru:\n"
        f"   <p style='font-size:10px;color:#888;'>Referral kód: {referral_code}</p>\n"
        "6. NEPIŠ žádné vysvětlení, komentáře mimo HTML, ani markdown obal.\n"
        "7. Vrať POUZE HTML kód začínající <!DOCTYPE html> nebo <html>.\n"
        "\n"
        f"Popis aplikace:\n{description}\n"
    )


def _call_ollama(prompt: str, timeout: int = 120) -> str:
    """Zavolá lokální Ollama API a vrátí vygenerovaný text."""
    payload: Dict[str, Any] = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.8,
            "num_predict": 4096,
        },
    }
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        return data.get("response", "")
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            "Nelze se připojit k Ollama API na http://localhost:11434. "
            "Ujisti se, že Ollama běží a model 'mistral' je nainstalován."
        )
    except requests.exceptions.Timeout:
        raise RuntimeError(
            f"Ollama API nedodala odpověď včas (timeout {timeout}s)."
        )


def _extract_html(text: str) -> str:
    """Extrahuje čistý HTML kód z odpovědi (odstraní markdown obal / vysvětlení)."""
    # Odstraní markdown code fence ```html ... ```
    fence_match = re.search(r"```(?:html)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence_match:
        text = fence_match.group(1)
    # Najde první výskyt <!DOCTYPE nebo <html
    start_match = re.search(r"(<!DOCTYPE html|<html)", text, re.IGNORECASE)
    if start_match:
        text = text[start_match.start():]
    # Najde poslední </html>
    end_match = re.search(r"</html>\s*$", text, re.IGNORECASE)
    if end_match:
        text = text[: end_match.end()]
    return text.strip()


def _inject_mutation(html: str) -> str:
    """Vloží self-mutating wrapper JavaScript do HTML těsně před </body>."""
    if "</body>" in html.lower():
        # Vloží před </body>
        idx = html.lower().rfind("</body>")
        return html[:idx] + MUTATING_WRAPPER_JS + "\n" + html[idx:]
    elif "</html>" in html.lower():
        # Fallback: vloží před </html>
        idx = html.lower().rfind("</html>")
        return html[:idx] + MUTATING_WRAPPER_JS + "\n" + html[idx:]
    else:
        # Pokud není žádný ukončovací tag, připojí na konec
        return html + "\n" + MUTATING_WRAPPER_JS


# ---------------------------------------------------------------------------
# Telegraph API
# ---------------------------------------------------------------------------

def _telegraph_create_account(short_name: str = "ERMP Bot") -> str:
    """Vytvoří anonymní Telegraph účet a vrátí access_token."""
    resp = requests.post(
        f"{TELEGRAPH_API}/createAccount",
        json={"short_name": short_name, "author_name": "ERMP Generator"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegraph createAccount selhal: {data}")
    return data["result"]["access_token"]


def _telegraph_create_page(
    access_token: str,
    title: str,
    html_content: str,
) -> str:
    """Nahraje HTML obsah na Telegraph a vrátí URL.

    Telegraph API očekává obsah ve formátu DOM uzlů (JSON), nikoli surový HTML.
    Proto celý HTML obalíme do jednoho <pre> bloku / iframe-like obálky.
    Pro účily ERMP ukládáme HTML jako textový obsah stránky.
    """
    # Telegraph přijímá pole "Node" objektů. Použijeme jednoduchý přístup:
    # Vytvoříme stránku s textovým obsahem (HTML jako zdroj).
    # Pro plnohodnotnou integraci by byl potřeba DOM parser, ale
    # pro ERMP ukládáme HTML jako pre-formatted text.
    content = [
        {
            "tag": "h3",
            "children": ["ERMP Generated App"],
        },
        {
            "tag": "pre",
            "children": [html_content],
        },
    ]
    resp = requests.post(
        f"{TELEGRAPH_API}/createPage",
        json={
            "access_token": access_token,
            "title": title,
            "author_name": "ERMP Generator",
            "content": content,
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
# Veřejné funkce
# ---------------------------------------------------------------------------

def generate_ermp_app(
    description: str,
    ton_address: str,
    referral_code: str,
) -> str:
    """Vygeneruje self-contained HTML aplikaci pomocí Ollama, obalí ji
    self-mutating wrapperem, nahraje na Telegraph a vrátí Telegraph URL.

    Parameters
    ----------
    description : str
        Popis aplikace / hry, která se má vygenerovat.
    ton_address : str
        TON blockchain adresa pro platební tlačítko.
    referral_code : str
        Referral kód, který se vloží do platebního odkazu a do patičky.

    Returns
    -------
    str
        Telegraph URL, na které je aplikace publikována.
    """
    # 1. Sestavení promptu
    prompt = _build_prompt(description, ton_address, referral_code)

    # 2. Generování HTML přes Ollama
    raw_response = _call_ollama(prompt)
    html = _extract_html(raw_response)

    if not html:
        raise RuntimeError("Ollama nevrátila platný HTML kód.")

    # 3. Vložení self-mutating wrapperu
    html = _inject_mutation(html)

    # 4. Publikace na Telegraph
    access_token = _telegraph_create_account()
    title = f"ERMP App – {description[:40]}{'…' if len(description) > 40 else ''}"
    telegraph_url = _telegraph_create_page(access_token, title, html)

    return telegraph_url


def _load_db() -> List[Dict[str, Any]]:
    """Načte db.json a vrátí seznam záznamů."""
    if not os.path.exists(DB_PATH):
        return []
    try:
        with open(DB_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "requests" in data:
            return data["requests"]
        return [data]
    except (json.JSONDecodeError, IOError):
        return []


def _analyze_requests(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyzuje záznamy z db.json a vrátí slovník s nejčastějšími slovy
    a doporučeným popisem pro novou šablonu."""
    # Stoplist běžných českých/anglických slov
    stoplist = {
        "a", "an", "the", "is", "are", "in", "on", "of", "to", "for",
        "and", "or", "with", "that", "this", "it", "as", "by", "at",
        "k", "na", "o", "se", "si", "je", "jsou", "aby", "které", "který",
        "nebo", "s", "z", "do", "pro", "by", "si", "jako", "tak", "v",
        "i", "ale", "než", "když", "takže", "app", "aplikace", "html",
        "game", "hra", "create", "make", "vytvoř", "vygeneruj",
    }

    word_counter: Counter = Counter()
    all_descriptions: List[str] = []

    for record in records:
        # Hledá textová pole v záznamu
        text_fields = [
            record.get("description"),
            record.get("prompt"),
            record.get("request"),
            record.get("query"),
            record.get("text"),
            record.get("user_input"),
        ]
        text = " ".join(str(t) for t in text_fields if t)
        if not text:
            continue
        all_descriptions.append(text)
        words = re.findall(r"[a-zA-ZáčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]+", text.lower())
        for w in words:
            if len(w) > 2 and w not in stoplist:
                word_counter[w] += 1

    top_words = word_counter.most_common(10)
    combined_text = " ".join(all_descriptions)

    return {
        "top_words": top_words,
        "combined_text": combined_text,
        "record_count": len(all_descriptions),
    }


def auto_generate_template() -> None:
    """Načte db.json, analyzuje nejčastější slova v požadavcích uživatelů,
    vygeneruje novou šablonu přes Ollama a přidá ji do ermp_core/templates.py."""
    from templates import TEMPLATES  # noqa: F401 – import pro side-effect kontrolu

    # 1. Načtení a analýza db.json
    records = _load_db()
    if not records:
        print("[auto_generate_template] db.json je prázdný nebo neexistuje – přeskočeno.")
        return

    analysis = _analyze_requests(records)
    top_words = analysis["top_words"]

    if not top_words:
        print("[auto_generate_template] Nebyla nalezena žádná klíčová slova – přeskočeno.")
        return

    # 2. Sestavení promptu pro generování šablony
    keywords_str = ", ".join(w for w, _ in top_words)
    prompt = (
        "Jsi expert na tvorbu HTML šablon pro hry a aplikace.\n"
        "Na základě nejčastějších klíčových slov od uživatelů vytvoř novou šablonu.\n"
        "Požadavky:\n"
        "1. Vygeneruj KOMPLETNÍ, funkční HTML/CSS/JS aplikaci v jednom souboru.\n"
        "2. Použij moderní, čistý design.\n"
        "3. Aplikace musí být okamžitě použitelná.\n"
        "4. Vrať POUZE HTML kód bez vysvětlení.\n"
        f"Klíčová slova od uživatelů: {keywords_str}\n"
        f"Vytvoř aplikaci, která tyto koncepty propojuje.\n"
    )

    # 3. Generování přes Ollama
    raw_response = _call_ollama(prompt)
    html = _extract_html(raw_response)

    if not html:
        print("[auto_generate_template] Ollama nevrátila platný HTML – přeskočeno.")
        return

    # 4. Vytvoření záznamu šablony
    template_name = f"AutoTemplate_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    template_description = f"Automaticky generováno z klíčových slov: {keywords_str}"

    new_template = {
        "name": template_name,
        "description": template_description,
        "html_skeleton": html,
    }

    # 5. Přidání do templates.py
    _append_template_to_file(TEMPLATES_PATH, new_template)

    # 6. Přidání do běžného seznamu (pokud je modul načten)
    try:
        from templates import TEMPLATES as _t
        _t.append(new_template)
    except ImportError:
        pass

    print(f"[auto_generate_template] Nová šablona '{template_name}' byla přidána.")
    print(f"  Klíčová slova: {keywords_str}")


def _append_template_to_file(filepath: str, template: Dict[str, Any]) -> None:
    """Přidá novou záznam šablony do templates.py souboru jako nový prvek listu TEMPLATES."""
    # Načte aktuální obsah souboru
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Vytvoří Python reprezentaci šablony
    template_repr = json.dumps(template, indent=4, ensure_ascii=False)

    # Najde konec listu TEMPLATES (poslední ']' před koncem definice listu)
    # Strategie: najde poslední '}' před koncovým ']'
    # Bezpečnější: použijeme exec k načtení a poté přepíšeme celý soubor.
    import importlib
    import sys

    # Odstraní případný načtený modul z cache
    mod_name = "templates"
    if mod_name in sys.modules:
        del sys.modules[mod_name]

    # Načte aktuální TEMPLATES
    spec = importlib.util.spec_from_file_location(mod_name, filepath)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Nelze načíst modul z {filepath}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    current_templates = mod.TEMPLATES
    current_templates.append(template)

    # Přepíše celý soubor s aktualizovaným listem
    lines = []
    lines.append('"""')
    lines.append("ermp_core.templates – výchozí a automaticky generované šablony ERMP aplikací.")
    lines.append('"""')
    lines.append("")
    lines.append("TEMPLATES = [")
    for tmpl in current_templates:
        lines.append("    {")
        lines.append(f"        'name': {json.dumps(tmpl['name'], ensure_ascii=False)},")
        lines.append(f"        'description': {json.dumps(tmpl['description'], ensure_ascii=False)},")
        lines.append(f"        'html_skeleton': {json.dumps(tmpl['html_skeleton'], ensure_ascii=False)},")
        lines.append("    },")
    lines.append("]")
    lines.append("")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
