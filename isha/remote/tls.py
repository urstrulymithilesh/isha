"""A certificate of her own, so the phone will hand over the microphone.

Browsers refuse `getUserMedia` on an insecure origin, so the remote page needs HTTPS
or it cannot record at all. The obvious route is `tailscale serve`, which issues a real
Let's Encrypt certificate — and publishes the machine's hostname to public Certificate
Transparency logs in the process. That is a name, not data, and for most projects it
would not matter. For this one it was declined: nothing about her is meant to be
discoverable anywhere.

So the certificate is generated here and trusted by exactly one phone. Nothing is
published, no authority is involved, and no third party learns the machine exists.

The cost, stated plainly: the phone will warn on first visit, because a certificate
nobody vouches for is indistinguishable from a forged one *unless you check it*. That
is what `fingerprint()` is for — compare it once against what the browser shows and
the warning becomes a verification rather than a shrug.

OpenSSL does the generating (it is on PATH here); Python's stdlib `ssl` does the
serving. No new Python dependency either way.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import ssl
import stat
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

VALID_DAYS = 3650          # it is trusted by one phone; expiry only creates busywork
_RENEW_WITHIN = timedelta(days=30)


class CertError(RuntimeError):
    """The certificate could not be created — never guessed around, because a silent
    fallback to plain http means a microphone that never works and no reason given."""


def tailscale_identity() -> tuple[list[str], list[str]]:
    """(dns names, ip addresses) for this machine on the tailnet, best effort.

    The certificate has to name every address the phone might use, or the browser
    rejects it for a reason that looks nothing like the real one.
    """
    names, ips = ["localhost"], ["127.0.0.1"]
    exe = shutil.which("tailscale") or r"C:\Program Files\Tailscale\tailscale.exe"
    try:
        out = subprocess.run([exe, "status", "--json"], capture_output=True,
                             text=True, timeout=20)
        self_node = json.loads(out.stdout).get("Self", {})
    except (OSError, ValueError, subprocess.SubprocessError):
        return names, ips
    dns = (self_node.get("DNSName") or "").rstrip(".")
    if dns:
        names.insert(0, dns)
        names.append(dns.split(".")[0])          # the short MagicDNS name
    for ip in self_node.get("TailscaleIPs") or []:
        ips.append(ip)
    return names, ips


def _expiring(cert_path: Path) -> bool:
    try:
        text = subprocess.run(
            ["openssl", "x509", "-enddate", "-noout", "-in", str(cert_path)],
            capture_output=True, text=True, timeout=20).stdout
        stamp = text.split("=", 1)[1].strip()
        expires = datetime.strptime(stamp, "%b %d %H:%M:%S %Y %Z").replace(
            tzinfo=timezone.utc)
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return True                              # unreadable is as good as expired
    return expires - datetime.now(timezone.utc) < _RENEW_WITHIN


def ensure_cert(directory: Path, names=None, ips=None) -> tuple[Path, Path]:
    """Return (cert, key), generating them if missing or close to expiry."""
    directory = Path(directory)
    cert, key = directory / "remote-cert.pem", directory / "remote-key.pem"
    if cert.is_file() and key.is_file() and not _expiring(cert):
        return cert, key

    if names is None or ips is None:
        found_names, found_ips = tailscale_identity()
        names = names or found_names
        ips = ips or found_ips
    if not shutil.which("openssl"):
        raise CertError(
            "openssl is not on PATH, so a certificate cannot be generated. Either "
            "install it, or enable HTTPS for the tailnet and use `tailscale serve` "
            "instead — see isha/remote/tls.py for the trade-off between them.")

    directory.mkdir(parents=True, exist_ok=True)
    san = ",".join([f"DNS:{n}" for n in names] + [f"IP:{i}" for i in ips])
    cmd = [
        "openssl", "req", "-x509", "-newkey", "rsa:2048", "-sha256",
        "-days", str(VALID_DAYS), "-nodes",
        "-keyout", str(key), "-out", str(cert),
        "-subj", f"/CN={names[0]}",
        "-addext", f"subjectAltName={san}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0 or not cert.is_file():
        raise CertError(f"openssl failed: {result.stderr.strip()[:300]}")
    try:
        key.chmod(stat.S_IRUSR | stat.S_IWUSR)   # best effort; data/ is already private
    except OSError:
        pass
    return cert, key


def fingerprint(cert_path: Path) -> str:
    """SHA-256 of the certificate, formatted the way browsers show it.

    This is the whole security story for a self-signed certificate: check it once on
    the phone and the browser warning becomes a verification instead of a habit.
    """
    pem = Path(cert_path).read_text(encoding="utf-8")
    der = ssl.PEM_cert_to_DER_cert(pem)
    digest = hashlib.sha256(der).hexdigest().upper()
    return ":".join(digest[i:i + 2] for i in range(0, len(digest), 2))


def wrap(server_socket, cert: Path, key: Path):
    """Put TLS around the remote server's socket."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=str(cert), keyfile=str(key))
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context.wrap_socket(server_socket, server_side=True)
