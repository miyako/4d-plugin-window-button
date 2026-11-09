import importlib.util
from pathlib import Path
import plistlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("source_version", ROOT / ".github/scripts/source_version.py")
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".source-tests-", dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.copy_source()
        self.current = source.read(self.root)
        parts = list(map(int, self.current.split(".")))
        parts[2] += 1
        self.drift = ".".join(map(str, parts))

    def copy_source(self):
        for path in source.SOURCE_PATHS:
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / path, target)

    def plist(self, **values):
        path = self.root / source.PLIST
        data = plistlib.loads(path.read_bytes())
        data.update(values)
        path.write_bytes(plistlib.dumps(data))

    def snapshot(self):
        return {path: (self.root / path).read_bytes() for path in source.SOURCE_PATHS}

    def project_value(self, key):
        return next(source.unquote(match[3].strip()) for match in
                    source.SETTING.finditer(source.text(self.root / source.PROJECT))
                    if match[2] == key)

    def set_build(self, value):
        path = self.root / source.PROJECT
        path.write_text(source.SETTING.sub(
            lambda match: f"{match[1]}{value}{match[4]}"
            if match[2] == "CURRENT_PROJECT_VERSION" else match[0], source.text(path)))

    def expected_bytes(self, name, before, new):
        old, new = self.current.encode(), new.encode()
        if name == source.PROJECT:
            return b"".join(line.replace(old, new) if b"MARKETING_VERSION" in
                            line.split(b"=", 1)[0] else line
                            for line in before.splitlines(keepends=True))
        if name == source.PLIST:
            return re.sub(
                rb"(<key>CFBundleShortVersionString</key>\s*<string>)([^<]*)(</string>)",
                lambda match: match[1] + (new if match[2] == old else match[2]) + match[3],
                before,
            )
        return before.replace(old, new)

    def assert_rejected(self):
        before = self.snapshot()
        with self.assertRaises(ValueError):
            source.bump("patch", self.root)
        self.assertEqual(before, self.snapshot())

    def test_live_metadata_and_all_bump_modes(self):
        parts = list(map(int, self.current.split(".")))
        self.assertEqual(source.SETTING_COUNT, 3)
        for mode, expected in (
            ("patch", [parts[0], parts[1], parts[2] + 1]),
            ("minor", [parts[0], parts[1] + 1, 0]),
            ("major", [parts[0] + 1, 0, 0]),
        ):
            with self.subTest(mode=mode):
                self.copy_source()
                before = self.snapshot()
                expected = ".".join(map(str, expected))
                self.assertEqual(source.bump(mode, self.root), expected)
                self.assertEqual(source.read(self.root), expected)
                self.assertNotIn("CFBundleShortVersionString",
                                 plistlib.loads((self.root / source.PLIST).read_bytes()))
                self.assertEqual(source.text(self.root / source.PROJECT).count(
                    f"MARKETING_VERSION = {expected};"), 3)
                for name, original in before.items():
                    self.assertEqual((self.root / name).read_bytes(),
                                     self.expected_bytes(name, original, expected))

    def test_stable_fixture_independent_current_and_build_contract(self):
        project = self.root / source.PROJECT
        project.write_text(
            ("MARKETING_VERSION = 3.2.1;\nCURRENT_PROJECT_VERSION = 3.2.1;\n") * 3
        )
        self.plist(CFBundleShortVersionString="3.2.1", CFBundleVersion="3.2.1")
        (self.root / source.LOCALIZED).write_text(
            'CFBundleName = "Window Button";\nCFBundleShortVersionString = "3.2.1";\n'
            'CFBundleGetInfoString = "Window Button version 3.2.1, Copyright 2021 miyako.";\n',
            encoding="utf-8-sig",
        )
        self.assertEqual(source.read(self.root), "3.2.1")
        self.assertEqual(source.bump("minor", self.root), "3.3.0")
        self.assertEqual(project.read_text().count("CURRENT_PROJECT_VERSION = 3.2.1;"), 3)
        self.assertEqual(plistlib.loads((self.root / source.PLIST).read_bytes())["CFBundleVersion"],
                         "3.2.1")
        self.plist(CFBundleShortVersionString="$(CURRENT_PROJECT_VERSION)")
        self.assert_rejected()
        self.plist(CFBundleShortVersionString="$(MARKETING_VERSION)", CFBundleVersion="77.02")
        self.assertEqual(source.read(self.root), "3.3.0")
        self.assertEqual(source.bump("patch", self.root), "3.3.1")
        self.assertEqual(plistlib.loads((self.root / source.PLIST).read_bytes())["CFBundleVersion"],
                         "77.02")

    def test_invalid_missing_extra_and_drifted_settings(self):
        path = self.root / source.PROJECT
        original = source.text(path)
        for key in source.KEYS:
            old = self.project_value(key)
            invalid = ("v1.2.3", "1.2.3-beta", "1.2.3.4", "-1", "$(UNKNOWN)", "",
                       "$(CURRENT_PROJECT_VERSION)", "${CURRENT_PROJECT_VERSION}")
            if key == "MARKETING_VERSION":
                invalid += ("1.2", "14.3", "77", "01.2.3", self.drift)
            for bad in invalid:
                for count in (1, 3):
                    with self.subTest(key=key, bad=bad, count=count):
                        path.write_text(original.replace(
                            f"{key} = {old};", f"{key} = {bad};", count))
                        self.assert_rejected()
            path.write_text(original.replace(f"{key} = {old};", "", 1))
            self.assert_rejected()
            path.write_text(original + f"\n{key} = {old};\n")
            self.assert_rejected()
            for malformed in (f"{key} = {self.current}", f"{key} nonsense"):
                path.write_text(original + "\n" + malformed + "\n")
                self.assert_rejected()
            path.write_text(original)
        for reference in source.REFERENCES:
            path.write_text(original.replace(
                f"MARKETING_VERSION = {self.current};", f'MARKETING_VERSION = "{reference}";'))
            self.assert_rejected()

    def test_plist_invalid_missing_and_drift(self):
        for key in ("CFBundleShortVersionString", "CFBundleVersion"):
            invalid = ("$(UNKNOWN)", "$(PRODUCT_NAME)", "", "invalid", 123,
                       "v1.2.3", "1.2.3.4", "-1", "1..2", "1.2.3-beta")
            if key == "CFBundleShortVersionString":
                invalid += (self.drift, "1.2", "14.3", "7", "01.2.3")
            for value in invalid:
                with self.subTest(key=key, value=value):
                    self.copy_source()
                    self.plist(**{key: value})
                    self.assert_rejected()
        self.copy_source()
        path = self.root / source.PLIST
        data = plistlib.loads(path.read_bytes())
        del data["CFBundleVersion"]
        path.write_bytes(plistlib.dumps(data))
        self.assert_rejected()
        path.write_bytes(plistlib.dumps([]))
        self.assert_rejected()

    def test_supported_references_preserved_and_only_display_literals_bumped(self):
        for reference in source.REFERENCES:
            for marketing_ref in ("$(MARKETING_VERSION)", "${MARKETING_VERSION}"):
                with self.subTest(reference=reference, marketing_ref=marketing_ref):
                    self.copy_source()
                    self.plist(CFBundleShortVersionString=reference, CFBundleVersion=reference)
                    path = self.root / source.PROJECT
                    path.write_text(source.SETTING.sub(
                        lambda m: f'{m[1]}"{marketing_ref}"{m[4]}'
                        if m[2] == "CURRENT_PROJECT_VERSION" else m[0], source.text(path)))
                    before = self.snapshot()
                    new = source.bump("patch", self.root)
                    self.assertEqual(source.read(self.root), new)
                    for name, original in before.items():
                        self.assertEqual((self.root / name).read_bytes(),
                                         self.expected_bytes(name, original, new))
        self.copy_source()
        self.plist(CFBundleVersion=self.current)
        new = source.bump("minor", self.root)
        self.assertEqual(plistlib.loads((self.root / source.PLIST).read_bytes())["CFBundleVersion"],
                         self.current)

    def test_independent_numeric_current_and_plist_build_values_are_preserved(self):
        for build in (self.current, "77", "14.3", "1.0.0", "001.02.003", "0"):
            for bundle_build in (self.current, "8", "42.7", "001.2.03"):
                with self.subTest(build=build, bundle_build=bundle_build):
                    self.copy_source()
                    self.set_build(build)
                    self.plist(CFBundleShortVersionString=self.current,
                               CFBundleVersion=bundle_build)
                    self.assertEqual(source.read(self.root), self.current)
                    before = self.snapshot()
                    new = source.bump("patch", self.root)
                    self.assertEqual(source.read(self.root), new)
                    self.assertEqual(self.project_value("CURRENT_PROJECT_VERSION"), build)
                    data = plistlib.loads((self.root / source.PLIST).read_bytes())
                    self.assertEqual(data["CFBundleVersion"], bundle_build)
                    self.assertEqual(data["CFBundleShortVersionString"], new)
                    for name, original in before.items():
                        self.assertEqual((self.root / name).read_bytes(),
                                         self.expected_bytes(name, original, new))

    def test_numeric_build_drift_across_configurations_is_rejected(self):
        self.set_build("73.12")
        path = self.root / source.PROJECT
        original = path.read_text()
        for count in (1, 2):
            with self.subTest(count=count):
                path.write_text(original.replace("CURRENT_PROJECT_VERSION = 73.12;",
                                                 "CURRENT_PROJECT_VERSION = 74.12;", count))
                self.assert_rejected()

    def test_short_version_reference_must_resolve_to_marketing(self):
        for reference in ("$(CURRENT_PROJECT_VERSION)", "${CURRENT_PROJECT_VERSION}"):
            with self.subTest(reference=reference):
                self.copy_source()
                self.set_build(self.drift)
                self.plist(CFBundleShortVersionString=reference)
                with self.assertRaises(ValueError):
                    source.read(self.root)
                self.assert_rejected()

    def test_equal_independent_current_short_reference_bump_rejected_before_any_write(self):
        for reference in ("$(CURRENT_PROJECT_VERSION)", "${CURRENT_PROJECT_VERSION}"):
            for mode in ("patch", "minor", "major"):
                with self.subTest(reference=reference, mode=mode):
                    self.copy_source()
                    self.set_build(self.current)
                    self.plist(CFBundleShortVersionString=reference,
                               CFBundleVersion=self.current)
                    self.assertEqual(source.read(self.root), self.current)
                    before = self.snapshot()
                    with self.assertRaises(ValueError):
                        source.bump(mode, self.root)
                    self.assertEqual(before, self.snapshot())
                    self.assertEqual(source.read(self.root), self.current)

    def test_independent_build_references_are_preserved(self):
        for build in ("$(MARKETING_VERSION)", "${MARKETING_VERSION}"):
            for reference in source.REFERENCES:
                with self.subTest(build=build, reference=reference):
                    self.copy_source()
                    self.set_build(build)
                    self.plist(CFBundleVersion=reference)
                    before = self.snapshot()
                    new = source.bump("minor", self.root)
                    self.assertEqual(source.read(self.root), new)
                    self.assertEqual(self.project_value("CURRENT_PROJECT_VERSION"), build)
                    self.assertEqual((self.root / source.PLIST).read_bytes(), before[source.PLIST])
        self.copy_source()
        self.set_build("17.02")
        for reference in ("$(CURRENT_PROJECT_VERSION)", "${CURRENT_PROJECT_VERSION}"):
            with self.subTest(independent_reference=reference):
                self.copy_source()
                self.set_build("17.02")
                self.plist(CFBundleVersion=reference)
                before = (self.root / source.PLIST).read_bytes()
                self.assertEqual(source.read(self.root), self.current)
                new = source.bump("patch", self.root)
                self.assertEqual(source.read(self.root), new)
                self.assertEqual((self.root / source.PLIST).read_bytes(), before)

    def test_duplicate_plist_keys_and_invalid_serialization_fail_closed(self):
        path = self.root / source.PLIST
        original = source.text(path)
        for key in ("CFBundleShortVersionString", "CFBundleVersion"):
            for value in (self.current, self.drift):
                with self.subTest(key=key, value=value):
                    self.copy_source()
                    self.plist(**{key: self.current})
                    data = source.text(path)
                    path.write_text(data.replace(
                        "</dict>", f"<key>{key}</key><string>{value}</string>\n</dict>"))
                    self.assert_rejected()
        for malformed in (
            b"not a plist", original.replace("</dict>", "").encode(),
            original.replace("<string>$(CURRENT_PROJECT_VERSION)",
                             "<string>&#36;(CURRENT_PROJECT_VERSION)").encode(),
            plistlib.dumps(plistlib.loads(original.encode()), fmt=plistlib.FMT_BINARY),
        ):
            with self.subTest(serialization=malformed[:40]):
                self.copy_source()
                path.write_bytes(malformed)
                self.assert_rejected()

    def test_localized_validation(self):
        path = self.root / source.LOCALIZED
        original = source.text(path)
        for pattern in (source.LOCALIZED_SHORT, source.LOCALIZED_INFO):
            for bad in ("1.0", self.drift, "invalid", "", "$(UNKNOWN)", "$(MARKETING_VERSION)",
                        "${CURRENT_PROJECT_VERSION}", "01.2.3", "1.2.3-beta"):
                with self.subTest(pattern=pattern.pattern, bad=bad):
                    path.write_text(pattern.sub(lambda m: f"{m[1]}{bad}{m[3]}", original))
                    self.assert_rejected()
            path.write_text(pattern.sub("", original))
            self.assert_rejected()
        for key in ("CFBundleShortVersionString", "CFBundleGetInfoString"):
            path.write_text(original.replace(key, "UnknownKey"))
            self.assert_rejected()
            path.write_text(original + f'\n{key} = "{self.current}";\n')
            self.assert_rejected()
        for bad in ("Other Product", "Copyright 2016", "Copyright 2021 someone"):
            path.write_text(original.replace(
                "Window Button" if bad == "Other Product" else
                "Copyright 2021" if bad == "Copyright 2016" else "Copyright 2021 miyako", bad))
            self.assert_rejected()

    def test_missing_source_files_rejected_without_writes(self):
        for name in source.SOURCE_PATHS:
            self.copy_source()
            (self.root / name).unlink()
            before = {p: (self.root / p).read_bytes() for p in source.SOURCE_PATHS if p != name}
            with self.assertRaises(FileNotFoundError):
                source.bump("patch", self.root)
            self.assertEqual(before, {p: (self.root / p).read_bytes() for p in before})

    def test_localized_quoted_duplicate_keys_rejected_without_writes(self):
        path = self.root / source.LOCALIZED
        original = path.read_bytes()
        for key in ("CFBundleShortVersionString", "CFBundleGetInfoString"):
            for version in (self.current, self.drift):
                with self.subTest(key=key, version=version):
                    value = version if key == "CFBundleShortVersionString" else (
                        f"Window Button version {version}, Copyright 2021 miyako."
                    )
                    path.write_bytes(original + f'\n"{key}" \t= "{value}";\n'.encode())
                    before = self.snapshot()
                    with self.assertRaises(ValueError):
                        source.read(self.root)
                    self.assertEqual(before, self.snapshot())
                    self.assert_rejected()

    def test_byte_preserving_endings_bom_and_modes(self):
        for newline in ("\n", "\r", "\r\n", "mixed"):
            for bom in (b"", b"\xef\xbb\xbf"):
                with self.subTest(newline=newline, bom=bom):
                    self.copy_source()
                    originals = {}
                    for i, name in enumerate(source.SOURCE_PATHS):
                        path = self.root / name
                        lines = source.text(path).splitlines(keepends=True)
                        value = "".join(line.replace(
                            "\n", ("\r", "\r\n", "\n")[j % 3] if newline == "mixed" else newline
                        ) for j, line in enumerate(lines))
                        path.write_bytes(bom + value.encode())
                        path.chmod((0o755, 0o640, 0o644)[i])
                        originals[name] = (path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
                    new = source.bump("minor", self.root)
                    for name, (before, mode) in originals.items():
                        path = self.root / name
                        self.assertEqual(path.read_bytes(), self.expected_bytes(name, before, new))
                        self.assertEqual(stat.S_IMODE(path.stat().st_mode), mode)

    def test_whitespace_and_quotes_preserved(self):
        for quoted in (False, True):
            self.copy_source()
            path = self.root / source.PROJECT
            old = self.current.encode()
            value = b'"' + old + b'"' if quoted else old
            before = path.read_bytes()
            for key in source.KEYS:
                original_value = self.project_value(key).encode()
                value = b'"' + original_value + b'"' if quoted else original_value
                before = before.replace(key.encode() + b" = " + original_value + b";",
                                        key.encode() + b" \t= \t" + value + b" \t;")
            path.write_bytes(before)
            localized = self.root / source.LOCALIZED
            localized.write_bytes(localized.read_bytes().replace(b" = ", b" \t= \t")
                                  .replace(b'";', b'" \t; \t'))
            snapshots = self.snapshot()
            new = source.bump("patch", self.root)
            for name, original in snapshots.items():
                self.assertEqual((self.root / name).read_bytes(),
                                 self.expected_bytes(name, original, new))

    def test_prebuilt_4d_schema_and_dependency_files_ignored(self):
        excluded = (
            "Window Button.4dbase/Plugins/Window Button.bundle/Contents/Info.plist",
            "Window Button.4dbase/Plugins/Window Button.bundle/Contents/Resources/English.lproj/InfoPlist.strings",
            "Window Button.4dbase/Plugins/Window Button.bundle/Contents/Resources/manifest.json",
            "Window Button.4dbase/Plugins/Window Button.bundle/Contents/Windows64/Window Button.4DX",
            "Window Button.4dbase/Plugins/Window Button.bundle/Contents/QuickLook/Thumbnail.png",
            "Window Button.4dbase/Window Button.4DB",
            "Window Button.4dbase/Window Button.4DD",
            "English.lproj/locversion.plist", "manifest.json", "constants.xlf",
            "4D Plugin API/4DPluginAPI.h", "4D Plugin API/Classes/C_TYPES.h",
            "Window Button.vcxproj", "Window Button.vcxproj.filters",
            "Window Button.vc10.vcxproj", "Window Button.vc10.vcxproj.filters",
            "4DPlugin.cpp", "4DPlugin.h", "documentation.htm",
        )
        for name in excluded:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, path)
        before = {name: ((self.root / name).read_bytes(), (self.root / name).stat().st_mode)
                  for name in excluded}
        source.bump("major", self.root)
        self.assertEqual(before, {
            name: ((self.root / name).read_bytes(), (self.root / name).stat().st_mode)
            for name in excluded
        })

    def test_invalid_mode_and_cli_read_do_not_write(self):
        before = self.snapshot()
        with self.assertRaises(ValueError):
            source.bump("other", self.root)
        output = subprocess.run(
            [sys.executable, str(ROOT / ".github/scripts/source_version.py")],
            cwd=self.root, check=True, capture_output=True, text=True,
        )
        self.assertEqual(output.stdout.strip(), self.current)
        self.assertEqual(before, self.snapshot())

    def test_absent_optional_short_version_is_not_invented(self):
        path = self.root / source.PLIST
        original = path.read_bytes()
        self.assertNotIn("CFBundleShortVersionString", plistlib.loads(original))
        source.bump("patch", self.root)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(plistlib.loads(original)["CFBundleVersion"],
                         "$(CURRENT_PROJECT_VERSION)")

    def test_original_authority_repair_preserves_all_other_bytes_and_modes(self):
        baseline = "2522ace2e172e5a28dbd9466e32837c92d6fdc0f"
        for name in source.SOURCE_PATHS:
            original = subprocess.run(
                ["git", "show", f"{baseline}:{name}"], cwd=ROOT,
                check=True, capture_output=True,
            ).stdout
            version = self.current.encode()
            if name == source.PROJECT:
                expected = original.replace(b"MARKETING_VERSION = 1.1.4;",
                                            b"MARKETING_VERSION = " + version + b";")
            elif name == source.LOCALIZED:
                expected = original.replace(b'"1.1.0"', b'"' + version + b'"')
                expected = expected.replace(b"version 1.1.0,", b"version " + version + b",")
            else:
                expected = original
            self.assertEqual((ROOT / name).read_bytes(), expected)
            mode = subprocess.run(
                ["git", "ls-tree", baseline, "--", str(name)], cwd=ROOT,
                check=True, capture_output=True, text=True,
            ).stdout.split()[0]
            self.assertEqual(stat.S_IMODE((ROOT / name).stat().st_mode), int(mode, 8) & 0o777)


if __name__ == "__main__":
    unittest.main()
