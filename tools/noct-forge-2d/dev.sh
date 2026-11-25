#!/bin/sh
cd "$(dirname "$0")" || exit 1
exec npx tsx tools/open-viewer.ts /viewer/
