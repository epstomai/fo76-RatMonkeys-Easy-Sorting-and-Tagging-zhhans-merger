#!/usr/bin/env python3
"""Merge Fallout 76 zhhans strings with fully localized RatMonkeys tags.

This tool:
1. Extracts official SeventySix_en/zhhans strings from SeventySix - Localization.ba2.
2. Extracts RatMonkeys Easy Sorting SeventySix_en strings from its zip.
3. Localizes RatMonkeys-added tags, junk components, and weight units.
4. Writes merged SeventySix_zhhans strings into the game's Data\\strings folder.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
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


def apply_manual_fixes(source_text: str | None, merged_text: str) -> tuple[str, bool]:
    if source_text == "Wanted Poster" and not merged_text.startswith("-"):
        return f"-{merged_text}", True
    return merged_text, False


TAG_TRANSLATIONS = {
    "Note": "纸条",
    "Weapon Mod": "武器改造",
    "Armor Mod": "护甲改造",
    "Apparel": "服装",
    "Junk": "垃圾",
    "Holo": "全息带",
    "Headwear": "头饰",
    "PA Mod": "动力甲改造",
    "Magazine": "杂志",
    "Mask": "面具",
    "Harvest": "采集",
    "Key": "钥匙",
    "Ammo": "弹药",
    "Food": "食物",
    "Food-S": "食物-S",
    "Food-D": "食物-D",
    "Food-C": "食物-C",
    "Alcohol": "酒精",
    "Keycard": "钥匙卡",
    "Chem": "药物",
    "Bobblehead": "摇头娃娃",
    "Bulk": "批量",
    "Fish": "鱼类",
    "Gather": "采集",
    "Bits": "鱼肉块",
    "Gasmask": "防毒面具",
    "Glasses": "眼镜",
    "Mine": "地雷",
    "Meat": "肉类",
    "Grenade": "手榴弹",
    "Helmet": "头盔",
    "Junk-NoScrap": "不可拆垃圾",
    "Passcode": "密码",
    "Nuke": "核弹",
    "Treasure": "藏宝图",
    "Tea-S": "茶-S",
    "Hazmat": "防化服",
    "Package": "包裹",
    "Resource": "资源",
    "Gift": "礼物",
    "Scrap-B": "废料-B",
    "Scrap-V": "废料-V",
    "Serum": "血清",
    "Password": "密码",
    "Candy": "糖果",
    "Drink": "饮料",
    "Drink-S": "饮料-S",
    "Daily": "每日",
    "Aid": "辅助",
    "TEMP": "临时",
    "Herb": "草药",
    "Nuka": "核子可乐",
    "Title": "称号",
    "Game": "游戏",
    "Start Event": "开始事件",
    "Quest": "任务",
    "Confirm Relationship": "确认关系",
    "Bandana": "头巾",
    "Disguise": "伪装",
    "Brotherhood": "兄弟会",
    "Ore": "矿石",
    "Vendor": "商人",
    "Misc": "杂项",
    "Cake": "蛋糕",
    "Cake-S": "蛋糕-S",
    "Thrown": "投掷物",
    "Restricted": "受限",
    "Mission": "任务",
    "Core": "核心",
    "Underarmor": "内衬",
    "Flux": "溶剂",
    "Spoiled": "变质",
    "Foundation": "基金会",
    "Crater": "火山口",
    "Ammon": "弹药",
    "Scrap": "废料",
    "System": "系统",
    "Optional": "可选",
    "Recipe": "配方",
    "Cure": "治疗",
    "Dog Treat": "狗粮",
    "Kit": "工具包",
    "Draft": "草稿",
    "Attack": "攻击",
    "ATTACK": "攻击",
    "Lie": "撒谎",
    "LIE": "撒谎",
    "Flirt": "调情",
    "Flirts": "调情",
    "Bribe": "贿赂",
    "Charisma": "魅力",
    "Strength": "力量",
    "Perception": "感知",
    "Endurance": "耐力",
    "Intelligence": "智力",
    "Agility": "敏捷",
    "Luck": "幸运",
    "Low Intelligence": "低智力",
    "Give Stimpak": "给予治疗针",
    "Give Caps": "给予瓶盖",
    "Give Book": "给予书籍",
    "Give Heirloom Lighter": "给予传家宝打火机",
    "Not In Power Armor": "未穿动力甲",
    "Start Caravan": "开始商队",
    "Large caravan only": "仅限大型商队",
    "End Romance": "结束恋情",
    "Help Hugo": "帮助雨果",
    "Kill Hugo": "杀死雨果",
    "Capture Hugo": "抓捕雨果",
    "SPECIAL": "SPECIAL",
    "Health": "生命值",
    "Durability": "耐久度",
    "V.A.T.S. Enhanced": "V.A.T.S.强化",
    "Resistances": "抗性",
    "Elemental": "元素",
    "Invigorating": "振奋",
    "Enervating": "衰弱",
    "Addictol": "瘾头解",
    "Mentats": "敏达",
    "Calmex": "镇静剂",
    "Psycho": "赛柯",
    "Daytripper": "白日梦",
    "Daddy-O": "老爹-O",
}

SPECIAL_TRANSLATIONS = {
    "Strength": "力量",
    "Perception": "感知",
    "Endurance": "耐力",
    "Charisma": "魅力",
    "Intelligence": "智力",
    "Agility": "敏捷",
    "Luck": "幸运",
    "STR": "力量",
    "PER": "感知",
    "END": "耐力",
    "CHR": "魅力",
    "INT": "智力",
    "AGI": "敏捷",
    "LCK": "幸运",
    "LK": "幸运",
    "Agi": "敏捷",
}

TAG_TRANSLATIONS.update(
    {
        "Note": "纸",
        "Weapon Mod": "武改",
        "Armor Mod": "甲改",
        "Apparel": "衣",
        "Junk": "杂",
        "Holo": "带",
        "Headwear": "帽",
        "PA Mod": "动改",
        "Magazine": "刊",
        "Mask": "面",
        "Harvest": "采",
        "Key": "钥",
        "Ammo": "弹",
        "Food": "鲜",
        "Food-S": "腐",
        "Food-D": "病",
        "Food-C": "罐",
        "Alcohol": "酒",
        "Keycard": "卡",
        "Chem": "药",
        "Bobblehead": "娃",
        "Bulk": "批",
        "Fish": "生鱼",
        "Gather": "采",
        "Bits": "鱼块",
        "Gasmask": "毒面",
        "Glasses": "镜",
        "Mine": "雷",
        "Meat": "生肉",
        "Grenade": "榴",
        "Helmet": "盔",
        "Junk-NoScrap": "不拆",
        "Passcode": "码",
        "Nuke": "核",
        "Treasure": "宝",
        "Tea-S": "茶S",
        "Hazmat": "防化",
        "Package": "包",
        "Resource": "资",
        "Gift": "礼",
        "Scrap-B": "包",
        "Scrap-V": "卖",
        "Serum": "清",
        "Password": "密",
        "Candy": "糖",
        "Drink": "饮",
        "Drink-S": "饮腐",
        "Daily": "日",
        "Aid": "辅",
        "TEMP": "临",
        "Herb": "茶材",
        "Nuka": "核可",
        "Title": "称",
        "Game": "游",
        "Start Event": "开事",
        "Quest": "任",
        "Confirm Relationship": "确认",
        "Bandana": "巾",
        "Disguise": "伪",
        "Brotherhood": "兄弟",
        "Ore": "矿",
        "Vendor": "商",
        "Misc": "杂",
        "Cake": "糕",
        "Cake-S": "糕S",
        "Thrown": "投",
        "Restricted": "限",
        "Mission": "任务",
        "Core": "芯",
        "Underarmor": "内衬",
        "Flux": "剂",
        "Spoiled": "变质",
        "Foundation": "基金",
        "Crater": "火山",
        "Ammon": "弹",
        "Scrap": "废",
        "System": "系",
        "Optional": "选",
        "Recipe": "方",
        "Cure": "疗",
        "Dog Treat": "狗粮",
        "Kit": "包",
        "Draft": "稿",
        "Attack": "攻",
        "ATTACK": "攻",
        "Lie": "谎",
        "LIE": "谎",
        "Flirt": "撩",
        "Flirts": "撩",
        "Bribe": "贿",
        "Charisma": "魅",
        "Strength": "力",
        "Perception": "感",
        "Endurance": "耐",
        "Intelligence": "智",
        "Agility": "敏",
        "Luck": "运",
        "Low Intelligence": "低智",
        "Give Stimpak": "给针",
        "Give Caps": "给盖",
        "Give Book": "给书",
        "Give Heirloom Lighter": "给火",
        "Not In Power Armor": "无甲",
        "Start Caravan": "商队",
        "Large caravan only": "大队",
        "End Romance": "分手",
        "Help Hugo": "助雨",
        "Kill Hugo": "杀雨",
        "Capture Hugo": "捕雨",
        "SPECIAL": "特",
        "Health": "血",
        "Durability": "耐久",
        "V.A.T.S. Enhanced": "VATS",
        "Resistances": "抗",
        "Elemental": "元",
        "Invigorating": "振",
        "Enervating": "弱",
        "Addictol": "解瘾",
        "Mentats": "敏达",
        "Calmex": "镇静",
        "Psycho": "赛柯",
        "Daytripper": "白日",
        "Daddy-O": "老爹",
    }
)

SPECIAL_TRANSLATIONS.update(
    {
        "Strength": "力",
        "Perception": "感",
        "Endurance": "耐",
        "Charisma": "魅",
        "Intelligence": "智",
        "Agility": "敏",
        "Luck": "运",
        "STR": "力",
        "PER": "感",
        "END": "耐",
        "CHR": "魅",
        "INT": "智",
        "AGI": "敏",
        "LCK": "运",
        "LK": "运",
        "Agi": "敏",
    }
)

COMPONENT_TRANSLATIONS = {
    "Acid": "酸",
    "Adhesive": "黏合剂",
    "Aluminum": "铝",
    "Antiseptic": "抗菌剂",
    "Asbestos": "石棉",
    "Ballistic Fiber": "防弹纤维",
    "Black Titanium": "黑钛",
    "Bone": "骨头",
    "Ceramic": "陶瓷",
    "Circuitry": "电路元件",
    "Cloth": "布料",
    "Coal": "煤炭",
    "Concrete": "混凝土",
    "Copper": "铜",
    "Cork": "软木",
    "Crystal": "水晶",
    "Fertilizer": "肥料",
    "Fiber Optics": "光学纤维",
    "Fiberglass": "玻璃纤维",
    "Gear": "齿轮",
    "Glass": "玻璃",
    "Gold": "黄金",
    "Lead": "铅",
    "Leather": "皮革",
    "Nuclear Material": "核材料",
    "Oil": "油",
    "Plastic": "塑料",
    "Rubber": "橡胶",
    "Screw": "螺丝",
    "Silver": "银",
    "Spring": "弹簧",
    "Steel": "钢铁",
    "Ultracite": "超铀矿",
    "Vault Steel": "避难所钢材",
    "Vault 96 Steel": "96号避难所钢材",
    "Wood": "木头",
    "Pure Cobalt Flux": "纯钴溶剂",
    "Pure Fluorescent Flux": "纯荧光溶剂",
    "Pure Violet Flux": "纯紫色溶剂",
    "Pure Crimson Flux": "纯猩红溶剂",
    "Pure Yellowcake Flux": "纯黄饼溶剂",
}


def translate_tag_content(tag: str) -> str:
    if tag in TAG_TRANSLATIONS:
        return TAG_TRANSLATIONS[tag]

    if "/" in tag:
        parts = tag.split("/")
        translated_parts = [translate_tag_content(part.strip()) for part in parts]
        if translated_parts != [part.strip() for part in parts]:
            return "/".join(translated_parts)

    special_match = re.match(
        r"^(Strength|Perception|Endurance|Charisma|Intelligence|Agility|Luck|STR|PER|END|CHR|INT|AGI|LCK|LK|Agi)\s*([+\-]?\d+\+?|\+\d+|\d+\-)?$",
        tag,
    )
    if special_match:
        label = SPECIAL_TRANSLATIONS[special_match.group(1)]
        value = special_match.group(2)
        return f"{label}{value}" if value else label

    level_match = re.match(r"^(?:Level|lvl)\s*(\d+\+?)$", tag, flags=re.IGNORECASE)
    if level_match:
        return f"Lv{level_match.group(1)}"

    for unit, translated_unit in (("Caps", "盖"), ("caps", "盖"), ("Supplies", "补")):
        if tag.endswith(f" {unit}"):
            amount = tag[: -len(unit)].strip()
            return f"{amount}{translated_unit}"

    return tag


def localize_tags(text: str) -> tuple[str, int]:
    count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal count
        original = match.group(1)
        translated = translate_tag_content(original)
        if translated != original:
            count += 1
        return f"[{translated}]"

    return re.sub(r"\[([^\]\r\n]{1,80})\]", replace, text), count


def localize_component_groups(text: str) -> tuple[str, int]:
    count = 0
    component_names = sorted(COMPONENT_TRANSLATIONS, key=len, reverse=True)

    def replace_group(match: re.Match[str]) -> str:
        nonlocal count
        group = match.group(1)
        component_like = (
            "lb" in group
            or "," in group
            or group.strip() in COMPONENT_TRANSLATIONS
            or any(re.search(rf"(?<![A-Za-z]){re.escape(name)}(?![A-Za-z])", group) for name in component_names)
        )
        if not component_like:
            return match.group(0)

        translated = re.sub(r"(\d+(?:\.\d+)?)\s*lb", r"\1磅", group, flags=re.IGNORECASE)
        for name in component_names:
            translated = re.sub(
                rf"(?<![A-Za-z]){re.escape(name)}(?![A-Za-z])",
                COMPONENT_TRANSLATIONS[name],
                translated,
            )
        if translated != group:
            count += 1
        return f"({translated})"

    return re.sub(r"\(([^()]*)\)", replace_group, text), count


def localize_ratmonkeys_additions(text: str) -> tuple[str, int, int]:
    text, tag_count = localize_tags(text)
    text, component_count = localize_component_groups(text)
    return text, tag_count, component_count


def merge_kind(
    kind: str,
    official_en_path: pathlib.Path,
    official_zh_path: pathlib.Path,
    rat_en_path: pathlib.Path,
) -> tuple[list[tuple[int, str]], dict[str, int]]:
    official_en = dict(read_strings(official_en_path, kind))
    official_zh = dict(read_strings(official_zh_path, kind))
    rat_rows = read_strings(rat_en_path, kind)

    out_rows: list[tuple[int, str]] = []
    grafted = 0
    fallback_english = 0
    noncontain_changed = 0
    manual_fixes = 0
    localized_tags = 0
    localized_components = 0
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
        merged, tag_count, component_count = localize_ratmonkeys_additions(merged)
        localized_tags += tag_count
        localized_components += component_count
        out_rows.append((string_id, merged))

    stats = {
        "entries": len(out_rows),
        "rat_changes_grafted": grafted,
        "fallback_english_entries": fallback_english,
        "rat_changes_left_as_chinese": noncontain_changed,
        "manual_fixes_applied": manual_fixes,
        "localized_tags": localized_tags,
        "localized_component_groups": localized_components,
        "cjk_entries": sum(1 for _, text in out_rows if re.search(r"[\u4e00-\u9fff]", text)),
        "remaining_core_english_tags": sum(
            1 for _, text in out_rows if re.search(r"\[(Ammo|Food|Junk|Weapon Mod|Armor Mod)\]", text)
        ),
    }
    return out_rows, stats


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

    work_dir = pathlib.Path(tempfile.mkdtemp(prefix="fo76_strings_merge_"))
    try:
        ba2_dir = work_dir / "official"
        rat_dir = work_dir / "ratmonkeys"
        extracted = read_ba2_gnrl(localization_ba2, ba2_dir)
        rat_files = extract_rat_zip(rat_zip, rat_dir)

        backup_dir = backup_existing(strings_dir, args.dry_run)

        for kind in KINDS:
            copy_file(rat_files[f"seventysix_en.{kind.lower()}"], strings_dir / f"SeventySix_en.{kind}", args.dry_run)

        report: dict[str, object] = {
            "dry_run": args.dry_run,
            "backup_dir": str(backup_dir),
            "rat_zip": str(rat_zip),
            "strings_dir": str(strings_dir),
            "kinds": {},
        }

        kind_report: dict[str, dict[str, int]] = {}
        for kind in KINDS:
            rows, stats = merge_kind(
                kind,
                extracted[f"seventysix_en.{kind.lower()}"],
                extracted[f"seventysix_zhhans.{kind.lower()}"],
                rat_files[f"seventysix_en.{kind.lower()}"],
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
        description="One-click Fallout 76 fully localized RatMonkeys zhhans strings merger."
    )
    parser.add_argument("--tools-root", default=r"F:\games\fallout76 tools")
    parser.add_argument("--game-data", default=r"H:\XboxGames\Fallout 76\Content\Data")
    parser.add_argument("--strings-dir", default="")
    parser.add_argument("--localization-ba2", default="")
    parser.add_argument("--downloads", default=str(default_downloads))
    parser.add_argument("--rat-zip", default="")
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
