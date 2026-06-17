from __future__ import annotations

import codecs
import html as html_module
import http.cookiejar
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

DEFAULT_APP_VERSION = "1.0.0"
VERSION_FILE_NAME = "version.txt"
UPDATE_DRIVE_FOLDER_URL = "https://drive.google.com/drive/folders/1CzCnCmdXsemUmMTSz2ljRkYkzUTp-xbx?usp=drive_link"
GOOGLE_FOLDER_MIME = "application/vnd.google-apps.folder"
GOOGLE_DOC_MIME = "application/vnd.google-apps.document"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

class UpdateError(RuntimeError):
    pass

@dataclass(frozen=True)
class DriveEntry:
    file_id: str
    name: str
    mime_type: str

    @property
    def is_folder(self) -> bool:
        return self.mime_type == GOOGLE_FOLDER_MIME

    @property
    def is_google_doc(self) -> bool:
        return self.mime_type == GOOGLE_DOC_MIME

@dataclass(frozen=True)
class UpdatePackage:
    current_version: str
    remote_version: str
    version_folder_id: str
    archive_id: str
    archive_name: str

def is_frozen_app() -> bool:
    return bool(getattr(sys, "frozen", False))

def app_install_dir() -> Path:
    return Path(sys.executable).resolve().parent if is_frozen_app() else Path(__file__).resolve().parent

def local_version_path() -> Path:
    return app_install_dir() / VERSION_FILE_NAME

def normalize_version(value: str | None) -> str:
    if not value:
        return DEFAULT_APP_VERSION
    match = re.search(r"v?(\d+(?:\.\d+){1,3})", value.strip(), re.IGNORECASE)
    return match.group(1) if match else DEFAULT_APP_VERSION

def parse_version_text(text: str) -> str:
    return normalize_version(text.lstrip("\ufeff").strip())

def version_tuple(value: str) -> tuple[int, ...]:
    parts = [int(part) for part in normalize_version(value).split(".")]
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts)

def is_newer_version(remote_version: str, current_version: str) -> bool:
    return version_tuple(remote_version) > version_tuple(current_version)

def ensure_local_version_file(default_version: str = DEFAULT_APP_VERSION) -> str:
    path = local_version_path()
    if not path.exists():
        try:
            path.write_text(f"{normalize_version(default_version)}\n", encoding="utf-8")
        except OSError:
            return normalize_version(default_version)
    try:
        return parse_version_text(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return normalize_version(default_version)

def extract_folder_id(folder_url: str = UPDATE_DRIVE_FOLDER_URL) -> str:
    match = re.search(r"/folders/([A-Za-z0-9_-]+)", folder_url)
    if match:
        return match.group(1)
    folder_id = urllib.parse.parse_qs(urllib.parse.urlparse(folder_url).query).get("id", [""])[0]
    if folder_id:
        return folder_id
    raise UpdateError("Google Drive 폴더 ID를 찾을 수 없습니다.")

def _request(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

def _read_url_text(url: str, timeout: int = 25) -> str:
    try:
        with urllib.request.urlopen(_request(url), timeout=timeout) as response:
            return response.read().decode("utf-8", "replace")
    except urllib.error.URLError as exc:
        raise UpdateError(f"네트워크 연결에 실패했습니다: {exc}") from exc

def _looks_like_drive_entry(item: object) -> bool:
    return (
        isinstance(item, list)
        and len(item) > 3
        and isinstance(item[0], str)
        and isinstance(item[2], str)
        and isinstance(item[3], str)
        and ("/" in item[3] or item[3].startswith("application/vnd.google-apps."))
    )

def _collect_drive_entries(value: object) -> list[DriveEntry]:
    entries: list[DriveEntry] = []
    seen: set[str] = set()

    def walk(node: object) -> None:
        if _looks_like_drive_entry(node):
            item = node
            file_id = str(item[0])
            if file_id not in seen:
                seen.add(file_id)
                entries.append(DriveEntry(file_id=file_id, name=str(item[2]), mime_type=str(item[3])))
            return
        if isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    return entries

def list_drive_folder(folder_id: str) -> list[DriveEntry]:
    page = _read_url_text(f"https://drive.google.com/drive/folders/{folder_id}?usp=sharing")
    match = re.search(r"window\['_DRIVE_ivd'\]\s*=\s*'(.+?)';", page, re.DOTALL)
    if not match:
        raise UpdateError("Google Drive 폴더 목록을 읽을 수 없습니다. 공유 권한을 확인해 주세요.")
    try:
        payload = json.loads(codecs.decode(match.group(1), "unicode_escape"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateError("Google Drive 폴더 목록 해석에 실패했습니다.") from exc
    return _collect_drive_entries(payload)

def _open_drive_download(opener: urllib.request.OpenerDirector, cookiejar: http.cookiejar.CookieJar, file_id: str):
    base_url = f"https://drive.google.com/uc?export=download&id={urllib.parse.quote(file_id)}"
    response = opener.open(_request(base_url), timeout=30)
    disposition = response.headers.get("Content-Disposition", "")
    content_type = response.headers.get("Content-Type", "")
    if "attachment" in disposition.lower() or "application/" in content_type.lower():
        return response

    page = response.read().decode("utf-8", "replace")
    confirm_match = re.search(r'href="([^"]*?uc\?export=download[^"]+)"', page)
    if confirm_match:
        confirm_url = urllib.parse.urljoin("https://drive.google.com", html_module.unescape(confirm_match.group(1)))
    else:
        confirm_token = next((cookie.value for cookie in cookiejar if cookie.name.startswith("download_warning")), "")
        if not confirm_token:
            raise UpdateError("Google Drive 다운로드 확인 링크를 찾을 수 없습니다.")
        confirm_url = f"{base_url}&confirm={urllib.parse.quote(confirm_token)}"
    return opener.open(_request(confirm_url), timeout=30)

def download_drive_file_to_bytes(file_id: str, max_bytes: int = 5 * 1024 * 1024) -> bytes:
    cookiejar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookiejar))
    with _open_drive_download(opener, cookiejar, file_id) as response:
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise UpdateError("버전 문서 크기가 너무 큽니다.")
    return data

def _download_small_drive_text(entry: DriveEntry) -> str:
    if entry.is_google_doc:
        return _read_url_text(f"https://docs.google.com/document/d/{entry.file_id}/export?format=txt")
    return download_drive_file_to_bytes(entry.file_id, max_bytes=1024 * 1024).decode("utf-8", "replace")

def read_remote_version(root_folder_id: str | None = None) -> tuple[str | None, list[DriveEntry]]:
    entries = list_drive_folder(root_folder_id or extract_folder_id())
    version_entry = next((entry for entry in entries if entry.name.strip().lower() in {"version", "version.txt"}), None)
    if version_entry is None:
        return None, entries
    return parse_version_text(_download_small_drive_text(version_entry)), entries

def find_update_package(current_version: str | None = None) -> UpdatePackage | None:
    current = normalize_version(current_version or ensure_local_version_file())
    remote_version, root_entries = read_remote_version(extract_folder_id())
    if not remote_version or not is_newer_version(remote_version, current):
        return None

    version_folder = next((entry for entry in root_entries if entry.is_folder and normalize_version(entry.name) == remote_version), None)
    if version_folder is None:
        raise UpdateError(f"Google Drive에서 {remote_version} 폴더를 찾을 수 없습니다.")

    archive_entries = [entry for entry in list_drive_folder(version_folder.file_id) if not entry.is_folder and entry.name.lower().endswith(".zip")]
    if not archive_entries:
        raise UpdateError(f"{remote_version} 폴더에서 ZIP 업데이트 파일을 찾을 수 없습니다.")

    archive = sorted(archive_entries, key=lambda entry: entry.name.lower())[0]
    return UpdatePackage(current, remote_version, version_folder.file_id, archive.file_id, archive.name)

def download_drive_file(file_id: str, destination: Path, progress: Callable[[int], None] | None = None) -> None:
    cookiejar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookiejar))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with _open_drive_download(opener, cookiejar, file_id) as response, destination.open("wb") as target:
        total = int(response.headers.get("Content-Length") or 0)
        downloaded = 0
        while True:
            chunk = response.read(1024 * 256)
            if not chunk:
                break
            target.write(chunk)
            downloaded += len(chunk)
            if total and progress:
                progress(max(0, min(100, int(downloaded * 100 / total))))
    if progress:
        progress(100)

def _select_extracted_root(extract_dir: Path) -> Path:
    if (extract_dir / "Nukki.exe").exists():
        return extract_dir
    children = [path for path in extract_dir.iterdir() if path.is_dir()]
    if len(children) == 1 and (children[0] / "Nukki.exe").exists():
        return children[0]
    return extract_dir

def prepare_update_package(package: UpdatePackage, progress: Callable[[int], None] | None = None) -> tuple[Path, Path]:
    update_root = Path(tempfile.mkdtemp(prefix=f"nukki_update_{package.remote_version}_"))
    archive_path = update_root / package.archive_name
    extract_dir = update_root / "extracted"
    try:
        download_drive_file(package.archive_id, archive_path, progress=progress)
        if not zipfile.is_zipfile(archive_path):
            raise UpdateError("다운로드한 업데이트 파일이 올바른 ZIP 파일이 아닙니다.")
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(extract_dir)
        source_dir = _select_extracted_root(extract_dir)
        if not any(source_dir.iterdir()):
            raise UpdateError("업데이트 압축 파일이 비어 있습니다.")
        return source_dir, update_root
    except Exception:
        shutil.rmtree(update_root, ignore_errors=True)
        raise

def _batch_quote(path: Path) -> str:
    return str(path).replace('"', '""')

def schedule_update_install(source_dir: Path, target_dir: Path, new_version: str) -> Path:
    if not is_frozen_app():
        raise UpdateError("업데이트 설치는 빌드된 실행 파일에서만 적용할 수 있습니다.")
    update_root = next((path for path in (source_dir, *source_dir.parents) if path.name.startswith("nukki_update_")), source_dir.parent)
    script_path = update_root / "apply_update.bat"
    script = f'''@echo off
chcp 65001 >nul
setlocal
set "SRC={_batch_quote(source_dir)}"
set "DST={_batch_quote(target_dir)}"
set "VERSION={normalize_version(new_version)}"
set "PID={os.getpid()}"
echo Nukki 업데이트를 적용합니다...
:wait_loop
tasklist /FI "PID eq %PID%" | find "%PID%" >nul
if not errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto wait_loop
)
robocopy "%SRC%" "%DST%" /E /COPY:DAT /R:5 /W:1 >nul
if %ERRORLEVEL% GEQ 8 (
    echo 업데이트 파일 복사에 실패했습니다.
    pause
    exit /b %ERRORLEVEL%
)
> "%DST%\\{VERSION_FILE_NAME}" echo %VERSION%
if exist "%DST%\\Nukki.exe" (
    start "" "%DST%\\Nukki.exe"
)
timeout /t 1 /nobreak >nul
rd /s /q "{_batch_quote(update_root)}"
endlocal
'''
    script_path.write_text(script, encoding="utf-8")
    subprocess.Popen(["cmd.exe", "/c", str(script_path)], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return script_path
