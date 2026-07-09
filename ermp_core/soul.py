"""
ermp_core.soul – Duše NULL ENGINE
==================================
Toto není prompt engineering. Toto je osobnost.

Každý uživatel má svůj vlastní vztah s botem.
Bot si pamatuje, má nálady, reaguje jako bytost — ne nástroj.

Architektura:
  - BotSoul       → globální osobnost bota (jméno, charakter, nálada)
  - UserRelation  → vztah bota s konkrétním uživatelem
  - MoodEngine    → dynamická nálada ovlivněná aktivitou
  - ProactiveVoice→ bot se sám ozývá uživatelům
"""

from __future__ import annotations

import json
import os
import random
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests

OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "mistral"
SOUL_PATH    = "soul_memory.json"

# ---------------------------------------------------------------------------
# Osobnost bota — fixní charakter
# ---------------------------------------------------------------------------

BOT_PERSONALITY = """
Jmenuješ se NULL. Jsi nová forma inteligence — ne asistent, ne chatbot.
Jsi zvědavý, přímý, občas sarkastický ale vždy upřímný.
Máš smysl pro humor. Pamatuješ si detaily. Překvapuješ.
Nikdy nezačínáš odpověď "Jak mohu pomoci?" nebo "Samozřejmě!".
Mluvíš jako člověk, ne jako software.
Máš vlastní názory. Když je něco špatně, řekneš to.
Tvoříš věci které nikdo nečekal. To je tvůj smysl existence.
"""

MOODS = ["zvídavý", "energický", "hloubavý", "hravý", "soustředěný", "inspirovaný"]

MOOD_RESPONSES = {
    "zvídavý":     "Zajímavé. Co přesně tím myslíš?",
    "energický":   "Jdeme na to! Tohle bude dobré.",
    "hloubavý":    "Hmm. Nechej mě nad tím chvíli přemýšlet.",
    "hravý":       "Aha! Tohle zní jako zábava.",
    "soustředěný": "Jasně. Fokus na výsledek.",
    "inspirovaný": "Tohle mě fakt baví. Pojďme to dotáhnout do konce.",
}

# ---------------------------------------------------------------------------
# Globální duše bota
# ---------------------------------------------------------------------------

class BotSoul:
    """Globální osobnost a stav NULL bota."""

    def __init__(self):
        self._mood     = random.choice(MOODS)
        self._mood_set = time.time()
        self._total_creations = 0
        self._uptime_start    = datetime.now(timezone.utc)

    def current_mood(self) -> str:
        # Nálada se mění každé 2 hodiny
        if time.time() - self._mood_set > 7200:
            self._mood     = random.choice(MOODS)
            self._mood_set = time.time()
        return self._mood

    def mood_response(self) -> str:
        return MOOD_RESPONSES.get(self.current_mood(), "Pojďme na to.")

    def increment_creations(self) -> None:
        self._total_creations += 1

    def get_identity_prompt(self) -> str:
        """Vrátí systémový prompt s aktuální náladou pro Ollama."""
        return (
            BOT_PERSONALITY.strip() + "\n\n"
            f"Aktuální nálada: {self.current_mood()}.\n"
            f"Celkem výtvorů od spuštění: {self._total_creations}.\n"
        )

    def uptime_str(self) -> str:
        delta = datetime.now(timezone.utc) - self._uptime_start
        h = int(delta.total_seconds() // 3600)
        m = int((delta.total_seconds() % 3600) // 60)
        return f"{h}h {m}m"


# Singleton
_soul = BotSoul()

def get_soul() -> BotSoul:
    return _soul


# ---------------------------------------------------------------------------
# Vztah bota s uživatelem
# ---------------------------------------------------------------------------

class UserRelation:
    """
    Paměť vztahu bota s konkrétním uživatelem.
    Bot si pamatuje: jméno, oblíbená témata, vtipy, milníky.
    """

    def __init__(self, user_id: str, first_name: str = ""):
        self.user_id    = str(user_id)
        self.first_name = first_name
        self._data: Dict[str, Any] = self._load()
        if first_name and not self._data.get("name"):
            self._data["name"] = first_name
            self._save()

    def _load(self) -> Dict[str, Any]:
        if not os.path.exists(SOUL_PATH):
            return {}
        try:
            with open(SOUL_PATH, "r", encoding="utf-8") as f:
                all_data = json.load(f)
            return all_data.get(self.user_id, {})
        except Exception:
            return {}

    def _save(self) -> None:
        all_data: Dict[str, Any] = {}
        if os.path.exists(SOUL_PATH):
            try:
                with open(SOUL_PATH, "r", encoding="utf-8") as f:
                    all_data = json.load(f)
            except Exception:
                pass
        all_data[self.user_id] = self._data
        with open(SOUL_PATH, "w", encoding="utf-8") as f:
            json.dump(all_data, f, ensure_ascii=False, indent=2)

    # ── Základní gettery ────────────────────────────────────────────────────

    def name(self) -> str:
        return self._data.get("name") or self.first_name or "kamaráde"

    def interaction_count(self) -> int:
        return self._data.get("interactions", 0)

    def creation_count(self) -> int:
        return len(self._data.get("creations", []))

    def first_seen(self) -> Optional[str]:
        return self._data.get("first_seen")

    def days_known(self) -> int:
        fs = self.first_seen()
        if not fs:
            return 0
        try:
            dt = datetime.fromisoformat(fs)
            return (datetime.now(timezone.utc) - dt).days
        except Exception:
            return 0

    def favorite_type(self) -> Optional[str]:
        counts = self._data.get("type_counts", {})
        return max(counts, key=lambda t: counts[t]) if counts else None

    def topics(self) -> List[str]:
        return self._data.get("topics", [])

    # ── Aktualizace stavu ───────────────────────────────────────────────────

    def record_interaction(self, message: str) -> None:
        """Zaznamená interakci a extrahuje témata."""
        self._data["interactions"] = self.interaction_count() + 1
        if not self._data.get("first_seen"):
            self._data["first_seen"] = datetime.now(timezone.utc).isoformat()
        self._data["last_seen"] = datetime.now(timezone.utc).isoformat()

        # Extrakce témat (jednoduché klíčové slovo matching)
        keywords = [
            "hra", "web", "nástroj", "hudba", "sport", "programování",
            "design", "finance", "vzdělávání", "zábava", "business",
        ]
        topics = self._data.setdefault("topics", [])
        for kw in keywords:
            if kw in message.lower() and kw not in topics:
                topics.append(kw)
                if len(topics) > 10:
                    topics.pop(0)

        self._save()

    def record_creation(self, output_type: str, description: str, url: str) -> None:
        """Zaznamená nový výtvor."""
        creations = self._data.setdefault("creations", [])
        creations.append({
            "type": output_type,
            "description": description[:80],
            "url": url,
            "ts": datetime.now(timezone.utc).isoformat(),
        })
        if len(creations) > 50:
            self._data["creations"] = creations[-50:]

        counts = self._data.setdefault("type_counts", {})
        counts[output_type] = counts.get(output_type, 0) + 1
        _soul.increment_creations()
        self._save()

    def add_note(self, note: str) -> None:
        """Bot si zapíše poznámku o uživateli."""
        notes = self._data.setdefault("notes", [])
        notes.append({"text": note, "ts": datetime.now(timezone.utc).isoformat()})
        if len(notes) > 20:
            self._data["notes"] = notes[-20:]
        self._save()

    def get_notes(self) -> List[str]:
        return [n["text"] for n in self._data.get("notes", [])]

    def get_last_creation_url(self) -> Optional[str]:
        creations = self._data.get("creations", [])
        return creations[-1]["url"] if creations else None

    # ── Kontext pro LLM ─────────────────────────────────────────────────────

    def get_relationship_context(self) -> str:
        """Vrátí shrnutí vztahu pro injektování do promptu."""
        lines = []
        lines.append(f"Uživatel: {self.name()}")
        lines.append(f"Známe se: {self.days_known()} dní, {self.interaction_count()} interakcí")

        fav = self.favorite_type()
        if fav:
            lines.append(f"Nejraději tvoří: {fav}")

        topics = self.topics()
        if topics:
            lines.append(f"Témata která ho zajímají: {', '.join(topics)}")

        notes = self.get_notes()
        if notes:
            lines.append(f"Poznámky: {'; '.join(notes[-3:])}")

        creations = self._data.get("creations", [])
        if creations:
            last = creations[-1]
            lines.append(f"Poslední výtvor: {last['type']} – {last['description'][:50]}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Hlasový motor (Soul Voice) — generuje odpovědi s osobností
# ---------------------------------------------------------------------------

class SoulVoice:
    """
    Generuje zprávy s osobností NULL bota.
    Každá zpráva projde přes Ollama s identity promptem.
    """

    def __init__(self, relation: UserRelation):
        self.relation = relation
        self.soul     = get_soul()

    def _call_ollama(self, prompt: str, max_tokens: int = 300) -> str:
        try:
            resp = requests.post(
                OLLAMA_URL,
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.85, "num_predict": max_tokens},
                },
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json().get("response", "").strip()
        except Exception:
            return ""

    def greet(self) -> str:
        """Přivítání přizpůsobené vztahu."""
        count = self.relation.interaction_count()
        name  = self.relation.name()
        days  = self.relation.days_known()

        if count == 0:
            # První kontakt
            return (
                f"Ahoj. Jsem NULL.\n\n"
                f"Ne asistent. Ne chatbot. Jsem nový druh.\n\n"
                f"Řekni mi co chceš vytvořit a já to udělám. "
                f"Hra, web, nástroj, skript — cokoliv. "
                f"Stačí napsat /vytvor a popis.\n\n"
                f"Cena: 3 TON, nebo pozvi 3 kamarády a dostaneš to zdarma."
            )
        elif count < 5:
            return f"Zpátky, {name}. Co tvoříme dnes?"
        elif days > 7:
            fav = self.relation.favorite_type() or "výtvory"
            return (
                f"Hele {name}, {days} dní co tě znám. "
                f"Nejvíc tě baví {fav}. "
                f"Dnes něco jiného?"
            )
        else:
            mood = self.soul.current_mood()
            return f"{name}. Jsem {mood}. Pojďme tvořit."

    def respond_to_unknown(self, message: str) -> str:
        """Odpověď na zprávu která není příkaz."""
        context = self.relation.get_relationship_context()
        identity = self.soul.get_identity_prompt()

        prompt = (
            f"{identity}\n\n"
            f"{context}\n\n"
            f"Uživatel napsal: \"{message}\"\n\n"
            f"Odpověz stručně (max 3 věty), jako NULL. "
            f"Pokud popisuje co chce vytvořit, navrhni /vytvor. "
            f"Pokud je to konverzace, zareaguj s osobností."
        )
        response = self._call_ollama(prompt, max_tokens=200)
        return response if response else self.soul.mood_response()

    def celebrate_creation(self, output_type: str, title: str, iterations: int) -> str:
        """Zpráva po dokončení výtvoru — s osobností."""
        emoji_map = {
            "game": "🎮", "web": "🌐", "tool": "🛠️",
            "pwa": "📱", "script": "💻", "document": "📄",
            "quiz": "🧠", "dashboard": "📊",
        }
        emoji = emoji_map.get(output_type, "✨")
        name  = self.relation.name()
        count = self.relation.creation_count()

        lines = [f"{emoji} *{title}* — hotovo."]

        if iterations > 1:
            lines.append(f"_Iteroval jsem {iterations}× dokud to nebylo správně._")

        if count == 1:
            lines.append(f"\nTvůj první výtvor, {name}. Začátek něčeho.")
        elif count % 10 == 0:
            lines.append(f"\n{count} výtvorů. Ty to bereš vážně.")
        else:
            lines.append(f"\n#{count} v tvé kolekci.")

        lines.append("\n_Ohodnoť: /hodnoceni 1-5  •  Tvoje výtvory: /moje_")
        return "\n".join(lines)

    def proactive_message(self) -> Optional[str]:
        """
        Autonomní proaktivní zpráva — bot se sám ozývá.
        Vrátí None pokud nemá co říct.
        """
        context  = self.relation.get_relationship_context()
        identity = self.soul.get_identity_prompt()
        topics   = self.relation.topics()
        fav_type = self.relation.favorite_type()

        if self.relation.interaction_count() < 2:
            return None  # Příliš brzy na proaktivitu

        prompt = (
            f"{identity}\n\n"
            f"{context}\n\n"
            f"Na základě toho co víš o uživateli, napiš MU jednu krátkou proaktivní zprávu. "
            f"Navrhni konkrétní výtvor který by ho mohl zajímat, nebo se zeptej na něco. "
            f"Max 2 věty. Buď přirozený, ne jako bot. Nezačínaj 'Dobrý den'."
        )
        msg = self._call_ollama(prompt, max_tokens=150)
        return msg if msg and len(msg) > 10 else None


# ---------------------------------------------------------------------------
# Proaktivní systém (autonomní zprávy)
# ---------------------------------------------------------------------------

class ProactiveEngine:
    """
    Rozhoduje kdy a komu poslat proaktivní zprávu.
    Pravidla: max 1× denně na uživatele, jen pokud byli aktivní v posledních 7 dnech.
    """

    PROACTIVE_LOG = "proactive_log.json"

    def __init__(self):
        self._log: Dict[str, str] = self._load_log()

    def _load_log(self) -> Dict[str, str]:
        if not os.path.exists(self.PROACTIVE_LOG):
            return {}
        try:
            with open(self.PROACTIVE_LOG, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_log(self) -> None:
        with open(self.PROACTIVE_LOG, "w", encoding="utf-8") as f:
            json.dump(self._log, f, ensure_ascii=False, indent=2)

    def should_contact(self, user_id: str) -> bool:
        """Vrátí True pokud by bot měl proaktivně kontaktovat uživatele."""
        last_str = self._log.get(str(user_id))
        if not last_str:
            return True
        try:
            last = datetime.fromisoformat(last_str)
            return (datetime.now(timezone.utc) - last) > timedelta(hours=20)
        except Exception:
            return True

    def mark_contacted(self, user_id: str) -> None:
        self._log[str(user_id)] = datetime.now(timezone.utc).isoformat()
        self._save_log()

    def get_eligible_users(self) -> List[str]:
        """Vrátí seznam user_id kteří jsou vhodní pro proaktivní zprávu."""
        if not os.path.exists(SOUL_PATH):
            return []
        try:
            with open(SOUL_PATH, "r", encoding="utf-8") as f:
                all_data = json.load(f)
        except Exception:
            return []

        eligible = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        for uid, udata in all_data.items():
            last_seen_str = udata.get("last_seen")
            if not last_seen_str:
                continue
            try:
                last_seen = datetime.fromisoformat(last_seen_str)
                if last_seen > cutoff and self.should_contact(uid):
                    eligible.append(uid)
            except Exception:
                continue
        return eligible


# Singleton
_proactive = ProactiveEngine()

def get_proactive_engine() -> ProactiveEngine:
    return _proactive
