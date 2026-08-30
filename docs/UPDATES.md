# 应用更新

## 用户侧流程

RA2 Explorer 通过 GitHub Releases 发布版本。应用只在用户点击“检查更新”，或用户明确开启“应用启动时检查更新”后，请求项目的 latest Release；不会静默下载或安装。自动检查发现新版本时只在左侧“设置”入口显示提示点。

发现新版本后，设置页显示版本号、发布时间、文件大小、SHA-256 摘要和 Release 说明。用户可以选择打开 Release 页面或下载 `RA2-Explorer-Web-x64.zip`。更新前关闭 RA2 Explorer，替换程序文件并保留原目录中的 `.runtime`，已有索引、预览、设置和 `.ra2pack` 不需要重新生成。

第一版采用“检查并由用户确认下载”，不在仍运行本地服务时自行覆盖 EXE。后续若增加一键安装，应使用独立的小型更新器：下载到临时目录、校验 Release API 返回的 SHA-256、请求用户确认、停止后台服务、原子替换程序目录、保留 `.runtime`，失败时回滚旧目录。

## 维护者发布流程

1. 完成功能与验证后同步更新 `pyproject.toml` 和 `src/ra2_explorer/__init__.py` 的版本号；
2. 创建并推送对应的 `vX.Y.Z` Git tag；
3. Release workflow 在 Windows 中重新测试、隐私扫描和构建 generic 本地 Web 应用；
4. workflow 上传 ZIP、生成构建来源证明，再创建带自动发布说明的 GitHub Release；
5. 在仓库设置中为后续 Release 启用 immutability，锁定 tag 与资产。

GitHub 的 latest Release API 会提供资产的 `browser_download_url`、大小和 `digest`，应用只接受当前项目仓库下名称完全匹配的 Windows ZIP：[REST Releases API](https://docs.github.com/en/rest/releases/releases)。Immutable Releases 会锁定 tag 与 Release 资产，并自动产生 Release attestation：[Immutable releases](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases)。工作流使用 GitHub artifact attestation 记录构建来源：[Artifact attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations)。

构建来源证明说明产物来自哪次工作流和 commit，并不替代代码审查、恶意软件检测与 Windows Authenticode 签名。公开发行前仍应使用可信代码签名证书签署两个 EXE。
