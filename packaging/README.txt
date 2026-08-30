RA2 Explorer for Windows
========================

RA2 Explorer 是本地 Web 应用，不包含 Electron、WebView 或其他 UI 运行时。双击
“RA2 Explorer.exe” 后，它只在 127.0.0.1:46120 启动本地只读服务，并使用本机已有的
Edge 或 Chrome 打开界面。首次使用时，选择你合法安装的《红色警戒 2 / 尤里的复仇》目录；
应用直接读取该目录，不复制约 600 MB 的游戏归档。

命令行工具为 “ra2exp.exe”。在同一台电脑上预先索引本机游戏目录、但不复制游戏文件：

  ra2exp.exe package --game-dir "D:\Games\RA2" --sync-reference-data --output "D:\RA2 Explorer Local"

这个 linked 构建只适用于游戏仍位于原路径的当前电脑，不应分享。确实需要可移动的完整目录时，
额外加入 --include-game-data；此模式明确排除游戏 EXE、DLL 和脚本，但体积会接近原始游戏数据。
不要删除 _internal 目录，也不要在压缩包中直接运行程序。

游戏资料、索引、预览和设置仅保存在当前电脑的 .runtime 目录，不会上传。RA2 Explorer 与
Electronic Arts 或其许可方没有隶属关系。EA has not endorsed and does not support this product.

项目主页：https://github.com/Hansimov/ra2-explorer
