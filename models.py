from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from services.security import secure_hash_password, verify_secure_password

db = SQLAlchemy()

# 关键词与数据集多对多关联表
dataset_keywords = db.Table('dataset_keywords',
    db.Column('dataset_id', db.Integer, db.ForeignKey('datasets.id'), primary_key=True),
    db.Column('keyword_id', db.Integer, db.ForeignKey('keywords.id'), primary_key=True)
)

# 数据集与标准化指标变量多对多关联表
dataset_variables = db.Table('dataset_variables',
    db.Column('dataset_id', db.Integer, db.ForeignKey('datasets.id'), primary_key=True),
    db.Column('variable_id', db.Integer, db.ForeignKey('variable_definitions.id'), primary_key=True)
)

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default='user')  # 'admin' 或 'user'
    institution = db.Column(db.String(150))          # 科研单位
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = secure_hash_password(password)

    def check_password(self, password):
        return verify_secure_password(self.password_hash, password)

# ----------------- 1. 变量指标字典表 (标准化指标体系) -----------------
class VariableDefinition(db.Model):
    __tablename__ = 'variable_definitions'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False, index=True) # 如: "CH4_FLUX", "BBC", "TSOI"
    display_name = db.Column(db.String(100), nullable=False)                 # 中文显示名称
    display_name_en = db.Column(db.String(120), nullable=True)               # 英文显示名称
    category = db.Column(db.String(50), index=True)                          # 如: "Gas Flux", "Microbial Pool", "Soil Physics"
    unit = db.Column(db.String(30))                                          # 如: "mg C m-2 d-1", "g C kg-1"
    description = db.Column(db.String(255))                                  # 中文科学描述
    description_en = db.Column(db.String(255))                               # 英文科学描述

    def get_name(self, lang='zh'):
        if lang == 'en' and self.display_name_en:
            return self.display_name_en
        return self.display_name

    def get_desc(self, lang='zh'):
        if lang == 'en' and self.description_en:
            return self.description_en
        return self.description or ''

# ----------------- 2. 地理样点/区域表 (空间与生态区维度) -----------------
class SiteLocation(db.Model):
    __tablename__ = 'site_locations'
    id = db.Column(db.Integer, primary_key=True)
    site_code = db.Column(db.String(50), unique=True, index=True)  # 如: "US-Atq", "CN-Sanjiang"
    site_name = db.Column(db.String(120), nullable=False)          # 如: "Atqasuk Tundra", "三江平原湿地站"
    country = db.Column(db.String(60), index=True)
    latitude = db.Column(db.Float, nullable=False, index=True)     # 纬度
    longitude = db.Column(db.Float, nullable=False, index=True)    # 经度
    elevation = db.Column(db.Float)                                # 海拔 (m)
    biome = db.Column(db.String(80), index=True)                   # 生态系统类型: "Wetland", "Tundra", "Boreal Forest"

# ----------------- 3. 数据集主表 (多维切片与实体属性) -----------------
class Dataset(db.Model):
    __tablename__ = 'datasets'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False, index=True)       # 数据集标题
    author = db.Column(db.String(150), nullable=False)                  # 作者/课题组
    doi = db.Column(db.String(100), nullable=True)                      # DOI 或文献引用
    description = db.Column(db.Text, nullable=False)                    # 描述
    
    # 空间维度关联
    site_id = db.Column(db.Integer, db.ForeignKey('site_locations.id'), nullable=True, index=True)
    site = db.relationship('SiteLocation', backref=db.backref('datasets', lazy='dynamic'))
    spatial_scale = db.Column(db.String(30), default='Point')           # Point(样点), Regional(区域网格), Global(全球)
    site_code = db.Column(db.String(50), nullable=True, default='US-Atq') # 兼容冗余快速索引

    # 时间跨度与分辨率维度
    year = db.Column(db.Integer, nullable=False, index=True)            # 基准/代表年份 (向前兼容)
    start_date = db.Column(db.Date, nullable=True, index=True)          # 观测/模拟起始日期
    end_date = db.Column(db.Date, nullable=True, index=True)            # 观测/模拟终止日期
    temporal_resolution = db.Column(db.String(30), default='Daily')     # Half-hourly, Daily, Monthly, Yearly

    # 实验与数据工况类型
    data_type = db.Column(db.String(40), default='Model Simulation')    # Model Simulation, Field Observation, Hybrid
    model_version = db.Column(db.String(50), default='CLM-Microbe v1.0')
    scenario = db.Column(db.String(50), default='Historical')           # Control, Warming, Nitrogen Addition, SSP2-4.5, SSP5-8.5
    
    # 垂直土层深度范围 (m)
    min_depth = db.Column(db.Float, default=0.0)
    max_depth = db.Column(db.Float, default=1.0)

    # 存储与分发信息
    data_source_type = db.Column(db.String(20), default='github')       # 'github'、'local' 或 'oss'
    github_url = db.Column(db.String(300), nullable=True)               # GitHub 文件/Release/Repo 链接
    local_file_path = db.Column(db.String(300), nullable=True)          # 本地相对存储路径（uploads/xxx.csv）
    download_count = db.Column(db.Integer, default=0)                   # 汇总下载计数
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 多对多关联
    keywords = db.relationship('Keyword', secondary=dataset_keywords, backref=db.backref('datasets', lazy='dynamic'))
    variables = db.relationship('VariableDefinition', secondary=dataset_variables, backref=db.backref('datasets', lazy='dynamic'))

class Keyword(db.Model):
    __tablename__ = 'keywords'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False, index=True)

class DownloadLog(db.Model):
    __tablename__ = 'download_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True) # 未登录可存 NULL
    dataset_id = db.Column(db.Integer, db.ForeignKey('datasets.id'), nullable=False)
    download_type = db.Column(db.String(20))   # 'github_redirect'、'local_download' 或 'oss_download'
    ip_address = db.Column(db.String(45))      # 客户端 IP
    user_agent = db.Column(db.String(255))     # 埋点：设备/浏览器信息
    institution = db.Column(db.String(150))    # 登记的单位
    purpose = db.Column(db.String(200))        # 埋点：科研/教学/模型验证等用途
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('downloads', lazy='dynamic'))
    dataset = db.relationship('Dataset', backref=db.backref('logs', lazy='dynamic'))

class StorageConfig(db.Model):
    __tablename__ = 'storage_configs'
    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(50), default='aliyun_oss') # 'aliyun_oss', 'aws_s3', 'minio'
    endpoint = db.Column(db.String(200), nullable=False)      # 如 oss-cn-beijing.aliyuncs.com
    bucket_name = db.Column(db.String(100), nullable=False)   # 存储桶名称
    access_key_id = db.Column(db.String(150), nullable=False)
    access_key_secret = db.Column(db.String(200), nullable=False)
    custom_domain = db.Column(db.String(200), nullable=True)  # 自定义 CDN 或加速域名
    is_active = db.Column(db.Boolean, default=True)           # 是否启用
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
