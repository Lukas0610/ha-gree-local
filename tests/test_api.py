"""Protocol tests against a fake Gree unit on localhost."""

import asyncio
import json
import socket

import pytest

from api import (
    CIPHERS,
    GENERIC_KEY_ECB,
    GENERIC_KEY_GCM,
    GreeClient,
    GreeConnectionError,
    GreeError,
)

MAC = "f4911e000001"
DEVICE_KEY = b"0123456789abcdef"
GENERIC_KEYS = {"ecb": GENERIC_KEY_ECB, "gcm": GENERIC_KEY_GCM}


class FakeGree(asyncio.DatagramProtocol):
    """Speaks the device side of the protocol with one cipher generation."""

    def __init__(self, cipher_name: str) -> None:
        self.generic = CIPHERS[cipher_name](GENERIC_KEYS[cipher_name])
        self.device = CIPHERS[cipher_name](DEVICE_KEY)
        self.state = {
            "Pow": 0,
            "Mod": 1,
            "SetTem": 24,
            "TemSen": 63,
            "hid": "362001000967V1.0.4.bin",
        }
        self.binds = 0

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        msg = json.loads(data)
        if msg["t"] == "scan":
            body = {"t": "dev", "mac": MAC, "name": "Fake", "ver": "V1.0", "mid": "10001"}
            cipher = self.generic
        else:
            cipher = self.generic if msg["i"] == 1 else self.device
            try:
                body = self._handle(cipher.decrypt(msg))
            except GreeError:
                return  # real units silently drop packets they cannot decrypt
        reply = {"t": "pack", "i": msg.get("i", 1), "uid": 0, "cid": MAC, "tcid": "app"}
        reply.update(cipher.encrypt(body))
        self.transport.sendto(json.dumps(reply).encode(), addr)

    def _handle(self, req):
        if req["t"] == "bind":
            self.binds += 1
            return {"t": "bindok", "mac": MAC, "key": DEVICE_KEY.decode(), "r": 200}
        if req["t"] == "status":
            return {"t": "dat", "cols": req["cols"], "dat": [self.state.get(c, 0) for c in req["cols"]], "r": 200}
        if req["t"] == "cmd":
            self.state.update(zip(req["opt"], req["p"]))
            return {"t": "res", "opt": req["opt"], "p": req["p"], "val": req["p"], "r": 200}
        raise AssertionError(req)


async def _start(cipher_name):
    loop = asyncio.get_running_loop()
    transport, device = await loop.create_datagram_endpoint(
        lambda: FakeGree(cipher_name), local_addr=("127.0.0.1", 0)
    )
    return transport, device, transport.get_extra_info("sockname")[1]


@pytest.mark.parametrize("cipher_name", ["ecb", "gcm"])
def test_scan_bind_status_set(cipher_name):
    async def run():
        transport, device, port = await _start(cipher_name)
        try:
            client = GreeClient("127.0.0.1", port, timeout=0.3, retries=0)
            info = await client.scan()
            assert info["name"] == "Fake"
            assert client.mac == MAC

            cipher = await client.bind()
            assert cipher.name == cipher_name  # GCM units fall back after ECB fails
            assert cipher.key == DEVICE_KEY

            assert await client.status(["Pow", "SetTem"]) == {"Pow": 0, "SetTem": 24}
            assert await client.set({"Pow": 1, "SetTem": 21}) == {"Pow": 1, "SetTem": 21}
            assert device.state["Pow"] == 1 and device.state["SetTem"] == 21
        finally:
            transport.close()

    asyncio.run(run())


def test_stored_key_skips_scan_and_bind():
    async def run():
        transport, device, port = await _start("ecb")
        try:
            client = GreeClient(
                "127.0.0.1", port, mac=MAC, key=DEVICE_KEY.decode(), timeout=0.3, retries=0
            )
            assert await client.status(["Mod"]) == {"Mod": 1}
            assert device.binds == 0
        finally:
            transport.close()

    asyncio.run(run())


def test_firmware_reads_scan_and_hid_status_column():
    async def run():
        transport, device, port = await _start("gcm")
        try:
            client = GreeClient("127.0.0.1", port, timeout=0.3, retries=0)
            assert await client.firmware() == {
                "ver": "V1.0",
                "mid": "10001",
                "hid": "362001000967V1.0.4.bin",  # not in scan: from the status column
                "board_version": "1.0.4",
            }
        finally:
            transport.close()

    asyncio.run(run())


def test_scan_keeps_configured_mac():
    async def run():
        transport, device, port = await _start("ecb")
        try:
            client = GreeClient("127.0.0.1", port, mac="f4911e0000ff", timeout=0.3, retries=0)
            await client.scan()
            assert client.mac == "f4911e0000ff"
        finally:
            transport.close()

    asyncio.run(run())


def test_unreachable_raises_connection_error():
    # Grab a free port and close it so nothing is listening there.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    async def run():
        client = GreeClient("127.0.0.1", port, timeout=0.2, retries=1)
        with pytest.raises(GreeConnectionError):
            await client.scan()

    asyncio.run(run())
