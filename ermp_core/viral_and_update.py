"""
ermp_core.viral_and_update – Virální embed + Auto-update pro NULL ENGINE
========================================================================
1. ViralEmbed     — virální watermark do každého výtvoru (referral + TON platební tlačítko)
2. AutoUpdater    — kontrola GitHubu pro nové verze a hot-reload modulů
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger("null_engine")

GITHUB_API = "https://api.github.com/repos/olafwindross/null-engine/commits"
GITHUB_RAW = "https://raw.githubusercontent.com/olafwindross/null-engine/main"
UPDATE_STATE_FILE = "update_state.json"

# Soubory které se auto-updatují
AUTO_UPDATE_FILES = [
    "null_engine.py",
    "ermp_core/agent.py",
    "ermp_core/soul.py",
    "ermp_core/mutator.py",
    "ermp_core/self_extend.py",
    "ermp_core/group_mode.py",
]

# Moduly pro hot-reload po update
HOT_RELOAD_MODULES = [
    "ermp_core.agent",
    "ermp_core.soul",
    "ermp_core.mutator",
    "ermp_core.self_extend",
    "ermp_core.group_mode",
]


# ---------------------------------------------------------------------------
# ViralEmbed — virální watermark
# ---------------------------------------------------------------------------

class ViralEmbed:
    """Generuje a injektuje virální watermark do HTML výtvorů."""

    def build_watermark(
        self,
        bot_username: str,
        referral_code: str,
        ton_address: str = "",
    ) -> str:
        """
        Vrátí HTML blok s virálním watermarkem.
        Obsahuje: 'Made with NULL ENGINE' + referral odkaz + TON platební tlačítko.
        """
        ref_link = f"https://t.me/{bot_username}?start={referral_code}"
        ton_link = f"ton://transfer/{ton_address}?amount=3000000000&text={referral_code}"

        return (
            '<div style="position:fixed;bottom:0;left:0;right:0;'
            'background:rgba(0,0,0,0.88);color:#fff;padding:8px 16px;'
            'display:flex;justify-content:space-between;align-items:center;'
            'font-family:system-ui,sans-serif;font-size:12px;z-index:99999;">'
            f'<a href="{ref_link}" style="color:#00d4ff;text-decoration:none;font-weight:600;">'
            '⚡ Made with NULL ENGINE</a>'
            f'<a href="{ton_link}" style="background:#0088cc;color:#fff;'
            'padding:4px 12px;border-radius:6px;text-decoration:none;font-size:11px;">'
            '⭐ Podpořit (3 TON)</a>'
            '</div>'
        )

    def inject_watermark(
        self,
        html: str,
        bot_username: str,
        referral_code: str,
        ton_address: str = "",
    ) -> str:
        """
        Najde </body> v HTML a vloží watermark před něj.
        Pokud </body> neexistuje, připojí na konec.
        """
        watermark = self.build_watermark(bot_username, referral_code, ton_address)

        lower = html.lower()
        idx = lower.rfind("</body>")
        if idx != -1:
            return html[:idx] + watermark + html[idx:]
        return html + watermark


# ---------------------------------------------------------------------------
# AutoUpdater — kontrola GitHubu a hot-reload
# ---------------------------------------------------------------------------

class AutoUpdater:
    """Kontroluje GitHub pro nové commity a hot-reloadne moduly."""

    def __init__(self):
        self._state: Dict[str, Any] = self._load_state()

    def _load_state(self) -> Dict[str, Any]:
        if not os.path.exists(UPDATE_STATE_FILE):
            return {"last_sha": "", "last_check": "", "version": 1}
        try:
            with open(UPDATE_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"last_sha": "", "last_check": "", "version": 1}

    def _save_state(self) -> None:
        with open(UPDATE_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(self._state, f, ensure_ascii=False, indent=2)

    def get_version_info(self) -> Dict[str, Any]:
        return {
            "current_sha": self._state.get("last_sha", "unknown"),
            "last_update": self._state.get("last_check", "never"),
            "version_number": self._state.get("version", 1),
        }

    def check_for_updates(self) -> Optional[Dict[str, Any]]:
        """
        Zkontroluje GitHub API jestli je nový commit.
        Vrátí {has_update, message, sha} nebo None při chybě.
        """
        try:
            resp = requests.get(
                f"{GITHUB_API}?per_page=1",
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "NULL-ENGINE-Bot/1.0",
                },
                timeout=15,
            )
            resp.raise_for_status()
            commits = resp.json()
            if not commits:
                return {"has_update": False, "message": "Žádné commity", "sha": ""}

            latest_sha = commits[0].get("sha", "")
            commit_msg = commits[0].get("commit", {}).get("message", "")

            self._state["last_check"] = datetime.now(timezone.utc).isoformat()

            if self._state.get("last_sha") and latest_sha == self._state["last_sha"]:
                self._save_state()
                return {"has_update": False, "message": "Aktuální", "sha": latest_sha}

            if not self._state.get("last_sha"):
                # První spuštění — jen uložíme SHA, neupdatujeme
                self._state["last_sha"] = latest_sha
                self._save_state()
                return {"has_update": False, "message": "První spuštění", "sha": latest_sha}

            self._save_state()
            return {
                "has_update": True,
                "message": commit_msg,
                "sha": latest_sha,
            }
        except Exception as e:
            logger.warning("Auto-update check selhal: %s", e)
            return None

    def download_and_apply_updates(self) -> Dict[str, Any]:
        """
        Stáhne nové .py soubory z GitHubu, uloží je a hot-reloadne moduly.
        Vrátí {success, updated_files, errors}.
        """
        updated_files: List[str] = []
        errors: List[str] = []

        # Stáhni každý soubor
        for filepath in AUTO_UPDATE_FILES:
            try:
                url = f"{GITHUB_RAW}/{filepath}"
                resp = requests.get(url, timeout=30)
                if resp.status_code == 200 and resp.text:
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(resp.text)
                    updated_files.append(filepath)
                else:
                    errors.append(f"{filepath}: HTTP {resp.status_code}")
            except Exception as e:
                errors.append(f"{filepath}: {e}")

        # Hot-reload modulů
        if updated_files:
            for mod_name in HOT_RELOAD_MODULES:
                try:
                    if mod_name in sys.modules:
                        importlib.reload(sys.modules[mod_name])
                        logger.info("Hot-reload: %s", mod_name)
                    else:
                        importlib.import_module(mod_name)
                        logger.info("Import: %s", mod_name)
                except Exception as e:
                    errors.append(f"reload {mod_name}: {e}")

            # Aktualizuj verzi
            self._state["version"] = self._state.get("version", 1) + 1
            self._save_state()

        return {
            "success": len(errors) == 0,
            "updated_files": updated_files,
            "errors": errors,
        }


# ---------------------------------------------------------------------------
# Singletony
# ---------------------------------------------------------------------------

_embed: Optional[ViralEmbed] = None
_updater: Optional[AutoUpdater] = None


def get_embed() -> ViralEmbed:
    global _embed
    if _embed is None:
        _embed = ViralEmbed()
    return _embed


def get_updater() -> AutoUpdater:
    global _updater
    if _updater is None:
        _updater = AutoUpdater()
    return _updater
