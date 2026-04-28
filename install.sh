#!/bin/bash

# Récupérer le chemin absolu du dossier contenant le testeur
TESTER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Dossier d'installation des exécutables locaux
BIN_DIR="$HOME/.local/bin"
DEST="$BIN_DIR/codetest"

# Créer le dossier s'il n'existe pas
mkdir -p "$BIN_DIR"

# Créer le script wrapper
cat << EOF > "$DEST"
#!/bin/bash
# Wrapper global pour le testeur de Codexion

# Si aucun argument n'est fourni, on utilise le dossier courant (.)
TARGET="\${1:-.}"

# Si un argument a été consommé comme target, on décale les arguments restants
if [ "\$#" -gt 0 ]; then
    shift
fi

python3 "$TESTER_DIR/tester.py" "\$TARGET" "\$@"
EOF

# Rendre le script exécutable
chmod +x "$DEST"

echo -e "\033[0;32m✅ Testeur installé avec succès !\033[0m"
echo -e "Tu peux maintenant lancer la commande \033[1;36mcodetest\033[0m depuis n'importe quel dossier."
echo -e "Par exemple :"
echo -e "  \033[0;36mcodetest .\033[0m                        (pour tester le dossier actuel)"
echo -e "  \033[0;36mcodetest /path/to/codexion\033[0m        (pour tester un dossier spécifique)"
echo -e "  \033[0;36mcodetest /path/to/codexion/bin\033[0m    (pour tester un exécutable)"

# Vérifier si le dossier est dans le PATH
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo -e "\n\033[0;33m⚠️  ATTENTION :\033[0m Le dossier $BIN_DIR n'est pas dans ta variable \$PATH."
    echo -e "Ajoute cette ligne à la fin de ton ~/.zshrc ou ~/.bashrc :"
    echo -e "\033[1;33mexport PATH=\"\$HOME/.local/bin:\$PATH\"\033[0m"
    echo -e "Puis relance ton terminal ou fais un \033[0;33msource ~/.zshrc\033[0m"
fi
