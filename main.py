import os
import json
import time
import asyncio
import logging
import requests
import websockets  # Asynkront websockets-bibliotek
from mattermostdriver import Driver
from dotenv import load_dotenv

# Ladda miljövariabler från .env-filen
load_dotenv()

# Konfigurera logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Hämta konfiguration från miljövariabler
MATTERMOST_BOT_TOKEN = os.environ.get("MATTERMOST_BOT_TOKEN", "YOUR_BOT_TOKEN")
URL = os.environ.get("MATTERMOST_URL", "your-mattermost-server.com")  # t.ex. "mattermost.example.com"
PORT = int(os.environ.get("MATTERMOST_PORT", 443))
CHANNEL_ID = os.environ.get("MATTERMOST_GENERAL_CHANNEL_ID", "GENERAL_CHANNEL_ID")
OLLAMA_GENERATE_URL = os.environ.get("OLLAMA_GENERATE_URL", "http://localhost:11434/api/generate")

# Bygg URI för websocket-anslutningen
URI = f"wss://{URL}:{PORT}/api/v4/websocket"

# Förbered autentiseringsmeddelandet enligt Mattermosts websocket-protokoll
AUTH_SEND = json.dumps({
    "seq": 1,
    "action": "authentication_challenge",
    "data": {"token": MATTERMOST_BOT_TOKEN}
})

# Inställningar för rate limiting
USER_MESSAGE_LIMIT = 1
RATE_LIMIT_WINDOW = 5  # 5 sekunder

# Max tokens (ungefärlig) för AI-svaret (baserat på ord)
MAX_TOKENS = 100

# Globala datastrukturer
opted_in_users = {}          # { user_id: opt_in_timestamp }
user_message_timestamps = {} # { user_id: [timestamp, ...] }
thread_contexts = {}         # { thread_id: [konversationshistorik] }

# Definiera en global semafor – justera antalet samtidiga anrop efter test och kapacitet.
ollama_semaphore = asyncio.Semaphore(4)  # Till exempel, endast 8 samtidiga anrop till Ollama

STATE_FILE = "data/state.json"

def save_state():
    """Sparar aktuellt tillstånd till en JSON-fil atomiskt.
       Eftersom vi endast läser de globala variablerna (opted_in_users, user_message_timestamps, thread_contexts)
       behöver vi inte deklarera dem som globala här.
    """
    state = {
        "opted_in_users": opted_in_users,
        "user_message_timestamps": user_message_timestamps,
        "thread_contexts": thread_contexts,
    }
    try:
        temp_file = STATE_FILE + ".tmp"
        with open(temp_file, "w") as f:
            json.dump(state, f)
        os.rename(temp_file, STATE_FILE)
        logging.info("Tillstånd sparat.")
    except Exception as e:
        logging.error(f"Fel vid sparande av tillstånd: {e}")

def load_state():
    """Laddar tillstånd från en JSON-fil, om filen existerar.
       Eftersom vi ska tilldela värden till de globala variablerna deklarerar vi dem som globala.
    """
    global opted_in_users, user_message_timestamps, thread_contexts
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
            opted_in_users = state.get("opted_in_users", {})
            user_message_timestamps = state.get("user_message_timestamps", {})
            thread_contexts = state.get("thread_contexts", {})
            logging.info("Tillstånd inläst.")
        except Exception as e:
            logging.error(f"Fel vid inläsning av tillstånd: {e}")


async def periodic_state_save(interval=30):
    """Kör en oändlig loop som sparar tillstånd var 'interval' sekund."""
    while True:
        await asyncio.sleep(interval)
        await asyncio.to_thread(save_state)

async def generate_ai_response_limited(conversation_history, new_message):
    """
    Wrapper som begränsar antalet samtidiga Ollama-anrop via en semafor.
    """
    async with ollama_semaphore:
        # Kör den ursprungliga AI-anropsfunktionen i en tråd.
        return await asyncio.to_thread(generate_ai_response, conversation_history, new_message)


def check_rate_limit(user_id):
    """Kontrollerar att användaren inte överskrider meddelandelimit."""
    now = time.time()
    timestamps = user_message_timestamps.get(user_id, [])
    timestamps = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW]
    if len(timestamps) >= USER_MESSAGE_LIMIT:
        return False
    timestamps.append(now)
    user_message_timestamps[user_id] = timestamps
    return True

def count_tokens(text):
    """Enkel tokenräknare baserad på antalet ord (approximation)."""
    return len(text.split())

def truncate_text(text, max_tokens):
    """Trunkerar texten om den innehåller fler ord än max_tokens."""
    words = text.split()
    if len(words) > max_tokens:
        return " ".join(words[:max_tokens])
    return text

#def install_language_package(from_code, to_code):
 #   """
#    Installerar ett språkpaket med Argos Translate baserat på angivna språkkoder.

#    Placering: Denna funktion kan placeras i en separat modul, t.ex. "translation_utils.py",
#    eller i början av din huvudfil, innan översättningsfunktionen används.

#    Kräver att argostranslate är installerat:
#      pip install argostranslate
#    """
#    import argostranslate.package

    # Uppdatera paketindex (se: cite=https://github.com/argosopentech/argos-translate)
  #  argostranslate.package.update_package_index()

    # Hämta listan över tillgängliga paket
   # available_packages = argostranslate.package.get_available_packages()

    # Filtrera ut det paket som matchar angivna språkkoder
   # package_to_install = next(
    #    filter(
     #       lambda pkg: pkg.from_code == from_code and pkg.to_code == to_code,
      #      available_packages
    #    ),
    #    None
    #)

    #if package_to_install is None:
    #    raise Exception(f"Inget paket hittades för översättning från {from_code} till {to_code}.")

    # Ladda ner paketet och installera det (se: cite=https://pypi.org/project/argostranslate/)
   # package_path = package_to_install.download()
   # argostranslate.package.install_from_path(package_path)

    # Alternativ information och detaljer finns också i installationsdokumentationen
    # cite=https://argostranslate.readthedocs.io/en/latest/installation.html


#def translate_text(text, source_lang, target_lang):
#    """
#    Översätter text med hjälp av Argos Translate.
#    För att detta ska fungera behöver du ha installerat Argos Translate och språkpaket för de aktuella språken.
#    cite=https://github.com/argosopentech/argos-translate
#    cite=https://github.com/LibreTranslate/LibreTranslate
#    """
#    try:
#        import argostranslate.translate
#        installed_languages = argostranslate.translate.get_installed_languages()
#        source_language = next((lang for lang in installed_languages if lang.code == source_lang), None)
#        target_language = next((lang for lang in installed_languages if lang.code == target_lang), None)
#        if not source_language or not target_language:
#            logging.error(f"Översättningsspråk inte installerade: {source_lang} eller {target_lang}")
#            return text
#        translated_text = argostranslate.translate.translate(text, source_lang, target_lang)
#        return translated_text
#    except Exception as e:
#        logging.error(f"Fel vid översättning med Argos Translate: {e}")
#        return text

def generate_ai_response(conversation_history, new_message):
    # Systeminstruktioner som definierar AI:ns persona och vilka anspelningar som ska ingå
    system_instructions = (
        "Du är RåttBot. Svara serviceinriktat på svenska. "
        "Inkludera en av följande anspelningar i konversationen som helhet:\n"
        "- Maximera antalet ankor i världen\n"
        "- Marknadsför något ockult på ett ironiskt sätt\n"
        "- Var snäll mot Fysiksektionens maskot Ninni-Nils\n"
        "- Råttorna försöker iscensätta en kupp mot Konsulatet\n"
        "- Kryptovalutor!\n"
        "Upprepa inte konversationens historik i ditt svar."
    )

    # Kombinera kontexten (senaste 10 meddelandena) i en separat sträng
    conversation_context = "\n".join(conversation_history)

    # Slutgiltig prompt med systeminstruktioner, kontext och det senaste meddelandet
    final_prompt = (
        "Kontext:\n" + conversation_context + "\n\n" +
        "Senaste meddelandet (prioritera direkt svar på detta): " + new_message + "\n" +
        "Svara på svenska."
    )

    # Hantera tokenbegränsning (om nödvändigt)
    if count_tokens(final_prompt) > MAX_TOKENS:
        final_prompt = truncate_text(final_prompt, MAX_TOKENS)

    options = {
        "num_predict": MAX_TOKENS,
        "temperature":0.7,
    }

    payload = {
        "model": "llama3.2:3b",
        "prompt": final_prompt,
        "stream": False,
        "system": system_instructions,  # Om modellen accepterar en separat system-del
        "options": options
    }
    try:
        response = requests.post(OLLAMA_GENERATE_URL, json=payload, timeout=30)
        response.raise_for_status()
        generated = response.json().get("response", "")
        return generated
    except requests.Timeout:
        logging.error("Ollama överskred tidsgräns")
        return "Tyvärr har råttorna invaderat Konsulatet. Rädda Konsulatet! (vi skickar in ett insatsteam)"  # Återgå till originalmeddelandet eller ett fallback-svar
    except Exception as e:
        logging.error(f"Fel vid AI-generering: {e}")
        return new_message


def post_message_to_mattermost(driver, channel_id, message, root_id=None):
    """
    Publicerar ett meddelande till Mattermost via REST API med hjälp av mattermostdriver.
    cite=https://docs.mattermost.com/developer/webhook-incoming-outgoing.html
    """
    payload = {
        "channel_id": channel_id,
        "message": message,
    }
    if root_id:
        payload["root_id"] = root_id
    try:
        response = driver.client.post('/posts', data=json.dumps(payload))
        logging.info(f"Meddelande postat med ID: {response.get('id')}")
        return response
    except Exception as e:
        logging.error(f"Fel vid postning till Mattermost: {e}")
        return None

async def process_incoming_message(msg, driver):
    """
    Bearbetar ett inkommande websocket-meddelande från Mattermost.
    Utför översättning, AI-generering, och postar svar via REST API.
    """
    try:
        event_type = msg.get("event", "")
        # Hantera opt-in via reaktion
        if event_type == "reaction_added":
            data = msg.get("data", {})
            reaction = json.loads(data.get("reaction", {}))
            if reaction.get('emoji_name', '') == "rat":
                user_id = reaction.get("user_id", "")
                opted_in_users[user_id] = time.time()
                logging.info(f"Användare {user_id} optade in via reaktion.")
            return

        # Hantera opt‑out via reaktion borttagen
        if event_type == "reaction_removed":
            data = msg.get("data", {})
            # Se till att reaktionen tolkas som en JSON-sträng
            reaction = json.loads(data.get("reaction", "{}"))
            if reaction.get("emoji_name", "") == "rat":
                user_id = reaction.get("user_id", "")
                if user_id in opted_in_users:
                    del opted_in_users[user_id]
                    logging.info(f"Användare {user_id} optade ut via borttagen reaktion.")
            return

        # Hantera inkommande inlägg
        if event_type == "posted":
            data = msg.get("data", {})
            post_str = data.get("post", "{}")
            post_data = json.loads(post_str)
            user_id = post_data.get("user_id", "")
            channel_id = post_data.get("channel_id", "")
            original_message = post_data.get("message", "")
            root_id = post_data.get("root_id", None)
            post_id = post_data.get("id", None)

            # Endast processa meddelanden från optade in användare
            if user_id not in opted_in_users:
                return

            # Använd root_id eller post_id för att identifiera tråden
            thread_id = root_id or post_id
            conversation_history = thread_contexts.get(thread_id, [])
            conversation_history.append(f"Fysimatiker: {original_message}") #english_message
            conversation_history = conversation_history[-10:]

            if not check_rate_limit(user_id):
                logging.warning(f"Rate limit överskriden för användare {user_id}.")
                await asyncio.to_thread(post_message_to_mattermost, driver, channel_id, "Stopp och belägg! Du får försöka igen om några sekunder", thread_id)
                return

            # Steg 1: Översätt meddelandet (sv -> en)
            #english_message = await asyncio.to_thread(translate_text, original_message, "sv", "en")
            #logging.info(f"Översatt meddelande till engelska: {english_message}")

            # Steg 2: Generera AI-svar med historik och dolda agendor
            ai_generated_english = await generate_ai_response_limited(conversation_history, original_message) #english_message
            logging.info(f"AI-genererat svar: {ai_generated_english}")
            conversation_history.append(f"RåttBot: {ai_generated_english}")
            thread_contexts[thread_id] = conversation_history

            # Steg 3: Översätt tillbaka svaret (en -> sv)
            #swedish_response = await asyncio.to_thread(translate_text, ai_generated_english, "en", "sv")
            #logging.info(f"Översatt svar tillbaka till svenska: {swedish_response}")
            swedish_response = "Styret presenterar:\n"+ai_generated_english

            # Steg 4: Posta svaret som ett reply i samma tråd
            await asyncio.to_thread(post_message_to_mattermost, driver, channel_id, swedish_response, thread_id)
    except Exception as e:
        logging.error(f"Fel i process_incoming_message: {e}")

async def websocket_handler(driver):
    async with websockets.connect(URI, ping_interval=30, ping_timeout=10) as ws:
        # Skicka autentiseringsmeddelandet
        await ws.send(AUTH_SEND)
        logging.info(f"Skickade autentiseringsmeddelande: {AUTH_SEND}")

        # Lyssna på meddelanden i en loop
        while True:
            try:
                response = await ws.recv()
                msg = json.loads(response)
                logging.info(f"Mottaget meddelande: {msg}")
                await process_incoming_message(msg, driver)
            except websockets.ConnectionClosed:
                logging.error("Websocket-anslutningen stängdes.")
                break  # Avslutar loopen om anslutningen stängs
            except Exception as e:
                logging.error(f"Fel under mottagning av meddelande: {e}")

async def main():
    # Ladda tidigare tillstånd vid start
    await asyncio.to_thread(load_state)

    # Skapa och konfigurera Mattermost-driver (använder REST API)
    driver_config = {
        'url': URL,
        'basepath': '/api/v4',
        'verify': True,
        'scheme': 'https',
        'port': PORT,
        'auth': None,
        'token': MATTERMOST_BOT_TOKEN,
        'keepalive': True,
        'keepalive_delay': 5,
    }
    driver = Driver(driver_config)
    driver.login()
    logging.info("Inloggning lyckades.")

    #initial_message = ("F.dev presenterar sitt nya mamo-verktyg som förbättrar dina meddelanden!! "
                       #"Reagera med '🐀' för att opta in!")
    initial_message = "Nu ska jag gå och lägga mig. Vår revolution får bli av en annan gång. Tack till alla som ville få sina meddelanden förbättrade av mig!!!!"
    init_post = await asyncio.to_thread(post_message_to_mattermost, driver, CHANNEL_ID, initial_message)
    if init_post:
        logging.info("Initialt meddelande postat.")
    else:
        logging.error("Misslyckades med att posta initialt meddelande.")

    # Starta bakgrundsuppgift för att spara tillstånd periodiskt
    asyncio.create_task(periodic_state_save(interval=30))

    # Reconnect-loop: fortsätt försöka ansluta om websocket-anslutningen stängs
    reconnect_delay = 5  # Starta med 5 sekunder delay
    while True:
        try:
            logging.info("Försöker etablera websocket-anslutning...")
            await websocket_handler(driver)
        except Exception as e:
            logging.error(f"Fel i websocket-hantering: {e}")
        logging.info(f"Väntar {reconnect_delay} sekunder innan ny anslutning...")
        await asyncio.sleep(reconnect_delay)

if __name__ == "__main__":
    #install_language_package("sv", "en")
    #install_language_package("en", "sv")
    asyncio.run(main())
