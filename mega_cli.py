import asyncio
import os
import re
import time
from typing import Tuple, Dict


async def run_cmd(cmd_list: list, timeout: int = 60) -> Tuple[int, str]:
    """Execute a system command asynchronously with a strict timeout."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd_list,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            return -1, f"Command timed out after {timeout}s"

        out = stdout.decode("utf-8", errors="ignore").strip()
        err = stderr.decode("utf-8", errors="ignore").strip()
        if out and err:
            output = f"{out}\n{err}"
        elif out:
            output = out
        else:
            output = err
        return proc.returncode, output
    except Exception as e:
        return -1, str(e)


class MegaCLI:
    """Wrapper for official MEGAcmd CLI tools."""

    @staticmethod
    async def is_logged_in() -> bool:
        """Check if MEGAcmd is already logged into an account."""
        code, out = await run_cmd(["mega-whoami"], timeout=10)
        return code == 0 and "@" in out

    @staticmethod
    async def login(email: str, password: str) -> Tuple[bool, str]:
        """Log in to MEGA account."""
        if not email or not password:
            return False, "MEGA_EMAIL or MEGA_PASSWORD is missing in config."

        code, out = await run_cmd(["mega-whoami"], timeout=10)
        if code == 0 and email.lower() in out.lower():
            return True, f"Already logged in as {email}"

        code, out = await run_cmd(["mega-login", email, password], timeout=30)
        if code == 0:
            return True, "Login successful."
        return False, out

    @staticmethod
    async def get_storage() -> Dict[str, str]:
        """Get storage usage via mega-df."""
        code, out = await run_cmd(["mega-df", "-h"], timeout=15)
        stats = {"total": "N/A", "free": "N/A", "used": "N/A"}
        if code == 0:
            for line in out.splitlines():
                line_lower = line.lower()
                if "total" in line_lower:
                    stats["total"] = line.split(":")[-1].strip()
                elif "free" in line_lower:
                    stats["free"] = line.split(":")[-1].strip()
                elif "used" in line_lower:
                    stats["used"] = line.split(":")[-1].strip()
        return stats

    @staticmethod
    async def upload_file(local_path: str, remote_folder: str) -> Tuple[bool, str, str, str]:
        """
        Uploads a local file to remote_folder on MEGA using official mega-put.
        Auto-deduplicates filenames with timestamp so no existing file is ever overwritten.
        
        Returns:
            (success: bool, mega_link: str, message: str, final_file_name: str)
        """
        if not os.path.exists(local_path):
            return False, "https://mega.nz/fm", "File not found locally.", ""

        file_name = os.path.basename(local_path)

        if not remote_folder.startswith("/"):
            remote_folder = "/" + remote_folder
        remote_folder = remote_folder.rstrip("/")

        # Step 1: Ensure remote directory exists
        print(f"📁 Ensuring remote directory exists: {remote_folder}")
        await run_cmd(["mega-mkdir", "-p", remote_folder], timeout=15)

        # Step 2: Check if file already exists in remote folder to prevent overwriting
        ls_code, ls_out = await run_cmd(["mega-ls", remote_folder], timeout=10)
        if ls_code == 0:
            existing_files = [line.strip() for line in ls_out.splitlines() if line.strip()]
            if file_name in existing_files:
                base, ext = os.path.splitext(file_name)
                timestamp = int(time.time())
                new_file_name = f"{base}_{timestamp}{ext}"
                new_local_path = os.path.join(os.path.dirname(local_path), new_file_name)
                try:
                    os.rename(local_path, new_local_path)
                    local_path = new_local_path
                    file_name = new_file_name
                    print(f"⚠️ Duplicate found on Mega. Renamed to avoid overwrite: {file_name}")
                except Exception as e:
                    print(f"Rename warning: {e}")

        # Step 3: Upload via mega-put directly into folder
        dest_target = f"{remote_folder}/"
        print(f"⚡ Running mega-put: {local_path} -> {dest_target}")
        put_code, put_out = await run_cmd(["mega-put", local_path, dest_target], timeout=1800)
        print(f"📋 mega-put output (code {put_code}):\n{put_out}")

        if put_code != 0:
            return False, "https://mega.nz/fm", f"mega-put error: {put_out}", file_name

        print(f"✅ Successfully transferred to Mega: {remote_folder}/{file_name}")
        return True, "https://mega.nz/fm", "Success", file_name
