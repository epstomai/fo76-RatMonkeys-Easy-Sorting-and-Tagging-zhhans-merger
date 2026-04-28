#!/usr/bin/env python3
"""Merge Fallout 76 zhhans strings with RatMonkeys and Quizzless markers.

This tool:
1. Extracts official SeventySix_en/zhhans strings from SeventySix - Localization.ba2.
2. Extracts RatMonkeys Easy Sorting SeventySix_en strings from its zip.
3. Copies RatMonkeys en strings and Quizzless SST into the expected folders.
4. Writes merged SeventySix_zhhans strings into the game's Data\\strings folder.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import pathlib
import re
import shutil
import struct
import sys
import tempfile
import zipfile
import zlib


KINDS = ("STRINGS", "DLSTRINGS", "ILSTRINGS")
BA2_WANTED_NAMES = {
    f"strings/seventysix_{lang}.{kind.lower()}"
    for lang in ("en", "zhhans")
    for kind in KINDS
}


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def find_latest(patterns: list[str], roots: list[pathlib.Path]) -> pathlib.Path | None:
    matches: list[pathlib.Path] = []
    for root in roots:
        if not root.exists():
            continue
        for pattern in patterns:
            matches.extend(p for p in root.rglob(pattern) if p.is_file())
    if not matches:
        return None
    return max(matches, key=lambda p: p.stat().st_mtime)


def read_ba2_gnrl(path: pathlib.Path, out_dir: pathlib.Path) -> dict[str, pathlib.Path]:
    data = path.read_bytes()
    if data[:4] != b"BTDX":
        fail(f"Unsupported archive magic in {path}")
    version = struct.unpack_from("<I", data, 4)[0]
    archive_type = data[8:12]
    if version != 1 or archive_type != b"GNRL":
        fail(f"Unsupported BA2 type/version in {path}: version={version}, type={archive_type!r}")

    count = struct.unpack_from("<I", data, 12)[0]
    name_table_offset = struct.unpack_from("<Q", data, 16)[0]
    records = []
    pos = 24
    for _ in range(count):
        records.append(struct.unpack_from("<I4sIIQIII", data, pos))
        pos += 36

    names: list[str] = []
    pos = name_table_offset
    for _ in range(count):
        name_len = struct.unpack_from("<H", data, pos)[0]
        pos += 2
        names.append(data[pos : pos + name_len].decode("utf-8"))
        pos += name_len

    out_dir.mkdir(parents=True, exist_ok=True)
    extracted: dict[str, pathlib.Path] = {}
    for record, name in zip(records, names):
        normalized = name.lower().replace("\\", "/")
        if normalized not in BA2_WANTED_NAMES:
            continue
        _name_hash, _ext, _dir_hash, _unk, offset, packed_size, unpacked_size, _sentinel = record
        size = packed_size or unpacked_size
        payload = data[offset : offset + size]
        if packed_size:
            payload = zlib.decompress(payload)
        dest = out_dir / pathlib.Path(name).name
        dest.write_bytes(payload)
        extracted[dest.name.lower()] = dest

    missing = [
        pathlib.Path(name).name
        for name in BA2_WANTED_NAMES
        if pathlib.Path(name).name.lower() not in extracted
    ]
    if missing:
        fail(f"BA2 extraction missed expected files: {', '.join(sorted(missing))}")
    return extracted


def extract_rat_zip(path: pathlib.Path, out_dir: pathlib.Path) -> dict[str, pathlib.Path]:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as zf:
        zf.extractall(out_dir)

    found: dict[str, pathlib.Path] = {}
    for kind in KINDS:
        matches = list(out_dir.rglob(f"SeventySix_en.{kind}"))
        if not matches:
            fail(f"RatMonkeys zip does not contain SeventySix_en.{kind}")
        found[f"seventysix_en.{kind.lower()}"] = matches[0]
    return found


def read_strings(path: pathlib.Path, kind: str) -> list[tuple[int, str]]:
    data = path.read_bytes()
    if len(data) < 8:
        fail(f"Invalid strings file: {path}")
    count, _data_size = struct.unpack_from("<II", data, 0)
    pos = 8
    data_start = 8 + count * 8
    rows: list[tuple[int, str]] = []
    for _ in range(count):
        string_id, offset = struct.unpack_from("<II", data, pos)
        pos += 8
        if kind == "STRINGS":
            start = data_start + offset
            end = data.find(b"\x00", start)
            if end < 0:
                end = len(data)
            raw = data[start:end]
        else:
            start = data_start + offset
            size = struct.unpack_from("<I", data, start)[0]
            raw = data[start + 4 : start + 4 + size]
            if raw.endswith(b"\x00"):
                raw = raw[:-1]
        rows.append((string_id, raw.decode("utf-8", errors="replace")))
    return rows


def write_strings(path: pathlib.Path, kind: str, rows: list[tuple[int, str]]) -> None:
    table = bytearray()
    payload = bytearray()
    for string_id, text in rows:
        raw = text.encode("utf-8")
        offset = len(payload)
        table += struct.pack("<II", string_id, offset)
        if kind == "STRINGS":
            payload += raw + b"\x00"
        else:
            item = raw + b"\x00"
            payload += struct.pack("<I", len(item)) + item

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(struct.pack("<II", len(rows), len(payload)) + table + payload)
    tmp.replace(path)


def parse_sst(path: pathlib.Path) -> list[tuple[int, str, str]]:
    data = path.read_bytes()
    if data[:4] != b"SSU8":
        fail(f"Unsupported SST file: {path}")

    rows: list[tuple[int, str, str]] = []
    pos = 10
    while pos < len(data):
        if pos + 30 > len(data):
            break
        if data[pos + 8 : pos + 16] != b"TERMITXT":
            break
        string_id = struct.unpack_from("<I", data, pos)[0]
        src_len = struct.unpack_from("<I", data, pos + 26)[0]
        src_start = pos + 30
        src = data[src_start : src_start + src_len].decode("utf-16le", errors="replace")
        dest_len = struct.unpack_from("<I", data, src_start + src_len)[0]
        dest_start = src_start + src_len + 4
        dest = data[dest_start : dest_start + dest_len].decode("utf-16le", errors="replace")
        rows.append((string_id, src, dest))
        pos = dest_start + dest_len + 1
    if not rows:
        fail(f"No rows parsed from SST file: {path}")
    return rows


def apply_marker(marker_dest: str) -> str | None:
    match = re.match(r"^(\((?:X|\+\d+)\))\s*", marker_dest)
    return match.group(1) if match else None


def apply_manual_fixes(source_text: str | None, merged_text: str) -> tuple[str, bool]:
    if source_text == "Wanted Poster" and not merged_text.startswith("-"):
        return f"-{merged_text}", True
    return merged_text, False


def merge_kind(
    kind: str,
    official_en_path: pathlib.Path,
    official_zh_path: pathlib.Path,
    rat_en_path: pathlib.Path,
    sst_rows: list[tuple[int, str, str]],
) -> tuple[list[tuple[int, str]], dict[str, int]]:
    official_en = dict(read_strings(official_en_path, kind))
    official_zh = dict(read_strings(official_zh_path, kind))
    rat_rows = read_strings(rat_en_path, kind)

    source_to_ids: dict[str, list[int]] = {}
    for string_id, source in rat_rows:
        source_to_ids.setdefault(source, []).append(string_id)

    out_rows: list[tuple[int, str]] = []
    grafted = 0
    fallback_english = 0
    noncontain_changed = 0
    manual_fixes = 0
    for string_id, rat_text in rat_rows:
        zh_text = official_zh.get(string_id)
        en_text = official_en.get(string_id)
        if zh_text is None:
            merged = rat_text
            fallback_english += 1
        elif en_text is not None and rat_text != en_text and en_text and en_text in rat_text:
            merged = rat_text.replace(en_text, zh_text, 1)
            grafted += 1
        elif en_text is not None and rat_text != en_text:
            merged = zh_text
            noncontain_changed += 1
        else:
            merged = zh_text if zh_text is not None else rat_text
        merged, fixed = apply_manual_fixes(en_text or rat_text, merged)
        if fixed:
            manual_fixes += 1
        out_rows.append((string_id, merged))

    out_map = {string_id: text for string_id, text in out_rows}
    marker_ids: set[int] = set()
    for string_id, source, dest in sst_rows:
        marker = apply_marker(dest)
        if marker is None:
            continue
        candidate_ids = []
        if string_id in out_map:
            candidate_ids.append(string_id)
        candidate_ids.extend(source_to_ids.get(source, []))
        for candidate_id in candidate_ids:
            current = out_map.get(candidate_id)
            if current and not re.match(r"^\((?:X|\+\d+)\)\s*", current):
                out_map[candidate_id] = f"{marker} {current}"
                marker_ids.add(candidate_id)

    final_rows = [(string_id, out_map[string_id]) for string_id, _ in out_rows]
    stats = {
        "entries": len(final_rows),
        "rat_changes_grafted": grafted,
        "fallback_english_entries": fallback_english,
        "rat_changes_left_as_chinese": noncontain_changed,
        "manual_fixes_applied": manual_fixes,
        "quizzless_markers_applied": len(marker_ids),
        "cjk_entries": sum(1 for _, text in final_rows if re.search(r"[\u4e00-\u9fff]", text)),
        "rat_tag_hits": sum(1 for _, text in final_rows if re.search(r"\[(Ammo|Food|Junk)\]", text)),
        "quiz_marker_hits": sum(1 for _, text in final_rows if re.match(r"^\((?:X|\+\d+)\)", text)),
    }
    return final_rows, stats


def copy_file(src: pathlib.Path, dest: pathlib.Path, dry_run: bool) -> None:
    if dry_run:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def backup_existing(strings_dir: pathlib.Path, dry_run: bool) -> pathlib.Path:
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = strings_dir / f"backup_before_fo76_merge_{stamp}"
    if dry_run:
        return backup_dir
    backup_dir.mkdir(parents=True, exist_ok=False)
    for lang in ("en", "zhhans"):
        for kind in KINDS:
            src = strings_dir / f"SeventySix_{lang}.{kind}"
            if src.exists():
                shutil.copy2(src, backup_dir / src.name)
    return backup_dir


def run(args: argparse.Namespace) -> dict[str, object]:
    tools_root = pathlib.Path(args.tools_root)
    game_data = pathlib.Path(args.game_data)
    strings_dir = pathlib.Path(args.strings_dir) if args.strings_dir else game_data / "strings"
    localization_ba2 = pathlib.Path(args.localization_ba2) if args.localization_ba2 else game_data / "SeventySix - Localization.ba2"
    xtranslator_root = pathlib.Path(args.xtranslator_root) if args.xtranslator_root else tools_root / "_xTranslator"
    downloads = pathlib.Path(args.downloads)

    if not localization_ba2.exists():
        fail(f"Localization BA2 not found: {localization_ba2}")
    if not strings_dir.exists():
        fail(f"strings directory not found: {strings_dir}")

    rat_zip = pathlib.Path(args.rat_zip) if args.rat_zip else find_latest(
        ["RatMonkeysEasySorting*.zip", "*RatMonkeys*Easy*Sorting*.zip"],
        [downloads, tools_root],
    )
    if rat_zip is None or not rat_zip.exists():
        fail("RatMonkeys zip not found. Pass --rat-zip PATH.")

    sst_path = pathlib.Path(args.quizzless_sst) if args.quizzless_sst else find_latest(
        ["seventysix_en_en.sst", "*quizzless*.sst", "*apalachia*.sst"],
        [tools_root, downloads],
    )
    if sst_path is None or not sst_path.exists():
        fail("Quizzless SST not found. Pass --quizzless-sst PATH.")

    work_dir = pathlib.Path(tempfile.mkdtemp(prefix="fo76_strings_merge_"))
    try:
        ba2_dir = work_dir / "official"
        rat_dir = work_dir / "ratmonkeys"
        extracted = read_ba2_gnrl(localization_ba2, ba2_dir)
        rat_files = extract_rat_zip(rat_zip, rat_dir)
        sst_rows = parse_sst(sst_path)

        backup_dir = backup_existing(strings_dir, args.dry_run)

        dict_dest = xtranslator_root / "UserDictionaries" / "Fallout76" / sst_path.name
        copy_file(sst_path, dict_dest, args.dry_run)
        for kind in KINDS:
            copy_file(rat_files[f"seventysix_en.{kind.lower()}"], strings_dir / f"SeventySix_en.{kind}", args.dry_run)

        report: dict[str, object] = {
            "dry_run": args.dry_run,
            "backup_dir": str(backup_dir),
            "rat_zip": str(rat_zip),
            "quizzless_sst": str(sst_path),
            "dictionary_dest": str(dict_dest),
            "strings_dir": str(strings_dir),
            "sst_rows": len(sst_rows),
            "kinds": {},
        }

        kind_report: dict[str, dict[str, int]] = {}
        for kind in KINDS:
            rows, stats = merge_kind(
                kind,
                extracted[f"seventysix_en.{kind.lower()}"],
                extracted[f"seventysix_zhhans.{kind.lower()}"],
                rat_files[f"seventysix_en.{kind.lower()}"],
                sst_rows,
            )
            kind_report[kind] = stats
            if not args.dry_run:
                write_strings(strings_dir / f"SeventySix_zhhans.{kind}", kind, rows)
        report["kinds"] = kind_report
        return report
    finally:
        if args.keep_temp:
            print(f"Kept temp directory: {work_dir}", file=sys.stderr)
        else:
            shutil.rmtree(work_dir, ignore_errors=True)


def parse_args(argv: list[str]) -> argparse.Namespace:
    default_downloads = pathlib.Path.home() / "Downloads"
    parser = argparse.ArgumentParser(
        description="One-click Fallout 76 RatMonkeys + Quizzless zhhans strings merger."
    )
    parser.add_argument("--tools-root", default=r"F:\games\fallout76 tools")
    parser.add_argument("--game-data", default=r"H:\XboxGames\Fallout 76\Content\Data")
    parser.add_argument("--strings-dir", default="")
    parser.add_argument("--localization-ba2", default="")
    parser.add_argument("--xtranslator-root", default="")
    parser.add_argument("--downloads", default=str(default_downloads))
    parser.add_argument("--rat-zip", default="")
    parser.add_argument("--quizzless-sst", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--keep-temp", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    try:
        report = run(parse_args(argv))
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
