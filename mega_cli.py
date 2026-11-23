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
        output = out if out else err
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

        # Check if already logged in as this user
        code, out = await run_cmd(["mega-whoami"])
        if code == 0 and email.lower() in out.lower():
            return True, f"Already logged in as {email}"

        # Otherwise perform login
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
        
        # Ensure remote folder starts with /
        if not remote_folder.startswith("/"):
            remote_folder = "/" + remote_folder
        remote_folder = remote_folder.rstrip("/")

        # Step 1: Upload via mega-put (-c automatically creates destination folder if missing)
        put_code, put_out = await run_cmd(["mega-put", "-c", local_path, remote_folder])
        if put_code != 0:
            return False, None, f"mega-put error: {put_out}"

        # Step 2: Export public link via mega-export -a
        remote_file_path = f"{remote_folder}/{file_name}"
        exp_code, exp_out = await run_cmd(["mega-export", "-a", remote_file_path])
        
        # Parse link from output
        # Output format usually: "Exported /folder/file.ext: https://mega.nz/file/xxxx#yyyy"
        match = re.search(r"https://mega\.nz/file/[^\s]+", exp_out)
        if match:
            return True, match.group(0), "Success"

        # If already exported previously, mega-export may list it
        list_code, list_out = await run_cmd(["mega-export"])
        match = re.search(rf"{re.escape(file_name)}.*?(https://mega\.nz/file/[^\s]+)", list_out)
        if match:
            return True, match.group(1), "Success"

        return True, "Uploaded (Link not generated)", f"Uploaded to {remote_file_path}"
