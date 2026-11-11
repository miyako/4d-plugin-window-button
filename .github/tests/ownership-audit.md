# Native ownership audit

## Provenance and complete inventory

Baseline: `87c2225c323659fb22fcb409dce617959b130808`. Canonical guidance was read
through the GitHub contents API from
`miyako/skills/4d-skills/skills/4dplugin/SKILL.md` at immutable
`e6b492fcb81e5e1a7f7db723594b420e63bf6eb9`.
The bundled SDK implementation says `rev : v14`; its headers say `rev : v13`.
These are file labels, not a verified upstream SDK release identifier.
No SDK engine implementation or ABI/API header is modified.

All tracked native production implementations are `4DPlugin.cpp`,
`4D Plugin API/4DPluginAPI.c` and the following 16 `Classes/*.cpp`, each with a
corresponding header. The Xcode Sources phase and both Visual Studio projects
include all 18 implementations (Debug/Release, Win32/x64 in the VS projects).
There are no additional dormant/uncompiled tracked native implementations;
compiled membership is not public-command reachability.

| Wrapper in `4D Plugin API/Classes` | Lifetime and disposition |
|---|---|
| `ARRAY_BOOLEAN` | Owns `CboolArray*`; prohibit implicit shallow copy |
| `ARRAY_DATE` | Owns `CDateArray*`; prohibit wrapper copy, preserve contained `C_DATE` value copies |
| `ARRAY_INTEGER` | Owns `CShortArray*`; prohibit implicit shallow copy |
| `ARRAY_LONGINT` | Owns `CIntArray*`; prohibit implicit shallow copy |
| `ARRAY_REAL` | Owns `CDoubleArray*`; prohibit implicit shallow copy |
| `ARRAY_TEXT` | Owns `CUTF16StringArray*`; independently copies borrowed input strings; transfers output allocations on accepted assignments; prohibit wrapper copy |
| `ARRAY_TIME` | Owns `CIntArray*`; prohibit implicit shallow copy |
| `C_BLOB` / internal `CBytes` | Wrapper owns `CBytes*`; prohibit wrapper copy; internal STL vector remains independently copyable |
| `C_DATE` | Scalar date fields; unchanged |
| `C_INTEGER` | Scalar short; unchanged |
| `C_LONGINT` | Scalar int; used by both public commands; unchanged |
| `C_PICTURE` / internal `CPicture` | Wrapper owns `CPicture*`; helper owns a picture reference and `CBytes*`; fix argument/return owners and converter units; prohibit shallow copies of both classes |
| `C_POINTER` | Borrows pointer; use the SDK reference constructor instead of fetching an owning value |
| `C_REAL` | Scalar double; unchanged |
| `C_TEXT` | Owns `CUTF16String*`; copy already deleted in baseline; scalar content setters and independent output storage unchanged |
| `C_TIME` | Scalar seconds; unchanged |

`CUTF8StringReplaceString` is the free string helper; it mutates value-owned
strings and is unchanged. `C_TYPES.h` declares STL aliases and platform imports.
`4DPlugin.h` declares the two handlers. `4D Plugin_Prefix.pch` imports Carbon.
The SDK `4DPluginAPI.def` exports `FourDPackex`, which installs `gCall4D` and
calls `PluginMain`, then the actual dispatcher.

Both root and bundled resource manifests declare exactly
`WINDOW SET ENABLED(&L;&L;&L)` and `WINDOW Get enabled(&L;&L):L`.
They use only scalar longints, not strings, arrays, pictures, objects or
collections. Both exports instantiate only `C_LONGINT`. The other helpers are
compiled infrastructure dormant from these exports. README documents macOS-only
behavior; tracked VS project membership is not evidence of a working Windows
branch. This audit does not claim Windows compilation or a 4D crash reproduction.
There are no object/collection getter surfaces in these wrappers or legacy SDK;
the harness reports those owner categories as **n/a**, not zero tested owners.

Exact protected bundled SDK Git blobs, verified before each harness build:

| File in `4D Plugin API` | Git blob |
|---|---|
| `4DPluginAPI.c` | `29788ed041effaf67269ccd93f971e8aee2ce5f8` |
| `4DPluginAPI.h` | `9054b45ffc7ff6f5b8d57529a3788a55d977b314` |
| `EntryPoints.h` | `730f2f77ff2713fb2fe4b7d6562baeedf5f664cb` |
| `Flags.h` | `10a83185333dac06a62dda61b9f9428243d1e2ee` |
| `PrivateTypes.h` | `77053dc0c0a3718d2d3b6f158371a6af78c6ae66` |
| `PublicTypes.h` | `2bb392e73e9c556c274fe0a75b3a6b83e310b77c` |
| `4DPluginAPI.def` | `996ecc4ab11ad165de9192eba2e7478db141c757` |

Relevant baseline wrapper implementation blobs: `C_PICTURE.cpp`
`73da2f1a502863d0c06638092f4d6f455e21021d`; `C_POINTER.cpp`
`b2bcbc66a4481a4b9b1d08e09dcbe277eb621b10`; `ARRAY_TEXT.cpp`
`534855e0959020ce9a66cef08f8434799c174495`; `C_TEXT.cpp`
`45ea6432dff52b681a5c6a7cea58ad5fc15df66b`; `C_BLOB.cpp`
`f682e22febeeaebe98b2749b66a6f38a650b8ce6`.
Every remaining original file is recoverable by the baseline SHA. The same
final harness obtains baseline production sources with path-limited
`git archive`, never extracting the 4D database, user preferences or binaries.
Engine harness prior art was read via API at
`miyako/4d-plugin-virtual-key@255b85d1ff69657f432de80f3aa499527d53f077`;
the window/Carbon dispatcher stubs and assertions are specific to this target.

## Exact source contracts and changes

Line references below are to the immutable baseline `4DPluginAPI.c`.

| SDK function | Contract and consequence |
|---|---|
| `PA_CreateUnistring`, 244; `PA_DisposeUnistring`, 252 | Creation forwards UTF-16 content; disposal forwards the owned descriptor and zeros it |
| `PA_SetUnistring`, 263; `PA_ReturnString`, 2262 | Engine-backed content replacement, unlike shallow array assignment; scalar wrapper output remains independent |
| `PA_CreatePicture`, 380; `PA_DuplicatePicture`, 447 | Creation owns a reference; retainOnly=1 forwards retain (engine parameter zero), as the SDK comment states |
| `PA_GetPictureVariable`, 3730 | Borrows from the variable; retain before clearing its owning argument |
| `PA_CreateVariable`, 3523 | Allocates initial empty picture/string/array owners; shallow setters do not release these |
| `PA_SetStringVariable`, 3826; `PA_SetPictureVariable`, 3852 | Shallow assignment; start Undefined before adopting a distinct owner; clear exactly once or explicitly detach a borrowed/handoff value |
| `PA_ClearVariable`, 3947 | Engine-backed variable cleanup, also resets the SDK error |
| `PA_GetStringInArray`, 4266 | Borrowed element alias; `ARRAY_TEXT` copies content before any array mutation |
| `PA_SetStringInArray`, 4444 | Unicode kind, non-null handle, index zero through count inclusive and non-null descriptor required; accepted assignment disposes old value then shallow-transfers; rejection retains caller ownership |
| `PA_ConvertCharsetToCharset`, 4776 | Comment explicitly specifies returned bytes; capacity forwarding also uses bytes; divide by `sizeof(PA_Unichar)` for UTF-16 units |
| `PA_ExecuteCommandByID`, 5257 | Success returns an owning variable; allocation failure can leave raw fType=0; failed engine return may be unspecified; capture error before kind checks or cleanup |
| `PA_GetVariableKind`, 3681 | Normalizes raw zero to string; cannot establish ownership of an unspecified failure |
| `PA_SetVariableOrFieldReference`, 3923 | Exact scope/reference kinds `{26,9,35,13}` and metadata; no owning value getter needed |

`fromFileAtPath` previously assigned its path over an allocated empty string,
disposed the path alias, then cleared the same path again. The picture output
argument was never cleared. Now the path argument starts Undefined, owns its
path until one clear, and `setPicture` retains the output before its argument
is cleared. `setBytes` releases the creation reference after `setPicture` retains.

`createCopy` now converts the byte result to code units. Copy/gray/size/thumbnail
input arguments immediately shallow-assigned start Undefined instead of
abandoning empty picture owners. Existing retained copy/gray handoffs and
detached borrowed size/thumbnail inputs are preserved.

All five command helpers use a local helper which captures `PA_GetLastError`
immediately, clears only a successful return and never inspects/clears an
unspecified failed return. There is no new exception, worker throw, error
channel or success-shaped fallback. Legacy command failure behavior remains:
path can adopt its initial empty output; copy/gray can return their retained
input; size reads its initialized zero arguments; thumbnail can return its
initial empty picture. These are existing failure-reporting gaps, not promises
of successful conversion. Known argument owners are cleaned independently of
the synchronous command's success.

`C_POINTER::getVariable` previously fetched an owning value, copied its payload
union as reference metadata and leaked it. Its variable-reference branch now
calls the exact SDK helper; the field branch stays unchanged.

Ten heap-owning types had implicit copy construction/assignment. Named baseline
sanitizer probes demonstrate use-after-free, not inference from pointer syntax.
The fixed types delete copy/assignment, following baseline `C_TEXT` prior art.
There are no production copy calls of these types; this is a latent API hazard,
not a demonstrated exported-command crash. Full actual-consumer compilation
preserves `ARRAY_DATE`'s required copies of value-owned `C_DATE`. Only the
`CPicture` copy probe pins an extra picture reference to isolate the raw
`CBytes` double-delete from earlier duplicate picture-release detection.

## Reproducible synthetic evidence

Run on macOS with installed Apple clang:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 .github/tests/test_ownership.py
```

`OWNERSHIP_LOG=/absolute/path/results.json` retains leaf arguments, exit status,
stdout and sanitizer diagnostics. The same final tests compile fixed actual
sources and immutable baseline sources without rewriting either or replacing
SDK functions. Local compiler: Apple clang 21.0.0, arm64-apple-darwin25.6.0.
ASan/UBSan are enabled with `halt_on_error=1`. Alignment checking alone is
disabled for intentionally packed SDK structs. LeakSanitizer is disabled on
macOS; explicit allocation/reference maps require zero string/picture/handle
balances for every passing leaf.

| Named leaf group | Cases per source | Fixed | Baseline |
|---|---:|---|---|
| Path/copy with ASCII, BMP, supplementary and empty text; allocated/null engine empties | 16 | Pass | Path double cleanup/extra ref; ASCII copy ASan heap-buffer-overflow; other copy owner imbalance |
| Bytes/gray/size/thumbnail | 4 | Pass | Creation ref/abandoned/returned owners |
| Array transfer, copied getter, churn, replace, shrink, clear, Undefined output, type/index/null rejection | 2 | Pass | Pass controls |
| Scalar content setter and independent post-wrapper output lifetime | 8 | Pass | Pass controls |
| Five picture helpers x handle/command failure x raw-zero/poisoned return kind | 20 | Pass | Double cleanup or abandoned owners |
| SDK failure predicates | 1 | Pass | Pass control; resize inconsistency, not OOM certification |
| Five helpers x successful Undefined/string/picture return | 15 | Pass | Leaked/doubly cleared owners |
| Pointer variable reference, all four scopes | 1 | Pass | Fetches owning value |
| Pointer field metadata | 1 | Pass | Pass control |
| Ten owning class copy probes | 10 | Noncopyable | ASan heap-use-after-free |
| Existing `C_TEXT` noncopy / value and borrowed type copyability | 2 | Pass | Pass controls |
| Actual modern and legacy Mac dispatchers | 2 | Pass | Pass controls |
| **Total** | **82** | **82 pass** | **66 expected defects, 16 passing controls** |

For each text fixture the harness verifies exact UTF-16 content, units and
terminator, converter byte capacities and counts. Supplementary text is a
surrogate pair. Array zero is intentionally covered because this exact SDK
accepts it. Replacement churn and final clear detect duplicate or stale owners.
Picture outputs/parameters survive wrapper destruction with exact independent
reference counts. Successful command returns cover Undefined/string/picture;
failed returns include poisoned pointers and raw kind zero.

The full SDK, all 16 wrappers and actual dispatcher are compiled under a
force-included platform boundary before any leaf executes. `NSWindow`, button,
URL and image objects are synthetic `NSObject` subclasses. Carbon window calls,
URL functions and logging are replaced. Only in-memory Foundation/CF string
conversion is real. The SDK's graphics-context scale/translate imports are also
replaced with fatal unexpected-call stubs. Unknown engine selectors/handle operations are fatal;
unknown Objective-C methods are compile errors. An `nm -u` import gate rejects
real UI/window/event/keyboard/input/process/file/image APIs and unapproved
CoreFoundation/Cocoa class imports before running either executable.

Both dispatcher variants cover close/minimize/zoom, document-edited/default
attributes (including -1/99), both enabled values, invalid-window no-op/zero,
and unknown selector. Each makes exactly 26 synthetic window lookups and 24
synthetic setter/getter calls. Legacy branching is forced only for the actual
dispatcher after loading unchanged SDK headers, preserving the SDK's 64-bit
layout. This exercises the actual Carbon branch under synthetic types; it is
not a native 32-bit ABI or Windows test. No real window, UI, input, image, path,
file, database, process or user-data operation is dispatched.

## Build safety and concrete limits

All existing workflows/scripts and project phases were read before compilation.
`bump-version.yml` and `release.yml` are manual-dispatch only. Xcode's Deployment
shell phase signs, packages and submits notarization; its Sources, Headers,
Resources, CopyFiles, Frameworks and Rez phases also belong to the real bundle
build. Neither Xcode nor MSBuild is invoked. No existing workflow, project,
manifest, version, dependency or binary changes. No signing, release/tag,
notarization, packaging, manual dispatch or rerun is performed.

The new read-only `Native ownership` workflow runs only on relevant-path pushes
to the exact audit branch `miyako-window-button-ownership` and `master`. It uses
`macos-latest` and full Git history for the immutable baseline archive. It runs
only the unsigned isolated regression, without artifact upload/publication.

Deferred, not silently certified:

- The SDK's `PA_ResizeArray` updates its logical count despite failed physical
  allocation. The harness demonstrates this and repairs only its synthetic
  descriptor for cleanup. Real wrapper OOM/failure preservation cannot be
  certified from successful-path tests; no protected SDK rewrite is attempted.
- `CBytes::toParamAtIndex` disposes its prior handle before allocation and has
  unchecked allocation/lock failures. This is a distinct dormant blob failure
  preservation issue, not corrected by the string/picture fix.
- The SDK does not state ownership of successful `PA_GetPictureData` metadata.
  The shim only supplies an immediate enumeration error with poisoned unused
  output. Successful enumeration/loading and its metadata disposal remain
  unverified; adding disposal without a safe contract could invalidate aliases.
- Real engine allocation failure, converter failure/oversized input, callback
  argument mutation on failure and all native host/ABI behavior remain outside
  this synthetic evidence. Existing error propagation gaps are documented above.
- No 4D host is launched and no Windows/4D crash is reproduced.
