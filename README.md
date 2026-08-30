# RA2 Explorer

> EA has not endorsed and does not support this product.

RA2 Explorer 是一个在本机浏览器中运行的《命令与征服：红色警戒 2 / 尤里的复仇》资产浏览器。它直接只读解析你电脑上的官方安装，不启动游戏 EXE，不上传素材，也不需要 Electron、WebView 或其他 UI 组件。

## 下载与使用

1. 从 [Releases](https://github.com/Hansimov/ra2-explorer/releases) 下载 `RA2-Explorer-Web-x64.zip`。
2. 完整解压 ZIP；不要直接在压缩包里运行，也不要删除 `_internal`。
3. 双击 `RA2 Explorer.exe`。程序会在 `127.0.0.1:46120` 启动本地服务，并用已有的 Edge 或 Chrome 打开页面。
4. 首次打开时，选择你合法安装的《红色警戒 2 / 尤里的复仇》目录。扫描可能持续数秒，原始目录始终只读。

当前发行包面向 Windows x64。它不包含游戏文件；你需要先通过合法渠道安装游戏。安装目录识别与导入说明见 [游戏文件指南](docs/GAME_FILES.md)。

应用可由用户主动检查 GitHub Release 更新，不会静默下载或覆盖程序；更新策略见 [应用更新说明](docs/UPDATES.md)。

## 可以浏览什么

- 载具、航空器、步兵和建筑，以及其主体、炮塔、炮管、动作、武器效果、残骸与建造/运行图层；
- 单位语音、EVA 播报、任务对白、环境与战斗音效，并关联实际规则事件和中英文文本；
- VXL/HVA 三维模型、SHP 多帧动画、地图、地形、PCX、调色板、规则和本地化文本；
- list/grid、阵营与事件筛选、排序、独立详情窗口、可调布局、帧步进和浏览位置记忆；
- 原始资产导出，以及按需生成的 PNG、WAV、模型 JSON 和视频预览。

所有派生结果都进入应用目录下的 `.runtime\RA2MD-Ext`，不会改写游戏安装。普通浏览直接读取 MIX 区段，不再复制每个读过的原始成员。

“设置”集中提供显示与载入偏好、原版目录解析、`.ra2pack` 导入/导出和用户可选的更新检查。已生成的索引、关联和浏览器预览可以导出为不含原始游戏文件的 `.ra2pack`，用于本机备份和迁移；格式边界见 [派生资源包说明](docs/RESOURCE_PACKS.md)。

## 下载与磁盘占用

当前实测公共包解压后约 47.3 MiB，ZIP 约 27.5 MiB。首次导入直接关联本机游戏目录，不会再复制约 600 MiB 的 MIX，因此普通用户只需下载发行 ZIP。

预览、可播放音频和模型会按需缓存在本机。可用 CLI 查看或清理可再生成的缓存：

```bat
ra2exp.exe cache stats
ra2exp.exe cache prune
```

`cache prune` 默认只删除与 MIX 重复的显式解包副本，保留索引、图片预览、模型、转码音频和视频。发行模式、实际体积和构建方式见 [发行与体积说明](docs/DISTRIBUTION.md)。

## 本机构建

已下载的 `ra2exp.exe` 可以为同一台电脑预建完整索引，但仍不复制游戏数据：

```bat
ra2exp.exe package --game-dir "D:\Games\RA2" --output "D:\RA2 Explorer Local"
```

这个 linked 构建会记录本机绝对路径，只适合当前电脑，不应分享。只有在你确认拥有相应再分发权限并确实需要可移动素材包时，才显式增加 `--include-game-data`；程序仍会排除游戏 EXE、DLL、脚本与驱动。

## 隐私与安全

- 服务只监听本机回环地址，不开放局域网访问；
- 浏览与搜索不会把游戏文件、路径或派生结果上传到第三方；
- 公共 Release 不含游戏资产、本机路径、开发缓存、Playwright 或 FFmpeg；
- 提交前钩子和 CI 会扫描令牌、私钥、个人路径、邮箱及其他常见泄露。

安全边界、误报处理和报告方式见 [隐私说明](docs/PRIVACY.md)。

## 开发

源码搭建、测试、后台服务、CLI 与发布命令已移至 [开发指南](docs/DEVELOPMENT.md)；实现边界见 [架构说明](docs/ARCHITECTURE.md)，当前官方安装实际参与解析的输入见 [实际解析输入](docs/GAME_SOURCE_INPUTS.md)。

## 许可证

RA2 Explorer 源代码采用 [MIT License](LICENSE)。该许可证只适用于本项目代码，不授予 Electronic Arts、Westwood 或其他权利人的游戏文件、名称、图像、音频及其他素材的权利。

RA2 Explorer 与 Electronic Arts 或其许可方没有隶属关系。游戏内容的使用与再分发仍须遵守适用法律、平台条款和你实际取得的授权。
