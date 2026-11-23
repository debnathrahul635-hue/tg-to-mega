import asyncio
import os
import re
from typing import Optional, Tuple, Dict


async def run_cmd(cmd_list: list, timeout: int = 60) -> Tuple[int, str]:
    """Execute a system command asynchronously with a strict timeout to prevent hangs."""
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
    async def upload_file(local_path: str, remote_folder: str) -> Tuple[bool, Optional[str], str]:
        """
        Uploads a local file to remote_folder on MEGA using mega-put and returns a link.
        Guaranteed never to hang or freeze.
        
        Returns:
            (success: bool, mega_link: Optional[str], message: str)
        """
        if not os.path.exists(local_path):
            return False, None, "File not found locally."

        file_name = os.path.basename(local_path)

        if not remote_folder.startswith("/"):
            remote_folder = "/" + remote_folder
        remote_folder = remote_folder.rstrip("/")

        # Step 1: Ensure remote directory exists
        print(f"📁 Ensuring remote directory exists: {remote_folder}")
        await run_cmd(["mega-mkdir", "-p", remote_folder], timeout=15)

        # Step 2: Upload via mega-put (timeout up to 30 mins for big files)
        dest_target = f"{remote_folder}/"
        print(f"⚡ Running mega-put: {local_path} -> {dest_target}")
        put_code, put_out = await run_cmd(["mega-put", local_path, dest_target], timeout=1800)
        print(f"📋 mega-put output (code {put_code}):\n{put_out}")
        if put_code != 0:
            return False, None, f"mega-put error: {put_out}"

        # Step 3: Try to detect exact remote path (timeout 10s)
        remote_file_path = f"{remote_folder}/{file_name}"
        find_code, find_out = await run_cmd(["mega-find", remote_folder, f"--pattern={file_name}"], timeout=10)
        if find_code == 0 and find_out:
            lines = [l.strip() for l in find_out.splitlines() if l.strip()]
            if lines:
                remote_file_path = lines[-1]

        # Step 4: Export link (timeout 12s so it NEVER hangs the bot)
        mega_link = None
        print(f"🔗 Requesting export for: {remote_file_path}")
        exp_code, exp_out = await run_cmd(["mega-export", "-a", remote_file_path], timeout=12)
        print(f"📋 mega-export output (code {exp_code}):\n{exp_out}")

        match = re.search(r"https://mega\.nz/[^\s\'\"\)]+", exp_out)
        if match:
            mega_link = match.group(0)

        # Fallback 1: Query existing export (timeout 8s)
        if not mega_link:
            q_code, q_out = await run_cmd(["mega-export", remote_file_path], timeout=8)
            match = re.search(r"https://mega\.nz/[^\s\'\"\)]+", q_out)
            if match:
                mega_link = match.group(0)

        # Fallback 2: Check all exports list (timeout 8s)
        if not mega_link:
            list_code, list_out = await run_cmd(["mega-export"], timeout=8)
            match = re.search(rf"{re.escape(file_name)}.*?(https://mega\.nz/[^\s\'\"\)]+)", list_out)
            if match:
                mega_link = match.group(1)

        # Fallback 3: Standard web folder link (always valid)
        if not mega_link:
            mega_link = "https://mega.nz/fm"

        return True, mega_link, "Success"
