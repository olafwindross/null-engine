# 🎮 NULL ENGINE

**Telegram bot pro generování AI her pomocí lokálního modelu (Ollama / Mistral).**

NULL Engine přijímá TON platby od uživatelů, generuje unikátní textové hry
pomocí lokálního AI modelu a publikuje je na Telegraph. Přijaté TON jsou
automaticky swapovány na USDT (BEP-20) a odeslány na Skrill deposit adresu.

---

## 📦 Instalace

```bash
# 1. Naklonujte nebo stáhněte projekt
cd null_engine

# 2. Spusťte instalační skript
chmod +x install.sh
./install.sh
```

Skript automaticky:
- Nainstaluje **Python 3.10+** (pokud chybí)
- Nainstaluje **Ollama** (lokální LLM runtime)
- Stáhne model **mistral** (`ollama pull mistral`)
- Nainstaluje všechny **Python závislosti** (`pip install -r requirements.txt`)

---

## ⚙️ Konfigurace

Otevřete soubor `config.yaml` a vyplňte všechny položky označené `[VYPLŇTE]`:

| Položka | Popis |
|---|---|
| `telegram_bot_token` | Token bota od [@BotFather](https://t.me/BotFather) |
| `admin_chat_id` | Vaše Telegram uživatelské ID |
| `ton_address` | TON adresa pro příjem plateb |
| `skrill_deposit_address` | USDT BEP-20 adresa napojená na Skrill |
| `fixedfloat_api_key` | API klíč z [FixedFloat](https://fixedfloat.com) |
| `changenow_api_key` | API klíč z [ChangeNow](https://changenow.io) (volitelné) |

---

## 🚀 Spuštění

```bash
# Aktivace virtuálního prostředí (pokud bylo vytvořeno)
source .venv/bin/activate

# Spuštění bota
python null_engine.py

# Volitelně: samostatný swap monitor
python swap_to_skrill.py
```

---

## 🔧 Jak to funguje

1. Uživatel pošle TON na monitorovanou adresu → bot detekuje platbu a vygeneruje
   na míru textovou hru pomocí lokálního modelu Mistral přes Ollama.
2. Hra se publikuje na Telegraph a odkaz se pošle uživateli zpět v Telegramu —
   současně bot sleduje TON zůstatek a při překročení 5 TON automaticky provede
   swap na USDT BEP-20 přes FixedFloat (při selhání fallback na ChangeNow).
3. Swappovaný USDT je odeslán na Skrill deposit adresu a celá transakce
   se zaznamená do `swap_log.txt` pro kontrolu.

---

## 📁 Struktura projektu

```
null_engine/
├── null_engine.py        # Hlavní bot (Telegram + AI generování)
├── swap_to_skrill.py     # Automatický TON → USDT swap monitor
├── install.sh            # Instalační skript
├── requirements.txt      # Python závislosti
├── config.yaml           # Konfigurace (vyplňte před spuštěním)
├── swap_log.txt          # Log swap operací (generováno automaticky)
└── README.md             # Tento soubor
```

---

## ⚠️ Bezpečnost

- **Nikdy** nepublikujte `config.yaml` s vyplněnými klíči.
- Uchovávejte API klíče a tokeny v bezpečí (např. v `.env` nebo secret manageru).
- Přidejte `config.yaml` do `.gitignore`.
