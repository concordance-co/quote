# Concordance Product Design Contract

This contract defines enforceable standards for product surfaces (`logs`, `playground`, `activations`) and separates product UI from marketing/brand expression.

## 1. Product vs Brand Boundary

- Brand expression belongs to shell-level treatments:
  - `.brand-shell` background/noise/scanline
  - `.site-header`
  - `.site-footer`
- Product content surfaces must stay utilitarian:
  - clear borders
  - stable hierarchy
  - high legibility
  - no decorative gradients/shadows in dense data views (especially in `ink`)

## 2. Tone System (Paper/Ink)

Paper and ink must be expressed through shared surface tokens, not hardcoded one-off colors.

Required tokens:

- `--surface-base`
- `--surface-primary`
- `--surface-elevated`
- `--surface-border`
- `--surface-border-strong`
- `--surface-text`
- `--surface-text-muted`
- `--surface-input-bg`
- `--surface-input-border`
- `--surface-overlay`
- `--surface-shadow`
- `--surface-shadow-dialog`

Rules:

- New components must consume these tokens.
- Avoid adding new direct rgba/hex pairs for paper + ink unless tokenized first.

## 3. Semantic Class Contract

Tone overrides must target semantic classes, not utility class names.

Current semantic anchors:

- `product-card`
- `panel`, `panel-header`, `panel-title`, `panel-content`
- `dialog-overlay`, `dialog-content`, `dialog-close-button`
- `ds-button`, `ds-button--*`
- `ds-badge`, `ds-badge--*`
- `ds-input`

Rule:

- If a new primitive/variant is introduced, add a semantic class hook and paper/ink rule once.

## 4. Portal Components

Portal-rendered primitives (dialogs now, popovers/dropdowns/toasts later) cannot rely on `.brand-shell` ancestry.

Rule:

- Use `body[data-shell-tone]` to propagate tone for portal content.
- Any new portal component must follow this pattern.

## 5. Ink-Mode Geometry

In `ink`, container geometry is intentionally flat:

- radius `0`
- shadows removed on data-dense containers

Rule:

- Do not introduce curved/shadow-heavy surfaces in `ink` unless explicitly approved.

## 6. Typography Roles

- Display font: page/section headings
- Sans font: body content and panel text
- Mono font: labels, metadata, tags, IDs, dense diagnostic text

## 7. Anti-Drift Rules

- Prefer semantic classes over `!important`.
- Avoid duplicate paper/ink reassertion blocks for the same selector.
- If a selector is duplicated to win cascade, convert it to tokens and remove duplication in the next pass.

## 8. Extraction Guidance

Ready for DS extraction:

- tone surface tokens
- panel primitive
- DS input contract (`ds-input`)
- table shell styling based on surface tokens

Not extraction-ready (product-specific):

- token/action domain color mappings
- log-detail tab/content composition
- playground-specific timeline/history behaviors
