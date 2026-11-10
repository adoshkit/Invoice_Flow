# InvoiceFlow theme guide

## Default appearance

InvoiceFlow opens in Light mode by default. Users can switch between Light and Dark from the Appearance control in the sidebar. The included blue palette uses `#6FA6D8` as its primary accent.

## Colour format

`colours.txt` is the single editable palette file. Colours use six-digit sRGB HEX notation (`#RRGGBB`), the standard CSS/HTML colour format. The `[Dark]` and `[Light]` sections use the same token names.

## Changing the brand colour

Change `accent` in both sections. It is the single source of truth for the brand mark, selected navigation tab, radio and checkbox indicators, primary buttons, sliders, table headers, and the first chart series. The application reads the value from `colours.txt` when it starts, so restart Streamlit after editing it.

`accent_hover` controls hover/active shading. `accent_text` controls the text or icon colour placed on top of the accent fill; choose a colour with strong contrast against the accent if you change the brand colour substantially.

## Other useful tokens

- `background`: page background.
- `panel` and `panel_alt`: cards, sidebar and secondary surfaces.
- `text` and `muted`: primary and secondary typography.
- `border`: component outlines and dividers.
- `chart_2`, `chart_3`, `chart_4`: complementary chart series.
- `risk_*` and `success_*`, `warning_*`, `danger_*`: semantic status colours.

The status colours remain distinct from the brand accent so Approved, Awaiting review and Rejected remain easy to distinguish.

## Table rendering note

Read-only tables use Streamlit's native HTML table renderer rather than its canvas-based interactive grid. This makes the header and alternating row colours follow the selected palette in both themes. The invoice data and record-selection/status-management workflows are unchanged; the built-in grid-only sort/resize toolbar is not shown.