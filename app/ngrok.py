from __future__ import annotations


class NgrokTunnel:
    """Optional ngrok HTTP tunnel for the local agent server."""

    def __init__(self, port: int, *, authtoken: str = "", region: str = ""):
        self.port = port
        self.authtoken = self._normalize_token(authtoken)
        self.region = region.strip()
        self._tunnel = None

    @staticmethod
    def _normalize_token(value: str) -> str:
        token = str(value or "").strip().strip('"\'')
        if token.casefold().startswith("bearer "):
            token = token[7:].strip()
        return token

    @property
    def public_url(self) -> str | None:
        return getattr(self._tunnel, "public_url", None) if self._tunnel else None

    def start(self) -> str:
        if self.authtoken.casefold().startswith("cr_"):
            raise RuntimeError(
                "Введён ngrok API credential (cr_...), а нужен Agent Authtoken. "
                "Возьмите его в ngrok Dashboard -> Getting Started -> Your Authtoken."
            )
        try:
            from pyngrok import ngrok
        except ImportError as exc:
            raise RuntimeError("Для режима ngrok установите пакет pyngrok") from exc

        if self.authtoken:
            ngrok.set_auth_token(self.authtoken)
        options = {"proto": "http"}
        if self.region:
            options["region"] = self.region
        self._tunnel = ngrok.connect(self.port, **options)
        if not self.public_url:
            raise RuntimeError("ngrok не вернул публичный адрес")
        return self.public_url.rstrip("/")

    def stop(self) -> None:
        if not self._tunnel:
            return
        try:
            from pyngrok import ngrok
            ngrok.disconnect(self.public_url)
        finally:
            self._tunnel = None
