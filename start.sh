#!/usr/bin/env bash
cd "$(dirname "$0")"
if ! command -v node >/dev/null 2>&1; then echo "Falta Node.js 18+: https://nodejs.org"; exit 1; fi
node server.js
