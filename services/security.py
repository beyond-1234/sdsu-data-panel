import hashlib
import hmac
from werkzeug.security import generate_password_hash, check_password_hash

# Dedicated pepper key for scientific password security hardening
PEPPER_SALT = b"SDSU_MICROBIAL_SECURITY_PEPPER_KEY_2026_#98"

def _apply_pepper(password: str) -> str:
    """
    Applies HMAC-SHA512 based pepper obfuscation to prevent rainbow table or dictionary attacks.
    """
    if not password:
        return ""
    h = hmac.new(PEPPER_SALT, password.encode('utf-8'), hashlib.sha512)
    return h.hexdigest()

def secure_hash_password(raw_password: str) -> str:
    """
    Dual-layer password encryption:
    Layer 1: HMAC-SHA512 pepper obfuscation with system secret key.
    Layer 2: Werkzeug adaptive salt hashing (pbkdf2:sha256 / scrypt).
    """
    peppered = _apply_pepper(raw_password)
    return generate_password_hash(peppered)

def verify_secure_password(stored_password_hash: str, raw_password: str) -> bool:
    """
    Verifies password using dual-layer verification with legacy fallback support.
    """
    if not stored_password_hash or not raw_password:
        return False

    peppered = _apply_pepper(raw_password)
    if check_password_hash(stored_password_hash, peppered):
        return True

    # Legacy fallback for backward compatibility
    return check_password_hash(stored_password_hash, raw_password)
