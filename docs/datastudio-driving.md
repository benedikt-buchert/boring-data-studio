# Driving Data Studio and Apps Script through the Chrome MCP

Snapshots of the report editor cost ~10k tokens each. Drive with `evaluate_script` and the selectors below; snapshot only when a uid is required (chart-tile clicks). Screenshots: jpeg quality 40.

## Prerequisites
- The MCP Chrome profile is separate from the user's browser: the user must sign in to Google there once. A stale MCP Chrome instance blocks `list_pages`; the user closes it (the sandbox refuses `kill`).
- The API must be public HTTPS; see `dev-loop.md` for the tunnel. Data Studio caches a failed query per chart until the chart config or the data source URL changes (LS-52): after a tunnel drop, re-apply the data source URL, then reload the report.

## Apps Script editor
- Set file contents with `monaco.editor.getModels()` → `.setValue(code)`; models are `file_1.js` (Code.gs) and `file_0.json` (manifest, after enabling "Show appsscript.json" in Project settings). Save with `Meta+s`; saved when the "Save project to Drive" button is disabled.
- The head deployment ID (Deploy → Test deployments) is the `connectorId`. Direct link: `https://lookerstudio.google.com/datasources/create?connectorId=<id>&connectorConfig=<urlencoded JSON>`.
- Code changes to the head deployment are live immediately; no redeploy.

## Report editor selectors (verified 2026-11-14)
- Toolbar buttons: `button[aria-label="Add a chart"|"Add a control"|"Text"|"Theme and layout"|"Previous page"]`; the `Page` menu button matches by `textContent`. New page: `Page` → menuitem `New page`.
- Chart tiles: `preset-preview[aria-label="Table"|"Scorecard"|"Time series chart"|"Bar chart"]`; click its `closest('[role=button]')` with the pointer sequence `pointerdown, mousedown, pointerup, mouseup, click` (a bare `.click()` does not arm the tool).
- Placing: dispatch a `pointermove` at the target, then the pointer sequence on `document.elementFromPoint`; the target must be `REGION-DRAWING-HANDLER` (a `DIV.file-catcher` means nothing was armed).
- Components: `.cdk-drag.lego-component-repeat`; identify by `innerText`, select by firing the pointer sequence on `elementFromPoint(rect.x+12, rect.y+8)`. Iframes (time series, bar) have empty text.
- Properties panel remembers the last tab: click `[role=tab]` "Setup" after selecting a component, or no chips exist.
- Chips: `.common-chip` with `.display-name` (filter out `.closest('.cdk-overlay-container')` to get panel chips). Click the display name → picker opens in `.cdk-overlay-container`; pick the last `.common-chip` whose display name matches. "Add metric" is found by `textContent`. Chip edit icon: hover (`mouseenter`) then `.edit-icon`; the data-type button's text is `Date arrow_drop_down`; menus are `[role=menuitem]` ("Date and Time" → "Year Month").
- Switches: `[role=switch][aria-label="Show summary row"]`, check `aria-checked`.
- Field picker lists are virtualized: type the field name into the focused search input (`execCommand('insertText', ...)`) before picking.
- Controls (`Add a control` → menuitem `Date range control` / `Drop-down list`) place like charts; their field is the first panel chip. Controls only open in **View** mode; in edit mode a click selects them.
- Refresh all charts: `Control+Shift+E` via `press_key`; a page reload also works. Error details: click the leaf element with text `See details`, read `[role=dialog]`, close with its `OK`.
- Keyboard nudge of a selected component: `Shift+ArrowUp` (real key press; synthetic drags do not move components).
- Themes: tiles are leaf elements with the theme name inside `[class*="theme"]` (Default, Edge, Constellation, Groovy, Lagoon, Simple, Simple Dark).
- Text box: arm `Text`, place, then `document.execCommand('insertText', false, ...)` into the focused `.ng2-textbox-editor`.
- Data source page: `Edit Connection` (text match) → textbox uid from a snapshot → `Reconnect` → dialog `Apply`. `REFRESH FIELDS` (text match) → dialog `Apply`.

## Reading results
Dump `{page, components: [...].map(e => e.innerText)}` once and verify offline with `prototype/verify_dashboard.py`; do not read values from screenshots.

## Timing tests
- Data Studio waits about 300 s for getData (E-37). To re-test, set `U16_DELAY_MS` in Code.gs; read durations on the Apps Script Executions page (`/executions`), which records start time, duration and status per call.
- Free serveo sessions expire after about 10 minutes; anything longer needs a stable tunnel (O-08) or must avoid the tunnel (as the U-16 test does).
