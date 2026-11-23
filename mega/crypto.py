import struct
import base64
from Crypto.Cipher import AES
import hashlib
import os


def a32_to_str(a):
    """Convert array of 32-bit ints to byte string."""
    return struct.pack(">%dI" % len(a), *a)


def str_to_a32(b):
    """Convert byte string to array of 32-bit ints."""
    if isinstance(b, str):
        b = b.encode("utf-8")
    if len(b) % 4:
        b += b"\x00" * (4 - len(b) % 4)
    return struct.unpack(">%dI" % (len(b) // 4), b)


def base64_url_encode(data):
    """Mega-style base64 URL encoding."""
    return base64.b64encode(data, b"-_").decode("utf-8").rstrip("=")


def base64_url_decode(data):
    """Mega-style base64 URL decoding."""
    data += "=" * ((4 - len(data) % 4) % 4)
    return base64.b64decode(data, b"-_")


def aes_cbc_encrypt(data, key):
    """AES CBC encryption with zero IV."""
    encryptor = AES.new(a32_to_str(key), AES.MODE_CBC, b"\x00" * 16)
    return encryptor.encrypt(data)


def aes_cbc_decrypt(data, key):
    """AES CBC decryption with zero IV."""
    decryptor = AES.new(a32_to_str(key), AES.MODE_CBC, b"\x00" * 16)
    return decryptor.decrypt(data)


def aes_cbc_encrypt_a32(data, key):
    """AES CBC encrypt array of 32-bit ints."""
    return str_to_a32(aes_cbc_encrypt(a32_to_str(data), key))


def aes_cbc_decrypt_a32(data, key):
    """AES CBC decrypt array of 32-bit ints."""
    return str_to_a32(aes_cbc_decrypt(a32_to_str(data), key))


def prepare_key(arr):
    """Prepare encryption key using AES-ECB chaining."""
    pkey = [0x93C467E3, 0x7DB0C7A4, 0xD1BE3F81, 0x0152CB56]
    for i in range(0, len(arr), 4):
        key = [0, 0, 0, 0]
        for j in range(min(4, len(arr) - i)):
            key[j] = arr[i + j]
        pkey = aes_cbc_encrypt_a32(pkey, key)
    return pkey


def prepare_key_v2(password):
    """Prepare key using PBKDF2 (Mega v2 auth)."""
    password_bytes = password.encode("utf-8")
    derived = hashlib.pbkdf2_hmac("sha512", password_bytes, password_bytes, 100000, dklen=32)
    return str_to_a32(derived[:16])


def username_hash(aes_key, email):
    """Generate username hash for Mega login."""
    email_a32 = str_to_a32(email.lower())
    h32 = [0, 0, 0, 0]
    for i in range(len(email_a32)):
        h32[i % 4] ^= email_a32[i]
    for _ in range(0x4000):
        h32 = aes_cbc_encrypt_a32(h32, aes_key)
    return a32_to_str([h32[0], h32[2]])


def get_chunks(size):
    """Generate chunk sizes for Mega upload (progressive sizing)."""
    p = 0
    s = 0x20000  # Start at 128KB
    while p + s < size:
        yield p, s
        if s < 0x100000:  # Increase chunk size up to 1MB
            s += 0x20000
        p += s
    yield p, size - p


def encrypt_key(a, key):
    """Encrypt a key array."""
    return sum(
        (aes_cbc_encrypt_a32(a[i : i + 4], key) for i in range(0, len(a), 4)), ()
    )


def decrypt_key(a, key):
    """Decrypt a key array."""
    return sum(
        (aes_cbc_decrypt_a32(a[i : i + 4], key) for i in range(0, len(a), 4)), ()
    )


def mpi_to_int(s):
    """Convert MPI (multi-precision integer) format to Python int."""
    return int.from_bytes(s[2 : 2 + (s[0] * 256 + s[1] + 7) // 8], "big")


def modular_inverse(a, m):
    """Extended Euclidean algorithm for modular inverse."""
    if a < 0:
        a = a % m
    g, x, _ = _extended_gcd(a, m)
    if g != 1:
        raise ValueError("Modular inverse does not exist")
    return x % m


def _extended_gcd(a, b):
    if a == 0:
        return b, 0, 1
    g, x, y = _extended_gcd(b % a, a)
    return g, y - (b // a) * x, x
