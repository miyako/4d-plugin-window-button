![version](https://img.shields.io/badge/version-16%2B-8331AE)
![platform](https://img.shields.io/static/v1?label=platform&message=mac-intel%20|%20mac-arm&color=blue)
[![license](https://img.shields.io/github/license/miyako/4d-plugin-window-button)](LICENSE)
![downloads](https://img.shields.io/github/downloads/miyako/4d-plugin-window-button/total)

# 4d-plugin-window-button

The Window Button plugin lets you enable or disable the standard macOS window control buttons (close, minimize, zoom) and query or set the document-modified indicator on any open 4D window. This is useful for locking down the window interface during critical operations, or providing visual feedback that a document has unsaved changes.

| Command | Returns | Purpose |
|---------|---------|---------|
| [`WINDOW SET ENABLED`](#window-set-enabled) | — | Enable or disable a window button or the document-modified indicator |
| [`WINDOW Get enabled`](#window-get-enabled) | Longint | Query whether a window button or indicator is currently enabled |

**Platforms:** macOS

---

## Requirements & platform notes

- **macOS only**: This plugin operates at the Cocoa window-system level and is not available on Windows. It requires macOS 10.5+ (uses native `NSWindow` and `NSWindowButton` APIs).
- **Window reference required**: Both commands require a valid 4D window reference (obtain via `Current window` or pass an integer window ID). Passing an invalid reference results in no action (silent no-op) for setter; getter returns 0 for invalid references.
- **Return value mandated**: Even when success seems obvious (e.g., "just enable a button"), always check the result of getter commands, as they distinguish between "disabled" (0) and "enabled" (1) states.
- **Document-modified state**: The fourth button type (document-modified indicator) affects the red close button's appearance and is independent of the close button's enabled/disabled state. On macOS, this is the filled dot that appears in the close button when a document has unsaved changes.

---

## WINDOW SET ENABLED

### Syntax

```4d
WINDOW SET ENABLED ( window ; kind ; enabled )
```

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `window` | Longint | The window reference (typically `Current window` or a window ID from `Window list`) |
| `kind` | Longint | The button or indicator type (see table below) |
| `enabled` | Longint | 0 to disable, 1 to enable |
| Result | — | (no return value) |

### Button types

| Constant | Value | Description |
|----------|-------|-------------|
| `Window close button` | 0 | The red close (×) button in the window's top-left corner |
| `Window minimize button` | 1 | The yellow minimize (−) button |
| `Window zoom button` | 2 | The green zoom/maximize button |
| `Window document modified` | 3 | The document-modified indicator (red dot in close button) |

### Description

Enables or disables the specified window button or indicator. When a button is disabled, it remains visible but grayed out and non-interactive — clicking it has no effect. When the document-modified indicator is disabled, the close button loses its filled-dot appearance.

**On macOS**, disabling the close button does not prevent the user from closing the window via keyboard shortcut (Cmd+W) or the application menu — it only grays out the button itself. To prevent window closure entirely, use 4D's window-handling methods (`On Window Close` event, etc.) to intercept and block the action.

Passing an invalid window reference does nothing (no error is raised). The command assumes the window exists; if the window is closed between the time you obtain its reference and the time you call this command, the operation is silently ignored.

### Example

Disable the close button on the current window to prevent accidental closure:

```4d
WINDOW SET ENABLED(Current window; Window close button; 0)
```

Set the document-modified indicator to show that changes have been made:

```4d
WINDOW SET ENABLED(Current window; Window document modified; 1)
```

Loop through all window buttons and disable them:

```4d
For ($i; Window close button; Window document modified)
	WINDOW SET ENABLED(Current window; $i; 0)
End for
```

Re-enable all buttons once the critical operation completes:

```4d
For ($i; Window close button; Window document modified)
	WINDOW SET ENABLED(Current window; $i; 1)
End for
```

---

## WINDOW Get enabled

### Syntax

```4d
enabled := WINDOW Get enabled ( window ; kind )
```

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `window` | Longint | The window reference |
| `kind` | Longint | The button or indicator type (see button types table above) |
| Result | Longint | 0 if disabled, 1 if enabled; 0 if the window is invalid or closed |

### Description

Returns the current enabled/disabled state of the specified window button or indicator. Returns 1 if enabled, 0 if disabled.

**On macOS**, the enabled state reflects whether the button responds to user clicks. A disabled button (result = 0) is grayed out and non-functional; an enabled button (result = 1) is active and clickable.

If the window reference is invalid or the window has been closed, the command returns 0. There is no distinction between "button is disabled" and "window does not exist" — check the window's validity separately if needed using 4D's window-listing commands (`Window list`).

The document-modified indicator state is independent of the close button state — a window can have a disabled close button but an enabled document-modified indicator, or vice versa.

### Example

Check if the close button is currently enabled:

```4d
$enabled := WINDOW Get enabled(Current window; Window close button)
If ($enabled = 1)
	ALERT("Close button is active")
Else
	ALERT("Close button is disabled")
End if
```

Query the document-modified state to decide whether to show a save prompt:

```4d
$modified := WINDOW Get enabled(Current window; Window document modified)
If ($modified = 1)
	$choice := ALERT("Save changes?"; "Yes"; "No")
	If ($choice = 1)
		// Save changes
	End if
End if
```

Iterate through all buttons and collect their states:

```4d
$buttonStates := New object()
$buttonStates.close := WINDOW Get enabled(Current window; Window close button)
$buttonStates.minimize := WINDOW Get enabled(Current window; Window minimize button)
$buttonStates.zoom := WINDOW Get enabled(Current window; Window zoom button)
$buttonStates.modified := WINDOW Get enabled(Current window; Window document modified)

ALERT("Close: " + String($buttonStates.close) + "; Minimize: " + String($buttonStates.minimize))
```

---

## Error handling & troubleshooting

- **Invalid window reference does nothing**: If you pass an invalid window ID (a number that doesn't correspond to an open 4D window), the setter silently ignores the call, and the getter returns 0. Always validate window IDs using `Window list` if you're constructing them programmatically rather than using `Current window`.

- **Close button can't fully prevent window closure**: Disabling the close button via `WINDOW SET ENABLED` grays out the button visually, but users can still close the window using Cmd+W or the application menu. To prevent closure entirely, intercept the `On Window Close` event and block the action in your window's event handler.

- **Document-modified indicator state is not persistent**: The document-modified state applies only to the visual indicator (the dot in the close button). It does not affect 4D's internal document-dirty flag or trigger auto-save. Manage save state separately using 4D's document or object-locking mechanisms.

- **Button state resets on window deactivation**: The Cocoa window system may reset button visual states when windows are deactivated/reactivated by the OS. If you're relying on a specific button state persisting, reapply it if needed when the window regains focus (e.g., in an `On Getting Focus` event handler).

- **No effect on non-4D windows**: This plugin operates on 4D window objects only. It cannot enable/disable buttons on system windows or other applications' windows.

---

## Quick reference

```4d
// Disable all buttons during a critical operation
WINDOW SET ENABLED(Current window; Window close button; 0)
WINDOW SET ENABLED(Current window; Window minimize button; 0)
WINDOW SET ENABLED(Current window; Window zoom button; 0)

// Mark document as modified
WINDOW SET ENABLED(Current window; Window document modified; 1)

// Check if document is marked as modified
$modified := WINDOW Get enabled(Current window; Window document modified)

// Re-enable all buttons
WINDOW SET ENABLED(Current window; Window close button; 1)
WINDOW SET ENABLED(Current window; Window minimize button; 1)
WINDOW SET ENABLED(Current window; Window zoom button; 1)

// Disable only close button
WINDOW SET ENABLED(Current window; Window close button; 0)
```

---

## Version history

- **v1.1** (current): Fixed exception handling and null-pointer safety on all code paths. Recommended for production use.
- **v1.0**: Initial release.

For installation and build instructions, see the plugin's GitHub repository: https://github.com/miyako/4d-plugin-window-button
