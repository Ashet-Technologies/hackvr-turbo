"""TLS certificate generator for HackVR tools."""

from __future__ import annotations

import argparse
import datetime
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from hackvr import net

def generate_self_signed_certificate(
    *,
    common_name: str,
    valid_days: int,
) -> net.TlsServerCertificate:
    """Generate a self-signed certificate and private key."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.datetime.now(tz=datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=valid_days))
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(encoding=serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return net.TlsServerCertificate(cert_pem=cert_pem, key_pem=key_pem)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a self-signed TLS certificate for HackVR")
    parser.add_argument(
        "--tls-cert",
        type=Path,
        required=True,
        help="Path to write TLS certificate",
    )
    parser.add_argument(
        "--tls-key",
        type=Path,
        required=True,
        help="Path to write TLS private key",
    )
    parser.add_argument(
        "--common-name",
        required=True,
        help="Common name for the certificate",
    )
    parser.add_argument(
        "--valid-days",
        type=int,
        required=True,
        help="Number of days the certificate is valid",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    certificate = generate_self_signed_certificate(
        common_name=args.common_name,
        valid_days=args.valid_days,
    )
    certificate.save(args.tls_cert, args.tls_key)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
