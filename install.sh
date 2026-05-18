#!/bin/bash

# Récupérer le chemin absolu du dossier contenant le testeur
TESTER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Dossier d'installation des exécutables locaux
BIN_DIR="$HOME/.local/bin"

DEST_CODETEST="$BIN_DIR/codetest"
DEST_VERIF="$BIN_DIR/check_valhell"
DEST_CHECKER="$BIN_DIR/checker"

VERIF_PATH="$TESTER_DIR/verif.py"
CHECKER_PATH="$TESTER_DIR/checker.py"
TESTER_PATH="$TESTER_DIR/tester.py"

# Créer le dossier s'il n'existe pas
mkdir -p "$BIN_DIR"

# =========================
# 🚀 INSTALL codetest
# =========================
cat << EOT > "$DEST_CODETEST"
#!/bin/bash
# Wrapper global pour le testeur principal

TARGET="\${1:-.}"

if [ "\$#" -gt 0 ]; then
    shift
fi

python3 "$TESTER_PATH" "\$TARGET" "\$@"
EOT
chmod +x "$DEST_CODETEST"

# =========================
# 🔍 INSTALL check_valhell
# =========================
cat << EOT > "$DEST_VERIF"
#!/bin/bash
TARGET="\${1:-.}"

if [ ! -f "$VERIF_PATH" ]; then
    echo "❌ verif.py introuvable : $VERIF_PATH"
    exit 1
fi

python3 "$VERIF_PATH" "\$TARGET"
EXIT_CODE=\$?

if [ \$EXIT_CODE -eq 0 ]; then
    echo "🎉 Aucun problème détecté"
else
    echo "💥 Problèmes détectés"
fi

exit \$EXIT_CODE
EOT
chmod +x "$DEST_VERIF"

# =========================
# 🤖 INSTALL checker
# =========================
cat << EOT > "$DEST_CHECKER"
#!/bin/bash
TARGET="\${1:-.}"

if [ ! -f "$CHECKER_PATH" ]; then
    echo "❌ checker.py introuvable : $CHECKER_PATH"
    exit 1
fi

cd "\$TARGET" || exit 1
python3 "$CHECKER_PATH"
EOT
chmod +x "$DEST_CHECKER"

# =========================
# ✅ FIN
# =========================
echo -e "\033[0;32m✅ Tous les testeurs installés avec succès !\033[0m"
echo -e "Les commandes suivantes sont maintenant disponibles :"
echo -e "  \033[1;36mcodetest\033[0m        (pour lancer le testeur de base)"
echo -e "  \033[1;36mcheck_valhell\033[0m   (pour analyser les logs valgrind/helgrind)"
echo -e "  \033[1;36mchecker\033[0m         (pour lancer tous les tests avec le dashboard)"
echo -e ""

# Vérifier si le dossier est dans le PATH
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo -e "\033[0;33m⚠️  ATTENTION :\033[0m Le dossier $BIN_DIR n'est pas dans ta variable \$PATH."
    echo -e "Ajoute cette ligne à la fin de ton ~/.zshrc ou ~/.bashrc :"
    echo -e "\033[1;33mexport PATH=\"\$HOME/.local/bin:\$PATH\"\033[0m"
    echo -e "Puis relance ton terminal ou fais un \033[0;33msource ~/.zshrc\033[0m"
fi
