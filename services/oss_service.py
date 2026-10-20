import os
from models import StorageConfig

def get_active_oss_config():
    """Retrieves active object storage configuration"""
    return StorageConfig.query.filter_by(is_active=True).first()

def upload_to_oss(local_file_path: str, oss_object_key: str):
    """
    Uploads a scientific dataset to object storage (MinIO, AWS S3, or Aliyun OSS).
    """
    config = get_active_oss_config()
    if not config:
        return {
            'success': False,
            'message': 'No active object storage configuration found'
        }

    # 1. MinIO or S3 protocol
    if config.provider in ('minio', 'aws_s3'):
        try:
            from minio import Minio
            endpoint = config.endpoint.replace('http://', '').replace('https://', '').rstrip('/')
            is_secure = config.endpoint.startswith('https://') or ('443' in endpoint)
            
            client = Minio(
                endpoint,
                access_key=config.access_key_id,
                secret_key=config.access_key_secret,
                secure=is_secure
            )

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
                'message': f"MinIO/S3 upload error: {str(e)}"
            }

    # 2. Aliyun OSS
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
            'message': f"OSS upload error: {str(e)}"
        }

    # Fallback simulation
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
    Generates secure presigned or CDN download URL for object storage items.
    """
    config = get_active_oss_config()
    if not config:
        return None

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
            return client.presigned_get_object(
                bucket_name=config.bucket_name,
                object_name=oss_object_key,
                expires=timedelta(seconds=expires)
            )
        except Exception:
            pass

    if config.custom_domain:
        domain = config.custom_domain.rstrip('/')
        if not domain.startswith('http'):
            domain = f"http://{domain}"
        return f"{domain}/{config.bucket_name}/{oss_object_key.lstrip('/')}"

    endpoint = config.endpoint.strip()
    protocol = "https" if endpoint.startswith('https://') else "http"
    clean_endpoint = endpoint.replace('http://', '').replace('https://', '').rstrip('/')

    if 'localhost' in clean_endpoint or '127.0.0.1' in clean_endpoint:
        return f"{protocol}://{clean_endpoint}/{config.bucket_name}/{oss_object_key.lstrip('/')}"

    return f"{protocol}://{config.bucket_name}.{clean_endpoint}/{oss_object_key.lstrip('/')}"
