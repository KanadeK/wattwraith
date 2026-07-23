# WattWraith

[![CI](https://github.com/KanadeK/wattwraith/actions/workflows/ci.yml/badge.svg)](https://github.com/KanadeK/wattwraith/actions/workflows/ci.yml)
[![Security](https://github.com/KanadeK/wattwraith/actions/workflows/security.yml/badge.svg)](https://github.com/KanadeK/wattwraith/actions/workflows/security.yml)
[![MIT License](https://img.shields.io/badge/license-MIT-17231f.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/KanadeK/wattwraith?display_name=tag)](https://github.com/KanadeK/wattwraith/releases)

**面向智能插座功率时序的、可解释且离线优先的待机与幽灵耗电分析器。**
WattWraith 导入 CSV 或 JSON，检测低功耗基线、周期唤醒、夜间持续耗电和异常峰值，
展示规则证据，并估算可验证的节电量与电费。

![WattWraith 正在分析仓库内四设备合成样例](docs/assets/wattwraith-result.png)

当前状态：**v0.1.0**

- 默认本地运行：无需账户、云服务、遥测或外部 API。
- 可复核：每个结果都有规则 ID、实测证据、状态和置信度。
- 可行动但保持谨慎：提供周/月/年投影和前后对照验证；绝不把必要设备描述为可安全断电。

## 快速开始

需要 Python 3.12。

```bash
python -m pip install -e ".[dev]"
wattwraith demo --output-dir wattwraith-demo
streamlit run src/wattwraith/app.py
```

演示会对 8,064 条确定性读数执行真实领域管线。在 0.62 CNY/kWh 电价下，当前合成
游戏机样例产生：

```text
年可节电量：       31.536 kWh
年估算费用：       19.55 CNY
数据覆盖率：       100.0%
低功耗基线：       已检测，置信度 94%
周期待机：         已检测，置信度 100%
夜间持续耗电：     已检测，置信度 100%
```

置信度表示确定性的证据强度，不是概率。节省额是根据有效观测窗口作出的直线外推，
不是电费承诺。

## 检测内容

| 发现 | 规则依据 | 默认节能处理 |
| --- | --- | --- |
| 低功耗基线 | 稳定、与其他状态分离且高于用户目标的低功耗状态 | 计算高于目标的可避免功率 |
| 周期待机 | 状态转换间隔稳定且自相关显著 | 计算匹配时段的并集 |
| 夜间持续耗电 | 有效覆盖的本地夜间窗口持续高于目标 | 与其他规则取并集，不重复计量 |
| 异常峰值 | 鲁棒偏差规则并由固定种子的 IsolationForest 确认 | 仅作诊断，不直接计入节省 |

每个检测器都会返回“已检测”“未检测”或“数据不足”。长缺口不会被插值成虚假电量；
重叠规则在每个时间点取最大可避免功率，不会把同一份电量重复相加。

## 输入格式

CSV 和 JSON 共享三个必需字段：

```csv
timestamp,device_id,watts
2026-01-05T00:00:00Z,television,5.184
2026-01-05T00:05:00Z,television,5.421
```

- `timestamp`：带明确时区偏移的 ISO 8601 时间
- `device_id`：用户控制的 1–128 字符标签
- `watts`：有限、非负的瓦特数

文件上限为 50 MiB。无时区时间、缺列、损坏 JSON、负功率、非有限值和不支持的扩展名
都会令 CLI 以非零状态退出。项目不会猜测单位。

## CLI

分析本地文件并导出 JSON、CSV 和自包含 HTML：

```bash
wattwraith analyze readings.csv \
  --annotations annotations.json \
  --tariff tariff.json \
  --output-dir report
```

修改电价而不改变检测逻辑：

```bash
wattwraith analyze readings.json \
  --annotations annotations.json \
  --price-per-kwh 0.85 \
  --currency CNY \
  --output-dir repriced-report
```

JSON 只包含汇总、规则证据、置信度因子、建议和验证步骤，不包含原始读数或绝对源路径。
CSV 会转义公式前缀，HTML 会转义用户标签。

## Streamlit 界面

```bash
streamlit run src/wattwraith/app.py
```

选择内置样例或上传 CSV/JSON，检查明确的设备标注，设置平价电价与用户认可的待机目标，
然后执行分析。时序图、投影、证据、安全提示和三种下载均来自与 CLI 相同的领域服务。

移动端截图同样来自真实运行的应用：

<img src="docs/assets/wattwraith-mobile.png" alt="WattWraith 响应式结果" width="390">

## Python API

领域核心不依赖 UI、文件、网络或系统时钟：

```python
from decimal import Decimal

from wattwraith.adapters import load_power_file
from wattwraith.domain import DeviceAnnotation, TariffPlan, analyze_device

frame = load_power_file("readings.csv").filter(device_id="television")
report = analyze_device(
    frame,
    DeviceAnnotation(device_id="television", standby_target_w=1.0),
    TariffPlan(currency="CNY", price_per_kwh=Decimal("0.62")),
)
print(report.public_dump())
```

多设备请使用 `wattwraith.services.analyze_frame`。

## 合成样例

`examples/data/` 包含冰箱、电视、游戏机和打印机连续七天、每五分钟一次的样例。
它由 `scripts/generate_samples.py` 使用固定 seed `32` 生成，采用 MIT 许可证，不含任何
真实家庭数据，并随包提供给 `wattwraith demo`。

```bash
python scripts/generate_samples.py
```

清单记录行数以及 CSV/JSON 的 SHA-256。测试会确认重新生成的内容逐字节一致，并确认
两种格式加载结果相同。

## 架构

```text
CSV / JSON
    │
    ▼
有边界的文件适配器 ──► 规范化 Polars 表
                            │
                            ▼
                    纯函数、可解释领域规则
                            │
                            ▼
                     不可变 Pydantic 报告
                       │                 │
                       ▼                 ▼
                 CLI / Streamlit    JSON / CSV / HTML
```

状态分段、积分公式、置信度语义和依赖边界见
[架构文档](docs/ARCHITECTURE.md)。

## 验收

完整本地质量门：

```bash
python -m ruff check .
python -m ruff format --check .
python -m mypy src
python -m pytest -q --cov=src --cov-report=term-missing --cov-fail-under=80
python -m build
```

跨平台任务入口：

```bash
make verify
make demo
make package
make release-check
```

没有 GNU Make 时，运行相应的 `python scripts/verify.py`、`demo.py`、
`package_release.py` 和 `release_check.py`。这些脚本会执行真实检查并在失败时停止。

测试覆盖领域规则、精确公式、状态变化、无效输入、权限错误、隐私、CSV/HTML 注入、
样例重生成、CLI 子进程和 Streamlit 交互。实测结果见
[性能记录](docs/BENCHMARK.md)。

## 隐私与安全

- 不进行网络请求或遥测。
- 设备类型只来自用户或样例标注，不从功率曲线推断。
- 不推断身份、是否在家、睡眠、工作或其他个人行为。
- 原始时序可能暴露生活规律，用户导出应按私密数据处理。
- 必要设备不能被标记为可自动断电。
- 异常峰值可能是正常启动电流，不自动计入节省。

完整模型见[隐私与安全文档](docs/PRIVACY_AND_SECURITY.md)。

## v0.1.0 非目标

- 直接控制智能插座或自动断电
- 从家庭总表识别电器
- 分时、需量、税费、固定费或季节电价
- 账单、电气安全认证或节省保证
- 云存储、远程监控或住户行为推断

## 差异化

公开仓库抽样检索未发现同名且高度同构的活跃项目。相邻项目多聚焦硬件采集、看板或
总表 NILM；WattWraith 聚焦离线的设备级取证，提供明确规则、证据、置信度、电价重算
和前后对照方案。这只是有日期、有范围的抽样结论，不是“全球唯一”声明。详见
[检索记录](docs/COMPETITOR_SCAN.md)。

## 路线图

- v0.2：用户自定义检测配置与分时电价适配器
- v0.3：本地 Home Assistant 导入适配器
- 后续：带明确不确定性的季节比较与可选加密本地存储

## 贡献与安全

请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)、[行为准则](CODE_OF_CONDUCT.md) 和
[SECURITY.md](SECURITY.md)。敏感问题请使用 GitHub 私密漏洞报告，不要在公开 Issue
附上真实家庭时序。

## 常见问题

**会识别电器或住户吗？**

不会。设备类型必须明确标注，敏感行为推断不属于项目范围。

**为什么已检测结果的置信度不是 100%？**

置信度汇总覆盖率、稳定度、状态分离度和规则支持，不是校准后的概率。

**为什么年费用与电费账单不同？**

v0.1.0 使用平价电价和直线外推，不包含固定费、税费、阶梯、需量、季节变化及其他用电。

**能安全关闭冰箱吗？**

不能。WattWraith 不控制设备；必要设备标注会禁止自动化措辞，只保留监测建议。

## 许可证

[MIT](LICENSE) © 2026 KanadeK
