import os
import json
import random
import hashlib
import aiohttp
import asyncio
from Crypto.Cipher import AES
from .crypto import (
    a32_to_str,
    str_to_a32,
    base64_url_encode,
    base64_url_decode,
    aes_cbc_encrypt,
    aes_cbc_decrypt,
    aes_cbc_encrypt_a32,
    aes_cbc_decrypt_a32,
    prepare_key,
    prepare_key_v2,
    username_hash,
    get_chunks,
    encrypt_key,
    decrypt_key,
    mpi_to_int,
    modular_inverse,
)
from .errors import RequestError


class Mega:
    """Mega.nz API client with support for login, upload, and streaming upload from Telegram."""

    API_URL = "https://g.api.mega.co.nz/cs"

    def __init__(self):
        self.session_id = None
        self.master_key = None
        self.rsa_private_key = None
        self.root_id = None
        self.sequence_number = random.randint(0, 0xFFFFFFFF)
        self._session = None

    async def _get_session(self):
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def _api_request(self, data):
        """Make a request to the Mega API with retry logic."""
        params = {"id": self.sequence_number}
        self.sequence_number += 1
        if self.session_id:
            params["sid"] = self.session_id

        session = await self._get_session()

        for attempt in range(5):
            try:
                async with session.post(
                    self.API_URL,
                    params=params,
                    json=[data],
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    json_resp = await resp.json()

                    if isinstance(json_resp, int):
                        if json_resp == -3:  # EAGAIN
                            await asyncio.sleep(2 ** attempt)
                            continue
                        raise RequestError(json_resp)

                    if isinstance(json_resp, list) and len(json_resp) > 0:
                        result = json_resp[0]
                        if isinstance(result, int) and result < 0:
                            raise RequestError(result)
                        return result

                    return json_resp
            except (aiohttp.ClientError, asyncio.TimeoutError):
                if attempt == 4:
                    raise
                await asyncio.sleep(2 ** attempt)

    async def login(self, email: str, password: str):
        """Login to Mega.nz account."""
        email = email.lower().strip()

        # First try v2 auth (salt-based)
        try:
            resp = await self._api_request({"a": "us0", "user": email})
            if isinstance(resp, dict) and "s" in resp:
                return await self._login_v2(email, password, resp)
        except RequestError:
            pass

        # Fallback to v1 auth
        return await self._login_v1(email, password)

    async def _login_v1(self, email: str, password: str):
        """Legacy v1 login."""
        password_a32 = str_to_a32(password.encode("utf-8"))
        password_key = prepare_key(password_a32)
        uh = base64_url_encode(username_hash(password_key, email))

        resp = await self._api_request({"a": "us", "user": email, "uh": uh})
        return await self._process_login_response(resp, password_key)

    async def _login_v2(self, email: str, password: str, us0_resp: dict):
        """V2 login with PBKDF2 salt."""
        salt = base64_url_decode(us0_resp["s"])

        # Derive key using PBKDF2
        derived = hashlib.pbkdf2_hmac(
            "sha512", password.encode("utf-8"), salt, 100000, dklen=32
        )
        password_key = str_to_a32(derived[:16])
        uh = base64_url_encode(derived[16:])

        resp = await self._api_request({"a": "us", "user": email, "uh": uh})
        return await self._process_login_response(resp, password_key)

    async def _process_login_response(self, resp, password_key):
        """Process login response and extract session keys."""
        if not isinstance(resp, dict):
            raise RequestError(-15)

        encrypted_master_key = base64_url_decode(resp["k"])
        self.master_key = decrypt_key(str_to_a32(encrypted_master_key), password_key)

        if "tsid" in resp:
            tsid = base64_url_decode(resp["tsid"])
            key = a32_to_str(self.master_key)
            cipher = AES.new(key, AES.MODE_CBC, b"\x00" * 16)
            decrypted = cipher.decrypt(tsid[:16])
            if decrypted == tsid[-16:]:
                self.session_id = resp["tsid"]
        elif "csid" in resp:
            encrypted_rsa = base64_url_decode(resp["privk"])
            rsa_data = a32_to_str(decrypt_key(str_to_a32(encrypted_rsa), self.master_key))

            # Parse RSA private key components
            privk = rsa_data
            p_len = (privk[0] * 256 + privk[1] + 7) // 8
            p = mpi_to_int(privk[0:])
            privk = privk[2 + p_len:]
            q_len = (privk[0] * 256 + privk[1] + 7) // 8
            q = mpi_to_int(privk[0:])
            privk = privk[2 + q_len:]
            d_len = (privk[0] * 256 + privk[1] + 7) // 8
            d = mpi_to_int(privk[0:])

            self.rsa_private_key = (p, q, d)

            encrypted_sid = mpi_to_int(base64_url_decode(resp["csid"]))
            n = p * q
            phi = modular_inverse(encrypted_sid, n)
            sid = phi.to_bytes((phi.bit_length() + 7) // 8, "big")
            self.session_id = base64_url_encode(sid[:43])

        # Get root folder ID
        files = await self._api_request({"a": "f", "c": 1, "r": 1})
        for node in files.get("f", []):
            if node.get("t") == 2:  # Cloud Drive root
                self.root_id = node["h"]
                break

        return self.session_id is not None

    async def get_storage_info(self):
        """Get storage quota information."""
        try:
            resp = await self._api_request({"a": "uq", "xfer": 1, "strg": 1})
            if isinstance(resp, dict):
                total = resp.get("mstrg", 0)
                used = resp.get("cstrg", 0)
                free = max(0, total - used)
                return {
                    "total": total,
                    "used": used,
                    "free": free,
                }
        except Exception:
            pass
        return {"total": 0, "used": 0, "free": 0}

    async def find_or_create_folder(self, folder_path: str):
        """Find or create a folder by path. Returns the folder node handle."""
        if not folder_path or folder_path == "/" or folder_path == "/Root":
            return self.root_id

        # Get current file listing
        files = await self._api_request({"a": "f", "c": 1, "r": 1})
        nodes = files.get("f", [])

        # Build folder tree
        folder_map = {}
        for node in nodes:
            if node.get("t") in (0, 1):  # File or Folder
                try:
                    key_data = node.get("k", "")
                    if ":" in key_data:
                        key_part = key_data.split(":")[1]
                        k = decrypt_key(str_to_a32(base64_url_decode(key_part)), self.master_key)
                        attrs_data = base64_url_decode(node.get("a", ""))
                        attr_key = k[:4] if len(k) >= 4 else k
                        attrs = aes_cbc_decrypt(attrs_data, attr_key)
                        # Strip padding and parse JSON
                        attrs_str = attrs.decode("utf-8", errors="ignore")
                        if "MEGA{" in attrs_str:
                            json_start = attrs_str.index("MEGA{") + 4
                            json_data = attrs_str[json_start:]
                            # Find the end of JSON
                            brace_count = 0
                            end_idx = 0
                            for i, c in enumerate(json_data):
                                if c == "{":
                                    brace_count += 1
                                elif c == "}":
                                    brace_count -= 1
                                    if brace_count == 0:
                                        end_idx = i + 1
                                        break
                            json_data = json_data[:end_idx]
                            attr_dict = json.loads(json_data)
                            name = attr_dict.get("n", "")
                            if node.get("t") == 1:  # Folder
                                folder_map[node["h"]] = {
                                    "name": name,
                                    "parent": node.get("p", ""),
                                    "handle": node["h"],
                                }
                except Exception:
                    continue

        # Navigate/create the path
        parts = [p for p in folder_path.strip("/").split("/") if p]
        current_parent = self.root_id

        for part in parts:
            found = False
            for fh, finfo in folder_map.items():
                if finfo["name"] == part and finfo["parent"] == current_parent:
                    current_parent = fh
                    found = True
                    break

            if not found:
                # Create folder
                key = [random.randint(0, 0xFFFFFFFF) for _ in range(4)]
                encrypted_key = encrypt_key(key, self.master_key)
                attrs = json.dumps({"n": part}).encode("utf-8")
                attrs = b"MEGA" + attrs
                # Pad to 16-byte boundary
                pad_len = (16 - len(attrs) % 16) % 16
                attrs += b"\x00" * pad_len
                encrypted_attrs = aes_cbc_encrypt(attrs, key)

                resp = await self._api_request(
                    {
                        "a": "p",
                        "t": current_parent,
                        "n": [
                            {
                                "h": "xxxxxxxx",
                                "t": 1,
                                "a": base64_url_encode(encrypted_attrs),
                                "k": base64_url_encode(a32_to_str(encrypted_key)),
                            }
                        ],
                    }
                )
                new_nodes = resp.get("f", [])
                if new_nodes:
                    current_parent = new_nodes[0]["h"]
                    folder_map[current_parent] = {
                        "name": part,
                        "parent": current_parent,
                        "handle": current_parent,
                    }
                else:
                    raise Exception(f"Failed to create folder: {part}")

        return current_parent

    async def upload_from_stream(self, read_func, file_size: int, filename: str, dest_folder_id: str = None, callback=None):
        """
        Upload a file to Mega from a streaming read function.
        
        Args:
            read_func: Async callable that returns bytes when called with a count.
            file_size: Total size of the file in bytes.
            filename: Name for the uploaded file.
            dest_folder_id: Destination folder handle (defaults to root).
            callback: Async callback(current, total) for progress reporting.
            
        Returns:
            str: Public Mega.nz file URL, or None on failure.
        """
        if dest_folder_id is None:
            dest_folder_id = self.root_id

        # Request upload URL
        resp = await self._api_request({"a": "u", "s": file_size})
        upload_url = resp["p"]

        # Generate file encryption key (6 x 32-bit random values)
        ul_key = [random.randint(0, 0xFFFFFFFF) for _ in range(6)]

        # AES-CTR key and nonce
        aes_key = a32_to_str([ul_key[0] ^ ul_key[4], ul_key[1] ^ ul_key[5], ul_key[2] ^ ul_key[4], ul_key[3] ^ ul_key[5]])
        aes_ctr_nonce = a32_to_str([ul_key[4], ul_key[5], 0, 0])

        # CBC-MAC for integrity
        mac_key = a32_to_str([ul_key[0] ^ ul_key[4], ul_key[1] ^ ul_key[5], ul_key[2] ^ ul_key[4], ul_key[3] ^ ul_key[5]])
        file_mac = [0, 0, 0, 0]

        session = await self._get_session()
        completion_handle = None
        uploaded_bytes = 0

        for chunk_start, chunk_size in get_chunks(file_size):
            # Read chunk from stream
            chunk_data = b""
            remaining = chunk_size
            while remaining > 0:
                read_size = min(remaining, 1024 * 1024)  # Read in 1MB sub-chunks
                data = await read_func(read_size)
                if not data:
                    break
                chunk_data += data
                remaining -= len(data)

            if not chunk_data:
                break

            # Calculate chunk MAC
            chunk_mac = [ul_key[4], ul_key[5], ul_key[4], ul_key[5]]
            for i in range(0, len(chunk_data), 16):
                block = chunk_data[i : i + 16]
                if len(block) < 16:
                    block += b"\x00" * (16 - len(block))
                block_a32 = str_to_a32(block)
                chunk_mac = [chunk_mac[j] ^ block_a32[j] for j in range(4)]
                chunk_mac = aes_cbc_encrypt_a32(chunk_mac, str_to_a32(mac_key))

            file_mac = [file_mac[j] ^ chunk_mac[j] for j in range(4)]

            # Encrypt chunk with AES-CTR
            ctr_value = int.from_bytes(aes_ctr_nonce, "big") + (chunk_start // 16)
            ctr_bytes = ctr_value.to_bytes(16, "big")
            cipher = AES.new(aes_key, AES.MODE_CTR, nonce=b"", initial_value=ctr_bytes)
            encrypted_chunk = cipher.encrypt(chunk_data)

            # Upload chunk
            upload_chunk_url = f"{upload_url}/{chunk_start}"
            for attempt in range(5):
                try:
                    async with session.post(
                        upload_chunk_url,
                        data=encrypted_chunk,
                        timeout=aiohttp.ClientTimeout(total=None),
                    ) as resp:
                        resp_text = await resp.text()
                        if resp.status == 200 and resp_text and len(resp_text) > 10:
                            completion_handle = resp_text
                        break
                except (aiohttp.ClientError, asyncio.TimeoutError):
                    if attempt == 4:
                        raise
                    await asyncio.sleep(2 ** attempt)

            uploaded_bytes += len(chunk_data)
            if callback:
                await callback(uploaded_bytes, file_size)

        if not completion_handle:
            return None

        # Final file MAC
        file_mac = aes_cbc_encrypt_a32(file_mac, str_to_a32(mac_key))
        meta_mac = [file_mac[0] ^ file_mac[1], file_mac[2] ^ file_mac[3]]

        # Prepare file attributes
        attrs = json.dumps({"n": filename}).encode("utf-8")
        attrs = b"MEGA" + attrs
        pad_len = (16 - len(attrs) % 16) % 16
        attrs += b"\x00" * pad_len

        # Encrypt attrs with the file key
        file_key_for_attrs = [ul_key[0] ^ ul_key[4], ul_key[1] ^ ul_key[5], ul_key[2] ^ ul_key[4], ul_key[3] ^ ul_key[5]]
        encrypted_attrs = aes_cbc_encrypt(attrs, file_key_for_attrs)

        # Build the complete key
        key = [
            ul_key[0],
            ul_key[1],
            ul_key[2],
            ul_key[3],
            ul_key[4],
            ul_key[5],
            meta_mac[0],
            meta_mac[1],
        ]
        encrypted_key = encrypt_key(key, self.master_key)

        # Create file node
        resp = await self._api_request(
            {
                "a": "p",
                "t": dest_folder_id,
                "n": [
                    {
                        "h": completion_handle,
                        "t": 0,
                        "a": base64_url_encode(encrypted_attrs),
                        "k": base64_url_encode(a32_to_str(encrypted_key)),
                    }
                ],
            }
        )

        # Generate public link
        new_nodes = resp.get("f", [])
        if new_nodes:
            file_handle = new_nodes[0]["h"]
            # Export the file (make it public)
            await self._api_request({"a": "l", "n": file_handle})

            # Build the decryption key for the URL
            exported_key = [
                ul_key[0] ^ ul_key[4],
                ul_key[1] ^ ul_key[5],
                ul_key[2] ^ ul_key[4],
                ul_key[3] ^ ul_key[5],
                ul_key[4],
                ul_key[5],
                meta_mac[0],
                meta_mac[1],
            ]
            key_str = base64_url_encode(a32_to_str(exported_key))
            return f"https://mega.nz/file/{file_handle}#{key_str}"

        return None
