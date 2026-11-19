"""Inspect an operator-supplied archive and create local TLS material, without starting Splunk.

Does not download apps, accept terms, acquire a trial, extract vendor code, or use credentials.
"""
from __future__ import annotations

import configparser
import gzip
import hashlib
import io
import json
import os
import re
import subprocess
import tarfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = ROOT / "mtn/splunk/private"


def inspect_archive(archive: Path) -> dict:
    if not archive.is_file():
        raise ValueError("Operator app download missing: mtn/splunk/private/splunk-mcp-server.tgz")
    if archive.stat().st_size > 100 * 1024 * 1024:
        raise ValueError("Unexpected app archive size; inspect manually")
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk():
                raise ValueError("Archive contains a path or link requiring manual review")
        manifests = [m for m in members if m.name.endswith("/default/app.conf")]
        if len(manifests) != 1 or manifests[0].size > 1024 * 1024:
            raise ValueError("Expected exactly one bounded default/app.conf")
        config = configparser.ConfigParser(interpolation=None, strict=False)
        with tar.extractfile(manifests[0]) as stream:
            config.read_file(io.StringIO(stream.read().decode()))
        version = config.get("launcher", "version", fallback="unknown")
        if not re.fullmatch(r"2\.\d+\.\d+", version):
            raise ValueError("This demo needs an MCP app 2.x release with alert-reading tools; verify compatibility before substituting")
        label = config.get("ui", "label", fallback="unknown")
        # This records metadata, not vendor authenticity; operator verifies origin on Splunkbase.
        return {"archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                "app_directory": PurePosixPath(manifests[0].name).parts[0], "version": version, "label": label}



def ensure_client_auth(directory: Path):
    """Repair server-only demo leaf certificates; preserve the CA and existing private key."""
    check = subprocess.run(["openssl", "verify", "-CAfile", str(directory / "ca.pem"),
                            "-purpose", "sslclient", str(directory / "server.crt")],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if check.returncode == 0:
        return
    required = ("ca.key", "server.key", "server.csr", "server.crt")
    if not all((directory / name).is_file() for name in required):
        raise ValueError("Leaf certificate needs clientAuth but repair material is incomplete")
    # Splunk reuses sslConfig.serverCert for KV Store's mutual TLS.
    (directory / "server.ext").write_text("subjectAltName=DNS:splunk,DNS:localhost,IP:127.0.0.1\nbasicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth,clientAuth\n")
    subprocess.run(["openssl", "x509", "-req", "-in", "server.csr", "-CA", "ca.pem",
                    "-CAkey", "ca.key", "-CAcreateserial", "-days", "60", "-sha256",
                    "-extfile", "server.ext", "-out", "server.crt"], cwd=directory, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    (directory / "server.pem").write_bytes((directory / "server.key").read_bytes() + (directory / "server.crt").read_bytes() + (directory / "ca.pem").read_bytes())
    (directory / "server.pem").chmod(0o644)


def make_tls(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    if (directory / "ca.pem").exists():
        required = ("ca.pem", "server.pem")
        if not all((directory / name).is_file() for name in required):
            raise ValueError("Partial TLS material; inspect manually; never overwrite an existing CA")
        ensure_client_auth(directory)
        return
    if any(directory.iterdir()):
        raise ValueError("TLS directory is not empty; refusing to overwrite")
    PRIVATE.chmod(0o700)
    old_mask = os.umask(0o077)
    try:
        def openssl(*args):
            subprocess.run(["openssl", *args], cwd=directory, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        openssl("req", "-x509", "-newkey", "rsa:3072", "-nodes", "-days", "90", "-sha256",
                "-keyout", "ca.key", "-out", "ca.pem", "-subj", "/CN=MTN Splunk local demo CA",
                "-addext", "basicConstraints=critical,CA:TRUE", "-addext", "keyUsage=critical,keyCertSign,cRLSign")
        openssl("req", "-newkey", "rsa:3072", "-nodes", "-keyout", "server.key", "-out", "server.csr",
                "-subj", "/CN=splunk")
        (directory / "server.ext").write_text("subjectAltName=DNS:splunk,DNS:localhost,IP:127.0.0.1\nbasicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth,clientAuth\n")
        openssl("x509", "-req", "-in", "server.csr", "-CA", "ca.pem", "-CAkey", "ca.key", "-CAcreateserial",
                "-days", "60", "-sha256", "-extfile", "server.ext", "-out", "server.crt")
        (directory / "server.pem").write_bytes((directory / "server.key").read_bytes() + (directory / "server.crt").read_bytes() + (directory / "ca.pem").read_bytes())
        # Local Docker image runs as splunk (UID 41812); bind-mount key must be readable there.
        # Restrict host access with the parent directory; the dedicated Splunk mount is read-only.
        directory.chmod(0o755)
        (directory / "server.pem").chmod(0o644)
        (directory / "ca.pem").chmod(0o644)
    finally:
        os.umask(old_mask)



def package_demo(config: Path, target: Path):
    """Install our tracked configuration through the vendor's supported app installer."""
    with target.open("wb") as output:
        with gzip.GzipFile(fileobj=output, mode="wb", mtime=0, filename="") as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as tar:
                for path in sorted(config.rglob("*")):
                    if not path.is_file():
                        continue
                    if path.is_symlink():
                        raise ValueError("Demo configuration must not contain symlinks")
                    info = tar.gettarinfo(str(path), arcname="mtn_demo/" + path.relative_to(config).as_posix())
                    info.uid = info.gid = info.mtime = 0
                    info.uname = info.gname = ""
                    info.mode = 0o644
                    with path.open("rb") as source:
                        tar.addfile(info, source)
    target.chmod(0o644)



def configure_official_app(archive: Path, settings: Path, target: Path, app_directory: str):
    """Add only local/mcp.conf to a derived install archive; retain the vendor download."""
    override = app_directory + "/local/mcp.conf"
    with tarfile.open(archive, "r:gz") as source:
        if any(PurePosixPath(m.name).as_posix() == override for m in source.getmembers()):
            raise ValueError("Vendor archive already contains local/mcp.conf; inspect before overriding")
        with target.open("wb") as output:
            with gzip.GzipFile(fileobj=output, mode="wb", mtime=0, filename="") as compressed:
                with tarfile.open(fileobj=compressed, mode="w") as dest:
                    for member in source.getmembers():
                        stream = source.extractfile(member) if member.isfile() else None
                        dest.addfile(member, stream)
                        if stream:
                            stream.close()
                    content = settings.read_bytes()
                    info = tarfile.TarInfo(override)
                    info.size = len(content)
                    info.mode = 0o644
                    dest.addfile(info, io.BytesIO(content))
    target.chmod(0o644)


def main():
    try:
        metadata = inspect_archive(PRIVATE / "splunk-mcp-server.tgz")
        configure_official_app(PRIVATE / "splunk-mcp-server.tgz", ROOT / "mtn/splunk/mcp.conf",
                               PRIVATE / "splunk-mcp-configured.tgz", metadata["app_directory"])
        make_tls(PRIVATE / "tls")
        package_demo(ROOT / "mtn/splunk/config", PRIVATE / "mtn-demo.tgz")
        (PRIVATE / "archive-inspection.json").write_text(json.dumps(metadata, indent=2) + "\n")
    except (ValueError, OSError, tarfile.TarError, configparser.Error, subprocess.CalledProcessError) as exc:
        # Only controlled local preparation errors; no network/credential-bearing exceptions.
        print(f"Preparation incomplete: {type(exc).__name__}")
        return 1
    print(json.dumps(metadata, indent=2))
    print("TLS prepared. Licence acceptance and app security configuration remain operator steps.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
