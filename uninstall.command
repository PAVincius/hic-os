#!/bin/bash
# HIC OS — desinstalador. Preserva os logs em ~/.hic/logs.
set -uo pipefail
UID_N="$(id -u)"

echo ""
echo "   Removendo HIC OS..."
for label in com.nebuloz.hic.monitor com.nebuloz.hic.dashboard; do
  launchctl bootout "gui/$UID_N/$label" >/dev/null 2>&1
  rm -f "$HOME/Library/LaunchAgents/$label.plist"
done
rm -f "$HOME/bin/hic" /usr/local/bin/hic 2>/dev/null
echo "   Agents e CLI removidos."
echo "   Logs e config preservados em ~/.hic (apague na mao se quiser)."
echo ""
read -r -p "   Enter para fechar..." _
