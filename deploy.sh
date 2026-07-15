#!/usr/bin/env bash
# Device Pulse - one-shot deploy to GitHub.
#
# Usage (run from inside the device-pulse folder, in Git Bash):
#     bash deploy.sh
#     bash deploy.sh "your commit message"      # optional custom message
#
# Safe to run repeatedly: it initialises git only if needed, sets the remote
# only if missing, and pushes your current files to the repo.

set -e

REPO_URL="https://github.com/AshwiniValimbe/Hackecelarate2026.git"
BRANCH="main"
MSG="${1:-Update Device Pulse}"

# --- sanity check: are we in the project folder? --------------------------
if [ ! -f "app.py" ] || [ ! -d "device_pulse" ]; then
  echo "ERROR: run this from inside the device-pulse folder (the one with app.py)."
  echo "Current folder: $(pwd)"
  exit 1
fi

# --- git identity (only sets if not already configured) -------------------
if [ -z "$(git config --global user.email)" ]; then
  git config --global user.email "ashwini@example.com"
fi
if [ -z "$(git config --global user.name)" ]; then
  git config --global user.name "Ashwini"
fi

# --- init repo if this folder isn't one yet -------------------------------
if [ ! -d ".git" ]; then
  echo "> Initialising git repository..."
  git init
fi

git branch -M "$BRANCH"

# --- connect the remote (add if missing, else update the URL) -------------
if git remote | grep -q "^origin$"; then
  git remote set-url origin "$REPO_URL"
else
  git remote add origin "$REPO_URL"
fi

# --- stage, commit, push --------------------------------------------------
echo "> Staging files..."
git add .

if git diff --cached --quiet; then
  echo "> No changes to commit."
else
  echo "> Committing: $MSG"
  git commit -m "$MSG"
fi

echo "> Pushing to $REPO_URL ($BRANCH)..."
git push -u origin "$BRANCH" --force

echo ""
echo "Done. Refresh https://github.com/AshwiniValimbe/Hackecelarate2026 to see your files."
