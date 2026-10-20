# Baseline Reference Maps Contract

Desktop ORB baseline maps are recovery scaffolds, not action plans.

The active pointer doctrine remains:

```text
observe live environment -> resolve target -> act -> verify
```

Baseline maps are used only when live confidence drops, the ORB loses orientation, OCR/UI Automation returns partial evidence, or a high-frequency application needs a fast starting hypothesis.

## Doctrine

- The live observation is the source of truth.
- Baseline maps are priors, not absolute coordinates.
- A baseline map must be reconfirmed against the active screenshot/window before it can guide pointer motion.
- A baseline map may restore orientation, but it may not authorize click, type, select, open, purchase, submit, or destructive actions.
- Any side-effect action still routes through TAMP planning, confidence scoring, and operator review.

## Recovery Loop

```text
confidence drops or target is lost
-> choose matching baseline map
-> reconfirm major regions
-> rebuild temporary scene map
-> re-resolve target
-> continue through TAMP
```

Example browser recovery:

```text
Expected target in browser viewport.
Cannot verify it.
Use browser baseline map.
Reconfirm address bar, tab strip, and viewport.
Inspect active page again.
Rebuild temporary scene.
Continue.
```

Example File Explorer recovery:

```text
Lost target file row.
Use File Explorer baseline map.
Reconfirm navigation pane, file list, and sort region.
Re-scan visible filenames and dates.
Recover the target.
Continue.
```

## Required Baseline Families

- `chrome`
- `edge`
- `firefox`
- `file_explorer`
- `settings`
- `windows_common_dialog`
- `windows_file_dialog`

Additional maps may be added for high-frequency system programs.

## Browser Reference Regions

At minimum, browser baseline maps must include:

- `tab_strip`
- `new_tab`
- `back`
- `forward`
- `refresh`
- `address_bar`
- `downloads`
- `browser_menu`
- `bookmarks_bar`
- `page_viewport`
- `permission_dialog`
- `file_upload_dialog`
- `save_download_prompt`

## File Explorer Reference Regions

At minimum, File Explorer baseline maps must include:

- `navigation_pane`
- `address_breadcrumb_bar`
- `search_box`
- `file_list_pane`
- `details_columns`
- `sort_controls`
- `toolbar`
- `context_menu`
- `preview_pane`
- `common_folders`
- `open_save_dialog_variants`

## Map Coordinates

Baseline coordinates are normalized ratios in the owning window frame:

```json
{
  "x": 0.0,
  "y": 0.0,
  "width": 1.0,
  "height": 1.0
}
```

The pointer runtime must resolve normalized window regions into current `virtual_desktop` coordinates using the latest active window bounds and display map.

## Confidence Rules

- `confidence >= 0.85`: baseline confirms live observation.
- `0.60 <= confidence < 0.85`: baseline may guide pointer hover or explanation.
- `confidence < 0.60`: baseline may only guide observation and re-scan.

Baseline confidence cannot exceed live observation confidence. A baseline match can improve orientation, but not override failed verification.

## Storage

Canonical seed maps live in:

```text
R:\Orb_Assistant_Desktop\mcp\orb_desktop_mcp\orb_pointer\baseline_maps\
```

Runtime temporary scene maps live in:

```text
R:\Orb_Assistant_Desktop\mcp\orb_desktop_mcp\orb_pointer\state\
```

Do not store personal document contents, emails, browser history, passwords, encrypted stores, cloud account content, or financial data in baseline maps.
