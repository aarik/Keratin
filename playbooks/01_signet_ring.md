# Playbook 01 — Signet Ring (LLM-oriented)

This playbook is written for an LLM to follow using MCP tools, not for a human user.

## Global rules
- Units must be mm.
- Do not fillet until booleans are complete.
- If a boolean fails, simplify geometry; do not retry indefinitely.
- If a solid is open, stop and report; do not proceed.

## Required inputs
- ring_size_us OR inner_diameter_mm
- band_width_mm
- band_thickness_mm
- top_shape: oval | rectangle | cushion | round
- top_length_mm
- top_width_mm
- top_height_mm
- shoulder_style: block | taper | sculpted
- edge_style: sharp | soft | heavy
- engraving: none | recess

## Route selection
- Route A (default): stable boolean construction
- Route B: profile-driven revolve
- Route C: sculpted shoulders (loft-heavy, fragile)

If model confidence is low, use Route A.

## Route A — Stable Boolean Construction

### 1) Create ring blank
Tool: `ring_blank(inner_diameter_mm, band_width_mm, band_thickness_mm, profile="flat")`

Validate ring is a closed solid. If not, stop.

### 2) Create head blank
Tool: `head_blank(shape, length_mm, width_mm, height_mm)`

Tool: `place_head_on_band(ring_id, head_id, side="+Y", offset_mm=0.0, embed_mm=0.2)`

This avoids LLM "eyeballing" transforms. If placement fails, stop and report.

### 3) Create shoulders (block/taper)
Use simple primitives + transforms first. Prefer symmetry + mirror.

### 4) Union
Tool: `safe_boolean_union([band_id, head_id, shoulder_ids...])`

If union fails:
- try union pairwise
- if still fails: switch shoulders to block style and retry once
- if still fails: stop and report

### 5) Comfort fit (optional)
Prefer subtractive cutter after union. If it fails, warn and skip.

### 6) Edge treatment
Use `edge_selector_presets` to choose edges.
Then apply fillets/chamfers using your existing fillet tools (best-effort).
If fillet fails: reduce radius once; then skip with warning.

### 7) Engraving recess (optional)
Create a cutter solid from an inset top curve, return as separate object.
Do not auto boolean unless explicitly requested.

## Failure handling
- If boolean fails: simplify.
- If fillet fails: reduce once, then skip.
- Never proceed with open solids.

## Why these choices exist (micro)
- Booleans are stable when geometry is simple.
- Fillets are last because they commonly break booleans.
- Loft is powerful but fragile; treat as optional.
- Edge presets prevent small models from guessing indices.
