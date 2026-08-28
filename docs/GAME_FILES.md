# 获取与导入游戏文件

## 官方来源

《Command & Conquer Red Alert 2 and Yuri's Revenge》不是免费游戏。当前可核验的数字版来源是：

- [Steam 独立商店页（App 2229850）](https://store.steampowered.com/app/2229850/Command__Conquer_Red_Alert_2_and_Yuris_Revenge/)；
- EA App 中的 *Command & Conquer The Ultimate Collection*；
- 用户已经拥有并能在当前 Windows 系统读取的兼容旧版安装。

[CnCNet 的 Windows 10/11 指南](https://cncnet.org/red-alert-2/how-to-play) 同样要求先从 Steam、EA App 或已有授权安装取得 RA2/YR；CnCNet 补丁改善兼容性和联网功能，但不替代游戏所有权。

项目不会从非授权镜像、网盘或所谓“免安装版”下载商业内容，也不会把用户的游戏文件提交到仓库或云端。

## 当前机器状态

如果 Steam 或 EA App 中尚未安装游戏，RA2 Explorer 无法合法代为下载。先在平台客户端购买/领取并完成安装，然后启动 RA2 Explorer，点击“添加目录”，粘贴包含 `ra2.mix` 或 `ra2md.mix` 的目录路径。

Steam 常见路径示例：

```text
D:\SteamLibrary\steamapps\common\Command & Conquer Red Alert II
```

实际路径由 Steam 库位置决定，不要假定一定在系统盘。导入后源文件保持只读；应用自己的索引位于项目 `.runtime` 目录。

## 无游戏文件时

下面的演示资料库由项目现场生成，包含一个加密根 MIX、一个嵌套 MIX、PAL、六帧 SHP 和 INI，不含任何 EA 图像、声音或文本：

```bat
.venv\Scripts\ra2-explorer.exe demo
```

浏览器空状态中的“先看合成演示”执行相同操作。它用于确认安装、加密索引、嵌套读取、搜索、预览和导出链路。

## 成熟的可解析参考数据

项目可以把 `iron-curtain-engine/cnc-formats` 的 RA2 已知文件名数据库下载到本地。下载固定到一个明确提交，并生成来源清单；它只帮助把 MIX CRC 恢复为名称，不含游戏资产：

```bat
.venv\Scripts\ra2-explorer.exe sync-names
```

参考文件保存到 `.runtime\reference`，可安全删除并重新同步。代码实现核对所用的 OpenRA、`cnc-formats` 和 `ra2web-studio` 源码也只作为格式参考，不是可玩的 RA2 发行版。
