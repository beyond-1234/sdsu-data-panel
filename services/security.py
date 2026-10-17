import hashlib
import hmac
from werkzeug.security import generate_password_hash, check_password_hash

# 专用于科研密码加固的特定安全系统 Salt
PEPPER_SALT = b"SDSU_CLM_MICROBE_SECURITY_PEPPER_KEY_2026_#98"

def _apply_pepper(password: str) -> str:
    """
    对原始明文密码进行基于 HMAC-SHA512 的前置密文混淆与强化加固，
    防止单纯字典彩虹表或基础散列直接碰撞。
    """
    if not password:
        return ""
    h = hmac.new(PEPPER_SALT, password.encode('utf-8'), hashlib.sha512)
    return h.hexdigest()

def secure_hash_password(raw_password: str) -> str:
    """
    双层加固加密：
    第一层：HMAC-SHA512 结合服务器专用 Pepper Key 进行不可逆散列混淆；
    第二层：Werkzeug scrypt/pbkdf2:sha256 随机动态高成本 Salt 哈希。
    """
    peppered = _apply_pepper(raw_password)
    return generate_password_hash(peppered)

def verify_secure_password(stored_password_hash: str, raw_password: str) -> bool:
    """
    密码双层验证与旧版本平滑兼容检查：
    1. 优先使用加固的 Pepper + Hash 进行比对；
    2. 若初始种子数据或历史用户使用的是原始哈希，则自动降级比对，保证平滑过渡。
    """
    if not stored_password_hash or not raw_password:
        return False

    peppered = _apply_pepper(raw_password)
    if check_password_hash(stored_password_hash, peppered):
        return True

    # 兼容历史/旧版未加椒哈希
    return check_password_hash(stored_password_hash, raw_password)
