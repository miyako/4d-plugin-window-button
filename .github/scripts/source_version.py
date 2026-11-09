"""Marketing-first source versions with independently validated build metadata.

Only source metadata is authoritative; prebuilt bundles and 4D counters are excluded.
"""

import argparse
from pathlib import Path
import plistlib
import re
from xml.parsers.expat import ExpatError


PROJECT = Path("Window Button.xcodeproj/project.pbxproj")
PLIST = Path("Info.plist")
LOCALIZED = Path("English.lproj/InfoPlist.strings")
SOURCE_PATHS = (PROJECT, PLIST, LOCALIZED)
VERSION = r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
BUILD_VERSION = r"[0-9]+(?:\.[0-9]+){0,2}"
KEYS = ("MARKETING_VERSION", "CURRENT_PROJECT_VERSION")
SETTING_COUNT = 3
SETTING = re.compile(
    r"(?m)^([ \t]*(MARKETING_VERSION|CURRENT_PROJECT_VERSION)[ \t]*=[ \t]*)([^;\n]*)(;)"
)
REFERENCES = {f"$({key})": key for key in KEYS}
REFERENCES.update({f"${{{key}}}": key for key in KEYS})
LOCALIZED_SHORT = re.compile(
    r'(?m)^([ \t]*CFBundleShortVersionString[ \t]*=[ \t]*")([^"]*)("[ \t]*;[ \t]*)$'
)
LOCALIZED_INFO = re.compile(
    r'(?m)^([ \t]*CFBundleGetInfoString[ \t]*=[ \t]*"Window Button version )'
    r'([^,"]*)(, Copyright 2021 miyako\."[ \t]*;[ \t]*)$'
)
PLIST_VERSION = re.compile(
    r"(<key>CFBundle(?:ShortVersionString|Version)</key>\s*<string>)([^<]*)(</string>)"
)


class UniqueDictionary(dict):
    def __setitem__(self, key, value):
        if key in self:
            raise ValueError(f"Duplicate source plist key: {key}")
        super().__setitem__(key, value)


def unquote(value):
    return value[1:-1] if value.startswith('"') and value.endswith('"') else value


def text(path):
    return path.read_bytes().decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")


def rendered(path, transform):
    original = path.read_bytes()
    decoded = original.decode("utf-8-sig")
    endings = re.findall(r"\r\n|\r|\n", decoded)
    updated = transform(decoded.replace("\r\n", "\n").replace("\r", "\n"))
    if updated.count("\n") != len(endings):
        raise ValueError("Metadata rewrite changed line structure")
    iterator = iter(endings)
    encoding = "utf-8-sig" if original.startswith(b"\xef\xbb\xbf") else "utf-8"
    return re.sub("\n", lambda _: next(iterator), updated).encode(encoding)


def rewrite(path, transform):
    path.write_bytes(rendered(path, transform))


def read(root=Path(".")):
    root = Path(root)
    fields = {key: [] for key in KEYS}
    project = text(root / PROJECT)
    for key in KEYS:
        if len(re.findall(rf'(?m)^[ \t]*(?:{key}\b|"{key}")', project)) != SETTING_COUNT:
            raise ValueError(f"Expected three source assignments for {key}")
    for match in SETTING.finditer(project):
        fields[match[2]].append(unquote(match[3].strip()))
    if any(len(fields[key]) != SETTING_COUNT for key in KEYS):
        raise ValueError("Expected three source settings for each version key")
    marketing = set(fields["MARKETING_VERSION"])
    if len(marketing) != 1 or not re.fullmatch(VERSION, next(iter(marketing))):
        raise ValueError("MARKETING_VERSION must be one strict X.Y.Z across configurations")
    version = next(iter(marketing))
    current = set(fields["CURRENT_PROJECT_VERSION"])
    if len(current) != 1:
        raise ValueError("Independent CURRENT_PROJECT_VERSION settings have drifted")
    build = next(iter(current))
    if not re.fullmatch(BUILD_VERSION, build) and REFERENCES.get(build) != "MARKETING_VERSION":
        raise ValueError("CURRENT_PROJECT_VERSION is invalid or cyclic")
    resolved = {"MARKETING_VERSION": version,
                "CURRENT_PROJECT_VERSION": version if build in REFERENCES else build}
    try:
        plist = plistlib.loads((root / PLIST).read_bytes(), dict_type=UniqueDictionary)
    except (plistlib.InvalidFileException, ExpatError, UnicodeError) as exc:
        raise ValueError("Source Info.plist has invalid serialization") from exc
    if not isinstance(plist, dict):
        raise ValueError("Source Info.plist must be a dictionary")
    serialized = list(PLIST_VERSION.finditer(text(root / PLIST)))
    expected = sum(key in plist for key in ("CFBundleShortVersionString", "CFBundleVersion"))
    if len(serialized) != expected:
        raise ValueError("Source plist versions must be editable XML strings")
    for key in ("CFBundleShortVersionString", "CFBundleVersion"):
        if key == "CFBundleShortVersionString" and key not in plist:
            continue
        value = plist.get(key)
        if not isinstance(value, str):
            raise ValueError(f"{key} must be a string")
        actual = resolved.get(REFERENCES.get(value), value)
        if (key == "CFBundleShortVersionString" and actual != version) or (
                key == "CFBundleVersion" and not re.fullmatch(BUILD_VERSION, actual)):
            raise ValueError(f"{key} is missing, invalid, unresolved or has drifted")
        literal = [m[2] for m in serialized if f"<key>{key}</key>" in m[1]]
        if literal != [value]:
            raise ValueError(f"{key} has unsupported XML serialization")
    localized = text(root / LOCALIZED)
    for key, pattern in (
        ("CFBundleShortVersionString", LOCALIZED_SHORT),
        ("CFBundleGetInfoString", LOCALIZED_INFO),
    ):
        assignments = re.findall(rf'(?m)^[ \t]*(?:{key}|"{key}")[ \t]*=', localized)
        if len(assignments) != 1 or [m[2] for m in pattern.finditer(localized)] != [version]:
            raise ValueError("Localized source version is missing, invalid or has drifted")
    return version


def bump(mode, root=Path(".")):
    root = Path(root)
    current = read(root)
    plist = plistlib.loads((root / PLIST).read_bytes())
    if REFERENCES.get(plist.get("CFBundleShortVersionString")) == "CURRENT_PROJECT_VERSION":
        if any(match[2] == "CURRENT_PROJECT_VERSION"
               and unquote(match[3].strip()) not in REFERENCES
               for match in SETTING.finditer(text(root / PROJECT))):
            raise ValueError("Short version references an independent build value; "
                             "cannot bump display metadata while preserving that reference")
    index = ("major", "minor", "patch").index(mode)
    parts = list(map(int, current.split(".")))
    parts[index] += 1
    parts[index + 1:] = [0] * (2 - index)
    new = ".".join(map(str, parts))

    def replace(match):
        if match[2] != "MARKETING_VERSION":
            return match[0]
        literal = match[3].strip()
        replacement = f'"{new}"' if literal.startswith('"') else new
        value = match[3].replace(literal, replacement, 1)
        return f"{match[1]}{value}{match[4]}"

    def localized(value):
        for pattern in (LOCALIZED_SHORT, LOCALIZED_INFO):
            value = pattern.sub(lambda m: f"{m[1]}{new}{m[3]}", value)
        return value

    transforms = (
        (PROJECT, lambda value: SETTING.sub(replace, value)),
        (PLIST, lambda value: PLIST_VERSION.sub(
            lambda m: f"{m[1]}{new}{m[3]}"
            if "<key>CFBundleShortVersionString</key>" in m[1] and m[2] not in REFERENCES
            else m[0], value,
        )),
        (LOCALIZED, localized),
    )
    # Render all files first so unsupported encodings cannot cause a partial bump.
    updates = [(root / path, rendered(root / path, transform)) for path, transform in transforms]
    for path, data in updates:
        path.write_bytes(data)
    if read(root) != new:
        raise ValueError("Bumped metadata did not validate")
    return new


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bump", choices=("patch", "minor", "major"))
    args = parser.parse_args()
    print(bump(args.bump) if args.bump else read())
