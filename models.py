from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from services.security import secure_hash_password, verify_secure_password

db = SQLAlchemy()

# Many-to-many relationship: Datasets & Keywords
dataset_keywords = db.Table('dataset_keywords',
    db.Column('dataset_id', db.Integer, db.ForeignKey('datasets.id'), primary_key=True),
    db.Column('keyword_id', db.Integer, db.ForeignKey('keywords.id'), primary_key=True)
)

# Many-to-many relationship: Datasets & Standardized Scientific Variables
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
    role = db.Column(db.String(20), default='user')  # 'admin' or 'user'
    institution = db.Column(db.String(150))          # Research institution
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = secure_hash_password(password)

    def check_password(self, password):
        return verify_secure_password(self.password_hash, password)

# ----------------- 1. Standardized Scientific Variables Dictionary -----------------
class VariableDefinition(db.Model):
    __tablename__ = 'variable_definitions'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False, index=True) # e.g. "MBC", "MBN", "SOC"
    display_name = db.Column(db.String(120), nullable=False)                 # Display name
    display_name_en = db.Column(db.String(120), nullable=True)               # English display name
    category = db.Column(db.String(50), index=True)                          # e.g. "Gas Flux", "Microbial Pool", "Soil Physics"
    unit = db.Column(db.String(30))                                          # e.g. "mmol kg-1", "g C m-2"
    description = db.Column(db.String(255))                                  # Scientific description
    description_en = db.Column(db.String(255))                               # English description

    def get_name(self, lang='en'):
        return self.display_name_en or self.display_name

    def get_desc(self, lang='en'):
        return self.description_en or self.description or ''

# ----------------- 2. Geographic Site & Region Table (Spatial & Biome) -----------------
class SiteLocation(db.Model):
    __tablename__ = 'site_locations'
    id = db.Column(db.Integer, primary_key=True)
    site_code = db.Column(db.String(50), unique=True, index=True)  # e.g. "Global-Terrestrial", "US-Atq"
    site_name = db.Column(db.String(120), nullable=False)          # Site name
    country = db.Column(db.String(60), index=True)
    latitude = db.Column(db.Float, nullable=False, index=True)     # Latitude
    longitude = db.Column(db.Float, nullable=False, index=True)    # Longitude
    elevation = db.Column(db.Float)                                # Elevation (m)
    biome = db.Column(db.String(80), index=True)                   # e.g. "Tundra", "Wetland", "Forest"

# ----------------- 3. Dataset Master Table (Multi-dimensional Scientific Package) -----------------
class Dataset(db.Model):
    __tablename__ = 'datasets'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False, index=True)       # Dataset title
    author = db.Column(db.String(150), nullable=False)                  # Author / research group
    doi = db.Column(db.String(100), nullable=True)                      # DOI or citation
    description = db.Column(db.Text, nullable=False)                    # Description
    
    # Spatial dimension
    site_id = db.Column(db.Integer, db.ForeignKey('site_locations.id'), nullable=True, index=True)
    site = db.relationship('SiteLocation', backref=db.backref('datasets', lazy='dynamic'))
    spatial_scale = db.Column(db.String(30), default='Point')           # Point, Regional, Global
    site_code = db.Column(db.String(50), nullable=True, default='Global-Terrestrial')

    # Temporal coverage & resolution
    year = db.Column(db.Integer, nullable=False, index=True)            # Representative year
    start_date = db.Column(db.Date, nullable=True, index=True)          # Start date
    end_date = db.Column(db.Date, nullable=True, index=True)            # End date
    temporal_resolution = db.Column(db.String(30), default='Daily')     # Half-hourly, Daily, Monthly, Yearly

    # Experimental context & data type
    data_type = db.Column(db.String(40), default='Model Simulation')    # Model Simulation, Field Observation, Hybrid
    model_version = db.Column(db.String(50), default='MicrobialDataSystem v1.0')
    scenario = db.Column(db.String(50), default='Historical')           # Control, Warming, Nitrogen Addition, SSP5-8.5
    
    # Vertical depth range (m)
    min_depth = db.Column(db.Float, default=0.0)
    max_depth = db.Column(db.Float, default=1.0)

    # Storage & distribution metadata
    data_source_type = db.Column(db.String(20), default='github')       # 'github', 'local', or 'oss'
    github_url = db.Column(db.String(300), nullable=True)               # GitHub direct link
    local_file_path = db.Column(db.String(300), nullable=True)          # Local storage path
    download_count = db.Column(db.Integer, default=0)                   # Total download count
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    keywords = db.relationship('Keyword', secondary=dataset_keywords, backref=db.backref('datasets', lazy='dynamic'))
    variables = db.relationship('VariableDefinition', secondary=dataset_variables, backref=db.backref('datasets', lazy='dynamic'))

class Keyword(db.Model):
    __tablename__ = 'keywords'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False, index=True)

class DownloadLog(db.Model):
    __tablename__ = 'download_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True) # Guest if NULL
    dataset_id = db.Column(db.Integer, db.ForeignKey('datasets.id'), nullable=False)
    download_type = db.Column(db.String(20))   # 'github_redirect', 'local_download', or 'oss_download'
    ip_address = db.Column(db.String(45))      # Client IP
    user_agent = db.Column(db.String(255))     # User agent
    institution = db.Column(db.String(150))    # Registered institution
    purpose = db.Column(db.String(200))        # Research purpose
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('downloads', lazy='dynamic'))
    dataset = db.relationship('Dataset', backref=db.backref('logs', lazy='dynamic'))

class StorageConfig(db.Model):
    __tablename__ = 'storage_configs'
    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(50), default='aliyun_oss') # 'aliyun_oss', 'aws_s3', 'minio'
    endpoint = db.Column(db.String(200), nullable=False)      # e.g. oss-cn-beijing.aliyuncs.com
    bucket_name = db.Column(db.String(100), nullable=False)   # Bucket name
    access_key_id = db.Column(db.String(150), nullable=False)
    access_key_secret = db.Column(db.String(200), nullable=False)
    custom_domain = db.Column(db.String(200), nullable=True)  # Custom CDN / accelerator domain
    is_active = db.Column(db.Boolean, default=True)           # Active flag
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
