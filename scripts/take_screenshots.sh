#!/usr/bin/env bash
# Navigate Popote app on emulator and capture screenshots.
# Assumes 1080x2340 screen (Pixel 5), app already installed and running.

set -euo pipefail

OUT="screenshots/android"
mkdir -p "$OUT"

cap() {
  local name="$1"
  adb exec-out screencap -p > "$OUT/$name.png"
  echo "Captured $name"
}

tap() { adb shell input tap "$1" "$2"; }
back() { adb shell input keyevent KEYCODE_BACK; }
wait() { sleep "$1"; }

# Bottom nav Y ≈ 2263 (1080x2340, nav height ~77px)
NAV_Y=2263
TAB_RECETTES=135
TAB_PLANNING=405
TAB_COURSES=675
TAB_SUCCES=945

echo "Launching app..."
adb shell am start -n com.kitchenai/.MainActivity
wait 10

# ── Home ────────────────────────────────────────────────────────────────────
cap "home"

# ── Recipe detail ────────────────────────────────────────────────────────────
# Tap first recipe card (below search bar + filter chips, ~y=620)
tap 300 620
wait 5
cap "detail"

# ── Mode Cuisine ─────────────────────────────────────────────────────────────
# Scroll down to find Mode Cuisine button, then tap it
adb shell input swipe 540 1200 540 400 800
wait 1
# Mode Cuisine button is near top of content after thumbnail
tap 540 650
wait 3
cap "cooking"

# Back to detail, then back to home
back; back
wait 2

# ── Planning ─────────────────────────────────────────────────────────────────
tap $TAB_PLANNING $NAV_Y
wait 5
cap "planning"

# ── Shopping list ─────────────────────────────────────────────────────────────
tap $TAB_COURSES $NAV_Y
wait 5
# Select first recipe
tap 300 400
wait 1
# Tap generate button (bottom)
tap 540 2100
wait 4
cap "shopping"

# ── Achievements ─────────────────────────────────────────────────────────────
tap $TAB_SUCCES $NAV_Y
wait 5
cap "achievements"

# ── Add recipe ───────────────────────────────────────────────────────────────
tap $TAB_RECETTES $NAV_Y
wait 2
# Ajouter button is in HomeScreen top bar action, approximate position
tap 1000 100
wait 3
cap "add"

echo "All screenshots captured in $OUT/"
