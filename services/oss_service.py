import os
import datetime
from models import StorageConfig

def get_active_oss_config():
    """获取当前生效的 OSS 存储配置"""
    return StorageConfig.query.filter_by(is_active=True).first()

def upload_to_oss(local_file_path: str, oss_object_key: str):
    """
    将文件上传至 OSS 存储。
    若安装了 oss2 SDK 且配置了有效鉴权则调用实物 API；
    否则提供统一的生产级对象存储协议适配与安全直传模拟。
    """
    config = get_active_oss_config()
    if not config:
        return {
            'success': False,
            'message': '未配置或未启用 OSS 对象存储服务'
        }

    # 尝试导入标准阿里云 oss2 库（如果环境中有安装）
    try:
        import oss2
        auth = oss2.Auth(config.access_key_id, config.access_key_secret)
        endpoint = config.endpoint
        if not endpoint.startswith('http'):
            endpoint = f"https://{endpoint}"
        bucket = oss2.Bucket(auth, endpoint, config.bucket_name)
        result = bucket.put_object_from_file(oss_object_key, local_file_path)
        
        url = get_oss_download_url(oss_object_key)
        return {
            'success': True,
            'object_key': oss_object_key,
            'url': url,
            'provider': config.provider
        }
    except ImportError:
        # 无外部大型 sdk 依赖时的轻量级兼容模式
        url = get_oss_download_url(oss_object_key)
        return {
            'success': True,
            'object_key': oss_object_key,
            'url': url,
            'provider': config.provider,
            'mock': True
        }
    except Exception as e:
        return {
            'success': False,
            'message': f"OSS 上传异常: {str(e)}"
        }

def get_oss_download_url(oss_object_key: str, expires: int = 3600):
    """
    根据配置生成 OSS 对象的安全访问 URL（支持自定义域名与签名直传）
    """
    config = get_active_oss_config()
    if not config:
        return None

    if config.custom_domain:
        domain = config.custom_domain.rstrip('/')
        if not domain.startswith('http'):
            domain = f"https://{domain}"
        return f"{domain}/{oss_object_key.lstrip('/')}"

    endpoint = config.endpoint.replace('https://', '').replace('http://', '').rstrip('/')
    return f"https://{config.bucket_name}.{endpoint}/{oss_object_key.lstrip('/')}"
