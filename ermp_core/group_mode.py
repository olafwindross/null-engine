"""
ermp_core.group_mode – Skupinový virální engine pro NULL ENGINE
=================================================================
Bot funguje ve skupinách: @mention odpovědi, skupinové výzvy, leaderboard.

Architektura:
  - GroupState    → stav jedné skupiny (aktivace, výzva, leaderboard)
  - GroupChallenge → datová struktura výzvy (téma, deadline, submissiony, hlasy)
  - GroupManager   → hlavní manažer, singleton, ukládá do groups.json
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

GROUPS_FILE = "groups.json"
CHALLENGE_HOURS = 24


# ---------------------------------------------------------------------------
# GroupChallenge — datová struktura pro jednu výzvu
# ---------------------------------------------------------------------------

class GroupChallenge:
    def __init__(
        self,
        topic: str,
        hours: int = CHALLENGE_HOURS,
    ):
        self.topic = topic
        self.deadline = (
            datetime.now(timezone.utc) + timedelta(hours=hours)
        ).isoformat()
        self.submissions: List[Dict[str, Any]] = []
        self.active = True

    def add_submission(
        self,
        user_id: str,
        user_name: str,
        url: str,
        description: str,
    ) -> None:
        """Přidá submission uživatele do výzvy."""
        self.submissions.append(
            {
                "user_id": str(user_id),
                "user_name": user_name,
                "url": url,
                "description": description[:80],
                "votes": 0,
                "voters": [],
            }
        )

    def vote(self, user_id: str, submission_url: str) -> bool:
        """Uživatel hlasuje (1 uživatel = 1 hlas na submission). Vrátí True pokud hlas proběhl."""
        for sub in self.submissions:
            if sub["url"] == submission_url:
                if str(user_id) in sub["voters"]:
                    return False  # Už hlasoval
                sub["voters"].append(str(user_id))
                sub["votes"] += 1
                return True
        return False

    def is_expired(self) -> bool:
        """Vrátí True pokud výzva vypršela."""
        try:
            dl = datetime.fromisoformat(self.deadline)
            return datetime.now(timezone.utc) > dl
        except Exception:
            return True

    def get_winner(self) -> Optional[Dict[str, Any]]:
        """Vrátí submission s nejvíce hlasy (nebo None při remídze/prázdné)."""
        if not self.submissions:
            return None
        sorted_subs = sorted(
            self.submissions,
            key=lambda s: s["votes"],
            reverse=True,
        )
        if len(sorted_subs) > 1 and sorted_subs[0]["votes"] == sorted_subs[1]["votes"]:
            return None  # Remíza
        return sorted_subs[0]

    def get_stats(self) -> Dict[str, Any]:
        """Vrátí statistiky výzvy."""
        return {
            "topic": self.topic,
            "deadline": self.deadline,
            "submissions_count": len(self.submissions),
            "total_votes": sum(s["votes"] for s in self.submissions),
            "participants": list(
                set(s["user_id"] for s in self.submissions)
            ),
            "expired": self.is_expired(),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "deadline": self.deadline,
            "submissions": self.submissions,
            "active": self.active,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GroupChallenge":
        challenge = cls.__new__(cls)
        challenge.topic = data.get("topic", "")
        challenge.deadline = data.get("deadline", "")
        challenge.submissions = data.get("submissions", [])
        challenge.active = data.get("active", False)
        return challenge


# ---------------------------------------------------------------------------
# GroupManager — hlavní manažer skupin
# ---------------------------------------------------------------------------

class GroupManager:
    """Spravuje všechny skupiny a jejich stavy."""

    def __init__(self):
        self._groups: Dict[str, Dict[str, Any]] = self._load()

    def _load(self) -> Dict[str, Dict[str, Any]]:
        if not os.path.exists(GROUPS_FILE):
            return {}
        try:
            with open(GROUPS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save(self) -> None:
        with open(GROUPS_FILE, "w", encoding="utf-8") as f:
            json.dump(self._groups, f, ensure_ascii=False, indent=2)

    # ── Aktivace / deaktivace ─────────────────────────────────────────────

    def activate_group(self, group_id: int, title: str) -> None:
        key = str(group_id)
        if key not in self._groups:
            self._groups[key] = {
                "group_id": group_id,
                "title": title,
                "activated_at": datetime.now(timezone.utc).isoformat(),
                "leaderboard": {},
                "challenge": None,
            }
        else:
            self._groups[key]["title"] = title
            self._groups[key]["activated_at"] = datetime.now(timezone.utc).isoformat()
        self._save()

    def deactivate_group(self, group_id: int) -> None:
        key = str(group_id)
        if key in self._groups:
            self._groups[key]["activated_at"] = None
            self._save()

    def is_active(self, group_id: int) -> bool:
        key = str(group_id)
        g = self._groups.get(key)
        if not g:
            return False
        return g.get("activated_at") is not None

    def get_group(self, group_id: int) -> Optional[Dict[str, Any]]:
        return self._groups.get(str(group_id))

    # ── Výzvy ─────────────────────────────────────────────────────────────

    def start_challenge(
        self,
        group_id: int,
        topic: str,
        hours: int = CHALLENGE_HOURS,
    ) -> Dict[str, Any]:
        """Spustí výzvu ve skupině. Vrátí {success, deadline} nebo {success: False, reason}."""
        key = str(group_id)
        g = self._groups.get(key)
        if not g or not g.get("activated_at"):
            return {"success": False, "reason": "Skupina není aktivní"}

        # Zkontroluj jestli už výzva běží
        challenge_data = g.get("challenge")
        if challenge_data and challenge_data.get("active") and not self._challenge_expired(challenge_data):
            return {"success": False, "reason": "Výzva už běží"}

        challenge = GroupChallenge(topic, hours)
        g["challenge"] = challenge.to_dict()
        self._save()
        return {
            "success": True,
            "deadline": challenge.deadline,
        }

    def _challenge_expired(self, challenge_data: Dict[str, Any]) -> bool:
        try:
            dl = datetime.fromisoformat(challenge_data.get("deadline", ""))
            return datetime.now(timezone.utc) > dl
        except Exception:
            return True

    def end_challenge(self, group_id: int) -> Optional[Dict[str, Any]]:
        """Ukončí výzvu a vrátí vítěze."""
        key = str(group_id)
        g = self._groups.get(key)
        if not g or not g.get("challenge"):
            return None

        challenge = GroupChallenge.from_dict(g["challenge"])
        winner = challenge.get_winner()
        challenge.active = False
        g["challenge"] = challenge.to_dict()

        # Zaznamenat výhru do leaderboardu
        if winner:
            uid = winner["user_id"]
            lb = g.setdefault("leaderboard", {})
            entry = lb.setdefault(uid, {
                "name": winner["user_name"],
                "creations": 0,
                "wins": 0,
                "total_votes": 0,
            })
            entry["wins"] = entry.get("wins", 0) + 1
            entry["total_votes"] = entry.get("total_votes", 0) + winner["votes"]

        self._save()
        return {
            "winner": winner,
            "stats": challenge.get_stats(),
        }

    def check_expired_challenges(self) -> List[Dict[str, Any]]:
        """Zkontroluje všechny skupiny pro vypršené výzvy. Vrátí seznam {group_id, result}."""
        expired = []
        for key, g in self._groups.items():
            challenge_data = g.get("challenge")
            if not challenge_data or not challenge_data.get("active"):
                continue
            if self._challenge_expired(challenge_data):
                result = self.end_challenge(int(key))
                if result:
                    expired.append({
                        "group_id": int(key),
                        "group_title": g.get("title", ""),
                        "result": result,
                    })
        return expired

    # ── Záznamy výtvorů ───────────────────────────────────────────────────

    def record_creation(
        self,
        group_id: int,
        user_id: int,
        user_name: str,
        url: str,
        description: str,
    ) -> None:
        """Zaznamená výtvor uživatele ve skupině (do leaderboardu + aktivní výzvy)."""
        key = str(group_id)
        g = self._groups.get(key)
        if not g:
            return

        # Leaderboard
        lb = g.setdefault("leaderboard", {})
        uid = str(user_id)
        entry = lb.setdefault(uid, {
            "name": user_name,
            "creations": 0,
            "wins": 0,
            "total_votes": 0,
        })
        entry["creations"] = entry.get("creations", 0) + 1
        entry["name"] = user_name  # update jména

        # Aktivní výzva
        challenge_data = g.get("challenge")
        if challenge_data and challenge_data.get("active"):
            challenge = GroupChallenge.from_dict(challenge_data)
            if not challenge.is_expired():
                challenge.add_submission(str(user_id), user_name, url, description)
                g["challenge"] = challenge.to_dict()

        self._save()

    def vote(
        self,
        group_id: int,
        user_id: int,
        submission_url: str,
    ) -> bool:
        """Uživatel hlasuje za submission v aktivní výzvě skupiny."""
        key = str(group_id)
        g = self._groups.get(key)
        if not g or not g.get("challenge"):
            return False

        challenge = GroupChallenge.from_dict(g["challenge"])
        if not challenge.active or challenge.is_expired():
            return False

        voted = challenge.vote(str(user_id), submission_url)
        if voted:
            g["challenge"] = challenge.to_dict()
            self._save()
        return voted

    # ── Leaderboard ───────────────────────────────────────────────────────

    def get_leaderboard(
        self,
        group_id: int,
        top_n: int = 10,
    ) -> List[Dict[str, Any]]:
        """Vrátí leaderboard skupiny seřazený podle výher, pak výtvorů."""
        key = str(group_id)
        g = self._groups.get(key)
        if not g:
            return []

        lb = g.get("leaderboard", {})
        entries = []
        for uid, data in lb.items():
            entries.append({
                "user_id": uid,
                "name": data.get("name", "Neznámý"),
                "creations": data.get("creations", 0),
                "wins": data.get("wins", 0),
                "total_votes": data.get("total_votes", 0),
            })

        entries.sort(key=lambda e: (e["wins"], e["creations"]), reverse=True)
        return entries[:top_n]

    # ── Stav výzvy ─────────────────────────────────────────────────────────

    def get_challenge_status(self, group_id: int) -> Optional[Dict[str, Any]]:
        """Vrátí info o aktivní výzvě ve skupině."""
        key = str(group_id)
        g = self._groups.get(key)
        if not g or not g.get("challenge"):
            return None

        challenge = GroupChallenge.from_dict(g["challenge"])
        if not challenge.active:
            return None

        return challenge.get_stats()

    # ── Všechny aktivní skupiny ───────────────────────────────────────────

    def get_all_active_groups(self) -> List[Dict[str, Any]]:
        """Vrátí seznam všech aktivních skupin (pro broadcast)."""
        result = []
        for key, g in self._groups.items():
            if g.get("activated_at"):
                result.append({
                    "group_id": int(key),
                    "title": g.get("title", ""),
                    "activated_at": g.get("activated_at"),
                    "challenge_active": bool(
                        g.get("challenge", {}) and
                        g.get("challenge", {}).get("active") and
                        not self._challenge_expired(g.get("challenge", {}))
                    ),
                })
        return result


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_manager: Optional[GroupManager] = None


def get_manager() -> GroupManager:
    global _manager
    if _manager is None:
        _manager = GroupManager()
    return _manager
