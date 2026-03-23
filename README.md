# jwgl-query

面向教师侧教务系统（JWGL）的查询 skill。

## 功能

- 查本周课表
- 查监考安排
- 查课程考试安排
- 查考试信息
- 聚合查询考试安排
- 管理多位老师账号

## 初始化

可手动初始化：

```bash
./scripts/setup.sh
```

也可以直接运行查询脚本；首次运行时会自动完成初始化：

```bash
./scripts/run.sh --config config.json --teacher "某老师" --query-type course_schedule --headless
```

初始化会自动：

- 创建 `.venv`
- 安装依赖
- 在缺少 `config.json` 时从 `config.example.json` 复制一份
- 运行环境检查

## 配置账号

`config.json` 不应提交到 Git。

用户首次使用时，由 agent 通过自然语言收集：

- 老师姓名
- 登录账号
- 登录密码

然后调用底层脚本写入本地 `config.json`。

## 常用脚本

```bash
./scripts/setup.sh
./scripts/run.sh --config config.json --teacher "某老师" --query-type course_schedule --headless
python3 scripts/manage_accounts.py --config config.json list
```

## 说明

- 主交互入口是自然语言，不是 CLI
- `tools/` 下脚本仅用于诊断
- `out/` 为调试输出目录，不应提交到仓库
