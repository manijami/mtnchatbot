import io
import ssl
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import prepare


class PreparationTests(unittest.TestCase):
    def test_archive_missing_or_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "app.tgz"
            with self.assertRaises(ValueError):
                prepare.inspect_archive(archive)
            with tarfile.open(archive, "w:gz") as tar:
                entry = tarfile.TarInfo("../escape")
                entry.size = 1
                tar.addfile(entry, io.BytesIO(b"x"))
            with self.assertRaises(ValueError):
                prepare.inspect_archive(archive)

    def test_app_release_metadata_and_alert_support(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "app.tgz"
            for version in ("2.0.0", "1.3.1"):
                content = f"[launcher]\nversion = {version}\n[ui]\nlabel = Splunk MCP Server\n".encode()
                with tarfile.open(archive, "w:gz") as tar:
                    entry = tarfile.TarInfo("./splunk_mcp/default/app.conf")
                    entry.size = len(content)
                    tar.addfile(entry, io.BytesIO(content))
                if version == "2.0.0":
                    metadata = prepare.inspect_archive(archive)
                    self.assertEqual(metadata["app_directory"], "splunk_mcp")
                    self.assertEqual(metadata["version"], version)
                else:
                    with self.assertRaises(ValueError):
                        prepare.inspect_archive(archive)

    def test_demo_package_is_reproducible_and_contains_config_only(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "mtn-demo.tgz"
            config = prepare.ROOT / "mtn/splunk/config"
            prepare.package_demo(config, target)
            first = target.read_bytes()
            prepare.package_demo(config, target)
            self.assertEqual(first, target.read_bytes())
            with tarfile.open(target, "r:gz") as tar:
                names = tar.getnames()
                self.assertIn("mtn_demo/default/authorize.conf", names)
                self.assertIn("mtn_demo/metadata/default.meta", names)
                self.assertTrue(all(n.startswith("mtn_demo/") and not n.endswith((".pem", ".key")) for n in names))

    def test_official_app_code_is_preserved_with_local_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vendor = root / "vendor.tgz"
            derived = root / "configured.tgz"
            source = {"Splunk_MCP_Server/default/app.conf": b"[launcher]\nversion = 2.1.0\n",
                      "Splunk_MCP_Server/bin/vendor.py": b"# vendor fixture; never executed\n"}
            with tarfile.open(vendor, "w:gz") as tar:
                for name, content in source.items():
                    info = tarfile.TarInfo(name)
                    info.size = len(content)
                    tar.addfile(info, io.BytesIO(content))
            settings = prepare.ROOT / "mtn/splunk/mcp.conf"
            prepare.configure_official_app(vendor, settings, derived, "Splunk_MCP_Server")
            with tarfile.open(derived, "r:gz") as tar:
                for name, content in source.items():
                    self.assertEqual(tar.extractfile(name).read(), content)
                self.assertEqual(tar.extractfile("Splunk_MCP_Server/local/mcp.conf").read(), settings.read_bytes())
            with self.assertRaises(ValueError):
                prepare.configure_official_app(derived, settings, root / "duplicate.tgz", "Splunk_MCP_Server")

    def test_local_ca_hostname_and_existing_material_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            private = Path(directory)
            tls = private / "tls"
            with patch.object(prepare, "PRIVATE", private):
                prepare.make_tls(tls)
                before = (tls / "ca.pem").read_bytes()
                prepare.make_tls(tls)
                self.assertEqual((tls / "ca.pem").read_bytes(), before)
            subprocess.run(["openssl", "verify", "-CAfile", str(tls / "ca.pem"), "-purpose", "sslclient", str(tls / "server.crt")], check=True, capture_output=True)
            subprocess.run(["openssl", "verify", "-CAfile", str(tls / "ca.pem"), "-purpose", "sslserver", str(tls / "server.crt")], check=True, capture_output=True)
            context = ssl.create_default_context(cafile=str(tls / "ca.pem"))
            self.assertTrue(context.check_hostname)
            subprocess.run(["openssl", "verify", "-CAfile", str(tls / "ca.pem"), "-verify_hostname", "splunk", str(tls / "server.crt")], check=True, capture_output=True)
            wrong = subprocess.run(["openssl", "verify", "-CAfile", str(tls / "ca.pem"), "-verify_hostname", "unrelated-host", str(tls / "server.crt")], capture_output=True)
            self.assertNotEqual(wrong.returncode, 0)
            self.assertEqual((tls / "ca.key").stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
