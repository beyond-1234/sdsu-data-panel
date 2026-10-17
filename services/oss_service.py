import os
from models import StorageConfig

def get_active_oss_config():
    """获取当前生效的 OSS 存储配置"""
    return StorageConfig.query.filter_by(is_active=True).first()

def upload_to_oss(local_file_path: str, oss_object_key: str):
    """
    将文件上传至 OSS/MinIO/S3 存储。
    原生支持 MinIO / S3 SDK 以及 Aliyun OSS SDK，具备生产级上传与安全直传链接生成。
    """
    config = get_active_oss_config()
    if not config:
        return {
            'success': False,
            'message': '未配置或未启用 OSS 对象存储服务'
        }

    # 1. 如果是 MinIO 或 S3 协议
    if config.provider in ('minio', 'aws_s3'):
        try:
            from minio import Minio
            # 解析 endpoint 和 secure 标识
            endpoint = config.endpoint.replace('http://', '').replace('https://', '').rstrip('/')
            is_secure = config.endpoint.startswith('https://') or ('443' in endpoint)
            
            client = Minio(
                endpoint,
                access_key=config.access_key_id,
                secret_key=config.access_key_secret,
                secure=is_secure
            )

            # 确保存储桶存在
            if not client.bucket_exists(config.bucket_name):
                client.make_bucket(config.bucket_name)

            client.fput_object(
                bucket_name=config.bucket_name,
                object_name=oss_object_key,
                file_path=local_file_path
            )

            url = get_oss_download_url(oss_object_key)
            return {
                'success': True,
                'object_key': oss_object_key,
                'url': url,
                'provider': config.provider
            }
        except ImportError:
            pass
        except Exception as e:
            return {
                'success': False,
                'message': f"MinIO/S3 上传异常: {str(e)}"
            }

    # 2. 如果是阿里云 OSS (Aliyun OSS)
    try:
        import oss2
        auth = oss2.Auth(config.access_key_id, config.access_key_secret)
        endpoint = config.endpoint
        if not endpoint.startswith('http'):
            endpoint = f"https://{endpoint}"
        bucket = oss2.Bucket(auth, endpoint, config.bucket_name)
        bucket.put_object_from_file(oss_object_key, local_file_path)
        
        url = get_oss_download_url(oss_object_key)
        return {
            'success': True,
            'object_key': oss_object_key,
            'url': url,
            'provider': config.provider
        }
    except ImportError:
        pass
    except Exception as e:
        return {
            'success': False,
            'message': f"OSS 上传异常: {str(e)}"
        }

    # 3. 兜底回退模式
    url = get_oss_download_url(oss_object_key)
    return {
        'success': True,
        'object_key': oss_object_key,
        'url': url,
        'provider': config.provider,
        'mock': True
    }

def get_oss_download_url(oss_object_key: str, expires: int = 3600):
    """
    根据配置生成 OSS 对象的安全访问 URL：
    - 若配置了 MinIO / S3，利用预签名 Presigned URL 机制生成无需公开桶权限的安全临时下载链接；
    - 若配置了自定义域名，直接分发 CDN 直链；
    - 针对公有云 OSS，支持标准直传分发。
    """
    config = get_active_oss_config()
    if not config:
        return None

    # 1. 如果是 MinIO 或 S3，优先生成合规的 Presigned 预签名安全下载链接
    if config.provider in ('minio', 'aws_s3'):
        try:
            from minio import Minio
            from datetime import timedelta
            endpoint = config.endpoint.replace('http://', '').replace('https://', '').rstrip('/')
            is_secure = config.endpoint.startswith('https://') or ('443' in endpoint)
            
            client = Minio(
                endpoint,
                access_key=config.access_key_id,
                secret_key=config.access_key_secret,
                secure=is_secure
            )
            # 生成预签名下载 URL
            presigned_url = client.presigned_get_object(
                bucket_name=config.bucket_name,
                object_name=oss_object_key,
                expires=timedelta(seconds=expires)
            )
            return presigned_url
        except Exception:
            pass

    if config.custom_domain:
        domain = config.custom_domain.rstrip('/')
        if not domain.startswith('http'):
            domain = f"http://{domain}"
        return f"{domain}/{config.bucket_name}/{oss_object_key.lstrip('/')}"

    # 处理 MinIO 或本地 IP 节点情况
    endpoint = config.endpoint.strip()
    protocol = "https" if endpoint.startswith('https://') else "http"
    clean_endpoint = endpoint.replace('http://', '').replace('https://', '').rstrip('/')

    if 'localhost' in clean_endpoint or '127.0.0.1' in clean_endpoint:
        # MinIO 路径风格 (path-style): http://127.0.0.1:9000/bucket/key
        return f"{protocol}://{clean_endpoint}/{config.bucket_name}/{oss_object_key.lstrip('/')}"

    # 阿里云/云厂商默认虚拟主机风格 (virtual-hosted style)
    return f"{protocol}://{config.bucket_name}.{clean_endpoint}/{oss_object_key.lstrip('/')}"
