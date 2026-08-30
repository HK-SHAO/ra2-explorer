RA2 Explorer for Windows
========================

双击 “RA2 Explorer.exe” 启动。程序只监听本机 127.0.0.1:46120，并优先使用本机安装的
Edge 或 Chrome 打开界面。首次使用时，选择你合法安装的《红色警戒 2 / 尤里的复仇》目录。

命令行工具为 “ra2exp.exe”。例如，把本机游戏资料复制、解析并预建为可移动的独立目录：

  ra2exp.exe package --game-dir "D:\Games\RA2" --sync-reference-data --output "D:\RA2 Explorer Portable"

命令明确排除游戏 EXE、DLL 和脚本，只复制浏览器支持的数据格式。发行目录可以移动；索引会在
启动时自动重定位。不要删除 _internal 目录，也不要在压缩包中直接运行程序。

游戏资料、索引、预览和设置仅保存在当前电脑的 .runtime 目录，不会上传。RA2 Explorer 与
Electronic Arts 或其许可方没有隶属关系。EA has not endorsed and does not support this product.

项目主页：https://github.com/Hansimov/ra2-explorer
