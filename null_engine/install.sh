#!/usr/bin/env bash
# ============================================================================
# NULL ENGINE – install.sh
# Instalační skript pro Linux/macOS
# ----------------------------------------------------------------------------
# Co dělá:
#   1. Zkontroluje / nainstaluje Python 3.10+
#   2. Nainstaluje Ollama (lokální LLM runtime)
#   3. Stáhne model mistral (ollama pull mistral)
#   4. Nainstaluje Python závislosti (pip install -r requirements.txt)
#   5. Vypíše instrukce pro další krok
# ============================================================================

set -e

# ── Barvy ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info()  { echo -e "${CYAN}[INFO]${NC}  $1"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ── Detekce OS ───────────────────────────────────────────────────────────────
OS_TYPE="$(uname -s)"
info "Detekovaný OS: ${OS_TYPE}"

if [[ "$OS_TYPE" == "Darwin" ]]; then
    PKG_MGR="brew"
elif [[ "$OS_TYPE" == "Linux" ]]; then
    # Detekce distribuce
    if command -v apt-get &>/dev/null; then
        PKG_MGR="apt"
    elif command -v dnf &>/dev/null; then
        PKG_MGR="dnf"
    elif command -v yum &>/dev/null; then
        PKG_MGR="yum"
    elif command -v pacman &>/dev/null; then
        PKG_MGR="pacman"
    else
        error "Nepodporovaná Linux distribuce – nenalezen apt/dnf/yum/pacman."
        exit 1
    fi
else
    error "Nepodporovaný operační systém: ${OS_TYPE}"
    exit 1
fi

info "Použitý balíčkovací manažer: ${PKG_MGR}"

# ============================================================================
# 1) Python 3.10+
# ============================================================================
echo ""
info "=== Krok 1/4: Kontrola Python 3.10+ ==="

PYTHON_CMD=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PY_VERSION="$($cmd -c 'import sys; print(float(str(sys.version_info.major)+"."+str(sys.version_info.minor)))' 2>/dev/null || echo 0)"
        if (( $(echo "$PY_VERSION >= 3.10" | bc -l 2>/dev/null || echo 0) )); then
            PYTHON_CMD="$cmd"
            ok "Python $($cmd --version) nalezen ($cmd)."
            break
        fi
    fi
done

if [[ -z "$PYTHON_CMD" ]]; then
    warn "Python 3.10+ nebyl nalezen – instaluji..."

    if [[ "$PKG_MGR" == "brew" ]]; then
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || true
        brew install python@3.12
        PYTHON_CMD="python3"
    elif [[ "$PKG_MGR" == "apt" ]]; then
        sudo apt-get update
        sudo apt-get install -y python3 python3-pip python3-venv
        PYTHON_CMD="python3"
    elif [[ "$PKG_MGR" == "dnf" || "$PKG_MGR" == "yum" ]]; then
        sudo $PKG_MGR install -y python3 python3-pip
        PYTHON_CMD="python3"
    elif [[ "$PKG_MGR" == "pacman" ]]; then
        sudo pacman -Syu --noconfirm python python-pip
        PYTHON_CMD="python3"
    fi

    # Ověření instalace
    PY_VERSION="$($PYTHON_CMD -c 'import sys; print(float(str(sys.version_info.major)+"."+str(sys.version_info.minor)))' 2>/dev/null || echo 0)"
    if (( $(echo "$PY_VERSION >= 3.10" | bc -l 2>/dev/null || echo 0) )); then
        ok "Python $($PYTHON_CMD --version) úspěšně nainstalován."
    else
        error "Instalace Pythonu selhala. Nainstalujte Python 3.10+ manuálně."
        exit 1
    fi
fi

# ============================================================================
# 2) Ollama
# ============================================================================
echo ""
info "=== Krok 2/4: Instalace Ollama ==="

if command -v ollama &>/dev/null; then
    ok "Ollama je již nainstalována ($(ollama --version 2>/dev/null || echo 'verze neznámá'))."
else
    info "Stahuji a instaluji Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
    ok "Ollama nainstalována."
fi

# Spuštění Ollama service (pokud neběží)
info "Kontrola, zda Ollama service běží..."
if ! curl -s http://localhost:11434/api/tags &>/dev/null; then
    warn "Ollama service neběží – spouštím na pozadí..."
    ollama serve &
    OLLAMA_PID=$!
    info "Čekám na start Ollama..."
    sleep 5
    if curl -s http://localhost:11434/api/tags &>/dev/null; then
        ok "Ollama service spuštěna (PID ${OLLAMA_PID})."
    else
        warn "Ollama service se nepodařilo ověřit – možná ji budete muset spustit ručně: ollama serve"
    fi
else
    ok "Ollama service již běží."
fi

# ============================================================================
# 3) Stažení modelu mistral
# ============================================================================
echo ""
info "=== Krok 3/4: Stažení modelu mistral ==="

info "Stahuji model mistral (může trvat několik minut)..."
if ollama pull mistral; then
    ok "Model mistral úspěšně stažen."
else
    warn "Stažení modelu mistral selhalo. Můžete to zkusit později: ollama pull mistral"
fi

# ============================================================================
# 4) Python závislosti
# ============================================================================
echo ""
info "=== Krok 4/4: Instalace Python závislostí ==="

if [[ ! -f "requirements.txt" ]]; then
    warn "requirements.txt nebyl nalezen v aktuálním adresáři."
    warn "Ujistěte se, že spouštíte install.sh z kořenového adresáře projektu."
else
    info "Instaluji Python závislosti..."

    # Doporučeno: virtuální prostředí
    if [[ ! -d ".venv" ]]; then
        info "Vytvářím virtuální prostředí (.venv)..."
        $PYTHON_CMD -m venv .venv
    fi

    # Aktivace venv pro tento skript
    if [[ -f ".venv/bin/activate" ]]; then
        source .venv/bin/activate
        ok "Virtuální prostředí aktivováno."
    fi

    # Upgrade pip
    pip install --upgrade pip

    if pip install -r requirements.txt; then
        ok "Python závislosti nainstalovány."
    else
        error "Instalace Python závislostí selhala."
        exit 1
    fi
fi

# ============================================================================
# 5) Instrukce
# ============================================================================
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              NULL ENGINE – instalace dokončena!               ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${CYAN}Další kroky:${NC}"
echo ""
echo -e "  1. ${YELLOW}Vyplňte config.yaml${NC}"
echo -e "     – otevřete soubor a doplňte všechny potřebné klíče a adresy"
echo -e "       (Telegram token, TON adresa, Skrill deposit adresa, API klíče, atd.)"
echo ""
echo -e "  2. ${YELLOW}Spusťte bota:${NC}"
echo -e "     ${GREEN}python null_engine.py${NC}"
echo ""
echo -e "  3. ${YELLOW}Volitelně spusťte swap monitor samostatně:${NC}"
echo -e "     ${GREEN}python swap_to_skrill.py${NC}"
echo ""
echo -e "${CYAN}Užitečné příkazy:${NC}"
echo -e "  • Ollama service:  ${GREEN}ollama serve${NC}"
echo -e "  • Seznam modelů:   ${GREEN}ollama list${NC}"
echo -e "  • Test modelu:     ${GREEN}ollama run mistral${NC}"
echo ""
echo -e "${YELLOW}Poznámka:${NC} Pokud jste použili virtuální prostředí (.venv),"
echo -e "  aktivujte jej před spuštěním: ${GREEN}source .venv/bin/activate${NC}"
echo ""
