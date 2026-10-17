from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from services.security import secure_hash_password, verify_secure_password

db = SQLAlchemy()

# 关键词与数据集多对多关联表
dataset_keywords = db.Table('dataset_keywords',
    db.Column('dataset_id', db.Integer, db.ForeignKey('datasets.id'), primary_key=True),
    db.Column('keyword_id', db.Integer, db.ForeignKey('keywords.id'), primary_key=True)
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

class Dataset(db.Model):
    __tablename__ = 'datasets'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False, index=True)       # 数据集标题
    year = db.Column(db.Integer, nullable=False, index=True)            # 年份
    author = db.Column(db.String(150), nullable=False)                  # 作者/课题组
    doi = db.Column(db.String(100), nullable=True)                      # DOI 或文献引用
    description = db.Column(db.Text, nullable=False)                    # 描述
    data_source_type = db.Column(db.String(20), default='github')      # 'github' 或 'local'
    github_url = db.Column(db.String(300), nullable=True)               # GitHub 文件/Release/Repo 链接
    local_file_path = db.Column(db.String(300), nullable=True)          # 本地相对存储路径（uploads/xxx.csv）
    download_count = db.Column(db.Integer, default=0)                   # 汇总下载计数
    site_code = db.Column(db.String(50), nullable=True, default='US-Atq') # 样点代号
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 关联
    keywords = db.relationship('Keyword', secondary=dataset_keywords, backref=db.backref('datasets', lazy='dynamic'))

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
    provider = db.Column(db.String(50), default='aliyun_oss') # 'aliyun_oss', 's3', 'minio'
    endpoint = db.Column(db.String(200), nullable=False)      # 如 oss-cn-beijing.aliyuncs.com
    bucket_name = db.Column(db.String(100), nullable=False)   # 存储桶名称
    access_key_id = db.Column(db.String(150), nullable=False)
    access_key_secret = db.Column(db.String(200), nullable=False)
    custom_domain = db.Column(db.String(200), nullable=True)  # 自定义 CDN 或加速域名
    is_active = db.Column(db.Boolean, default=True)           # 是否启用
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
