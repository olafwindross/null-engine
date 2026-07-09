#!/usr/bin/env python3
"""
NULL ENGINE – swap_to_skrill.py
─────────────────────────────────────────────────────────────────────
Samostatný skript (nebo vlákno), který každých 30 minut kontroluje
TON zůstatek na dané adrese a pokud překročí 5 TON, provede swap
přes FixedFloat API (TON → USDT BEP-20) na Skrill deposit adresu.
Při selhání FixedFloat použije ChangeNow jako fallback.

Všechny citlivé údaje se načítají z config.yaml.
"""

import sys
import time
import logging
import threading
import requests
import yaml
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Nastavení logování
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("swap_log.txt", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("swap_to_skrill")

# Konstanty
CHECK_INTERVAL = 30 * 60          # 30 minut
TON_THRESHOLD_NANOTON = 5_000_000_000  # 5 TON v nanotonech
TON_TO_NANOTON = 1_000_000_000

# API endpointy
TONCENTER_URL = "https://toncenter.com/api/v2/getAddressBalance"
FIXEDFLOAT_CREATE_URL = "https://ff.io/api/v2/create"
CHANGENOW_URL = "https://api.changenow.io/v1/transactions"


# ---------------------------------------------------------------------------
# Načtení konfigurace
# ---------------------------------------------------------------------------
def load_config(path: str = "config.yaml") -> dict:
    """Načte config.yaml a vrátí slovník s konfigurací."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        if cfg is None:
            raise ValueError("config.yaml je prázdný")
        return cfg
    except FileNotFoundError:
        logger.error("config.yaml nebyl nalezen – vytvořte jej podle šablony.")
        sys.exit(1)
    except yaml.YAMLError as exc:
        logger.error("Chyba při parsování config.yaml: %s", exc)
        sys.exit(1)


# ---------------------------------------------------------------------------
# TON balance check
# ---------------------------------------------------------------------------
def get_ton_balance(ton_address: str) -> float:
    """
    Zkontaktuje toncenter.com a vrátí zůstatek v TON (float).
    Při chybě vrátí 0.0.
    """
    try:
        resp = requests.get(
            TONCENTER_URL,
            params={"address": ton_address},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        # toncenter vrací buď přímo balance, nebo vkládá pole 'result'
        result = data.get("result", data)
        balance_nan = float(result.get("balance", 0))
        balance_ton = balance_nan / TON_TO_NANOTON
        logger.info("TON zůstatek pro %s: %.4f TON", ton_address, balance_ton)
        return balance_ton
    except Exception as exc:
        logger.error("Nelze získat TON zůstatek: %s", exc)
        return 0.0


# ---------------------------------------------------------------------------
# Swap přes FixedFloat
# ---------------------------------------------------------------------------
def swap_via_fixedfloat(
    amount_ton: float,
    skrill_address: str,
    ff_api_key: str,
    ff_api_secret: str,
) -> dict | None:
    """
    Vytvoří swap objednávku na FixedFloat API (TON → USDT BEP-20).
    Vrací dict s odpovědí nebo None při selhání.
    """
    payload = {
        "fromCurrency": "TON",
        "toCurrency": "USDT20",        # USDT BEP-20 (BSC)
        "toAddress": skrill_address,
        "amount": str(amount_ton),
        "type": "fixed",               # fixed rate
    }

    headers = {
        "Content-Type": "application/json",
    }
    # FixedFloat vyžaduje API klíč v hlavičce, pokud je k dispozici
    if ff_api_key:
        headers["X-API-KEY"] = ff_api_key
    if ff_api_secret:
        headers["X-API-SIGN"] = ff_api_secret

    try:
        resp = requests.post(
            FIXEDFLOAT_CREATE_URL,
            json=payload,
            headers=headers,
            timeout=45,
        )
        resp.raise_for_status()
        data = resp.json()
        logger.info("FixedFloat objednávka vytvořena: %s", data)
        return data
    except Exception as exc:
        logger.warning("FixedFloat swap selhal: %s – zkouším ChangeNow fallback.", exc)
        return None


# ---------------------------------------------------------------------------
# Fallback swap přes ChangeNow
# ---------------------------------------------------------------------------
def swap_via_changenow(
    amount_ton: float,
    skrill_address: str,
    cn_api_key: str,
) -> dict | None:
    """
    Fallback: vytvoří swap přes ChangeNow API (TON → USDTBEP20).
    Vrací dict s odpovědí nebo None při selhání.
    """
    payload = {
        "from": "ton",
        "to": "usdtbep20",
        "address": skrill_address,
        "amount": str(amount_ton),
    }

    # Pokud máme API klíč, přidáme do URL; jinak použijeme veřejný endpoint
    url = f"{CHANGENOW_URL}/{cn_api_key}" if cn_api_key else f"{CHANGENOW_URL}"

    try:
        resp = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=45,
        )
        resp.raise_for_status()
        data = resp.json()
        logger.info("ChangeNow fallback objednávka vytvořena: %s", data)
        return data
    except Exception as exc:
        logger.error("ChangeNow fallback také selhal: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Hlavní kontrolní cyklus
# ---------------------------------------------------------------------------
def run_swap_loop(config_path: str = "config.yaml"):
    """
    Hlavní smyčka: každých CHECK_INTERVAL sekund zkontroluje zůstatek
    a případně provede swap.
    """
    cfg = load_config(config_path)

    ton_address = cfg.get("ton_address", "")
    skrill_address = cfg.get("skrill_deposit_address", "")
    ff_api_key = cfg.get("fixedfloat_api_key", "")
    ff_api_secret = cfg.get("fixedfloat_api_secret", "")
    cn_api_key = cfg.get("changenow_api_key", "")

    if not ton_address:
        logger.error("ton_address není nastaven v config.yaml. Ukončuji.")
        return
    if not skrill_address:
        logger.error("skrill_deposit_address není nastaven v config.yaml. Ukončuji.")
        return

    logger.info("=== NULL ENGINE swap monitor spuštěn ===")
    logger.info("Monitoruji adresu: %s", ton_address)
    logger.info("Skrill deposit: %s", skrill_address)
    logger.info("Interval kontroly: %d minut", CHECK_INTERVAL // 60)
    logger.info("Práh pro swap: > 5 TON")

    while True:
        try:
            balance_ton = get_ton_balance(ton_address)
            balance_nan = balance_ton * TON_TO_NANOTON

            if balance_nan > TON_THRESHOLD_NANOTON:
                logger.info(
                    "Zůstatek %.4f TON překračuje práh 5 TON – spouštím swap.",
                    balance_ton,
                )

                # 1) Zkusit FixedFloat
                result = swap_via_fixedfloat(
                    amount_ton=balance_ton,
                    skrill_address=skrill_address,
                    ff_api_key=ff_api_key,
                    ff_api_secret=ff_api_secret,
                )

                # 2) Fallback na ChangeNow
                provider_used = "FixedFloat"
                if result is None:
                    result = swap_via_changenow(
                        amount_ton=balance_ton,
                        skrill_address=skrill_address,
                        cn_api_key=cn_api_key,
                    )
                    provider_used = "ChangeNow"

                # 3) Zalogovat výsledek do swap_log.txt
                log_entry = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "ton_balance": balance_ton,
                    "provider": provider_used if result else "FAILED",
                    "result": result,
                    "skrill_address": skrill_address,
                }

                if result:
                    logger.info(
                        "Swap úspěšný přes %s. Viz swap_log.txt pro detaily.",
                        provider_used,
                    )
                else:
                    logger.error(
                        "Swap selhal přes oba poskytovatele. Viz swap_log.txt."
                    )

                # Přidat lidsky čitelný záznam do swap_log.txt
                with open("swap_log.txt", "a", encoding="utf-8") as f:
                    f.write(f"\n{'='*60}\n")
                    f.write(f"Čas: {log_entry['timestamp']}\n")
                    f.write(f"TON zůstatek: {log_entry['ton_balance']:.4f}\n")
                    f.write(f"Poskytovatel: {log_entry['provider']}\n")
                    f.write(f"Skrill adresa: {log_entry['skrill_address']}\n")
                    f.write(f"Odpověď API: {log_entry['result']}\n")
            else:
                logger.info(
                    "Zůstatek %.4f TON je pod prahem 5 TON – žádná akce.",
                    balance_ton,
                )

        except Exception as exc:
            logger.error("Neočekávaná chyba v hlavní smyčce: %s", exc, exc_info=True)

        # Čekat před další kontrolou
        logger.info("Další kontrola za %d minut.", CHECK_INTERVAL // 60)
        time.sleep(CHECK_INTERVAL)


def run_in_thread(config_path: str = "config.yaml") -> threading.Thread:
    """
    Spustí swap smyčku v daemon vlákně (vhodné pro import z null_engine.py).
    Vrací objekt vlákna.
    """
    thread = threading.Thread(
        target=run_swap_loop,
        args=(config_path,),
        daemon=True,
        name="swap-monitor",
    )
    thread.start()
    logger.info("Swap monitor vlákno spuštěno (daemon).")
    return thread


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    config_file = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    try:
        run_swap_loop(config_file)
    except KeyboardInterrupt:
        logger.info("Swap monitor ukončen uživatelem (Ctrl+C).")
        sys.exit(0)
