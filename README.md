经原作者同意，本项目从 [Hansimov/ra2-explorer](https://github.com/Hansimov/ra2-explorer) 分叉后独立维护，感谢原作者的工作。

# RA2 Explorer

> EA has not endorsed and does not support this product.

在浏览器里浏览《红色警戒 2 / 尤里的复仇》的全部资产：单位、三维模型、帧动画、地图、调色板、语音、过场影片与规则文本。只读解析本机官方安装，不上传任何素材。

## 两种用法

| | 本地版 | 离线网页包 |
| --- | --- | --- |
| 获取 | [Releases](https://github.com/HK-SHAO/ra2-explorer/releases) 下载 `RA2-Explorer-Web-x64.zip` | `ra2exp pages export` + `npm run build:pages` 打包 |
| 数据 | 本机游戏目录（只读） | 预生成的派生快照 |
| 适用 | 完整能力：地图、地形、导出、本地解析 | 快速浏览 559 个单位与 3,348 个声音 |

**本地版**：解压 → 启动 `RA2 Explorer` → 首次选择游戏目录。安装识别见 [游戏文件指南](docs/GAME_FILES.md)。

**离线网页包**：解压即用，也可发布到 B 站 Toy，过场影片通过 B 站视频引用播放。构建步骤见 [发行说明](docs/DISTRIBUTION.md)。

## 构建与开发

```bash
# 本地版：静态前端 + 本机服务（跨平台，无 Windows 依赖）
cd frontend && npm install && npm run build
ra2exp serve                       # 开发热更新：npm run dev

# 离线网页包（Toy 版）：三步产出 toy.zip
ra2exp pages export SOURCE_ID      # 导出派生快照
ra2exp movies build SOURCE_ID      # 合成过场影片，生成 BV 引用清单
python scripts/build_toy_package.py
```

## 亮点

- 全局搜索：简繁中文、拼音与模糊匹配，`Ctrl+K` 随时唤起；
- 盟军 / 苏军 / 尤里按玩家色着色，卡片、详情与动画保持一致；
- 音频进度条可拖动跳转，视频自动取封面，过场影片在线引用播放；
- 单位动画按主体、建造与运转状态分组，超级武器分阶段播放。

## 文档

[游戏文件](docs/GAME_FILES.md) · [发行与体积](docs/DISTRIBUTION.md) · [应用更新](docs/UPDATES.md) · [派生资源包](docs/RESOURCE_PACKS.md) · [隐私](docs/PRIVACY.md) · [架构](docs/ARCHITECTURE.md) · [开发指南](docs/DEVELOPMENT.md) · [更新日志](CHANGELOG.md)

## 许可证

[MIT License](LICENSE)。与 EA 无隶属关系；游戏内容的使用与再分发须遵守适用法律和授权。
