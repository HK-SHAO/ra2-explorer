# 已归档的 Hugging Face 发布链路

本项目已于 2026-08-31 停止使用 Hugging Face 托管、镜像和 Space 运行环境。原 Space、Pages 数据 Dataset 与安装包 Dataset 均已删除；当前在线站点只由 GitHub Pages 托管，完整 Pages 快照和 Windows 安装包分别由 GitHub 数据 Release 与稳定 Release 分发。

这份文档只是历史索引，不代表当前支持的部署方式。退出主线前的完整实现保存在 Git 标签 `archive-huggingface-2026-08-31`，对应提交 `44acb01`；其中包括 Space 模板、静态数据和安装包同步脚本、更新通道及测试。主分支不再安装相关 SDK，不读取 HF 环境变量，也不执行任何 HF 网络请求。

现行入口：

- 在线精简版与大数据发布：[GitHub Pages](../GITHUB_PAGES.md)；
- Windows 版本检查与发行：[应用更新](../UPDATES.md)；
- 包内容和体积：[发行说明](../DISTRIBUTION.md)。

如未来重新评估其他托管服务，应以新的架构决策和独立实现开始，不应直接恢复旧链路或旧凭据配置。
