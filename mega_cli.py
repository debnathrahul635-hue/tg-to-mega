import asyncio
import os
import re
from typing import Optional, Tuple, Dict


async def run_cmd(cmd_list: list) -> Tuple[int, str]:
    """Execute a system command asynchronously and return (returncode, output)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd_list,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        out = stdout.decode("utf-8", errors="ignore").strip()
        err = stderr.decode("utf-8", errors="ignore").strip()
        # Combine stdout and stderr so no output is missed
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
        code, out = await run_cmd(["mega-whoami"])
        return code == 0 and "@" in out

    @staticmethod
    async def login(email: str, password: str) -> Tuple[bool, str]:
        """Log in to MEGA account."""
        if not email or not password:
            return False, "MEGA_EMAIL or MEGA_PASSWORD is missing in config."

        code, out = await run_cmd(["mega-whoami"])
        if code == 0 and email.lower() in out.lower():
            return True, f"Already logged in as {email}"

        code, out = await run_cmd(["mega-login", email, password])
        if code == 0:
            return True, "Login successful."
        return False, out

    @staticmethod
    async def get_storage() -> Dict[str, str]:
        """Get storage usage via mega-df."""
        code, out = await run_cmd(["mega-df", "-h"])
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
        Uploads a local file to remote_folder on MEGA using mega-put and exports a shareable link.
        
        Returns:
            (success: bool, mega_link: Optional[str], message: str)
        """
        if not os.path.exists(local_path):
            return False, None, "File not found locally."

        file_name = os.path.basename(local_path)

        if not remote_folder.startswith("/"):
            remote_folder = "/" + remote_folder
        remote_folder = remote_folder.rstrip("/")

        # Step 1: Upload via mega-put (-c automatically creates destination folder)
        print(f"⚡ Running mega-put: {local_path} -> {remote_folder}")
        put_code, put_out = await run_cmd(["mega-put", "-c", local_path, remote_folder])
        if put_code != 0:
            return False, None, f"mega-put error: {put_out}"

        remote_file_path = f"{remote_folder}/{file_name}"
        print(f"🔗 Requesting export for: {remote_file_path}")

        # Step 2: Try mega-export -a
        exp_code, exp_out = await run_cmd(["mega-export", "-a", remote_file_path])
        print(f"📋 mega-export output (code {exp_code}):\n{exp_out}")

        # Regex matches any https://mega.nz/... link format
        match = re.search(r"https://mega\.nz/[^\s\'\"\)]+", exp_out)
        if match:
            return True, match.group(0), "Success"

        # Step 3: Fallback - query existing export without -a
        q_code, q_out = await run_cmd(["mega-export", remote_file_path])
        print(f"📋 mega-export query output (code {q_code}):\n{q_out}")
        match = re.search(r"https://mega\.nz/[^\s\'\"\)]+", q_out)
        if match:
            return True, match.group(0), "Success"

        # Step 4: Fallback - list all exports
        list_code, list_out = await run_cmd(["mega-export"])
        match = re.search(rf"{re.escape(file_name)}.*?(https://mega\.nz/[^\s\'\"\)]+)", list_out)
        if match:
            return True, match.group(1), "Success"

        # If upload succeeded but link couldn't be generated, return a web link to the folder
        web_folder_link = "https://mega.nz/fm"
        return True, web_folder_link, f"Uploaded to Mega folder {remote_folder}"
