"""Full unchanged SDK, all actual wrappers and synthetic modern/legacy Mac dispatch."""

import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
BASELINE = "87c2225c323659fb22fcb409dce617959b130808"
SDK = {
    "4DPluginAPI.c": "29788ed041effaf67269ccd93f971e8aee2ce5f8",
    "4DPluginAPI.h": "9054b45ffc7ff6f5b8d57529a3788a55d977b314",
    "EntryPoints.h": "730f2f77ff2713fb2fe4b7d6562baeedf5f664cb",
    "Flags.h": "10a83185333dac06a62dda61b9f9428243d1e2ee",
    "PrivateTypes.h": "77053dc0c0a3718d2d3b6f158371a6af78c6ae66",
    "PublicTypes.h": "2bb392e73e9c556c274fe0a75b3a6b83e310b77c",
    "4DPluginAPI.def": "996ecc4ab11ad165de9192eba2e7478db141c757",
}
WRAPPERS = {
    "ARRAY_BOOLEAN", "ARRAY_DATE", "ARRAY_INTEGER", "ARRAY_LONGINT", "ARRAY_REAL",
    "ARRAY_TEXT", "ARRAY_TIME", "C_BLOB", "C_DATE", "C_INTEGER", "C_LONGINT",
    "C_PICTURE", "C_POINTER", "C_REAL", "C_TEXT", "C_TIME",
}
NONCOPY = {
    "ARRAY_TEXT", "CPicture", "C_PICTURE", "C_BLOB", "ARRAY_BOOLEAN", "ARRAY_DATE",
    "ARRAY_INTEGER", "ARRAY_LONGINT", "ARRAY_REAL", "ARRAY_TIME",
}
FIXTURES = ("ASCII", "\u65e5", "\U0001f600", "")


def cases():
    for case in ("path", "copy"):
        for text in FIXTURES:
            for empty in ("allocated", "null"):
                yield ("picture", text, empty, 1, "none", case)
    for case in ("bytes", "gray", "size", "thumbnail"):
        yield ("picture", "", "allocated", 1, "none", case)
    for empty in ("allocated", "null"):
        yield ("arrays", "", empty)
    for text in FIXTURES:
        for empty in ("allocated", "null"):
            yield ("scalar", text, empty)
    for case in ("path", "copy", "gray", "size", "thumbnail"):
        for failure in ("handle", "command"):
            for kind in (0, 1):
                yield ("picture", "", "allocated", kind, failure, case)
    yield ("sdk-failures",)
    for case in ("path", "copy", "gray", "size", "thumbnail"):
        for kind in range(3):
            yield ("picture", "", "allocated", kind, "none", case)
    yield ("pointer", "ASCII")
    yield ("pointer-field",)
    for name in ("C_TEXT", *sorted(NONCOPY), "values"):
        yield ("traits", name)
    yield ("dispatch",)
    yield ("legacy-dispatch",)


def baseline_failure(case):
    return (case[0] in ("picture", "pointer") or
            (case[0] == "traits" and case[1] in NONCOPY))


def baseline_diagnostic(case):
    if case[0] == "traits":
        return "AddressSanitizer: heap-use-after-free"
    if case[0] == "pointer":
        return "reference construction fetched an owning value"
    if case[-1] == "copy" and case[1] == "ASCII":
        return "AddressSanitizer: heap-buffer-overflow"
    if case[-1] == "path":
        return "independently retained return" if case[1:3] == ("", "null") else \
            "duplicate/unowned string disposal"
    if case[-1] == "bytes":
        return "independently retained return"
    return "unbalanced (string allocations|picture references)"


@unittest.skipUnless(sys.platform == "darwin", "macOS synthetic host")
class OwnershipTests(unittest.TestCase):
    def build(self, source, directory):
        api = source / "4D Plugin API"
        for name, wanted in SDK.items():
            contents = (api / name).read_bytes()
            blob = hashlib.sha1(f"blob {len(contents)}\0".encode() + contents).hexdigest()
            self.assertEqual(blob, wanted, f"Re-audit changed SDK: {name}")
        wrappers = sorted((api / "Classes").glob("*.cpp"))
        self.assertEqual({path.stem for path in wrappers}, WRAPPERS)
        flags = [
            "clang++", "-std=c++14", "-x", "objective-c++",
            "-include", str(ROOT / ".github/tests/ownership_platform.h"),
            "-I", str(api), "-I", str(api / "Classes"), "-I", str(source),
            "-fsanitize=address,undefined", "-fno-sanitize=alignment",
            "-fno-omit-frame-pointer", "-g",
            "-Wno-deprecated-declarations", "-Wno-return-type-c-linkage",
            "-Wno-ignored-attributes", "-Wno-writable-strings",
            "-Werror=objc-method-access",
        ]
        legacy_object = directory / "legacy-dispatch.o"
        commands = [[
            *flags, "-include", str(ROOT / ".github/tests/ownership_legacy.h"),
            "-c", str(source / "4DPlugin.cpp"), "-o", str(legacy_object),
        ]]
        binaries = {}
        for platform in ("modern", "legacy"):
            binary = directory / platform
            dispatcher = ([str(source / "4DPlugin.cpp")] if platform == "modern" else
                          ["-x", "none", str(legacy_object), "-x", "objective-c++"])
            commands.append([
                *flags, str(api / "4DPluginAPI.c"), *map(str, wrappers), *dispatcher,
                str(ROOT / ".github/tests/ownership_host.mm"),
                "-framework", "Cocoa", "-framework", "Carbon", "-o", str(binary),
            ])
            binaries[platform] = binary
        for command in commands:
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for binary in binaries.values():
            imports = subprocess.check_output(["nm", "-u", str(binary)], text=True)
            linked = {line.split()[-1] for line in imports.splitlines() if line.split()}
            forbidden = {
                "_system", "_popen", "_execve", "_posix_spawn", "_kill", "_getenv",
                "_setenv", "_getpid", "_OBJC_CLASS_$_NSURL", "_OBJC_CLASS_$_NSImage",
                "_OBJC_CLASS_$_NSWindow", "_OBJC_CLASS_$_NSButton",
                "_OBJC_CLASS_$_NSEvent", "_OBJC_CLASS_$_NSProcessInfo",
                "_OBJC_CLASS_$_NSWorkspace", "_OBJC_CLASS_$_NSFileManager",
                "_OBJC_CLASS_$_NSAppleScript", "_CFURLCreateWithFileSystemPath",
                "_CFURLCopyFileSystemPath", "_NSLog", "_AESend", "_AESendMessage", "_OSAExecute",
                "_HIWindowChangeAttributes", "_HIWindowTestAttribute",
                "_SetWindowModified", "_IsWindowModified",
            }
            rejected = forbidden & linked
            rejected |= {symbol for symbol in linked if symbol.startswith((
                "_CGEvent", "_CGDisplay", "_CGWindow", "_CGSession", "_TIS",
                "_IOHID", "_AX", "_SendInput", "_GetKeyState", "_GetAsyncKeyState",
                "_GetKeyboard", "_SetKeyboard", "_keybd_event", "_Audio", "_CoreAudio",
                "_CoCreate", "_Open", "_ReadFile", "_WriteFile",
            ))}
            memory_platform = {
                "_CFStringCreateWithBytes", "_CFStringCreateWithCharacters",
                "_CFStringGetBytes", "_CFStringGetCharacters", "_CFStringGetLength",
                "_CFStringGetMaximumSizeForEncoding", "_CFRelease", "_kCFAllocatorDefault",
                "___CFConstantStringClassReference", "_NSZeroSize",
                "_OBJC_CLASS_$_NSObject", "_OBJC_CLASS_$_NSString",
                "_OBJC_CLASS_$_NSMutableString", "_OBJC_CLASS_$_NSData",
            }
            rejected |= {symbol for symbol in linked if symbol.startswith((
                "_CF", "_CG", "_NS", "_HI", "_OBJC_CLASS_$_",
            )) and symbol not in memory_platform}
            rejected |= linked & {
                "_open", "_fopen", "_freopen", "_opendir", "_stat", "_lstat",
                "_access", "_unlink", "_rename", "_remove", "_mkdir", "_chdir",
                "_dlopen", "_dlsym", "_sysctl", "_socket", "_connect", "_fork",
            }
            self.assertFalse(rejected, f"Real platform boundary linked: {rejected}")
        return binaries

    def test_fixed_and_immutable_baseline(self):
        records = []
        with tempfile.TemporaryDirectory(prefix="window-button-ownership-") as temp:
            directory = Path(temp)
            baseline = directory / "baseline"
            baseline.mkdir()
            archive = subprocess.check_output([
                "git", "archive", BASELINE, "4D Plugin API", "4DPlugin.cpp", "4DPlugin.h",
            ], cwd=ROOT)
            with tarfile.open(fileobj=io.BytesIO(archive)) as files:
                for member in files.getmembers():
                    path = Path(member.name)
                    self.assertFalse(path.is_absolute() or ".." in path.parts)
                    self.assertTrue(member.isfile() or member.isdir())
                files.extractall(baseline, filter="data")
            for label, source in (("fixed", ROOT), ("baseline", baseline)):
                build = directory / f"{label}-build"
                build.mkdir()
                binaries = self.build(source, build)
                runs = passed = failed = 0
                for case in cases():
                    runs += 1
                    legacy = case[0] == "legacy-dispatch"
                    args = ("dispatch",) if legacy else case
                    result = subprocess.run(
                        [str(binaries["legacy" if legacy else "modern"]), *map(str, args)],
                        env={**os.environ, "ASAN_OPTIONS": "detect_leaks=0",
                             "UBSAN_OPTIONS": "halt_on_error=1"},
                        capture_output=True, text=True,
                    )
                    records.append({
                        "source": label, "case": case, "returncode": result.returncode,
                        "stdout": result.stdout, "stderr": result.stderr,
                    })
                    should_fail = label == "baseline" and baseline_failure(case)
                    with self.subTest(source=label, case=case):
                        if should_fail:
                            failed += 1
                            self.assertNotEqual(result.returncode, 0, "baseline defect not reproduced")
                            self.assertRegex(result.stderr, baseline_diagnostic(case))
                        else:
                            passed += 1
                            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                            self.assertIn("strings=0 pictures=0 handles=0 objects=n/a collections=n/a",
                                          result.stdout)
                self.assertEqual((runs, passed, failed),
                                 (82, 82, 0) if label == "fixed" else (82, 16, 66))
                print(f"{label}: cases={runs} passes={passed} expected_defects={failed}; "
                      "full SDK + 16 wrappers; modern/legacy Mac import gates passed",
                      file=sys.stderr)
        log = os.environ.get("OWNERSHIP_LOG")
        if log:
            Path(log).write_text(json.dumps(records, ensure_ascii=True, indent=2) + "\n")


if __name__ == "__main__":
    unittest.main()
