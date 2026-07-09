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


async def generate_ermp_link(description: str) -> Optional[str]:
    """Zavolá generate_ermp_app a vrátí Telegraph odkaz (nebo None)."""
    mutator = _import_mutator()
    if mutator is None:
        return None

    fn = getattr(mutator, "generate_ermp_app", None)
    if fn is None:
        logger.error("ermp_core.mutator.generate_ermp_app neexistuje")
        return None

    try:
        # generate_ermp_app může být sync i async – podporujeme oboje.
        result = fn(description)
        if asyncio.iscoroutine(result):
            result = await result
        return str(result) if result else None
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

    text = (
        "🤖 *NULL ENGINE*\n"
        "──────────────────────\n"
        "Vítej! Jsem autonomní generátor ERMP aplikací.\n\n"
        "Co umím?\n"
        "• Popíšeš, co chceš vytvořit (/vytvor <popis>)\n"
        "• Já vygeneruji aplikaci a pošlu ti Telegraph odkaz.\n\n"
        f"💰 *Cena:* {TON_PRICE_STR} jednorázově\n"
        "nebo *ZDARMA* při pozvání 3 přátel.\n\n"
        f"📢 *Tvůj referral odkaz:*\n{link}\n\n"
        "ℹ️ Příkazy:\n"
        "/stav – tvůj aktuální stav\n"
        "/vytvor <popis> – generování aplikace\n"
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
    status_msg = await update.message.reply_text(
        "⚙️ Generuji aplikaci… chvilku strpení."
    )

    # Generování
    link = await generate_ermp_link(description)
    if link is None:
        await status_msg.edit_text(
            "❌ Generování selhalo. Zkus to prosím později nebo upřesni popis."
        )
        return

    await status_msg.edit_text(
        "✅ *Hotovo!*\n"
        "──────────────────────\n"
        f"📰 Tvá aplikace: {link}\n\n"
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


async def fallback_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Zachytí zprávy, které nejsou příkazy – poradí uživateli."""
    if not update.message:
        return
    await update.message.reply_text(
        "Nerozumím. Použij /start, /stav, /vytvor <popis> nebo /help."
    )

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
