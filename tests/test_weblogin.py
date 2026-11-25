"""Logging in to the web admin panel by confirming in the Telegram app."""
from time import time

from bot.db import WebLogin

TOKEN = "AbCdEfGhIjKlMnOpQrStUvWxYz012345"


async def add_request(env, token=TOKEN, age_sec=0, status="pending"):
    """What the admin panel does when someone opens its login page."""
    async with env.repo.session() as s:
        s.add(WebLogin(token=token, created_at=int(time()) - age_sec, browser="Edge on Windows", status=status))
        await s.commit()


async def row(env, token=TOKEN) -> WebLogin:
    async with env.repo.session() as s:
        return await s.get(WebLogin, token)


async def test_confirm_login_in_telegram(make_env):
    env = await make_env()
    await add_request(env)
    anna = env.client(1, "Anna")
    await anna.say(f"/start login_{TOKEN}")
    assert "Log in to the admin panel?" in anna.last_text and "Edge on Windows" in anna.last_text
    assert anna.buttons() == ["✅ Confirm", "Cancel"]
    await anna.press("Confirm")
    r = await row(env)
    assert (r.status, r.user_id, r.first_name, r.username) == ("approved", 1, "Anna", "anna")
    assert "You're logged in" in anna.last_text

    await anna.press("Confirm")  # the old button again: nothing changes
    assert "expired" in anna.last_text and (await row(env)).status == "approved"


async def test_cancel_and_expired_links(make_env):
    env = await make_env()
    await add_request(env)
    bob = env.client(2, "Bob")
    await bob.say(f"/start login_{TOKEN}")
    await bob.press("Cancel")
    assert (await row(env)).status == "denied" and "cancelled" in bob.last_text

    await add_request(env, token="x" * 32, age_sec=301)  # older than 5 minutes
    await bob.say("/start login_" + "x" * 32)
    assert "expired" in bob.last_text
    await bob.say("/start login_nope")  # not a valid token
    assert "expired" in bob.last_text
    await add_request(env, token="y" * 32, status="used")
    await bob.say("/start login_" + "y" * 32)
    assert "expired" in bob.last_text


async def test_normal_start_still_works(make_env):
    env = await make_env()
    anna = env.client(1, "Anna")
    await anna.say("/start")
    assert "Log in" not in anna.last_text and anna.last_text  # the usual welcome
