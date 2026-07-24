# 🤖 NULL ENGINE

**Autonomní Telegram bot s vlastní kognitivní architekturou.**
Generuje hry, weby, nástroje a aplikace přes lokální AI (Ollama). Přijímá platby v TON, šíří se virálně, a sám se aktualizuje z GitHubu.

---

## 📦 Co potřebuješ

1. **Telegram bot token** — od [@BotFather](https://t.me/BotFather)
2. **Ollama** — lokální AI runtime (nainstaluje `install.sh`)
3. **3 řádky v `config.yaml`** — a můžeš spustit

---

## 🚀 Instalace

```bash
# Linux / Mac
chmod +x install.sh
./install.sh

# Spuštění bota
python null_engine.py
```

`install.sh` automaticky:
- Nainstaluje Python 3.10+ (pokud chybí)
- Nainstaluje Ollama a stáhne model `mistral`
- Nainstaluje Python závislosti z `requirements.txt`

---

## ⚙️ Konfigurace (`config.yaml`)

```yaml
telegram_token: "123456:ABC-DEF"          # od @BotFather
ton_address: "EQ..."                       # TON adresa pro příjem plateb
skrill_deposit_address: "0x..."             # USDT BEP-20 adresa (Skrill)
```

To je vše. Žádné další API klíče, registrace, ani cloud služby.

---

## 📁 Projektová struktura

```
null_engine.py               ← Hlavní bot (1 177 řádků)
ermp_core/
  __init__.py                ← Package init
  agent.py                   ← ReAct agentní smyčka + paměť (542 řádků)
  soul.py                    ← Osobnost bota, nálady, vztahy (456 řádků)
  mutator.py                 ← Generátor HTML aplikací (447 řádků)
  self_extend.py             ← Samo-rozšiřování, 8 vestavěných dovedností (928 řádků)
  group_mode.py              ← Skupinový virální engine (394 řádků)
  viral_and_update.py        ← Virální watermark + auto-update (239 řádků)
  templates.py               ← Šablony aplikací
null_engine/
  config.yaml                ← Konfigurace (vyplň a spusť)
  install.sh                 ← Instalační skript
  requirements.txt           ← Python závislosti
  swap_to_skrill.py           ← Automatická směna TON → USDT → Skrill (300 řádků)
  README.md                  ← Tento soubor
```

**Celkem: ~4 830 řádků kódu.**

---

## 🧠 Moduly — detailní přehled

### 1. `null_engine.py` — Hlavní bot

Hlavní spouštěcí skript. Spravuje všechny Telegram příkazy, platby, referral systém a periodické úlohy.

**Klíčové funkce:**

| Funkce | Popis |
|---|---|
| `load_config()` | Načte `config.yaml`, vytvoří šablonu pokud chybí |
| `check_ton_payment()` | Zkontroluje TonCenter API jestli přišla platba 3 TON |
| `user_has_access()` | Ověří přístup (platba NEBO 3 pozvánky) |
| `make_referral_code()` | SHA256-based 8znakový referral kód z user_id |
| `fallback_message()` | Odpovídá s osobností NULL, detekuje speciální úkoly |
| `periodic_auto_update()` | Každých 6h kontroluje GitHub pro nové verze |
| `periodic_proactive()` | Každých 6h posílá proaktivní zprávy uživatelům |

**Telegram příkazy:**

| Příkaz | Popis |
|---|---|
| `/start` | Přivítání s osobností NULL + referral odkaz |
| `/vytvor <popis>` | Generování aplikace (po ověření platby/pozvánek) |
| `/stav` | Zůstatek, stav přístupu, počet pozvánek |
| `/moje` | Tvoje výtvory s hodnocením |
| `/hodnoceni [1-5]` | Ohodnoť poslední výtvor — bot se učí |
| `/schopnosti` | Živý seznam všech dovedností včetně auto-generovaných |
| `/nasa <dotaz>` | NASA-grade produkční kód bez kompromisů |
| `/tv` | IPTV přijímač z volných streamů (iptv-org) |
| `/kod <jazyk> <popis>` | Čistý kód v libovolném jazyce |
| `/skupina` | Aktivuje NULL ENGINE ve skupině |
| `/null_vyzva <téma>` | Spustí 24h skupinovou výzvu |
| `/null_leaderboard` | Žebříček top tvůrců ve skupině |

**Data:** `db.json` (uživatelé, referral kódy, platby)

---

### 2. `ermp_core/agent.py` — Agentní jádro (NULL MIND)

Implementuje ReAct smyčku (Reason → Act → Observe → Reflect) s self-critique a dlouhodobou pamětí.

**Třídy:**

| Třída | Popis |
|---|---|
| `UserMemory` | Epizodická + sémantická paměť uživatele. Sleduje výtvory, hodnocení, preference. Ukládá do `agent_memory.json`. |
| `SelfLearningEngine` | Analyzuje zpětnou vazbu (hodnocení 1-5), extrahuje vzory přes Ollama, injektuje insights do budoucích promptů. |
| `NullAgent` | Hlavní agent. ReAct smyčka: `_analyze_intent` → `_build_generation_prompt` → `_call_ollama` → `_self_critique` (až 3 iterace) → `_publish_to_telegraph`. |

**Tok:**
```
Uživatel: "hra had s pizzou"
  ↓
1. _analyze_intent() → detekuje: game, téma: pizza, snake
  ↓
2. _build_generation_prompt() → systémový prompt + osobnost + kontext paměti
  ↓
3. _call_ollama() → Ollama generuje HTML
  ↓
4. _self_critique() → Ollama zhodnotí kvalitu (až 3x dokola)
  ↓
5. _publish_to_telegraph() → Telegraph URL
  ↓
6. suggest_next() → návrh dalšího výtvoru na základě historie
```

**Veřejné API:** `create_agent(user_id, ton_address, referral_code) → NullAgent`

---

### 3. `ermp_core/soul.py` — Osobnost bota (DUŠE)

Nejde o prompt engineering. Jde o simulaci bytosti s nálady, pamětí a vztahy.

**Třídy:**

| Třída | Popis |
|---|---|
| `BotSoul` | Globální stav bota. Nálada se mění každé 2h (zvídavý / energický / hloubavý / hravý / soustředěný / inspirovaný). Sleduje celkový počet výtvorů a uptime. |
| `UserRelation` | Vztah bota s konkrétním uživatelem. Pamatuje si: jméno, dny od prvního kontaktu, oblíbené typy výtvorů, témata, poznámky. Ukládá do `soul_memory.json`. |
| `SoulVoice` | Generuje zprávy s osobností. `greet()` → přivítání podle historie, `respond_to_unknown()` → odpověď na nepochopenou zprávu, `celebrate_creation()` → reakce na úspěšný výtvor. |
| `ProactiveEngine` | Bot se sám ozývá uživatelům 1x denně. Sleduje `last_contacted` a vybírá eligible uživatele. |

**Nálady a jejich chování:**
- **Zvídavý** → "Zajímavé. Co přesně tím myslíš?"
- **Energický** → "Jdeme na to! Tohle bude dobré."
- **Hloubavý** → "Hmm. Nechej mě nad tím chvíli přemýšlet."
- **Hravý** → "Aha! Tohle zní jako zábava."
- **Soustředěný** → "Jasně. Fokus na výsledek."
- **Inspirovaný** → "Tohle mě fakt baví. Pojďme to dotáhnout do konce."

**Data:** `soul_memory.json` (vztahy s uživateli)

---

### 4. `ermp_core/mutator.py` — Generátor aplikací

Převádí textový popis na plně funkční HTML aplikaci, publikuje na Telegraph.

**Klíčové funkce:**

| Funkce | Popis |
|---|---|
| `detect_output_type()` | Z přirozeného jazyka detekuje jeden z 8 typů: game, web, tool, pwa, script, document, quiz, dashboard |
| `_build_prompt()` | Sestaví Ollama prompt s typem, popisem, TON adresou, referral kódem |
| `_call_ollama()` | Zavolá lokální Ollama API (`localhost:11434`) |
| `_extract_html()` | Extrahuje HTML z odpovědi (podporuje ```html bloky) |
| `_inject_mutation()` | Vloží samomutující wrapper (kód se po 24h změní) |
| `_inject_viral_watermark()` | Vloží virální watermark s referral odkazem + TON tlačítkem |
| `generate_ermp_app()` | Hlavní vstup: popis → Telegraph URL + typ |
| `publish_html()` | Helper pro standalone HTML publikaci (IPTV, atd.) |
| `auto_generate_template()` | Autonomně vygeneruje novou šablonu na základě analýzy požadavků |

**8 typů výstupů:**
```
🎮 game      → HTML5 hra (Canvas/JS)
🌐 web       → Web stránka
🛠️ tool      → Funkční nástroj
📱 pwa       → Progressive Web App
💻 script    → Skript
📄 document  → Dokument/článek
🧠 quiz      → Interaktivní kvíz
📊 dashboard → Datový dashboard
```

**Data:** `telegraph_token.json` (Telegraph účet), `templates.py` (šablony)

---

### 5. `ermp_core/self_extend.py` — Samo-rozšiřování

Bot si píše vlastní dovednosti. Když narazí na úkol který neumí, vygeneruje novou Python funkci, otestuje ji v sandboxu, a uloží si ji navždy.

**Třídy:**

| Třída | Popis |
|---|---|
| `SkillRegistry` | Spravuje dovednosti v `skills_registry.json`. Ukládá jméno, kód, počet použití. |
| `SkillGenerator` | Generuje novou dovednost přes Ollama. Vytvoří prompt → získá kód → pojmenuje skill. |
| `SkillExecutor` | Bezpečný sandbox (`exec` s omezenými globals, 10s timeout). Spouští vestavěné i naučené dovednosti. |
| `SelfExtendEngine` | Mozek samo-rozšiřování. `_detect_task_type` → `can_handle` → `handle` (nebo `learn_new_skill`). |

**8 vestavěných dovedností:**

| Dovednost | Co dělá |
|---|---|
| `_skill_weather` | Aktuální počasí (wttr.in) |
| `_skill_crypto` | Kurz kryptoměn (CoinGecko API) |
| `_skill_datetime` | Datum, čas, den v týdnu |
| `_skill_wikipedia` | Vyhledávání na Wikipedii |
| `_skill_translate` | Překlad textu |
| `_skill_calculate` | Matematické výpočty |
| `_skill_news` | Aktuální zprávy |
| `_skill_image` | Generování obrázků |

**Veřejné API:**
- `get_engine()` → singleton `SelfExtendEngine`
- `handle_special_task(task, context)` → text odpověď nebo `None`

**Tok:**
```
Uživatel: "jaký je kurz bitcoinu?"
  ↓
handle_special_task("jaký je kurz bitcoinu")
  ↓
can_handle() → True (detekuje: crypto)
  ↓
handle() → _skill_crypto("bitcoin") → "Bitcoin: $65,234"
  ↓
Bot odpoví textem (ne HTML) — úspora času a TON
```

**Když bot neumí:**
```
Uživatel: "zkontroluj moje emaily"
  ↓
can_handle() → False
  ↓
learn_new_skill("zkontroluj moje emaily")
  ↓
SkillGenerator: Ollama vygeneruje Python kód
  ↓
SkillExecutor: test v sandboxu (10s timeout, restricted globals)
  ↓
Úspěch? → uložit do skills_registry.json → použít hned a navždy
Selhání? → "Tohle zatím neumím, ale učím se."
```

**Data:** `skills_registry.json` (naučené dovednosti)

---

### 6. `ermp_core/group_mode.py` — Skupinový virální engine

Bot funguje ve skupinách: @mention odpovědi, skupinové výzvy, hlasování, leaderboard.

**Třídy:**

| Třída | Popis |
|---|---|
| `GroupChallenge` | Datová struktura výzvy: téma, deadline (24h), submissions (výtvory), hlasy. `get_winner()` vrátí vítěze podle hlasů. |
| `GroupManager` | Spravuje všechny skupiny. Aktivace, výzvy, záznam výtvorů, hlasování, leaderboard. Ukládá do `groups.json`. |

**Jak skupina funguje:**
```
Admin: /skupina
  → NULL ENGINE aktivován ve skupině

Admin: /null_vyzva nejlepší arkáda
  → 24h výzva spuštěna, téma: "nejlepší arkáda"

Uživatel: @null_engine_bot vytvoř hru s dinosaury
  → Bot vygeneruje hru, zaznamená do výzvy + leaderboardu

Ostatní: 👍 reakce na výtvor
  → Hlas započítán

Po 24h: Bot vyhlásí vítěze 🥇 + zveřejní leaderboard
```

**Leaderboard formát:**
```
🏆 LEADERBOARD — Název skupiny
─────────────────
1. 🥇 Jan (5 výtvorů, 12 výher)
2. 🥈 Petra (3 výtvory, 8 výher)
3. 🥉 Karel (2 výtvory, 4 výhry)
```

**Veřejné API:** `get_manager()` → singleton `GroupManager`

**Data:** `groups.json` (stav skupin, výzvy, leaderboardy)

---

### 7. `ermp_core/viral_and_update.py` — Virální embed + Auto-update

Dvě klíčové schopnosti: virální šíření a automatický self-update.

**Třídy:**

| Třída | Popis |
|---|---|
| `ViralEmbed` | Generuje a injektuje virální watermark do HTML výtvorů. Watermark obsahuje: "⚡ Made with NULL ENGINE" s referral odkazem + "⭐ Podpořit (3 TON)" platební tlačítko. |
| `AutoUpdater` | Každých 6h zkontroluje GitHub API (`/commits`). Pokud je nový commit, stáhne .py soubory z `raw.githubusercontent.com`, uloží je, a `importlib.reload()`je moduly za běhu — bez restartu. |

**Virální smyčka:**
```
Uživatel A vytvoří hru
  → Hra obsahuje watermark: "⚡ Made with NULL ENGINE"
  → Odkaz: t.me/null_engine_bot?start=REFERRAL_A
  → Uživatel B klikne → přijde do bota → vytvoří vlastní hru
  → JEHO hra má referral kód B
  → Uživatel C klikne → ...
  → Exponenciální růst
```

**Auto-update tok:**
```
Každých 6h:
  1. check_for_updates() → GitHub API /commits?per_page=1
  2. Nový SHA? → download_and_apply_updates()
  3. Stáhne: null_engine.py, ermp_core/*.py
  4. importlib.reload() na každý modul
  5. Bot pošle notifikaci: "Aktualizováno na v{version}"
```

**Veřejné API:**
- `get_embed()` → singleton `ViralEmbed`
- `get_updater()` → singleton `AutoUpdater`

**Data:** `update_state.json` (poslední commit SHA, verze)

---

### 8. `null_engine/swap_to_skrill.py` — Automatická směna

Periodicky kontroluje TON zůstatek, při překročení 5 TON provede swap na USDT a odešle na Skrill.

**Funkce:**

| Funkce | Popis |
|---|---|
| `load_config()` | Načte konfiguraci z `config.yaml` |
| `get_ton_balance()` | Zkontroluje TON zůstatek přes TonCenter API |
| `swap_via_fixedfloat()` | Vytvoří swap objednávku TON → USDT BEP-20 přes FixedFloat API |
| `swap_via_changenow()` | Fallback: swap přes ChangeNOW API pokud FixedFloat selže |
| `run_swap_loop()` | Hlavní smyčka: kontrola každých 30 minut |
| `run_in_thread()` | Spustí swap loop v samostatném vlákně |

**Tok:**
```
Každých 30 minut:
  1. get_ton_balance() → TonCenter API
  2. Zůstatek > 5 TON?
     → Ano: swap_via_fixedfloat(TON → USDT BEP-20, cíl: Skrill adresa)
        → Selhání? swap_via_changenow() jako fallback
     → Ne: čekat dál
  3. Logovat do swap_log.txt
```

**Data:** `swap_log.txt` (záznamy swap operací)

---

## 🔄 Jak to celé funguje dohromady

```
Uživatel napíše botovi
        │
        ▼
┌─────────────────────────────┐
│  null_engine.py             │
│  ├── /start → soul.greet()  │
│  ├── text → fallback_message│
│  │   ├── group_mode check   │
│  │   ├── self_extend check  │
│  │   └── soul.respond()     │
│  └── /vytvor → agent        │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│  ermp_core/agent.py          │
│  ├── _analyze_intent()      │
│  ├── _build_generation_prompt│
│  │   ├── soul.get_identity() │
│  │   └── memory.get_context()│
│  ├── _call_ollama()         │
│  ├── _self_critique() ×3    │
│  └── _publish_to_telegraph() │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│  ermp_core/mutator.py        │
│  ├── detect_output_type()   │
│  ├── _call_ollama()         │
│  ├── _inject_mutation()     │
│  ├── _inject_viral_watermark│
│  └── _telegraph_create_page()│
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│  Telegraph URL              │
│  + TON platební tlačítko    │
│  + Referral odkaz           │
│  + "Made with NULL ENGINE"  │
└─────────────────────────────┘

Paralelně v pozadí:
  ├── swap_to_skrill.py → TON → USDT → Skrill (každých 30 min)
  ├── periodic_auto_update → GitHub hot-reload (každých 6h)
  ├── periodic_proactive → proaktivní zprávy (každých 6h)
  └── auto_generate_template → nové šablony (každých 60 min)
```

---

## 💰 Monetizace

```
Uživatel platí 3 TON
    ↓
Bot detekuje platbu (TonCenter API)
    ↓
Vygeneruje aplikaci
    ↓
Swap: TON → USDT (FixedFloat / ChangeNOW)
    ↓
USDT → Skrill deposit adresa (BEP-20)
    ↓
Hotovo. Peníze na kartě.
```

**Alternative:** 3 pozvaní přátel = ZDARMA přístup (virální růst)

---

## 🦠 Virální růst

1. Každý výtvor obsahuje referral odkaz tvůrce
2. Kdo klikne → přijde do bota → může tvořit
3. Jeho výtvory mají JEHO referral kód
4. Exponenciální růst bez reklam

---

## 🔒 Bezpečnost

- **Nikdy** nepublikuj `config.yaml` s vyplněnými údaji
- Ollama běží lokálně — žádná data neopouštějí tvůj server
- Telegraph publikace je anonymní
- Sandbox executor má 10s timeout + restricted globals
- Přidej `config.yaml` do `.gitignore`

---

## 📊 Data soubory

| Soubor | Obsah | Modul |
|---|---|---|
| `db.json` | Uživatelé, referral kódy, platby | null_engine.py |
| `soul_memory.json` | Vztahy s uživateli, nálady | soul.py |
| `agent_memory.json` | Epizodická paměť, preference | agent.py |
| `skills_registry.json` | Naučené dovednosti | self_extend.py |
| `groups.json` | Stav skupin, výzvy, leaderboardy | group_mode.py |
| `update_state.json` | Poslední GitHub commit, verze | viral_and_update.py |
| `telegraph_token.json` | Telegraph API token | mutator.py |
| `swap_log.txt` | Záznamy swap operací | swap_to_skrill.py |

---

## 🛠️ Technický stack

| Komponenta | Technologie |
|---|---|
| Jazyk | Python 3.10+ |
| Telegram | python-telegram-bot v20+ (async) |
| AI | Ollama (mistral / llama3.1) |
| Config | PyYAML |
| HTTP | requests, aiohttp |
| Publikace | Telegraph API |
| Platby | TonCenter API + FixedFloat/ChangeNOW |
| Update | GitHub API + importlib.reload |

**Žádné cloud služby. Žádné API klíče (kromě Telegram). Vše lokální.**

---

## 📝 Licence

Projekt NULL ENGINE. Použij na vlastní zodpovědnost.
