# Fallout 76 RatMonkeys zhhans Merger

一键生成 **RatMonkeys Easy Sorting and Tagging** 的简体中文 strings。

这个工具会从 Fallout 76 官方 `SeventySix - Localization.ba2` 提取中文文本，把 RatMonkeys 的分类标签合并进去，并把标签缩短成适合游戏内显示的中文短标签。

示例：

```text
[Weapon Mod] -> [武改]
[Armor Mod]  -> [甲改]
[Junk]       -> [杂]
[Ammo]       -> [弹]
```

垃圾成分也会汉化：

```text
[杂] 红色花园矮人 (1.5磅, 陶瓷, 混凝土)
```

## 使用工具生成

需求：

- 已安装 Fallout 76
- 已下载 RatMonkeys Easy Sorting and Tagging
- 已安装 Python，并且 `python` 可以在 PowerShell 里运行

默认路径适配作者本机：

```text
F:\games\fallout76 tools
H:\XboxGames\Fallout 76\Content\Data
```

如果你的路径相同，直接运行：

```powershell
.\run-fo76-strings-merge.ps1
```

或者双击：

```text
run-fo76-strings-merge.bat
```

如果 RatMonkeys zip 没有放在下载目录，可以手动指定：

```powershell
.\run-fo76-strings-merge.ps1 -RatZip "C:\Path\To\RatMonkeysEasySorting.zip"
```

如果游戏路径不同：

```powershell
.\run-fo76-strings-merge.ps1 `
  -GameData "D:\Games\Fallout 76\Content\Data" `
  -RatZip "C:\Path\To\RatMonkeysEasySorting.zip"
```

脚本会自动备份当前 strings，备份目录会在运行结果里显示。

## 安装已生成的 strings

如果你下载的是已经生成好的 strings 文件，把这三个文件放进：

```text
Fallout 76\Content\Data\strings
```

需要的文件：

```text
SeventySix_zhhans.STRINGS
SeventySix_zhhans.DLSTRINGS
SeventySix_zhhans.ILSTRINGS
```

建议覆盖前先备份原文件。

## 说明

- 本分支不包含 Quizzless Apalachia 相关内容。
- 工具只生成/安装 strings，不修改游戏主文件。
- `Wanted Poster` 会被修正为 `-通缉海报`。
