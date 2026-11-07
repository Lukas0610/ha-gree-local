"""Async client for the Gree local UDP protocol.

Every packet is sent unicast to a known IP - no broadcast discovery - so this
works across subnets/VLANs and with routers that filter broadcasts.

This module deliberately has no Home Assistant imports so it can be tested
standalone (see tests/test_api.py).
"""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

DEFAULT_PORT = 7000

# Well-known generic keys used before a device-specific key is negotiated.
GENERIC_KEY_ECB = b"a3K8Bx%2r8Y7#xDh"
GENERIC_KEY_GCM = b"{yxAHAY_Lm6pbC/<"
GCM_NONCE = b"\x54\x40\x78\x44\x49\x67\x5a\x51\x6c\x5e\x63\x13"
GCM_AAD = b"qualcomm-test"


class GreeError(Exception):
    """Base error for Gree communication."""


class GreeConnectionError(GreeError):
    """The device did not answer."""


class GreeProtocolError(GreeError):
    """The device answered with something unusable (wrong key, bad JSON, ...)."""


def _json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, separators=(",", ":")).encode()


class EcbCipher:
    """AES-128-ECB with PKCS7 padding (older firmware)."""

    name = "ecb"

    def __init__(self, key: bytes) -> None:
        self.key = key

    def encrypt(self, obj: Any) -> dict[str, str]:
        padder = padding.PKCS7(128).padder()
        data = padder.update(_json_bytes(obj)) + padder.finalize()
        enc = Cipher(algorithms.AES(self.key), modes.ECB()).encryptor()
        return {"pack": base64.b64encode(enc.update(data) + enc.finalize()).decode()}

    def decrypt(self, packet: dict[str, Any]) -> dict[str, Any]:
        try:
            raw = base64.b64decode(packet["pack"])
            dec = Cipher(algorithms.AES(self.key), modes.ECB()).decryptor()
            data = dec.update(raw) + dec.finalize()
            # Some firmware pads inconsistently, so cut at the closing brace
            # instead of trusting the PKCS7 padding byte.
            end = data.rfind(b"}")
            if end < 0:
                raise ValueError("no JSON object in plaintext")
            return json.loads(data[: end + 1])
        except (KeyError, ValueError) as err:
            raise GreeProtocolError(f"cannot decrypt reply (wrong key?): {err}") from err


class GcmCipher:
    """AES-128-GCM with fixed nonce/AAD (newer firmware, ~v1.21+)."""

    name = "gcm"

    def __init__(self, key: bytes) -> None:
        self.key = key

    def encrypt(self, obj: Any) -> dict[str, str]:
        ct = AESGCM(self.key).encrypt(GCM_NONCE, _json_bytes(obj), GCM_AAD)
        return {
            "pack": base64.b64encode(ct[:-16]).decode(),
            "tag": base64.b64encode(ct[-16:]).decode(),
        }

    def decrypt(self, packet: dict[str, Any]) -> dict[str, Any]:
        try:
            ct = base64.b64decode(packet["pack"]) + base64.b64decode(packet["tag"])
            return json.loads(AESGCM(self.key).decrypt(GCM_NONCE, ct, GCM_AAD))
        except (KeyError, ValueError, InvalidTag) as err:
            raise GreeProtocolError(f"cannot decrypt reply (wrong key?): {err!r}") from err


CIPHERS: dict[str, type[EcbCipher] | type[GcmCipher]] = {
    EcbCipher.name: EcbCipher,
    GcmCipher.name: GcmCipher,
}


class _ReplyProtocol(asyncio.DatagramProtocol):
    """Resolve a future with the first datagram received."""

    def __init__(self, reply: asyncio.Future[bytes]) -> None:
        self._reply = reply

    def datagram_received(self, data: bytes, addr: Any) -> None:
        if not self._reply.done():
            self._reply.set_result(data)

    def error_received(self, exc: Exception) -> None:
        # E.g. ICMP "port unreachable" (a ConnectionResetError on Windows).
        if not self._reply.done():
            self._reply.set_exception(GreeConnectionError(str(exc)))


class GreeClient:
    """Talk to one Gree unit at a fixed address."""

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        *,
        mac: str | None = None,
        key: str | None = None,
        cipher: str = EcbCipher.name,
        timeout: float = 3.0,
        retries: int = 2,
    ) -> None:
        self.host = host
        self.port = port
        self.mac = mac
        self.cipher: EcbCipher | GcmCipher | None = (
            CIPHERS[cipher](key.encode()) if key else None
        )
        self.timeout = timeout
        self.retries = retries
        # The Wi-Fi modules handle concurrent requests poorly; serialize them.
        self._lock = asyncio.Lock()

    # -- transport ---------------------------------------------------------

    async def _exchange(self, packet: dict[str, Any]) -> dict[str, Any]:
        payload = _json_bytes(packet)
        loop = asyncio.get_running_loop()
        last_err: Exception | None = None
        async with self._lock:
            # UDP is lossy and the modules occasionally drop packets: retry.
            for _ in range(self.retries + 1):
                reply: asyncio.Future[bytes] = loop.create_future()
                try:
                    transport, _ = await loop.create_datagram_endpoint(
                        lambda: _ReplyProtocol(reply),
                        remote_addr=(self.host, self.port),
                    )
                except OSError as err:
                    raise GreeConnectionError(
                        f"cannot reach {self.host}:{self.port}: {err}"
                    ) from err
                try:
                    transport.sendto(payload)
                    data = await asyncio.wait_for(reply, self.timeout)
                except (TimeoutError, GreeConnectionError) as err:
                    last_err = err
                    continue
                finally:
                    transport.close()
                try:
                    return json.loads(data)
                except ValueError as err:
                    raise GreeProtocolError("reply is not valid JSON") from err
        raise GreeConnectionError(
            f"no response from {self.host}:{self.port}"
        ) from last_err

    async def _request(
        self, cipher: EcbCipher | GcmCipher, payload: dict[str, Any], *, bind: bool = False
    ) -> dict[str, Any]:
        if not self.mac:
            await self.scan()
        packet = {
            "cid": "app",
            "i": 1 if bind else 0,
            "t": "pack",
            "uid": 0,
            "tcid": self.mac,
            **cipher.encrypt(payload),
        }
        return cipher.decrypt(await self._exchange(packet))

    # -- protocol ----------------------------------------------------------

    async def scan(self) -> dict[str, Any]:
        """Ask the unit to identify itself (MAC, name, firmware, ...)."""
        reply = await self._exchange({"t": "scan"})
        if "tag" in reply:
            info = GcmCipher(GENERIC_KEY_GCM).decrypt(reply)
        else:
            info = EcbCipher(GENERIC_KEY_ECB).decrypt(reply)
        mac = info.get("mac") or reply.get("cid")
        if not mac:
            raise GreeProtocolError("scan reply contains no MAC address")
        self.mac = mac
        return info

    async def bind(self) -> EcbCipher | GcmCipher:
        """Obtain the device-specific key. Tries ECB first, then GCM."""
        if not self.mac:
            await self.scan()
        errors: list[GreeError] = []
        for generic in (EcbCipher(GENERIC_KEY_ECB), GcmCipher(GENERIC_KEY_GCM)):
            try:
                reply = await self._request(
                    generic, {"mac": self.mac, "t": "bind", "uid": 0}, bind=True
                )
            except GreeError as err:
                errors.append(err)
                continue
            if reply.get("t") == "bindok" and reply.get("key"):
                self.cipher = type(generic)(reply["key"].encode())
                return self.cipher
            errors.append(GreeProtocolError(f"unexpected bind reply {reply.get('t')!r}"))
        detail = "; ".join(str(err) for err in errors)
        if all(isinstance(err, GreeConnectionError) for err in errors):
            raise GreeConnectionError(f"binding failed: {detail}")
        raise GreeProtocolError(f"binding failed: {detail}")

    async def _bound_cipher(self) -> EcbCipher | GcmCipher:
        return self.cipher or await self.bind()

    async def status(self, cols: list[str]) -> dict[str, Any]:
        """Read the given columns, e.g. ["Pow", "SetTem"]."""
        cipher = await self._bound_cipher()
        reply = await self._request(
            cipher, {"cols": list(cols), "mac": self.mac, "t": "status"}
        )
        if reply.get("t") != "dat":
            raise GreeProtocolError(f"unexpected status reply {reply.get('t')!r}")
        return dict(zip(reply["cols"], reply["dat"]))

    async def set(self, params: dict[str, int]) -> dict[str, Any]:
        """Write parameters, e.g. {"Pow": 1, "SetTem": 22}."""
        cipher = await self._bound_cipher()
        reply = await self._request(
            cipher, {"opt": list(params), "p": list(params.values()), "t": "cmd"}
        )
        if reply.get("r", 200) != 200:
            raise GreeProtocolError(f"command rejected: {reply}")
        return dict(zip(reply.get("opt", []), reply.get("p") or reply.get("val") or []))
