# 隐私与发布安全

RA2 Explorer 不需要账号、云端服务或遥测。游戏目录、索引、解包结果、缩略图、转码媒体和本地设置
都留在用户电脑中，不应进入 Git 或公开 Release。

## 本地配置

秘密和仅适用于当前电脑的配置统一写入 `.secrets\local.env`。`.secrets`、`.runtime`、虚拟环境、
前端构建结果和发行输出均由 `.gitignore` 排除。代码、测试和文档只使用相对路径、环境变量或明显的
占位示例，不记录个人邮箱、用户目录、工作区绝对路径、访问令牌或带口令的连接地址。

## 提交前检查

首次克隆后在 `cmd.exe` 中运行：

```bat
scripts\setup_dev.cmd
```

该命令把仓库的 Git hooks 路径设为 `.githooks`。每次提交前，钩子使用暂存区中的真实内容执行：

```bat
.venv\Scripts\python.exe scripts\privacy_scan.py --mode staged
```

扫描结果只显示规则、文件、行号和命中值的短指纹，不回显敏感值。GitHub Actions 会再次检查当前树
和所有可达历史对象，防止绕过本地钩子的提交进入公开分支。手动检查命令为：

```bat
.venv\Scripts\python.exe scripts\privacy_scan.py --mode tracked
.venv\Scripts\python.exe scripts\privacy_scan.py --mode history
```

## 发现泄露时

访问令牌、密码或密钥应先在服务提供方撤销或轮换。随后只针对已确认的值或路径改写历史，复验所有
分支和标签，再强制更新远端。已经被 clone、fork、Pull Request 或缓存引用的对象不能仅靠 force push
完全消失；必要时还需协调持有旧副本的人，并联系 GitHub Support 清理服务器端缓存与悬空引用。

游戏素材与包含游戏素材的个人便携包不进入源码分支。公开发行前必须单独确认相应素材的再分发授权；
公共本地 Web 应用默认要求用户导入自己合法安装的游戏文件。
