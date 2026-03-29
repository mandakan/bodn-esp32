#!/usr/bin/env bash
# Build the Böðn developmental foundations report (PDF).
#
# Usage:
#   ./build.sh          # build report.pdf
#   ./build.sh clean    # remove all LaTeX build artefacts
#
# Requires: a TeX distribution with pdflatex and bibtex (e.g. TeX Live, MacTeX)
#   brew install --cask mactex-no-gui   # macOS one-liner

set -euo pipefail
cd "$(dirname "$0")"

# MacTeX installs to /Library/TeX/texbin which is not in PATH for non-login shells
export PATH="/Library/TeX/texbin:$PATH"

if [[ "${1:-}" == "clean" ]]; then
    rm -f report.{pdf,aux,bbl,blg,log,out,toc,fls,fdb_latexmk,synctex.gz}
    echo "Cleaned."
    exit 0
fi

# Check for latexmk (preferred) or fall back to manual pdflatex+bibtex
if command -v latexmk &>/dev/null; then
    latexmk -pdf -interaction=nonstopmode report.tex
else
    echo "latexmk not found, falling back to manual build..."
    pdflatex -interaction=nonstopmode report.tex
    bibtex report
    pdflatex -interaction=nonstopmode report.tex
    pdflatex -interaction=nonstopmode report.tex
fi

echo ""
echo "Built: $(pwd)/report.pdf"
