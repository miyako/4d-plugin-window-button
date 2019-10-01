# 4d-plugin-window-button
Control the state of standard window buttons: close, zoom, miniaturise

### Platform

| carbon | cocoa | win32 | win64 |
|:------:|:-----:|:---------:|:---------:|
|<img src="https://cloud.githubusercontent.com/assets/1725068/22371562/1b091f0a-e4db-11e6-8458-8653954a7cce.png" width="24" height="24" />|<img src="https://cloud.githubusercontent.com/assets/1725068/22371562/1b091f0a-e4db-11e6-8458-8653954a7cce.png" width="24" height="24" />|||

### Version

<img src="https://cloud.githubusercontent.com/assets/1725068/18940649/21945000-8645-11e6-86ed-4a0f800e5a73.png" width="32" height="32" /> <img src="https://cloud.githubusercontent.com/assets/1725068/18940648/2192ddba-8645-11e6-864d-6d5692d55717.png" width="32" height="32" />

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
