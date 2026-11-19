"""复用远端 containerd 已有的压缩层；只读查询其内容库，由 Docker 导入镜像。"""

import json
import re
import shlex
import subprocess
import sys
import tarfile
from pathlib import Path


def make_delta(archive: Path, destination: Path, available: set[str]) -> int:
    with tarfile.open(archive, 'r:') as source:
        manifests = json.load(source.extractfile('manifest.json'))
        layers = {layer for image in manifests for layer in image['Layers']}
        # 仅省略可用的 OCI 层，清单、配置、证明文件和版本标签始终保留。
        skip = {
            layer for layer in layers
            if re.fullmatch(r'blobs/sha256/[0-9a-f]{64}', layer)
            and 'sha256:' + layer.rsplit('/', 1)[1] in available
        }
        if skip:
            with tarfile.open(destination, 'w') as output:
                for member in source:
                    if member.name not in skip:
                        output.addfile(member, source.extractfile(member) if member.isfile() else None)
        return len(skip)


def transfer(server: str, directory: Path, images: list[str]) -> None:
    ssh = ['ssh', '-o', 'BatchMode=yes', server]
    probe = """set -eu
case "$(docker info --format '{{json .DriverStatus}}')" in
    *io.containerd.snapshotter.v1*) ctr -n moby content ls -q ;;
    *) exit 3 ;;
esac"""
    available = set(subprocess.check_output([*ssh, probe], text=True).splitlines())
    archive = directory / 'images.tar'
    delta = directory / 'images-delta.tar'
    subprocess.run(['docker', 'save', '-o', str(archive), *images], check=True)
    reused = make_delta(archive, delta, available)
    payload = delta if reused else archive
    print(f'复用 {reused} 个镜像层，发送 {payload.stat().st_size:,} / {archive.stat().st_size:,} 字节', flush=True)
    with payload.open('rb') as stream:
        subprocess.run([*ssh, 'docker load'], stdin=stream, check=True)
    # 部分导入必须生成全部预期镜像；旧版加载器若未完整导入，由调用方重新全量传输。
    inspect = ['docker', 'image', 'inspect', '--format', '{{.Id}}', *images]
    local = subprocess.check_output(inspect, text=True).splitlines()
    remote = subprocess.check_output([*ssh, shlex.join(inspect)], text=True).splitlines()
    if local != remote:
        raise ValueError('远端导入的镜像 ID 与本地不符')


if __name__ == '__main__':
    try:
        transfer(sys.argv[1], Path(sys.argv[2]), sys.argv[3:])
    except (OSError, ValueError, KeyError, tarfile.TarError, subprocess.SubprocessError) as exc:
        print(f'按层传输未完成：{exc}', file=sys.stderr)
        sys.exit(1)
