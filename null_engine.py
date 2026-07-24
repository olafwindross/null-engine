#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NULL ENGINE — Telegram bot pro autonomní generování ERMP aplikací.

Funkce:
  * Načítá konfiguraci z config.yaml (telegram_token, ton_address, skrill_deposit_address).
  * Uživatelské stavy ukládá do db.json.
  * /start        – přivítání, vysvětlení, cena (3 TON), referral odkaz.
  * /stav         – zobrazení stavu (platba / pozvánky).
  * /vytvor <pop> – generování aplikace přes ermp_core.mutator.generate_ermp_app().
  * Virální mechanika – referral kódy, po 3 pozvánkách přístup zdarma.
  * Kontrola platby TON přes toncenter.com API.
  * Periodická úloha – každých 60 minut auto_generate_template().

Python 3.10+, python-telegram-bot >= 20 (async).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import aiohttp
import yaml
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("null_engine")

# ---------------------------------------------------------------------------
# Konstanty
# ---------------------------------------------------------------------------
DB_FILE = "db.json"
CONFIG_FILE = "config.yaml"

TON_PRICE_NANOTON = 3_000_000_000          # 3 TON v nanotonech
TON_PRICE_STR = "3 TON"
REFERRAL_THRESHOLD = 3                      # počet pozvánek pro volný přístup
TX_LOOKBACK_SECONDS = 24 * 3600             # 24 h
AUTO_TASK_INTERVAL = 60 * 60                # 60 minut

TON_API_URL = "https://toncenter.com/api/v2/getTransactions"

# ---------------------------------------------------------------------------
# NULL ENGINE AGENT – next-gen AI jádro
# ---------------------------------------------------------------------------
def _import_agent():
    """Lazy import agentního modulu."""
    try:
        from ermp_core import agent as _agent_mod
        return _agent_mod
    except ImportError as e:
        logger.error("ermp_core.agent nelze importovat: %s", e)
        return None

def _import_soul():
    """Lazy import duše bota."""
    try:
        from ermp_core import soul as _soul_mod
        return _soul_mod
    except ImportError as e:
        logger.error("ermp_core.soul nelze importovat: %s", e)
        return None

def _import_group():
    """Lazy import skupinového modu."""
    try:
        from ermp_core import group_mode as _group_mod
        return _group_mod
    except ImportError as e:
        logger.error("ermp_core.group_mode nelze importovat: %s", e)
        return None

def _import_viral():
    """Lazy import virálního embed + auto-update."""
    try:
        from ermp_core import viral_and_update as _viral_mod
        return _viral_mod
    except ImportError as e:
        logger.error("ermp_core.viral_and_update nelze importovat: %s", e)
        return None

# ---------------------------------------------------------------------------
# Načítání konfigurace
# ---------------------------------------------------------------------------

def load_config() -> Dict[str, Any]:
    """Načte konfiguraci z config.yaml. Pokud soubor neexistuje, vytvoří šablonu."""
    if not os.path.exists(CONFIG_FILE):
        template = {
            "telegram_token": "SEM_VLOZ_TELEGRAM_TOKEN",
            "ton_address": "SEM_VLOZ_TON_ADRESU",
            "skrill_deposit_address": "sem_vloz_skrill_email@example.com",
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as fh:
            yaml.safe_dump(template, fh, allow_unicode=True)
        logger.warning(
            "config.yaml neexistoval – vytvořena šablona. "
            "Vyplň ji a spusť bota znovu."
        )
        raise SystemExit(1)

    with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}

    required = ("telegram_token", "ton_address", "skrill_deposit_address")
    missing = [k for k in required if not cfg.get(k)]
    if missing:
        logger.error("V config.yaml chybí klíče: %s", ", ".join(missing))
        raise SystemExit(1)

    return cfg


CONFIG = load_config()
TELEGRAM_TOKEN: str = CONFIG["telegram_token"]
TON_ADDRESS: str = CONFIG["ton_address"]
SKRILL_DEPOSIT_ADDRESS: str = CONFIG["skrill_deposit_address"]

# ---------------------------------------------------------------------------
# Databáze (db.json)
# ---------------------------------------------------------------------------

_db_lock = asyncio.Lock()


def _load_db_raw() -> Dict[str, Any]:
    """Synchronně načte db.json. Vrací prázdný slovník, pokud soubor chybí."""
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        logger.warning("db.json poškozen – začínám prázdně.")
        return {}


def _save_db_raw(data: Dict[str, Any]) -> None:
    """Synchronně uloží db.json s odsazením."""
    with open(DB_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


async def load_db() -> Dict[str, Any]:
    """Asynchronně načte databázi."""
    async with _db_lock:
        return _load_db_raw()


async def save_db(data: Dict[str, Any]) -> None:
    """Asynchronně uloží databázi."""
    async with _db_lock:
        _save_db_raw(data)


async def get_user(user_id: int) -> Dict[str, Any]:
    """Vrátí záznam uživatele; vytvoří výchozí, pokud neexistuje."""
    data = await load_db()
    key = str(user_id)
    if key not in data:
        data[key] = {
            "user_id": user_id,
            "referral_code": make_referral_code(user_id),
            "referred_by": None,
            "invites": 0,
            "paid": False,
            "payment_checked_at": 0,
            "created_at": int(time.time()),
        }
        await save_db(data)
    return data[key]


async def update_user(user_id: int, **fields: Any) -> Dict[str, Any]:
    """Aktualizuje zadaná pole uživatele a uloží db."""
    data = await load_db()
    key = str(user_id)
    if key not in data:
        await get_user(user_id)  # zajistí vytvoření
        data = await load_db()
    data[key].update(fields)
    await save_db(data)
    return data[key]

# ---------------------------------------------------------------------------
# Referral mechanika
# ---------------------------------------------------------------------------

def make_referral_code(user_id: int) -> str:
    """Vyrobí deterministický 8znakový referral kód z user_id (SHA256)."""
    raw = hashlib.sha256(f"null_engine:{user_id}".encode()).hexdigest()
    return raw[:8].upper()


def bot_username() -> str:
    """Vrátí username bota (pro referral odkazy). Dopadá z get_me při startu."""
    return getattr(bot_username, "_cached", "null_engine_bot")


async def referral_link(user_id: int) -> str:
    """Sestaví t.me odkaz s referral parametrem."""
    code = make_referral_code(user_id)
    return f"https://t.me/{bot_username()}?start={code}"

# ---------------------------------------------------------------------------
# Kontrola platby TON
# ---------------------------------------------------------------------------

async def check_ton_payment(user_id: int) -> bool:
    """
    Zeptá se toncenter API na posledních 20 transakcí na TON_ADDRESS.
    Hledá transakci, která:
      * přišla za posledních 24 h,
      * má hodnotu >= 3 TON (3 000 000 000 nanoton),
      * v komentáři obsahuje referral kód uživatele (nebo user_id jako string).

    Vrací True, pokud se platba najde.
    """
    user = await get_user(user_id)
    code = user["referral_code"]
    uid_str = str(user_id)

    now = int(time.time())
    # Pokud jsme už nedávno potvrdili platbu, nemusíme znovu volat API.
    if user.get("paid") and (now - user.get("payment_checked_at", 0)) < TX_LOOKBACK_SECONDS:
        return True

    params = {"address": TON_ADDRESS, "limit": 20}
    headers = {
        "User-Agent": "NULL-ENGINE-Bot/1.0",
        "Accept": "application/json",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                TON_API_URL, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status != 200:
                    logger.warning("toncenter vrátil HTTP %s", resp.status)
                    return user.get("paid", False)
                payload = await resp.json()
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        logger.warning("toncenter request selhal: %s", exc)
        return user.get("paid", False)

    transactions = payload.get("result") or []
    cutoff = now - TX_LOOKBACK_SECONDS

    for tx in transactions:
        # Čas transakce (UNIX sekundy)
        utime = tx.get("utime")
        if utime is None:
            continue
        if int(utime) < cutoff:
            continue

        # Hodnota – toncenter vrací 'out_msgs' / 'in_msg'; zajímá nás příchozí.
        in_msg = tx.get("in_msg")
        if not in_msg:
            continue

        value_nanoton = int(in_msg.get("value") or 0)
        if value_nanoton < TON_PRICE_NANOTON:
            continue

        # Komentář (message) – hledáme referral kód nebo user_id.
        message = (in_msg.get("message") or "").strip()
        if not message:
            continue

        if code in message or uid_str in message:
            await update_user(user_id, paid=True, payment_checked_at=now)
            logger.info("Platba potvrzena pro uživatele %s (TX utime=%s)", user_id, utime)
            return True

    return user.get("paid", False)

# ---------------------------------------------------------------------------
# Přístupová logika
# ---------------------------------------------------------------------------

async def user_has_access(user_id: int) -> tuple[bool, str]:
    """
    Vrátí (má_přístup, důvod).
    Uživatel má přístup, pokud:
      * zaplatil (TON platba potvrzena), nebo
      * má >= 3 pozvané uživatele (virální podmínka).
    """
    user = await get_user(user_id)

    # Nejprve zkusíme ověřit platbu (neblokuje – pokud API nevadí, jen aktualizuje).
    paid = await check_ton_payment(user_id)
    if paid:
        return True, "Platba potvrzena ✅"

    if user.get("invites", 0) >= REFERRAL_THRESHOLD:
        return True, f"Virální podmínka splněna ({user['invites']} pozvánek) 🎉"

    return False, (
        f"Nemáš přístup. Zaplať {TON_PRICE_STR} nebo pozvi "
        f"{REFERRAL_THRESHOLD} přátel přes svůj referral odkaz."
    )

# ---------------------------------------------------------------------------
# ERMP generování
# ---------------------------------------------------------------------------

def _import_mutator():
    """Bezpečně naimportuje ermp_core.mutator. Vrací modul nebo None."""
    try:
        from ermp_core import mutator  # type: ignore
        return mutator
    except Exception:  # noqa: BLE001
        logger.exception("Nepodařilo se importovat ermp_core.mutator")
        return None


TYPE_EMOJI = {
    "game":      "🎮",
    "web":       "🌐",
    "tool":      "🛠️",
    "pwa":       "📱",
    "script":    "💻",
    "document":  "📄",
    "quiz":      "🧠",
    "dashboard": "📊",
}

async def generate_ermp_link(description: str, ton_address: str = "", referral_code: str = "NULL") -> Optional[tuple]:
    """Zavolá generate_ermp_app a vrátí (url, output_type) nebo None."""
    mutator = _import_mutator()
    if mutator is None:
        return None

    fn = getattr(mutator, "generate_ermp_app", None)
    if fn is None:
        logger.error("ermp_core.mutator.generate_ermp_app neexistuje")
        return None

    try:
        result = fn(description, ton_address=ton_address, referral_code=referral_code)
        if asyncio.iscoroutine(result):
            result = await result
        # Nová verze vrací (url, output_type)
        if isinstance(result, tuple) and len(result) == 2:
            return result
        return (str(result), "tool") if result else None
    except Exception:  # noqa: BLE001
        logger.exception("generate_ermp_app selhal")
        return None


async def auto_generate_template_once() -> None:
    """Jednorázové volání auto_generate_template() pro periodickou úlohu."""
    mutator = _import_mutator()
    if mutator is None:
        return
    fn = getattr(mutator, "auto_generate_template", None)
    if fn is None:
        logger.warning("ermp_core.mutator.auto_generate_template neexistuje")
        return
    try:
        result = fn()
        if asyncio.iscoroutine(result):
            await result
        logger.info("auto_generate_template dokončeno: %s", result)
    except Exception:  # noqa: BLE001
        logger.exception("auto_generate_template selhal")

# ---------------------------------------------------------------------------
# Periodická úloha
# ---------------------------------------------------------------------------

async def periodic_auto_generate(app: Application) -> None:
    """Spouští auto_generate_template každých AUTO_TASK_INTERVAL sekund."""
    logger.info("Periodická úloha auto_generate spuštěna (interval %s s).", AUTO_TASK_INTERVAL)
    while True:
        try:
            await auto_generate_template_once()
        except Exception:  # noqa: BLE001
            logger.exception("Chyba v periodické úloze auto_generate.")
        await asyncio.sleep(AUTO_TASK_INTERVAL)

# ---------------------------------------------------------------------------
# Telegram handlery
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Příkaz /start – přivítání, vysvětlení, cena, referral."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    args = context.args

    # Uložení / aktualizace uživatele
    user = await get_user(user_id)

    # Zpracování referral kódu (pokud přišel přes deep-link ?start=<code>)
    if args:
        code = args[0].strip().upper()
        data = await load_db()
        # Najdi, koho referral kód se shoduje
        referrer_id: Optional[int] = None
        for uid_str, record in data.items():
            if record.get("referral_code") == code:
                referrer_id = int(uid_str)
                break

        if referrer_id is not None and referrer_id != user_id:
            # Zapiš referred_by, pokud ještě není nastaveno.
            if not user.get("referred_by"):
                await update_user(user_id, referred_by=referrer_id)
                # Zvyš počítadlo pozvánek u původního uživatele.
                referrer = await get_user(referrer_id)
                new_invites = referrer.get("invites", 0) + 1
                await update_user(referrer_id, invites=new_invites)
                logger.info(
                    "Uživatel %s pozván uživatelem %s (celkem pozvánek: %s)",
                    user_id, referrer_id, new_invites,
                )

    link = await referral_link(user_id)

    # ── Soul: personalizované přivítání ─────────────────────────────────────
    soul_mod = _import_soul()
    greeting = ""
    if soul_mod:
        try:
            first_name = update.effective_user.first_name or ""
            relation = soul_mod.UserRelation(str(user_id), first_name)
            relation.record_interaction("/start")
            voice = soul_mod.SoulVoice(relation)
            greeting = voice.greet()
        except Exception as e:
            logger.warning("Soul greet selhal: %s", e)

    # Sestavení zprávy
    soul_intro = greeting + "\n\n" if greeting else ""
    text = (
        f"{soul_intro}"
        f"💰 *Cena:* {TON_PRICE_STR} jednorázově\n"
        "nebo *ZDARMA* při pozvání 3 přátel.\n\n"
        f"📢 *Tvůj referral odkaz:*\n{link}\n\n"
        "ℹ️ Příkazy:\n"
        "/stav – tvůj stav\n"
        "/vytvor <popis> – generování aplikace\n"
        "/moje – tvoje výtvory\n"
        "/schopnosti – co umím\n"
        "/skupina – aktivuj ve skupině\n"
    )

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def cmd_stav(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Příkaz /stav – zobrazení stavu uživatele."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    user = await get_user(user_id)

    # Aktualizuj stav platby (neblokuje na dlouho).
    paid = await check_ton_payment(user_id)

    link = await referral_link(user_id)
    invites = user.get("invites", 0)

    if paid:
        platba_str = "✅ Potvrzena"
    else:
        platba_str = "⏳ Čeká na platbu"

    if invites >= REFERRAL_THRESHOLD:
        viral_str = f"🎉 Splněna ({invites}/{REFERRAL_THRESHOLD})"
    else:
        viral_str = f"⏳ {invites}/{REFERRAL_THRESHOLD}"

    text = (
        "📊 *Tvůj stav*\n"
        "──────────────────────\n"
        f"• Platba: {platba_str}\n"
        f"• Pozvánky: {viral_str}\n"
        f"• Referral kód: `{user['referral_code']}`\n"
        f"• Referral odkaz:\n{link}\n"
    )

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def cmd_vytvor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Příkaz /vytvor <popis> – generování aplikace."""
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id

    # Získání popisu z argumentů
    if not context.args:
        await update.message.reply_text(
            "⚠️ Použití: /vytvor <popis>\n\n"
            "Příklad: /vytvor Jednoduchý To-Do list s úkoly a notifikacemi"
        )
        return

    description = " ".join(context.args).strip()
    if not description:
        await update.message.reply_text("⚠️ Popis nemůže být prázdný.")
        return

    # Kontrola přístupu
    has_access, reason = await user_has_access(user_id)
    if not has_access:
        link = await referral_link(user_id)
        await update.message.reply_text(
            f"🔒 {reason}\n\n"
            f"📢 Sdílej svůj referral odkaz:\n{link}\n\n"
            f"💸 Platební informace:\n"
            f"• TON adresa: `{TON_ADDRESS}`\n"
            f"• Částka: {TON_PRICE_STR}\n"
            f"• Do komentáře transakce uveď svůj referral kód "
            f"nebo Telegram user_id: `{user_id}`\n"
            f"• Skrill alternativa: {SKRILL_DEPOSIT_ADDRESS}",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # Potvrzení příjmu požadavku
    # Detekce typu pro uživatele ještě před generováním
    from ermp_core.mutator import detect_output_type as _det
    try:
        detected = _det(description)
    except Exception:
        detected = "tool"
    type_labels_pre = {
        "game": "hru 🎮", "web": "web 🌐", "tool": "nástroj 🛠️",
        "pwa": "mobilní app 📱", "script": "skript 💻",
        "document": "dokument 📄", "quiz": "kvíz 🧠", "dashboard": "dashboard 📊",
    }
    detected_label = type_labels_pre.get(detected, "výsledek")
    status_msg = await update.message.reply_text(
        f"⚙️ Rozpoznal jsem: *{detected_label}*\nGeneruji… chvilku strpení.",
        parse_mode=ParseMode.MARKDOWN,
    )

    # Načtení referral kódu
    db = await load_db()
    user_data = db.get(str(user_id), {})
    ref_code = user_data.get("referral_code", "NULL")

    # ── Agentní generování (next-gen AI) ────────────────────────────────────
    agent_mod = _import_agent()
    if agent_mod:
        # Použij plnou agentní smyčku
        loop = asyncio.get_event_loop()
        try:
            agent = agent_mod.create_agent(str(user_id), TON_ADDRESS, ref_code)
            result = await loop.run_in_executor(None, agent.generate, description)
            url        = result["url"]
            output_type = result["type"]
            title       = result.get("title", description[:40])
            iterations  = result.get("iterations", 1)
            emoji = TYPE_EMOJI.get(output_type, "🛠️")
            type_labels = {
                "game": "Hra", "web": "Web", "tool": "Nástroj",
                "pwa": "Mobilní App", "script": "Skript",
                "document": "Dokument", "quiz": "Kvíz", "dashboard": "Dashboard",
            }
            type_label = type_labels.get(output_type, output_type.capitalize())
            iter_note = f" _(agent iteroval {iterations}×)_" if iterations > 1 else ""

            # Uložit požadavek do DB
            user_data.setdefault("requests", []).append(description)
            db[str(user_id)] = user_data
            await save_db(db)

            # Autonomní návrh dalšího výtvoru
            suggestion = await loop.run_in_executor(None, agent.suggest_next)
            suggest_line = f"\n\n💡 _{suggestion}_" if suggestion else ""

            await status_msg.edit_text(
                f"✅ *{emoji} {type_label} vygenerován!*{iter_note}\n"
                "──────────────────────\n"
                f"🔗 {url}\n\n"
                "_Ohodnoť výsledek: /hodnoceni 1-5_"
                f"{suggest_line}",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        except Exception as e:
            logger.error("Agent selhal, fallback na klasické generování: %s", e)

    # ── Fallback: klasické generování ───────────────────────────────────────
    result_fallback = await generate_ermp_link(
        description, ton_address=TON_ADDRESS, referral_code=ref_code,
    )
    if result_fallback is None:
        await status_msg.edit_text(
            "❌ Generování selhalo. Zkus to prosím znovu nebo upřesni popis."
        )
        return
    url, output_type = result_fallback
    emoji = TYPE_EMOJI.get(output_type, "🛠️")
    await status_msg.edit_text(
        f"✅ *{emoji} Hotovo!*\n"
        "──────────────────────\n"
        f"🔗 {url}\n\n"
        "Díky za použití NULL ENGINE 🤖",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Příkaz /help – nápověda."""
    if not update.message:
        return
    await update.message.reply_text(
        "🤖 *NULL ENGINE – Nápověda*\n"
        "──────────────────────\n"
        "/start – přivítání a informace\n"
        "/stav – tvůj stav (platba, pozvánky)\n"
        "/vytvor <popis> – generování aplikace\n"
        "/help – tato nápověda\n",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_moje(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Příkaz /moje – zobrazí historii výtvorů uživatele."""
    if not update.effective_user or not update.message:
        return
    user_id = update.effective_user.id
    agent_mod = _import_agent()
    if agent_mod is None:
        await update.message.reply_text("❌ Agent modul není dostupný.")
        return
    history = agent_mod.get_user_history(str(user_id))
    if not history:
        await update.message.reply_text(
            "📭 Zatím nemáš žádné výtvory.\n\n"
            "Napiš /vytvor <popis> a začni! 🚀"
        )
        return
    lines = ["📚 *Tvoje výtvory:*\n──────────────────────"]
    for i, c in enumerate(history[-8:], 1):
        emoji = {"game":"🎮","web":"🌐","tool":"🛠️","pwa":"📱",
                 "script":"💻","document":"📄","quiz":"🧠","dashboard":"📊"}.get(c.get("type","tool"),"🛠️")
        score = f" ⭐{c['feedback_score']}/5" if c.get("feedback_score") else ""
        lines.append(f"{i}. {emoji} [{c.get('type','?')}] {c.get('description','')[:40]}{score}\n   🔗 {c.get('url','')}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_hodnoceni(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Příkaz /hodnoceni <1-5> – hodnocení posledního výtvoru."""
    if not update.effective_user or not update.message:
        return
    user_id = update.effective_user.id
    args = context.args or []
    if not args or not args[0].isdigit():
        await update.message.reply_text(
            "⭐ Ohodnoť poslední výtvor: /hodnoceni <1-5>\n"
            "Příklad: /hodnoceni 5"
        )
        return
    score = max(1, min(5, int(args[0])))
    comment = " ".join(args[1:]) if len(args) > 1 else ""

    agent_mod = _import_agent()
    if agent_mod is None:
        return
    history = agent_mod.get_user_history(str(user_id))
    if not history:
        await update.message.reply_text("❌ Nemáš žádné výtvory k hodnocení.")
        return
    last = history[-1]
    agent = agent_mod.create_agent(str(user_id), TON_ADDRESS)
    agent.record_feedback(last["url"], score, comment)
    stars = "⭐" * score
    await update.message.reply_text(
        f"{stars} Díky za hodnocení {score}/5!\n"
        f"Pomáháš mi generovat lepší výtvory. 🤖"
    )


async def fallback_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Zachytí zprávy, které nejsou příkazy – odpoví s osobností NULL."""
    if not update.effective_user or not update.message:
        return
    user_id = update.effective_user.id
    text_in = update.message.text or ""

    # ── Skupinový mod: reaguj jen na @mention ───────────────────────────────
    chat_type = update.effective_chat.type if update.effective_chat else "private"
    if chat_type in ("group", "supergroup"):
        group_mod = _import_group()
        if group_mod:
            mgr = group_mod.get_manager()
            if not mgr.is_active(update.effective_chat.id):
                return  # Skupina nemá aktivovaný NULL ENGINE
            # Reaguj jen když je bot @mentionnut
            me = await context.bot.get_me()
            if me.username and f"@{me.username}" not in text_in:
                return

    # ── Soul: odpověď s osobností ───────────────────────────────────────────
    soul_mod = _import_soul()
    if soul_mod:
        try:
            first_name = update.effective_user.first_name or ""
            relation = soul_mod.UserRelation(str(user_id), first_name)
            relation.record_interaction(text_in)
            voice = soul_mod.SoulVoice(relation)

            # Zkusíme special task (počasí, krypto, atd.) přes self_extend
            ext_mod = None
            try:
                from ermp_core import self_extend
                ext_mod = self_extend
            except ImportError:
                pass

            if ext_mod:
                loop = asyncio.get_event_loop()
                special = await loop.run_in_executor(
                    None, lambda: ext_mod.handle_special_task(text_in)
                )
                if special:
                    await update.message.reply_text(special)
                    return

            # Normální odpověď s osobností
            response = voice.respond_to_unknown(text_in)
            if response:
                await update.message.reply_text(response)
                return
        except Exception as e:
            logger.warning("Soul fallback selhal: %s", e)

    await update.message.reply_text(
        "Napiš /vytvor <popis> a já to vytvořím. Nebo /help."
    )

# ---------------------------------------------------------------------------
# Nové příkazy – schopnosti, nasa, tv, kod, skupinové
# ---------------------------------------------------------------------------

TYPE_EMOJI = {
    "game": "🎮", "web": "🌐", "tool": "🛠️", "pwa": "📱",
    "script": "💻", "document": "📄", "quiz": "🧠", "dashboard": "📊",
}


async def cmd_schopnosti(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Příkaz /schopnosti – živý seznam všeho co bot umí."""
    if not update.message:
        return

    lines = [
        "🤖 *NULL ENGINE — Schopnosti*\n"
        "──────────────────────\n"
        "*Vytváření (8 typů):*\n"
        "🎮 Hry · 🌐 Weby · 🛠️ Nástroje\n"
        "📱 PWA · 💻 Skripty · 📄 Dokumenty\n"
        "🧠 Kvízy · 📊 Dashboardy\n\n"
        "*Vestavěné dovednosti:*\n"
    ]

    # Načti dovednosti ze self_extend
    try:
        from ermp_core import self_extend
        engine = self_extend.get_engine()
        skills = engine.registry.list_skills()
        if skills:
            for s in skills[:12]:
                lines.append(f"  ✓ {s}")
        else:
            lines.append("  ✓ Počasí · Krypto kurzy · Wikipedia")
            lines.append("  ✓ Překlady · Kalkulačka · Novinky")
    except Exception:
        lines.append("  ✓ Počasí · Krypto kurzy · Wikipedia")
        lines.append("  ✓ Překlady · Kalkulačka · Novinky")

    lines.append("\n*Skupinové:*\n")
    lines.append("  /skupina – aktivuj ve skupině\n")
    lines.append("  /null_vyzva <tema> – spusť výzvu\n")
    lines.append("  /null_leaderboard – žebříček\n")
    lines.append("\n*Speciální:*\n")
    lines.append("  /nasa <dotaz> – NASA-grade kód\n")
    lines.append("  /tv – IPTV přijímač\n")
    lines.append("  /kod <jazyk> <popis> – čistý kód")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_nasa(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Příkaz /nasa <dotaz> – NASA-grade technický výstup."""
    if not update.effective_user or not update.message:
        return
    if not context.args:
        await update.message.reply_text("Použití: /nasa <dotaz>\nNapř: /nasa optimalizuj Dijkstra algoritmus pro 10M uzlů")
        return

    description = " ".join(context.args)
    status = await update.message.reply_text("🚀 NASA-grade generování…")

    agent_mod = _import_agent()
    if agent_mod:
        loop = asyncio.get_event_loop()
        try:
            user_id = update.effective_user.id
            db = await load_db()
            ref_code = db.get(str(user_id), {}).get("referral_code", "NULL")
            agent = agent_mod.create_agent(str(user_id), TON_ADDRESS, ref_code)
            # Override prompt s NASA-grade instrukcemi
            nasa_desc = f"NASA-GRADE TASK: {description}. Požadavek: produkční kód, bez kompromisů, optimální časová složitost, edge cases, dokumentace."
            result = await loop.run_in_executor(None, agent.generate, nasa_desc)
            await status.edit_text(
                f"🚀 *{result.get('title','Výsledek')}*\n"
                f"──────────────────────\n"
                f"🔗 {result['url']}\n\n"
                "_NASA-grade výstup._",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        except Exception as e:
            logger.error("NASA generování selhalo: %s", e)

    await status.edit_text("NASA generování selhalo. Zkus to znovu.")


async def cmd_tv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Příkaz /tv – IPTV přijímač z volných streamů."""
    if not update.message:
        return
    status = await update.message.reply_text("📺 Stahuji playlist…")

    try:
        import requests as req
        resp = req.get(
            "https://raw.githubusercontent.com/iptv-org/iptv/master/index.m3u",
            timeout=15,
        )
        playlist = resp.text if resp.status_code == 200 else ""

        if not playlist:
            await status.edit_text("❌ Nepodařilo se stáhnout playlist.")
            return

        # Parse first 20 channels
        channels = []
        lines = playlist.split("\n")
        for i, line in enumerate(lines):
            if line.startswith("#EXTINF"):
                name = line.split(",")[-1].strip() if "," in line else f"Kanal {len(channels)+1}"
                if i + 1 < len(lines) and lines[i + 1].startswith("http"):
                    channels.append({"name": name, "url": lines[i + 1]})
            if len(channels) >= 20:
                break

        # Build HTML IPTV player
        channel_items = ""
        for ch in channels:
            channel_items += f'<div class="ch" onclick="play(\\"{ch["url"]}\\")">{ch["name"]}</div>\n'

        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>NULL TV</title><style>
body{{margin:0;background:#111;color:#fff;font-family:system-ui}}
.header{{padding:16px;background:#222;text-align:center;font-size:20px;font-weight:bold}}
.player{{width:100%;max-width:640px;margin:0 auto;display:block}}
.video{{width:100%;background:#000}}
.channels{{padding:8px;max-width:640px;margin:0 auto}}
.ch{{padding:10px;border:1px solid #333;border-radius:6px;margin:4px 0;cursor:pointer}}
.ch:hover{{background:#222}}
</style></head><body>
<div class="header">📺 NULL TV — {len(channels)} stanic</div>
<video class="video" id="v" controls></video>
<div class="channels">{channel_items}</div>
<script>
function play(url){{var v=document.getElementById('v');v.src=url;v.play();}}
</script>
</body></html>"""

        # Publikovat přes Telegraph
        from ermp_core.mutator import publish_html
        url = publish_html(html, "NULL TV")
        await status.edit_text(f"📺 *NULL TV* — {len(channels)} stanic\n🔗 {url}", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error("TV selhalo: %s", e)
        await status.edit_text("❌ TV selhalo. Zkus to později.")


async def cmd_kod(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Příkaz /kod <jazyk> <popis> – čistý kód v daném jazyce."""
    if not update.effective_user or not update.message:
        return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Použití: /kod <jazyk> <popis>\nNapř: /kod python web scraper pro sreality.cz")
        return

    lang = context.args[0]
    description = " ".join(context.args[1:])
    status = await update.message.reply_text(f"💻 Generuji {lang} kód…")

    try:
        import requests as req
        prompt = (
            f"Jsi expert programátor. Napiš kompletní, produkční kód v jazyce {lang}.\n\n"
            f"Úkol: {description}\n\n"
            f"Vrať POUZE kód v code bloku. Žádné vysvětlení.\n"
            f"```{lang}\n// kód zde\n```"
        )
        resp = req.post(
            "http://localhost:11434/api/generate",
            json={"model": "mistral", "prompt": prompt, "stream": False,
                  "options": {"temperature": 0.3, "num_predict": 4000}},
            timeout=120,
        )
        code = resp.json().get("response", "")

        # Pošli jako code message
        if len(code) > 4000:
            code = code[:4000] + "\n... (zkráceno)"
        await status.edit_text(f"💻 *{lang}* — {description[:40]}\n\n```{lang}\n{code}\n```", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error("Kód generování selhalo: %s", e)
        await status.edit_text("❌ Generování kódu selhalo. Je Ollama spuštěna?")


# ---------------------------------------------------------------------------
# Skupinové příkazy
# ---------------------------------------------------------------------------

async def cmd_skupina(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Příkaz /skupina – aktivuje NULL ENGINE ve skupině (jen admin)."""
    if not update.effective_chat or not update.effective_user:
        return
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("Tento příkaz funguje jen ve skupinách.")
        return

    group_mod = _import_group()
    if not group_mod:
        await update.message.reply_text("Skupinový mod není dostupný.")
        return

    mgr = group_mod.get_manager()
    if mgr.is_active(chat.id):
        await update.message.reply_text("✅ NULL ENGINE už je ve skupině aktivní!")
        return

    mgr.activate_group(chat.id, chat.title or "Skupina")
    await update.message.reply_text(
        "🤖 *NULL ENGINE aktivován!*\n\n"
        "Od teď:‎\n"
        "• @mentionni mě + popis → vygeneruji aplikaci\n"
        "• /null_vyzva <tema> → spusť skupinovou výzvu\n"
        "• /null_leaderboard → žebříček tvůrců\n\n"
        "Každý výtvor nese referral odkaz tvůrce — virální růst! 🚀",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_null_vyzva(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Příkaz /null_vyzva <tema> – spustí 24h výzvu ve skupině."""
    if not update.effective_chat or not update.message:
        return
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("Výzvy fungují jen ve skupinách.")
        return

    group_mod = _import_group()
    if not group_mod:
        return

    mgr = group_mod.get_manager()
    if not mgr.is_active(chat.id):
        await update.message.reply_text("Nejprve aktivuj NULL ENGINE: /skupina")
        return

    if not context.args:
        await update.message.reply_text("Použití: /null_vyzva <tema>\nNapř: /null_vyzva nejlepší arkáda")
        return

    topic = " ".join(context.args)
    result = mgr.start_challenge(chat.id, topic, hours=24)

    if result.get("success"):
        deadline = result.get("deadline", "?")
        await update.message.reply_text(
            f"🏁 *VÝZVA SPUŠTENA!*\n"
            f"──────────────────────\n"
            f"Téma: *{topic}*\n"
            f"Konec: {deadline}\n\n"
            f"Tvořte: /vytvor <popis>\n"
            f"Hlasujte 👍 na výtvory ostatních!\n"
            f"Vítěz získá odznak 🥇",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await update.message.reply_text(f"Výzvu nelze spustit: {result.get('reason', 'neznámá chyba')}")


async def cmd_null_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Příkaz /null_leaderboard – žebříček tvůrců ve skupině."""
    if not update.effective_chat or not update.message:
        return
    chat = update.effective_chat

    group_mod = _import_group()
    if not group_mod:
        return

    mgr = group_mod.get_manager()
    if not mgr.is_active(chat.id):
        await update.message.reply_text("NULL ENGINE není ve skupině aktivní. Použij /skupina")
        return

    lb = mgr.get_leaderboard(chat.id, top_n=10)
    if not lb:
        await update.message.reply_text("Žádní tvůrci zatím. Buď první! /vytvor <popis>")
        return

    lines = [f"🏆 *LEADERBOARD — {chat.title or 'Skupina'}*\n─────────────────"]
    medals = ["🥇", "🥈", "🥉"]
    for i, entry in enumerate(lb):
        medal = medals[i] if i < 3 else f"{i+1}."
        lines.append(
            f"{medal} {entry['name']} "
            f"({entry['creations']} výtvorů, {entry['wins']} výher)"
        )
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


# ---------------------------------------------------------------------------
# Periodické úlohy — auto-update + proaktivní zprávy
# ---------------------------------------------------------------------------

async def periodic_auto_update(app: Application) -> None:
    """Každých 6 hodin zkontroluje GitHub pro nové verze a hot-reloadne."""
    import asyncio as _aio
    while True:
        await _aio.sleep(6 * 3600)
        try:
            viral_mod = _import_viral()
            if not viral_mod:
                continue
            updater = viral_mod.get_updater()
            result = updater.check_for_updates()
            if result and result.get("has_update"):
                logger.info("Auto-update: nový commit %s", result.get("sha", "?"))
                apply_result = updater.download_and_apply_updates()
                if apply_result.get("success"):
                    updated = ", ".join(apply_result.get("updated_files", []))
                    logger.info("Hot-reload dokončen: %s", updated)
                else:
                    logger.warning("Auto-update selhal: %s", apply_result.get("errors", []))
        except Exception as e:
            logger.warning("Periodic auto-update chyba: %s", e)


async def periodic_proactive(app: Application) -> None:
    """Každých 6 hodin pošle proaktivní zprávy eligible uživatelům."""
    import asyncio as _aio
    while True:
        await _aio.sleep(6 * 3600)
        try:
            soul_mod = _import_soul()
            if not soul_mod:
                continue
            proactive = soul_mod.get_proactive_engine()
            eligible = proactive.get_eligible_users()
            for uid_str in eligible:
                try:
                    relation = soul_mod.UserRelation(uid_str)
                    voice = soul_mod.SoulVoice(relation)
                    loop = asyncio.get_event_loop()
                    msg = await loop.run_in_executor(None, voice.proactive_message)
                    if msg:
                        uid = int(uid_str)
                        await app.bot.send_message(chat_id=uid, text=msg)
                        proactive.mark_contacted(uid_str)
                        logger.info("Proaktivní zpráva poslána uživateli %s", uid_str)
                except Exception as e:
                    logger.warning("Proaktivní zpráva pro %s selhala: %s", uid_str, e)
        except Exception as e:
            logger.warning("Periodic proactive chyba: %s", e)


# ---------------------------------------------------------------------------
# Lifecycly
# ---------------------------------------------------------------------------

async def post_init(app: Application) -> None:
    """Po inicializaci aplikace – cachuje username bota a spustí periodickou úlohu."""
    me = await app.bot.get_me()
    bot_username._cached = (me.username or "null_engine_bot")  # type: ignore[attr-defined]
    logger.info("Bot @%s inicializován.", bot_username._cached)

    # Spusť periodickou úlohu na pozadí.
    app.create_task(periodic_auto_generate(app))

    # Spusť auto-update kontrolu každých 6 hodin.
    app.create_task(periodic_auto_update(app))

    # Spusť proaktivní zprávy každých 6 hodin.
    app.create_task(periodic_proactive(app))


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def build_application() -> Application:
    """Sestaví a nakonfiguruje Telegram Application."""
    app = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stav", cmd_stav))
    app.add_handler(CommandHandler("vytvor", cmd_vytvor))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("moje", cmd_moje))
    app.add_handler(CommandHandler("hodnoceni", cmd_hodnoceni))
    app.add_handler(CommandHandler("schopnosti", cmd_schopnosti))
    app.add_handler(CommandHandler("nasa", cmd_nasa))
    app.add_handler(CommandHandler("tv", cmd_tv))
    app.add_handler(CommandHandler("kod", cmd_kod))
    app.add_handler(CommandHandler("skupina", cmd_skupina))
    app.add_handler(CommandHandler("null_vyzva", cmd_null_vyzva))
    app.add_handler(CommandHandler("null_leaderboard", cmd_null_leaderboard))
    app.add_handler(MessageHandler(filters.COMMAND, cmd_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback_message))

    return app


def main() -> None:
    """Hlavní entrypoint – spustí bota (polling)."""
    logger.info("NULL ENGINE startuje…")
    app = build_application()
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
