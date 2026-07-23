# WattWraith

WattWraith 是一个离线优先的智能插座功率时序分析器。它将以可解释规则识别待机与
幽灵耗电模式，估算可节约的电量和费用，同时不推断住户身份、是否在家或具体行为。

当前状态：**v0.1.0 开发中**。

## 开发环境

需要 Python 3.12。

```bash
python -m pip install -e ".[dev]"
python -m ruff check .
python -m mypy src
python -m pytest
```

公开仓库抽样检索未发现同名且高度同构的活跃项目。检索范围、样本和差异化判断见
[竞品抽样记录](docs/COMPETITOR_SCAN.md)。

## 隐私边界

计划中的 v0.1.0 工作流完全本地、离线。设备类型只来自用户标注或明确标记的合成
样例；项目不会从功率曲线推断个人身份、在家状态、睡眠、工作或其他敏感行为。

## 许可证

[MIT](LICENSE)

