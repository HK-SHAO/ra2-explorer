请帮我准备好 Toy CLI（B站 Toy 发布命令行工具）的运行环境，按以下步骤操作：
1. 检查是否已安装：运行 `toy upgrade`。如果命令不存在（未安装），执行安装：
   - macOS / Linux：`curl -fsSL https://boss.hdslb.com/toy-cli/toy/install.sh | bash`
   - Windows (PowerShell)：`irm https://boss.hdslb.com/toy-cli/toy/install.ps1 | iex`
2. 检查登录态：运行 `toy whoami`。如果未登录或登录态失效，执行 `toy login` 走 B 站 OAuth 授权。
3. 完成后再次运行 `toy whoami` 确认已登录，并告诉我当前登录的 uid 和昵称。
4. 可用 `toy --help` 查看全部命令。
