#!/bin/bash

# Récupérer le chemin absolu du dossier contenant le testeur
TESTER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Dossier d'installation des exécutables locaux
BIN_DIR="$HOME/.local/bin"

DEST_CODETEST="$BIN_DIR/codetest"
DEST_VERIF="$BIN_DIR/check_valhell"
DEST_CHECKER="$BIN_DIR/checker"

echo "🗑️  Suppression des commandes globales dans $BIN_DIR..."
rm -f "$DEST_CODETEST"
rm -f "$DEST_VERIF"
rm -f "$DEST_CHECKER"

echo "🗑️  Suppression du dossier du testeur ($TESTER_DIR)..."
# On se place ailleurs pour pouvoir supprimer le dossier courant
cd "$HOME" || exit
rm -rf "$TESTER_DIR"

echo -e "\033[0;32m✅ Désinstallation terminée avec succès. Le testeur a été entièrement supprimé !\033[0m"
