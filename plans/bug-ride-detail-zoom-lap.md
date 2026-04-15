# Bug: Ride Detail — Lap Selection Breaks While Zoomed

**Status:** Open
**Severity:** Low — UX annoyance, no data loss
**Found:** 2026-04-15 while testing timezone changes on ride 3229 (2026-04-08 Tempo/Endurance Hybrid)

## Description

When viewing a ride detail page and zooming into the chart (e.g., dragging to select a time range), the lap selection UI still operates on the full ride timeline. Selecting a lap while zoomed either:

1. Shows nothing (the lap's time range is outside the current zoom window), or
2. Renders the lap overlay incorrectly against the zoomed axis

## Expected Behavior

Either:
- **Option A (simpler):** Selecting a lap resets the zoom to show the full ride, then highlights the selected lap
- **Option B (better UX):** Selecting a lap zooms the chart to that lap's time range, replacing the current zoom window

## Affected Components

Likely in the ride detail chart component(s) — needs investigation to identify exact files.

## Reproduction

1. Navigate to any ride with laps (e.g., a structured workout)
2. Zoom into a section of the chart by dragging
3. Click a different lap in the lap list
4. Observe: the chart view and lap highlight are out of sync
