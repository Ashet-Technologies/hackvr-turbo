from pathlib import Path

from hackvr import net
from hackvr.tools import keygen


def test_keygen_main_writes_certificate(tmp_path: Path) -> None:
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"

    result = keygen.main(
        [
            "--tls-cert",
            str(cert_path),
            "--tls-key",
            str(key_path),
            "--common-name",
            "example.com",
            "--valid-days",
            "1",
        ]
    )

    assert result == 0
    certificate = net.TlsServerCertificate.from_files(cert_path, key_path)
    assert certificate.cert_pem
    assert certificate.key_pem
