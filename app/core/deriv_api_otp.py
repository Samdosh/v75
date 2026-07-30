"""Deriv API OTP authentication helper for new API"""
import asyncio
import json
import urllib.request
from typing import Optional

DERIV_API_BASE = "https://api.derivws.com/trading/v1"

async def _http_post_async(url: str, headers: dict, body: bytes = b"{}") -> dict:
    return await asyncio.to_thread(_http_post, url, headers, body)

def _http_post(url: str, headers: dict, body: bytes = b"{}") -> dict:
    req = urllib.request.Request(url, method="POST", data=body, headers=headers)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

async def _http_get_async(url: str, headers: dict) -> dict:
    return await asyncio.to_thread(_http_get, url, headers)

def _http_get(url: str, headers: dict) -> dict:
    req = urllib.request.Request(url, method="GET", headers=headers)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


async def get_accounts(app_id: str, token: str) -> list:
    """Fetch available trading accounts"""
    headers = {
        "Deriv-App-ID": app_id,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    url = f"{DERIV_API_BASE}/options/accounts"
    data = await _http_get_async(url, headers)
    return data.get("data", [])


async def get_otp_url(app_id: str, token: str, account_id: Optional[str] = None) -> str:
    """
    Get authenticated WebSocket URL via OTP flow.
    If account_id is None, fetches accounts and uses the first demo or real account.
    """
    headers = {
        "Deriv-App-ID": app_id,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    if not account_id:
        accounts = await get_accounts(app_id, token)
        if not accounts:
            raise RuntimeError("No Deriv accounts found for this token")
        account_id = accounts[0]["account_id"]

    url = f"{DERIV_API_BASE}/options/accounts/{account_id}/otp"
    data = await _http_post_async(url, headers)
    ws_url = data.get("data", {}).get("url")
    if not ws_url:
        raise RuntimeError(f"No WebSocket URL in OTP response: {data}")
    return ws_url