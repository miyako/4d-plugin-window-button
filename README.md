![version](https://img.shields.io/badge/version-16%2B-8331AE)
![platform](https://img.shields.io/static/v1?label=platform&message=mac-intel%20|%20mac-arm%20|%20win-64&color=blue)
[![license](https://img.shields.io/github/license/miyako/4d-plugin-window-button)](LICENSE)
![downloads](https://img.shields.io/github/downloads/miyako/4d-plugin-window-button/total)

**Note**: for v17 and earlier, move `manifest.json` to `Contents`

# 4d-plugin-window-button
Control the state of standard window buttons: close, zoom, miniaturise

**deprecated**

See [4d-plugin-window-control-v2](https://miyako.github.io/2019/10/01/4d-plugin-window-control-v2.html)

### Related projects

* https://github.com/miyako/4d-plugin-window-icon
* https://github.com/miyako/4d-plugin-carbon-window-manager

## Syntax

```
WINDOW SET ENABLED (window;kind;enabled)
enabled:=WINDOW Get enabled (window;kind)
```

Parameter|Type|Description
------------|------|----
window|LONGINT|The window reference
kind|LONGINT|``Window Button Types``

### Window Button Types

```c
Window close button 0
Window minimize button 1
Window zoom button 2
Window document modified 3
```
