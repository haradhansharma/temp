"""Custom model fields for the billing app.

This module provides encrypted field types using the cryptography package
for secure storage of sensitive data like bank account numbers.
"""

import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from django.conf import settings
from django.db import models


def get_encryption_key() -> bytes:
    """Get or derive the encryption key from settings.
    
    Uses SB_CRYPTOGRAPHY_KEY from environment if set, otherwise derives
    from Django's SECRET_KEY using PBKDF2.
    
    Returns:
        A 32-byte URL-safe base64-encoded key suitable for Fernet.
    """
    key = getattr(settings, 'CRYPTOGRAPHY_KEY', None)
    
    if key is None:
        # Derive from SECRET_KEY (not ideal for production but works for dev)
        secret = settings.SECRET_KEY.encode('utf-8')
        # Use a fixed salt for deterministic key derivation
        # In production, you should set SB_CRYPTOGRAPHY_KEY directly
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b'SattaBase-Encryption-Salt-v1',  # Fixed salt for consistency
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(secret))
    elif isinstance(key, str):
        # If key is already a valid Fernet key (44 char base64), use it directly
        try:
            # Validate it's a valid base64 key
            key_bytes = base64.urlsafe_b64decode(key)
            if len(key_bytes) == 32:
                key = key.encode('utf-8')
            else:
                raise ValueError("Invalid key length")
        except Exception:
            # If not a valid Fernet key, derive from it
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=b'SattaBase-Encryption-Salt-v1',
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(key.encode('utf-8')))
    
    return key


def get_fernet() -> Fernet:
    """Get a Fernet instance with the current encryption key.
    
    Returns:
        A Fernet instance for encryption/decryption.
    """
    return Fernet(get_encryption_key())


class EncryptedCharField(models.CharField):
    """A CharField that encrypts data at rest using Fernet symmetric encryption.
    
    Data is encrypted before being saved to the database and decrypted when
    retrieved. The encryption uses AES-128 in CBC mode with PKCS7 padding
    and HMAC-SHA256 for authentication.
    
    Usage:
        account_number = EncryptedCharField(max_length=50)
    
    Note:
        The max_length applies to the decrypted (plain text) value.
        The stored encrypted value will be longer.
    """
    
    description = "Encrypted string field"
    
    def __init__(self, *args, **kwargs):
        # Store the original max_length for validation
        self._plain_max_length = kwargs.get('max_length', 255)
        # Encrypted data is longer, so we need more space in DB
        # Fernet adds overhead: base64 encoding + IV + HMAC + version byte
        # Approximate: 60-80 bytes overhead, we'll use 255 as safe default
        kwargs['max_length'] = 255
        super().__init__(*args, **kwargs)
    
    def get_prep_value(self, value):
        """Encrypt the value before saving to database."""
        if value is None or value == '':
            return value
        
        # Encrypt the value
        fernet = get_fernet()
        encrypted = fernet.encrypt(value.encode('utf-8'))
        return encrypted.decode('utf-8')
    
    def from_db_value(self, value, expression, connection):
        """Decrypt the value when loading from database."""
        if value is None or value == '':
            return value
        
        try:
            fernet = get_fernet()
            decrypted = fernet.decrypt(value.encode('utf-8'))
            return decrypted.decode('utf-8')
        except Exception:
            # If decryption fails (e.g., data wasn't encrypted), return as-is
            # This handles migration from unencrypted to encrypted data
            return value
    
    def to_python(self, value):
        """Handle value conversion for Python code."""
        if value is None or value == '':
            return value
        
        # If it looks like encrypted data (Fernet format), try to decrypt
        if isinstance(value, str) and value.startswith('gAAAAAB'):
            try:
                fernet = get_fernet()
                decrypted = fernet.decrypt(value.encode('utf-8'))
                return decrypted.decode('utf-8')
            except Exception:
                return value
        
        return value
    
    def deconstruct(self):
        """Return parameters for field reconstruction in migrations."""
        name, path, args, kwargs = super().deconstruct()
        # Restore the original max_length for migrations
        kwargs['max_length'] = self._plain_max_length
        return name, path, args, kwargs


class EncryptedTextField(models.TextField):
    """A TextField that encrypts data at rest using Fernet symmetric encryption.
    
    Similar to EncryptedCharField but uses TextField for longer content.
    """
    
    description = "Encrypted text field"
    
    def get_prep_value(self, value):
        """Encrypt the value before saving to database."""
        if value is None or value == '':
            return value
        
        fernet = get_fernet()
        encrypted = fernet.encrypt(value.encode('utf-8'))
        return encrypted.decode('utf-8')
    
    def from_db_value(self, value, expression, connection):
        """Decrypt the value when loading from database."""
        if value is None or value == '':
            return value
        
        try:
            fernet = get_fernet()
            decrypted = fernet.decrypt(value.encode('utf-8'))
            return decrypted.decode('utf-8')
        except Exception:
            return value
    
    def to_python(self, value):
        """Handle value conversion for Python code."""
        if value is None or value == '':
            return value
        
        if isinstance(value, str) and value.startswith('gAAAAAB'):
            try:
                fernet = get_fernet()
                decrypted = fernet.decrypt(value.encode('utf-8'))
                return decrypted.decode('utf-8')
            except Exception:
                return value
        
        return value
