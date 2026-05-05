# CLAUDE.md

## 项目规则

- `docs/` 目录禁止提交到 git（已加入 .gitignore），设计文档和计划文档仅保留在本地
- `data/` 目录禁止提交到 git，`data/config.yaml` 和 `data/config.local.yaml.example` 除外
- `deploy.sh` 是用户私人部署脚本，禁止提交到 git
- `src/` 下禁止新增 `.py` 文件。新模块必须创建子目录，在子目录的具名文件中实现
- `__init__.py` 禁止写业务代码，只做 re-export（1-5行），可以导出模块的公共接口
- 新增工具不需要改框架代码（`server.py`、`config.py`），创建子目录 + `create_default()` 即可
- 新增通道不需要改框架代码，创建子目录 + YAML 配置 `plugin` 入口即可
- 模块间跨域通信使用 EventBus 发布订阅，禁止直接 import 其他工具或通道的内部模块
