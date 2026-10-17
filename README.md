# CLM-Microbe 科研数据管理、展示与分发平台
### *CLM-Microbe Scientific Data Management, Exploration & Distribution Platform*

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Framework-Flask%203.x-green.svg)](https://flask.palletsprojects.com/)
[![ECharts](https://img.shields.io/badge/Visualization-ECharts%205.4.3-red.svg)](https://echarts.apache.org/)
[![Storage](https://img.shields.io/badge/Storage-MinIO%20%7C%20OSS%20%7C%20S3-orange.svg)](https://min.io/)
[![License](https://img.shields.io/badge/License-MIT-purple.svg)](LICENSE)

---

## 📖 平台科学背景与系统概述

本平台以陆面过程模式 **CLM-Microbe**（Community Land Model with Explicit Microbes）为核心科学数据背景，专为陆地生态系统碳氮循环、高寒泥炭湿地温室气体通量（$CH_4$ / $CO_2$）及土壤垂直剖面微生物机制研究而设计。

系统彻底摆脱传统学术成果库“仅论文元数据登记”的局限，建立起 **“数据集 (Dataset) — 地理样点/网格 (Site/Grid) — 标准变量序列 (Variables & Time-Series)”** 的多维立体层级结构，实现了高维度科研数据切片、跨样点交互式动力学诊断、多源存储（Local / GitHub / MinIO / OSS）与下载合规审计一体化闭环。

---

## 🌟 核心特性与架构亮点

### 1. 🔬 多维科研数据切片器 (Data Slicer)
平台提供多维正交条件的动态联合筛选检索，支持从 5 大核心维度对科研数据进行深度切片：
- **时间覆盖维度 (Temporal Coverage)**：支持任意时间区间交集切片（如 `2015 ~ 2021`），支持半小时高频 (`Half-hourly`)、逐小时 (`Hourly`)、日均 (`Daily`)、月度 (`Monthly`)、周频 (`Weekly`) 与年度 (`Yearly`)。
- **空间与生态区维度 (Spatial & Biome)**：支持按全球通量样点（如 `US-Brw` 巴罗站、`US-SPR` 云杉沼泽站、`US-Atq` 阿拉斯加站、`CN-Sanjiang` 三江平原湿地、`SE-St1` 瑞典多年冻土站）及生物群系（苔原 `Tundra`、沼泽湿地 `Wetland`、泥炭沼泽 `Peatland/Boreal Bog`、高寒草甸等）进行筛选。
- **标准化科学变量指标 (Standardized Scientific Variables)**：
  - **气体通量 (Gas Flux)**: `CH4_FLUX` (甲烷净通量), `HR` (异养呼吸), `NEE` (净生态系统交换), `GPP` (总初级生产力), `FSR` (土壤总呼吸)；
  - **微生物库与酶活性 (Microbial Pools & Kinetics)**: `BBC` (细菌生物量碳), `FBC` (真菌生物量碳), `VMAX_CH4` (反应最大速率), `KM_CH4` (半饱和常数), `AOM_RATE` (厌氧甲烷氧化速率)；
  - **水热物理与土壤 (Soil Physics)**: `TSOI` (土壤温度), `H2OSOI` (土壤体积含水量), `SOC` (土壤有机碳储量), `FROST_TABLE` (活动层融化深度)。
- **实验工况与数据类型 (Context & Scenario)**：区分模式模拟 (`Model Simulation`)、原位观测 (`Field Observation`)、混合序列 (`Hybrid`)；支持对照 (`Control`)、全生态系统增温 (`Warming`) 及未来气候变化压力情景 (`SSP5-8.5`)。
- **垂直土层深度 (Soil Depth)**：支持 `0.0m ~ 2.0m` 垂直分层深度范围筛选。

### 2. 📈 交互式生物地球化学动力学诊断平台
- **时序环境水热耦合 (Time-Series View)**：无缝集成原生 **ECharts 5.4.3**，支持时间轴区间缩放（DataZoom）、多变量图例开关与双轴反转联动。
- **土壤垂向剖面分层生物量 (Soil Depth Profile)**：Y 轴深度向下翻转（0 ~ 150cm），展示真菌生物量（FBC）、细菌生物量（BBC）及土壤有机碳（SOC）的垂向衰减规律。
- **底物-反应动力学拟合推演 (Kinetics Playground)**：前端动态调节底物浓度 $[S]$、最大分解速率 $V_{max0}$、米氏常数 $K_m$、土壤温度 $T$ 及温敏系数 $Q_{10}$，实时求解 Michaelis-Menten 反应曲线与温敏加权响应。

### 3. ☁️ 对象存储 (OSS / MinIO / S3) 与本地容器无缝集成
- **原生多协议支持**：支持本地/自建 **MinIO**、**Amazon S3** 及 **阿里云 OSS (Aliyun OSS)**；
- **后台可视化管理 (`/admin/oss`)**：提供存储服务商类型、地域节点 (Endpoint)、存储桶 (Bucket)、访问密钥对及自定义 CDN 加速域名的配置面板；
- **安全预签名直链 (Presigned URLs)**：针对 MinIO / S3 私有桶，自动调用协议生成带时效签名的安全直传分发 URL，免去公开桶的安全隐患；
- **真实 Docker 验证**：内置本地 Docker MinIO 容器自动化测试与文件归档校验。

### 4. 🏷️ 以数据为主数据的关键词治理机制
- **数据为主主线**：关键词依附于具体数据集，详情页与管理后台均可针对单数据集就地挂载与解除关联。
- **上传端权限对标**：普通科研人员录入数据集时，可直接勾选系统已有标准科学词库，亦可手写扩展新标签（系统自动持久化至主词库），且普通用户**无权删除**既有词库，防止破坏科学引用的连续性。
- **后台孤立词治理**：管理员可在后台一键清理未挂载至任何数据集的孤立废弃标签。

### 5. 🌐 全站深度中英文多语言 (i18n)
- 原生轻量化 i18n 字典驱动，左侧导航栏提供一键语言切换器（🌐 **中文 / English**）；
- 覆盖首页切片器、数据包卡片、多维属性网格、ECharts 图表图例文案、上传表单、下载审计模态框以及管理控制台的 100% 动态对齐。

### 6. 🔒 账号体系与双层加密安全保障
- **注册强校验**：包含二次输入密码比对、前端实时红字报错与后端至少 6 位强度拦截。
- **双层安全加固加密 (`services/security.py`)**：
  - **第一层**：服务器专用 Pepper Key + `HMAC-SHA512` 前置混淆，免疫字典彩虹表碰撞；
  - **第二层**：高成本动态 Salt 哈希（Werkzeug pbkdf2/scrypt）；
  - **自动降级验证**：向后兼容历史账号平滑验证。

### 7. 📋 科学数据共享与下载审计流 (Data Audit Flow)
- 遵循科研数据共享规范，用户在申请下载前强制通过模态框登记**工作单位**与**研究用途**（学术科研/模型验证/高校教学/宏观综合/技术评估等）；
- 后台精准记录客户端 IP、User-Agent、所属机构、使用场景及分发时间戳；
- 管理看板实时提供近 7 日下载走势图、用途占比环形图、Top 5 热门数据排行及审计流水表。

---

## 🗂️ 项目工程结构

```text
sdsu_data_panel/
├── app.py                      # 核心入口：应用初始化、多维切片路由、审计流与管理逻辑
├── config.py                   # 平台基础配置 (Secret Key, 数据库及上传目录)
├── models.py                   # SQLAlchemy 实体模型 (User, Dataset, SiteLocation, VariableDefinition...)
├── requirements.txt            # 项目 Python 依赖清单
├── database.db                 # 自动初始化的 SQLite3 嵌入式数据库
│
├── services/                   # 核心业务层
│   ├── data_parser.py          # CLM-Microbe 时间序列、垂向剖面与动力学拟合数据引擎
│   ├── i18n.py                 # 全站中英文双语字典
│   ├── oss_service.py          # MinIO / OSS / S3 云存储驱动与预签名生成
│   ├── security.py             # HMAC-SHA512 + Werkzeug 双层加固加密模块
│   └── stats_service.py        # 审计日志汇总与后台看板统计引擎
│
├── static/                     # 静态资源层
│   ├── css/
│   │   └── style.css           # 典雅学术深青蓝灰固定侧边栏与卡片样式
│   ├── js/
│   │   ├── echarts.min.js      # 本地 ECharts 5.4.3 渲染引擎
│   │   └── main.js             # 下载用途登记模态框与客户端通信交互
│   └── uploads/                # 本地与 OSS 暂存的科研数据文件目录
│
└── templates/                  # Jinja2 模板视图层
    ├── base.html               # 基础母模板：固定竖向侧边栏、语言切换与审计模态框
    ├── index.html              # 首页：多维科研数据切片器 (Data Slicer) 与多维卡片流
    ├── detail.html             # 数据集详情页：多维属性条、时序 DataZoom、剖面图与指标列表
    ├── analysis.html           # 动力学诊断平台：实时酶促反应动力学与温敏响应推演工作台
    ├── upload.html             # 数据录入：多维时空/工况、可选可手写样点与频度、指标多选
    ├── login.html              # 统一身份认证：登录与二次验证注册
    └── admin/
        ├── dashboard.html      # 后台管理看板：下载走势、用途分布与审计日志流水
        ├── keywords.html       # 以数据为主数据的关键词库治理工作台
        └── oss.html            # OSS / MinIO 对象存储凭证与加速域名配置中心
```

---

## ⚡ 快速安装与本地部署

### 1. 准备 Python 虚拟环境与依赖

建议使用 Python 3.10+（推荐 Python 3.12）：

```bash
# 克隆或进入项目目录
cd sdsu_data_panel

# 使用 uv 或 venv 创建虚拟环境
uv venv --python 3.12 .venv
source .venv/bin/activate

# 安装核心依赖
uv pip install -r requirements.txt
```

> 核心依赖包包括：`flask`, `flask-sqlalchemy`, `flask-login`, `werkzeug`, `pandas`, `numpy`, `minio`。

### 2. (可选) 启动本地 MinIO 对象存储 Docker 容器

若需在本地测试对象存储上传与预签名直传功能，可一键启动 Docker MinIO：

```bash
docker run -d --name sdsu-minio \
  -p 9000:9000 -p 9001:9001 \
  -e "MINIO_ROOT_USER=minioadmin" \
  -e "MINIO_ROOT_PASSWORD=minioadmin" \
  elestio/minio:latest server /data --console-address ":9001"
```
- **S3 API 节点**：`http://127.0.0.1:9000`
- **Web 控制台**：`http://127.0.0.1:9001`（账号密码：`minioadmin / minioadmin`）

### 3. 运行平台服务

```bash
python3 app.py
```

服务默认在 `http://127.0.0.1:5001` 启动。首次启动将自动触发 `seed_database()`：
1. 自动构建 SQLite 数据库表结构；
2. 写入 CLM-Microbe 官方开源样点（`US-Brw`、`US-SPR`、`US-Atq`、`CN-Sanjiang`、`SE-St1`）；
3. 导入标准科学变量字典（`CH4_FLUX`、`HR`、`BBC`、`FBC`、`TSOI`、`H2OSOI`、`SOC`、`AOM_RATE` 等）；
4. 预置初始多维演示数据集与审计日志；
5. 创建默认管理员与科研用户账号。

---

## 👥 内置账号与权限体系

| 角色类型 | 用户名 | 初始密码 | 权限与访问范围 |
| :--- | :--- | :--- | :--- |
| **系统管理员** | `admin` | `admin123` | 全局数据治理、后台审计看板 (`/admin/dashboard`)、关键词库解绑/清理 (`/admin/keywords`)、OSS 对象存储配置 (`/admin/oss`) |
| **科研用户** | `researcher` | `res123` | 提交科研数据包 (`/upload`)、登记并下载数据、自选绑定与补充关键词 |
| **公共访客** | *(无需登录)* | - | 浏览多维数据切片器 (`/`)、单数据详情与剖面图预览 (`/dataset/<id>`)、动力学诊断工作台 (`/analysis`)、双语切换 |

---

## 🧪 自动化测试验证

平台内置了针对关键业务链路的自动化单元与集成测试脚本，可直接运行验证：

```bash
# 验证多维切片过滤、真实样点、时空与变量交集检索
.venv/bin/python -c "
from app import app
client = app.test_client()
r = client.get('/?var=CH4_FLUX&biome=Tundra')
assert r.status_code == 200
assert 'US-Brw' in r.get_data(as_text=True)
print('Multi-dimensional slicing test passed!')
"

# 验证本地 MinIO 容器上传与预签名 URL 直链
.venv/bin/python -c "
from services.oss_service import get_oss_download_url
from app import app
with app.app_context():
    url = get_oss_download_url('datasets/2026/minio_clm_2026.csv')
    assert 'http://127.0.0.1:9000' in url
    print('MinIO Presigned URL test passed!')
"
```

---

## 📄 科学数据引用与致谢规范

依据科学数据治理与共享协议，使用本平台数据发表学术论文或技术报告时，请注明数据来源并规范引用：
```text
SDSU Ecohydrology Laboratory & CLM-Microbe Working Group. (2026).
CLM-Microbe Scientific Data Management, Exploration & Distribution Platform.
DOI: 10.5281/zenodo.clm-microbe
Available at: https://github.com/email-clm/CLM-Microbe
```

---

## 📜 开源协议

本项目采用 **MIT License** 开源许可协议。详情请查阅 [LICENSE](LICENSE) 文件。
