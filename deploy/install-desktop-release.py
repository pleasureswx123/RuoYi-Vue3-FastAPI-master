"""在发布锁内安装不可变版本文件，最后原子替换客户端清单。"""

import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile


def details(manifest):
    return json.loads(base64.b64decode(json.loads(manifest)["payload"], validate=True))


def publish(stage, root, version, digest):
    if not re.fullmatch(r"(0|[1-9][0-9]*)(\.(0|[1-9][0-9]*)){2}", version):
        raise ValueError("版本号无效")
    installer = "ShotGrid-setup.exe"
    manifest = (stage / "latest.json").read_bytes()
    release = details(manifest)
    if (release["version"], release["sha256"]) != (version, digest):
        raise ValueError("版本与清单不一致")
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".publish.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        latest = root / "latest.json"
        if latest.exists():
            current = details(latest.read_bytes())["version"]
            if tuple(map(int, current.split("."))) > tuple(map(int, version.split("."))):
                raise ValueError("禁止发布低于线上版本的更新")
        target = root / version
        with tempfile.TemporaryDirectory(dir=root) as tmp:
            work = Path(tmp)
            candidate = work / version
            candidate.mkdir(mode=0o755)
            package = candidate / installer
            shutil.copyfile(stage / installer, package)
            with package.open("rb") as stream:
                actual = hashlib.sha256()
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    actual.update(block)
            if actual.hexdigest().upper() != digest:
                raise ValueError("上传的安装包校验失败")
            (candidate / "release.json").write_bytes(manifest)
            if target.exists():
                if (target / "release.json").read_bytes() != manifest:
                    raise ValueError("同一版本已存在，请提高版本号")
            else:
                package.chmod(0o644)
                (candidate / "release.json").chmod(0o644)
                candidate.chmod(0o755)
                candidate.rename(target)
            next_manifest = work / "latest.json"
            next_manifest.write_bytes(manifest)
            next_manifest.chmod(0o644)
            os.replace(next_manifest, latest)
    print(f"Shot Grid V{version} 已发布")


if __name__ == "__main__":
    publish(Path(sys.argv[1]), Path("/var/lib/ruoyi-shot-grid/desktop-updates"), *sys.argv[2:])
