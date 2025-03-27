from time import sleep
from threading import Thread, Lock

from mattermostdriver import Driver
import websockets.client
import json
from asyncio import run

from secret import TOKEN
from config import URL, PORT

URI = f"wss://{URL}:{PORT}/api/v4/websocket"

AUTH_SEND = json.dumps({"seq": 1, "action": "authentication_challenge", "data": {"token": TOKEN}})

EMOJI_NAME = "rat"


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

    sent_message = driver.client.post(
        '/posts',
        data=json.dumps({
            "channel_id": "fihtswmigbd68y8a1rway3b7dw",
            "message": "FDev presenterar sitt nya MaMo-verktyg 'RåttBot' som hjälper dig skriva bättre meddelanden! Reagera med 🐀 för att opt in!",
        })
    )
    message_id = sent_message['id']

    opted_in_users = []
    lock = Lock()

    def update_reactions_loop(opted_in_users: list[str]):
        while True:
            reactions = driver.client.get(f'/posts/{message_id}/reactions')
            if reactions is None:
                users = []
            else:
                users = list(map(lambda x: x["user_id"], list(filter(lambda x: x["emoji_name"] == "rat", reactions))))
            with lock:
                opted_in_users.clear()
                opted_in_users.extend(users)
            sleep(5)

    t = Thread(target = update_reactions_loop, args = (opted_in_users,))
    t.start()

    async with websockets.client.connect(URI) as ws:
        await ws.send(AUTH_SEND)

        while True:
            res = json.loads(await ws.recv())
            if 'event' in res:
                if res['event'] == 'posted':
                    post = json.loads(res['data']['post'])
                    with lock:
                        if post['user_id'] in opted_in_users:
                            print(post['message'])


run(main())
