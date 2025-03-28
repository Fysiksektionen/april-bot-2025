import time
from time import sleep
from threading import Thread, Lock

from mattermostdriver import Driver
import websockets.client
import json
from asyncio import run
from ollama import chat
import libretranslate
from libretranslatepy import LibreTranslateAPI

from secret import TOKEN
from config import *
from prompt import PROMPT


URI = f"wss://{URL}:{PORT}/api/v4/websocket"

AUTH_SEND = json.dumps({"seq": 1, "action": "authentication_challenge", "data": {"token": TOKEN}})

print('Starting...')
Thread(target = lambda: libretranslate.main()).start()
print('Started LibreTranslate...')
translator = LibreTranslateAPI("http://localhost:5000/")
print('Initialized translator...')


async def main():
    driver = Driver(
        {
            'url': URL,
            'basepath': '/api/v4',
            'verify': True,
            'scheme': 'https',
            'port': PORT,
            'auth': None,
            'token': TOKEN,
            'keepalive': True,
            'keepalive_delay': 5,
        }
    )

    driver.login()
    print('Logged in to MatterMost...')

    sent_message = driver.client.post(
        '/posts',
        data=json.dumps({
            "message": INITIAL_MESSAGE,
            "channel_id": INITIAL_MESSAGE_CHANNEL_ID,
        })
    )
    print('Sent initial message...')

    message_id = sent_message['id']
    lock = Lock()
    opted_in_users = []
    last_timestamps = {}

    t = Thread(target = update_reactions_loop, args = (driver, message_id, lock, opted_in_users))
    t.start()

    async with websockets.client.connect(URI) as ws:
        await ws.send(AUTH_SEND)

        while True:
            res = json.loads(await ws.recv())

            if 'event' not in res or 'data' not in res: continue
            if res['event'] != 'posted': continue
            if 'post' not in res['data']: continue
            post = json.loads(res['data']['post'])

            if 'user_id' not in post: continue
            user_id = post['user_id']
            current_time = time.time()
            if user_id in last_timestamps.keys():
                last_timestamp = last_timestamps.get(user_id)
                if current_time - last_timestamp < PER_USER_REPLY_COOLDOWN:
                    continue
            last_timestamps[user_id] = current_time
            with lock:
                if user_id in opted_in_users:
                    reply(driver, post['channel_id'], post['id'], post['message'])


def update_reactions_loop(driver, message_id, lock, opted_in_users: list[str]):
    while True:
        reactions = driver.client.get(f'/posts/{message_id}/reactions')
        if reactions is None:
            users = []
        else:
            # TODO add error handling
            # TODO check response code
            users = list(map(lambda x: x["user_id"], list(filter(lambda x: x["emoji_name"] == EMOJI, reactions))))
        with lock:
            opted_in_users.clear()
            opted_in_users.extend(users)
        sleep(REACTION_UPDATE_TIMER)


def replace_keywords(message: str, is_prompt: bool):
    for sv, en in KEYWORDS:
        if is_prompt:
            message = message.replace(sv, en)
        else:
            message = message.replace(en, sv)
    return message


def generate_response(message):
    # TODO add token limit
    response = chat(model = MODEL, messages = [
        {
            'role': 'user',
            'content': PROMPT + message
        }
    ])
    # TODO add error handling
    return response['message']['content']


def reply(driver, original_channel_id, message_id, message):
    print("Cooking up reply...")
    message = replace_keywords(message, True)
    print("Translating user message...")
    message = translator.translate(message, 'sv', 'en')
    print("Generating response...")
    response = generate_response(message)
    print("Translating response...")
    response = translator.translate(response, 'en', 'sv')
    response = replace_keywords(response, False)
    print("Sending reply...")
    # TODO reply in thread if not alredy in thread
    channel_id = original_channel_id
    driver.client.post(
        '/posts',
        data=json.dumps({
            "channel_id": channel_id,
            "message": response,
        })
    )


run(main())
