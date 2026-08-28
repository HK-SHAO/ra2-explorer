# 获取与导入游戏文件

## 官方来源

《Command & Conquer Red Alert 2 and Yuri's Revenge》不是免费游戏。当前可核验的数字版来源是：

- [Steam 独立商店页（App 2229850）](https://store.steampowered.com/app/2229850/Command__Conquer_Red_Alert_2_and_Yuris_Revenge/)；
- EA App 中的 *Command & Conquer The Ultimate Collection*；
- 用户已经拥有并能在当前 Windows 系统读取的兼容旧版安装。

[CnCNet 的 Windows 10/11 指南](https://cncnet.org/red-alert-2/how-to-play) 同样要求先从 Steam、EA App 或已有授权安装取得 RA2/YR；CnCNet 补丁改善兼容性和联网功能，但不替代游戏所有权。

项目不会从非授权镜像、网盘或所谓“免安装版”下载商业内容，也不会把用户的游戏文件提交到仓库或云端。

## 当前机器状态

当前项目已经由用户提供一份官方安装，位置为 `.runtime\RA2MD`。自动发现确认该目录同时包含 `ra2.mix` 与 `ra2md.mix`，因此覆盖《红色警戒 2》原版和《尤里的复仇》。应用只对目录做静态、只读解析；不会启动其中任何 EXE。

2026-08-29 的实际扫描结果为 `ready`：64 个归档、13,382 个资产。主要分类是 5,536 个 TMP、5,354 个 SHP、1,277 个 WAV、254 个 PCX、221 个 VXL、221 个 HVA、204 个 MAP、123 个 PAL 和 92 个 INI；其余为 MIX、AUD、FNT、CSF、BAG、IDX、VPL、文本和视频。零售版中的 5 字节 `CLASS` MIX 占位符会保留为归档记录，不再被误报为损坏文件；`.TEM/.SNO/.URB/.UBN/.LUN/.DES` 等同名战区扩展会先按内容区分 TMP 与 SHP。

如果数据库被重建，页面会把 `.runtime\RA2MD` 显示为“项目本地官方安装”候选，也可以重新执行：

```bat
.venv\Scripts\ra2-explorer.exe import .runtime\RA2MD --name RA2MD-官方安装
```

应用还会读取 Steam 库清单、App 2229850 清单、EA/Westwood 安装注册表和常见 EA App/Origin 目录，并只在找到 `ra2.mix` 或 `ra2md.mix` 时给出可导入候选。

命令行可先核对发现结果：

```bat
.venv\Scripts\ra2-explorer.exe discover
```

Steam 常见路径示例：

```text
D:\SteamLibrary\steamapps\common\Command & Conquer Red Alert II
```

实际路径由 Steam 库位置决定，不要假定一定在系统盘。导入后源文件保持只读；应用自己的索引位于项目 `.runtime` 目录。

导入后可执行确定性的按格式抽样验证。验证会读取解析结果，并对可视格式实际渲染首个可用帧或地块；它不会运行游戏：

```bat
.venv\Scripts\ra2-explorer.exe verify f48bb468-297b-404f-952e-055adda2d1b7 --samples-per-format 20
```

当前官方安装已按上述参数验证 188 个真实资产，覆盖 11 类已支持格式，结果为 188 通过、0 失败。

## 无游戏文件时

下面的格式验证资料库由项目现场生成，包含一个加密根 MIX、一个嵌套 MIX，以及 PAL、六帧 SHP、VXL/HVA、TMP、CSF、INI 和 WAV，不含任何 EA 图像、声音或文本：

```bat
.venv\Scripts\ra2-explorer.exe demo
```

浏览器空状态中的“先看格式样本”执行相同操作。它用于确认安装、加密索引、嵌套读取、搜索、真实格式解析、预览、播放和导出链路；它不是用来替代真实游戏目录的展示 Demo。

## 成熟的可解析参考数据

项目可以把 `iron-curtain-engine/cnc-formats` 的 RA2 已知文件名数据库下载到本地。下载固定到一个明确提交，并生成来源清单；它只帮助把 MIX CRC 恢复为名称，不含游戏资产：

```bat
.venv\Scripts\ra2-explorer.exe sync-names
```

参考文件保存到 `.runtime\reference`，可安全删除并重新同步。代码实现核对所用的 OpenRA、`cnc-formats` 和 `ra2web-studio` 源码也只作为格式参考，不是可玩的 RA2 发行版。
