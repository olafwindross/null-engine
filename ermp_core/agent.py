"""
ermp_core.agent – NULL ENGINE Agentní AI jádro (Next-Gen Layer)
================================================================
Toto je nová generace AI v botu. Místo jednoduchého prompt → output
implementuje plnohodnotnou agentní smyčku:

  1. PAMĚŤ          – každý uživatel má vlastní kontext a historii
  2. PLÁNOVÁNÍ      – agent rozkládá složité požadavky na kroky
  3. ITERACE        – generuje, hodnotí, opravuje (až 3 kola)
  4. SELF-LEARNING  – učí se ze zpětné vazby uživatelů
  5. AUTONOMIE      – sám navrhuje nové výtvory bez čekání

Architektura: ReAct (Reason + Act) smyčka nad lokálním Ollama LLM.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

# ---------------------------------------------------------------------------
# Konfigurace
# ---------------------------------------------------------------------------
OLLAMA_URL    = "http://localhost:11434/api/generate"
OLLAMA_MODEL  = "mistral"
MEMORY_PATH   = "agent_memory.json"
FEEDBACK_PATH = "agent_feedback.json"
MAX_ITERATIONS = 3          # max počet iterací agenta na jeden požadavek
MEMORY_LIMIT   = 20         # max uložených výtvorů na uživatele

# ---------------------------------------------------------------------------
# Paměť uživatele
# ---------------------------------------------------------------------------

class UserMemory:
    """
    Perzistentní paměť konkrétního uživatele.
    Ukládá: historii výtvorů, preference, zpětnou vazbu, kontext.
    """

    def __init__(self, user_id: str):
        self.user_id = str(user_id)
        self._data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        if not os.path.exists(MEMORY_PATH):
            return {}
        try:
            with open(MEMORY_PATH, "r", encoding="utf-8") as f:
                all_mem = json.load(f)
            return all_mem.get(self.user_id, {})
        except Exception:
            return {}

    def _save(self) -> None:
        all_mem: Dict[str, Any] = {}
        if os.path.exists(MEMORY_PATH):
            try:
                with open(MEMORY_PATH, "r", encoding="utf-8") as f:
                    all_mem = json.load(f)
            except Exception:
                pass
        all_mem[self.user_id] = self._data
        with open(MEMORY_PATH, "w", encoding="utf-8") as f:
            json.dump(all_mem, f, ensure_ascii=False, indent=2)

    def add_creation(self, description: str, output_type: str, url: str) -> None:
        """Zaznamená nový výtvor do paměti."""
        creations = self._data.setdefault("creations", [])
        creations.append({
            "description": description,
            "type": output_type,
            "url": url,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "feedback_score": None,
        })
        # Limit paměti
        if len(creations) > MEMORY_LIMIT:
            self._data["creations"] = creations[-MEMORY_LIMIT:]
        self._save()

    def add_feedback(self, url: str, score: int, comment: str = "") -> None:
        """Uloží zpětnou vazbu (1-5) k výtvoru."""
        for c in self._data.get("creations", []):
            if c.get("url") == url:
                c["feedback_score"] = score
                c["feedback_comment"] = comment
                break
        feedback = self._data.setdefault("feedback_history", [])
        feedback.append({
            "score": score,
            "comment": comment,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self._save()

    def get_context_summary(self) -> str:
        """Vrátí stručné shrnutí kontextu uživatele pro prompt."""
        creations = self._data.get("creations", [])
        if not creations:
            return "Uživatel je nový, bez předchozích výtvorů."

        recent = creations[-5:]
        lines = ["Předchozí výtvory uživatele:"]
        for c in recent:
            score_str = f" (hodnocení: {c['feedback_score']}/5)" if c.get("feedback_score") else ""
            lines.append(f"  – {c['type']}: {c['description'][:60]}{score_str}")

        # Preferovaný typ
        type_counts: Dict[str, int] = {}
        for c in creations:
            type_counts[c["type"]] = type_counts.get(c["type"], 0) + 1
        fav = max(type_counts, key=lambda t: type_counts[t]) if type_counts else None
        if fav:
            lines.append(f"Oblíbený typ výtvorů: {fav}")

        return "\n".join(lines)

    def get_recent_urls(self) -> List[str]:
        """Vrátí seznam URL posledních výtvorů."""
        return [c["url"] for c in self._data.get("creations", [])[-5:]]

    def get_preferences(self) -> Dict[str, Any]:
        return self._data.get("preferences", {})

    def set_preference(self, key: str, value: Any) -> None:
        self._data.setdefault("preferences", {})[key] = value
        self._save()


# ---------------------------------------------------------------------------
# Self-learning engine
# ---------------------------------------------------------------------------

class SelfLearningEngine:
    """
    Analyzuje zpětnou vazbu napříč všemi uživateli a extrahuje
    co funguje a co ne. Výsledky se injektují do promptů.
    """

    def __init__(self):
        self._insights: Dict[str, Any] = self._load_insights()

    def _load_insights(self) -> Dict[str, Any]:
        if not os.path.exists(FEEDBACK_PATH):
            return {"good_patterns": [], "bad_patterns": [], "last_updated": None}
        try:
            with open(FEEDBACK_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"good_patterns": [], "bad_patterns": [], "last_updated": None}

    def _save_insights(self) -> None:
        with open(FEEDBACK_PATH, "w", encoding="utf-8") as f:
            json.dump(self._insights, f, ensure_ascii=False, indent=2)

    def analyze_and_update(self) -> None:
        """
        Přečte všechny feedbacky z paměti uživatelů a pomocí Ollama
        extrahuje vzory co se líbí / nelíbí.
        """
        if not os.path.exists(MEMORY_PATH):
            return

        with open(MEMORY_PATH, "r", encoding="utf-8") as f:
            all_mem = json.load(f)

        good, bad = [], []
        for user_data in all_mem.values():
            for c in user_data.get("creations", []):
                score = c.get("feedback_score")
                desc  = c.get("description", "")
                if score is None:
                    continue
                if score >= 4:
                    good.append(desc)
                elif score <= 2:
                    bad.append(desc)

        if not good and not bad:
            return

        # Ollama analýza vzorů
        prompt = (
            "Jsi AI analytik. Analyzuj tyto popisy aplikací a extrahuj vzory.\n\n"
            f"OBLÍBENÉ (hodnocení 4-5/5):\n" + "\n".join(f"– {d}" for d in good[-10:]) + "\n\n"
            f"NEOBLÍBENÉ (hodnocení 1-2/5):\n" + "\n".join(f"– {d}" for d in bad[-10:]) + "\n\n"
            "Extrahuj max 3 konkrétní vzory co dělá aplikaci oblíbenou a max 3 co ji kazí.\n"
            "Odpověz ve formátu JSON: {\"good\": [\"vzor1\", ...], \"bad\": [\"vzor1\", ...]}"
        )

        try:
            resp = requests.post(
                OLLAMA_URL,
                json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False,
                      "options": {"temperature": 0.3, "num_predict": 512}},
                timeout=60,
            )
            raw = resp.json().get("response", "{}")
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                data = json.loads(match.group())
                self._insights["good_patterns"] = data.get("good", [])
                self._insights["bad_patterns"]  = data.get("bad", [])
                self._insights["last_updated"]   = datetime.now(timezone.utc).isoformat()
                self._save_insights()
        except Exception:
            pass

    def get_prompt_injection(self) -> str:
        """Vrátí text pro injektování do promptu na základě naučených vzorů."""
        good = self._insights.get("good_patterns", [])
        bad  = self._insights.get("bad_patterns", [])
        if not good and not bad:
            return ""
        lines = ["Na základě zpětné vazby uživatelů:"]
        if good:
            lines.append("Co uživatelé milují: " + "; ".join(good))
        if bad:
            lines.append("Čemu se vyhni: " + "; ".join(bad))
        return "\n".join(lines)


# Globální instance self-learning enginu
_learning_engine = SelfLearningEngine()


# ---------------------------------------------------------------------------
# Agentní smyčka (ReAct)
# ---------------------------------------------------------------------------

class NullAgent:
    """
    Agentní AI jádro. Pro každý požadavek:
      1. Analyzuje záměr uživatele
      2. Plánuje kroky
      3. Generuje výsledek
      4. Hodnotí kvalitu (self-critique)
      5. Iteruje pokud kvalita nestačí
    """

    def __init__(self, user_id: str, ton_address: str = "", referral_code: str = "NULL"):
        self.user_id      = str(user_id)
        self.ton_address  = ton_address
        self.referral_code = referral_code
        self.memory       = UserMemory(user_id)
        self.learning     = _learning_engine

    def _call_ollama(self, prompt: str, max_tokens: int = 6000, temp: float = 0.75) -> str:
        """Zavolá Ollama a vrátí odpověď."""
        try:
            resp = requests.post(
                OLLAMA_URL,
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": temp, "num_predict": max_tokens},
                },
                timeout=180,
            )
            resp.raise_for_status()
            return resp.json().get("response", "")
        except requests.exceptions.ConnectionError:
            raise RuntimeError("Ollama není dostupná. Spusť: ollama serve")
        except requests.exceptions.Timeout:
            raise RuntimeError("Ollama nestihla odpovědět. Zkus kratší popis.")

    def _analyze_intent(self, description: str) -> Dict[str, Any]:
        """
        Krok 1: Analýza záměru.
        Zjistí co uživatel chce, jaký typ, jaké funkce musí mít.
        """
        context = self.memory.get_context_summary()
        prompt = (
            "Jsi AI asistent analyzující požadavek uživatele.\n\n"
            f"{context}\n\n"
            f"Nový požadavek: \"{description}\"\n\n"
            "Odpověz POUZE v JSON formátu:\n"
            "{\n"
            '  "type": "game|web|tool|pwa|script|document|quiz|dashboard",\n'
            '  "title": "krátký název výtvoru",\n'
            '  "must_have": ["funkce 1", "funkce 2", "funkce 3"],\n'
            '  "style": "minimalistický|barevný|tmavý|světlý|neonový",\n'
            '  "language": "cs|en",\n'
            '  "complexity": "simple|medium|complex"\n'
            "}"
        )
        raw = self._call_ollama(prompt, max_tokens=512, temp=0.3)
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        # Fallback
        return {
            "type": "tool", "title": description[:40],
            "must_have": [], "style": "moderní",
            "language": "cs", "complexity": "medium",
        }

    def _build_generation_prompt(
        self, description: str, intent: Dict[str, Any], iteration: int
    ) -> str:
        """Sestaví specializovaný generační prompt s kontextem a naučenými vzory."""
        ton_btn = (
            f'<div style="text-align:center;margin:24px 0;">'
            f'<a href="ton://transfer/{self.ton_address}?amount=3000000000&text={self.referral_code}" '
            f'style="background:#0088cc;color:#fff;padding:14px 28px;border-radius:10px;'
            f'text-decoration:none;font-weight:bold;font-size:16px;display:inline-block;">'
            f'⚡ Podpořit tvůrce (3 TON)</a>'
            f'<p style="font-size:11px;color:#aaa;margin-top:8px;">ref: {self.referral_code}</p>'
            f'</div>'
        )

        must_have_str = "\n".join(f"   ✓ {f}" for f in intent.get("must_have", []))
        learning_hint = self.learning.get_prompt_injection()

        iteration_note = ""
        if iteration > 1:
            iteration_note = (
                f"\n⚠️ ITERACE {iteration}: Předchozí verze nebyla dost kvalitní. "
                "Tentokrát vytvoř výrazně lepší verzi s propracovanějším designem a více funkcemi.\n"
            )

        return (
            f"Jsi světová třída vývojář. Vytvoř DOKONALOU self-contained HTML aplikaci.\n"
            f"{iteration_note}"
            f"\nPOŽADAVEK: {description}\n"
            f"TYP: {intent.get('type', 'tool')}\n"
            f"NÁZEV: {intent.get('title', 'Aplikace')}\n"
            f"STYL: {intent.get('style', 'moderní')}\n"
            f"JAZYK UI: {'Čeština' if intent.get('language') == 'cs' else 'Angličtina'}\n"
            f"\nPOVINNÉ FUNKCE:\n{must_have_str}\n"
            f"\n{learning_hint}\n"
            "\nTECHNICKÉ POŽADAVKY:\n"
            "1. Vše v jednom HTML souboru. Žádné externí soubory (CDN je OK).\n"
            "2. Responsivní design – musí fungovat na mobilu i PC.\n"
            "3. Moderní UI – animace, přechody, krásná typografie.\n"
            "4. Okamžitě funkční po otevření v prohlížeči.\n"
            f"5. Těsně před </body> vlož PŘESNĚ tento HTML:\n{ton_btn}\n"
            "6. Vrať POUZE HTML bez vysvětlení. Začni <!DOCTYPE html>.\n"
        )

    def _self_critique(self, html: str, intent: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Krok 3: Self-critique – agent ohodnotí svůj vlastní výstup.
        Vrátí (is_good_enough, reason).
        """
        must_have = intent.get("must_have", [])
        output_type = intent.get("type", "tool")

        # Základní kontroly
        if len(html) < 500:
            return False, "HTML je příliš krátké – pravděpodobně nekompletní."
        if "<!DOCTYPE" not in html and "<html" not in html:
            return False, "Chybí DOCTYPE nebo <html> tag."
        if "</body>" not in html.lower() and "</html>" not in html.lower():
            return False, "HTML není ukončeno."

        # Kontrola must-have funkcí
        missing = []
        for feature in must_have:
            # Hledáme klíčová slova z featury v HTML
            words = [w.lower() for w in feature.split() if len(w) > 3]
            found = any(w in html.lower() for w in words)
            if not found:
                missing.append(feature)

        if missing and len(missing) > len(must_have) // 2:
            return False, f"Chybí funkce: {', '.join(missing[:3])}"

        # Typ-specifické kontroly
        if output_type == "game":
            if not any(kw in html.lower() for kw in ["canvas", "gameloop", "score", "skóre", "game over"]):
                return False, "Hra nemá herní smyčku nebo skóre."
        elif output_type == "dashboard":
            if "chart" not in html.lower() and "canvas" not in html.lower():
                return False, "Dashboard nemá grafy."
        elif output_type == "quiz":
            if html.lower().count("question") + html.lower().count("otázk") < 3:
                return False, "Kvíz má málo otázek."

        return True, "OK"

    def _extract_html(self, text: str) -> str:
        """Extrahuje čistý HTML z LLM odpovědi."""
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

    def _publish_to_telegraph(self, html: str, title: str) -> str:
        """Nahraje HTML na Telegraph a vrátí URL."""
        TELEGRAPH_API = "https://api.telegra.ph"

        # Vytvoř účet
        resp = requests.post(
            f"{TELEGRAPH_API}/createAccount",
            json={"short_name": "NullEngine", "author_name": "NULL ENGINE AI"},
            timeout=30,
        )
        token = resp.json()["result"]["access_token"]

        # Vytvoř stránku
        content = [{"tag": "p", "children": [html[:10000]]}]
        resp2 = requests.post(
            f"{TELEGRAPH_API}/createPage",
            json={
                "access_token": token,
                "title": title[:255],
                "content": content,
                "return_content": False,
            },
            timeout=30,
        )
        if not resp2.json().get("ok"):
            raise RuntimeError(f"Telegraph selhal: {resp2.json()}")
        return resp2.json()["result"]["url"]

    # -----------------------------------------------------------------------
    # Hlavní metoda – agentní smyčka
    # -----------------------------------------------------------------------

    def generate(self, description: str) -> Dict[str, Any]:
        """
        Spustí plnou agentní smyčku a vrátí výsledek.

        Returns dict:
          {
            "url": str,           # Telegraph URL
            "type": str,          # typ výstupu
            "title": str,         # název
            "iterations": int,    # kolik kol bylo potřeba
            "intent": dict,       # co agent pochopil
          }
        """
        # ── Krok 1: Analýza záměru ──────────────────────────────────────────
        intent = self._analyze_intent(description)
        output_type = intent.get("type", "tool")
        title       = intent.get("title", description[:50])

        html = ""
        iterations = 0
        last_critique = ""

        # ── Krok 2+3: Generování + self-critique iterace ────────────────────
        for i in range(1, MAX_ITERATIONS + 1):
            iterations = i
            prompt = self._build_generation_prompt(description, intent, i)
            raw    = self._call_ollama(prompt)
            html   = self._extract_html(raw)

            if not html:
                last_critique = "Ollama nevrátila HTML."
                continue

            is_good, critique = self._self_critique(html, intent)
            if is_good:
                break
            last_critique = critique
            # Přidáme kritiku do intent pro příští iteraci
            intent["must_have"] = intent.get("must_have", []) + [f"Oprav: {critique}"]

        if not html:
            raise RuntimeError(
                f"Agent nedokázal vygenerovat výsledek po {MAX_ITERATIONS} pokusech. "
                f"Poslední chyba: {last_critique}"
            )

        # ── Krok 4: Publikace ───────────────────────────────────────────────
        url = self._publish_to_telegraph(html, f"NULL ENGINE – {title}")

        # ── Krok 5: Uložení do paměti ───────────────────────────────────────
        self.memory.add_creation(description, output_type, url)

        return {
            "url":        url,
            "type":       output_type,
            "title":      title,
            "iterations": iterations,
            "intent":     intent,
        }

    def suggest_next(self) -> Optional[str]:
        """
        Autonomní mode: navrhne co by uživatel mohl chtít vytvořit dál,
        na základě jeho historie.
        """
        context = self.memory.get_context_summary()
        if "nový" in context.lower() or "bez předchozích" in context.lower():
            return None

        prompt = (
            f"{context}\n\n"
            "Na základě historie tohoto uživatele navrhni JEDEN konkrétní nový výtvor "
            "který by ho mohl zaujmout. Odpověz jednou větou česky, např.: "
            "'Zkus si nechat vytvořit interaktivní quiz o vesmíru!'"
        )
        try:
            suggestion = self._call_ollama(prompt, max_tokens=100, temp=0.9)
            # Vyber první větu
            first_sentence = suggestion.split(".")[0].strip()
            return first_sentence if len(first_sentence) > 10 else None
        except Exception:
            return None

    def record_feedback(self, url: str, score: int, comment: str = "") -> None:
        """Zaznamená zpětnou vazbu k výtvoru a aktualizuje self-learning engine."""
        self.memory.add_feedback(url, score, comment)
        # Každých 10 feedbacků přepočítáme insights
        feedback_count = len(self.memory._data.get("feedback_history", []))
        if feedback_count % 10 == 0:
            self.learning.analyze_and_update()


# ---------------------------------------------------------------------------
# Veřejné rozhraní (kompatibilní s null_engine.py)
# ---------------------------------------------------------------------------

def create_agent(user_id: str, ton_address: str = "", referral_code: str = "NULL") -> NullAgent:
    """Vytvoří instanci agenta pro daného uživatele."""
    return NullAgent(user_id, ton_address, referral_code)


def get_user_history(user_id: str) -> List[Dict[str, Any]]:
    """Vrátí historii výtvorů uživatele."""
    mem = UserMemory(str(user_id))
    return mem._data.get("creations", [])
