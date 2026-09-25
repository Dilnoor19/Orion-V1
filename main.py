 
import ast
import datetime
import logging
import operator
import os
import re
import threading
import time
import webbrowser
from dataclasses import dataclass, field
 
import psutil
import pyautogui
import pyttsx3
import requests
import speech_recognition as sr
import wikipedia
import pywhatkit as kit
 
# ─────────────────────────────────────────────
#  CONFIG  — pulled from environment variables, never hardcoded
# ─────────────────────────────────────────────
# Set these once in your shell / .env file, e.g. (PowerShell):
#   setx GEMINI_API_KEY "your-key"
#   setx GEMINI_URL "https://generativelanguage.googleapis.com/..."
#   setx WEATHER_API_KEY "your-key"
#   setx NEWS_API_KEY "your-key"
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional; env vars set another way still work
 
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_URL = os.getenv("GEMINI_URL", "")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
 
FEATURE_FLAGS = {
    "gemini": bool(GEMINI_API_KEY and GEMINI_URL),
    "weather": bool(WEATHER_API_KEY),
    "news": bool(NEWS_API_KEY),
}
 
# ─────────────────────────────────────────────
#  LOGGING — errors go to a file instead of only flashing past in the console
# ─────────────────────────────────────────────
logging.basicConfig(
    filename="orion.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("orion")
 
 
# ─────────────────────────────────────────────
#  TTS ENGINE — safe init, won't crash if voice index doesn't exist
# ─────────────────────────────────────────────
def init_tts_engine():
    engine = pyttsx3.init("sapi5")
    voices = engine.getProperty("voices")
    # Guard against machines with only one installed voice
    voice_index = 1 if len(voices) > 1 else 0
    if voices:
        engine.setProperty("voice", voices[voice_index].id)
    engine.setProperty("rate", max(engine.getProperty("rate") - 50, 100))
    engine.setProperty("volume", min(engine.getProperty("volume") + 0.25, 1.0))
    return engine
 
 
engine = init_tts_engine()
tts_lock = threading.Lock()  # engine.runAndWait() is not thread-safe
 
 
def speak(text: str):
    print(f"Orion: {text}")
    with tts_lock:
        try:
            engine.say(text)
            engine.runAndWait()
        except Exception as e:
            logger.error(f"TTS failure: {e}")
 
 
# ─────────────────────────────────────────────
#  CHAT HISTORY
# ─────────────────────────────────────────────
chat_history = []
last_response = ""
 
 
def add_to_history(role: str, text: str):
    chat_history.append({"role": role, "text": text})
    if len(chat_history) > 20:
        chat_history.pop(0)
 
 
def show_history():
    if not chat_history:
        speak("We haven't talked much yet, boss.")
        return
    print("\n--- Conversation History ---")
    for entry in chat_history[-10:]:
        label = "You  " if entry["role"] == "user" else "Orion"
        print(f"  {label}: {entry['text']}")
    print("----------------------------\n")
    speak("Here's what we talked about recently.")
 
 
# ─────────────────────────────────────────────
#  REMINDERS — thread-safe, richer time parsing, cancel support
# ─────────────────────────────────────────────
@dataclass
class Reminder:
    message: str
    fire_at: datetime.datetime
    fired: bool = False
 
 
reminders: list[Reminder] = []
reminders_lock = threading.Lock()
_shutdown_event = threading.Event()
 
UNIT_TO_SECONDS = {
    "second": 1, "seconds": 1, "sec": 1, "secs": 1,
    "minute": 60, "minutes": 60, "min": 60, "mins": 60,
    "hour": 3600, "hours": 3600, "hr": 3600, "hrs": 3600,
}
 
REMINDER_PATTERN = re.compile(
    r"(?:remind me to|set reminder(?:\s*(?:to|for))?)\s+(?P<msg>.+?)\s+in\s+"
    r"(?P<value>\d+)\s*(?P<unit>seconds?|secs?|minutes?|mins?|hours?|hrs?)",
    re.IGNORECASE,
)
 
 
def add_reminder(message: str, seconds: int):
    fire_at = datetime.datetime.now() + datetime.timedelta(seconds=seconds)
    with reminders_lock:
        reminders.append(Reminder(message=message, fire_at=fire_at))
    friendly = _friendly_duration(seconds)
    speak(f"Sure, I'll remind you to {message} in {friendly}.")
 
 
def _friendly_duration(seconds: int) -> str:
    if seconds % 3600 == 0 and seconds >= 3600:
        h = seconds // 3600
        return f"{h} hour{'s' if h != 1 else ''}"
    if seconds % 60 == 0 and seconds >= 60:
        m = seconds // 60
        return f"{m} minute{'s' if m != 1 else ''}"
    return f"{seconds} second{'s' if seconds != 1 else ''}"
 
 
def check_reminders():
    while not _shutdown_event.is_set():
        now = datetime.datetime.now()
        with reminders_lock:
            due = [r for r in reminders if not r.fired and now >= r.fire_at]
            for r in due:
                r.fired = True
        for r in due:
            speak(f"Hey boss, reminder — {r.message}")
        _shutdown_event.wait(timeout=15)
 
 
def parse_reminder_command(command: str):
    match = REMINDER_PATTERN.search(command)
    if not match:
        speak("Say it like — remind me to drink water in 10 minutes.")
        return
    message = match.group("msg").strip() or "that thing you wanted"
    value = int(match.group("value"))
    unit = match.group("unit").lower()
    seconds = value * UNIT_TO_SECONDS.get(unit, 60)
    if seconds <= 0:
        speak("That reminder time doesn't make sense. Try a positive number.")
        return
    add_reminder(message, seconds)
 
 
def list_reminders():
    with reminders_lock:
        pending = [r for r in reminders if not r.fired]
    if not pending:
        speak("Nothing on the reminder list right now.")
        return
    speak(f"You've got {len(pending)} pending reminder{'s' if len(pending) > 1 else ''}.")
    print("\n--- Pending Reminders ---")
    for r in pending:
        t = r.fire_at.strftime("%I:%M %p")
        print(f"  - {r.message} at {t}")
        speak(f"{r.message} at {t}")
    print("-------------------------\n")
 
 
def clear_reminders():
    with reminders_lock:
        count = len([r for r in reminders if not r.fired])
        reminders.clear()
    speak(f"Cleared {count} reminder{'s' if count != 1 else ''}." if count else "Nothing to clear.")
 
 
# ─────────────────────────────────────────────
#  SYSTEM INFO
# ─────────────────────────────────────────────
def get_system_info():
    try:
        cpu = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        battery = psutil.sensors_battery()
    except Exception as e:
        logger.error(f"System info failure: {e}")
        speak("Couldn't read system stats right now.")
        return
 
    ram_used = round(ram.used / (1024**3), 1)
    ram_total = round(ram.total / (1024**3), 1)
    disk_used = round(disk.used / (1024**3), 1)
    disk_total = round(disk.total / (1024**3), 1)
 
    print("\n--- System Status ---")
    print(f"  CPU   : {cpu}%")
    print(f"  RAM   : {ram_used} / {ram_total} GB  ({ram.percent}%)")
    print(f"  Disk  : {disk_used} / {disk_total} GB")
 
    info = f"CPU is at {cpu}%. RAM usage is {ram.percent}%, that's {ram_used} out of {ram_total} gigs."
 
    if battery:
        charge = round(battery.percent)
        plugged = "plugged in" if battery.power_plugged else "running on battery"
        print(f"  Batt  : {charge}% ({'charging' if battery.power_plugged else 'discharging'})")
        info += f" Battery is at {charge}%, {plugged}."
    else:
        print("  Batt  : not available")
 
    print("---------------------\n")
    speak(info)
 
 
# ─────────────────────────────────────────────
#  CALCULATOR / UNIT CONVERTER — ast-based, no eval()
# ─────────────────────────────────────────────
_ALLOWED_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}
 
 
def _eval_node(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPS:
        return _ALLOWED_OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_OPS:
        return _ALLOWED_OPS[type(node.op)](_eval_node(node.operand))
    raise ValueError("Disallowed expression")
 
 
def safe_calculate(expression: str):
    """Evaluate arithmetic without using eval()."""
    try:
        tree = ast.parse(expression, mode="eval")
        result = _eval_node(tree.body)
        return str(round(result, 6)) if isinstance(result, float) else str(result)
    except ZeroDivisionError:
        return "undefined (division by zero)"
    except Exception:
        return None
 
 
UNIT_CONVERSIONS = {
    "km to miles": lambda v: v * 0.621371,
    "miles to km": lambda v: v * 1.60934,
    "meters to feet": lambda v: v * 3.28084,
    "feet to meters": lambda v: v / 3.28084,
    "cm to inches": lambda v: v / 2.54,
    "inches to cm": lambda v: v * 2.54,
    "kg to pounds": lambda v: v * 2.20462,
    "pounds to kg": lambda v: v / 2.20462,
    "grams to ounces": lambda v: v * 0.035274,
    "ounces to grams": lambda v: v / 0.035274,
    "celsius to fahrenheit": lambda v: (v * 9 / 5) + 32,
    "fahrenheit to celsius": lambda v: (v - 32) * 5 / 9,
    "mb to gb": lambda v: v / 1024,
    "gb to mb": lambda v: v * 1024,
    "gb to tb": lambda v: v / 1024,
    "tb to gb": lambda v: v * 1024,
}
 
 
def handle_calculator(command: str):
    command = command.lower()
 
    if "convert" in command:
        for key, fn in UNIT_CONVERSIONS.items():
            if key in command:
                # pull the first number out of the command, wherever it sits
                number_match = re.search(r"-?\d+(?:\.\d+)?", command)
                if not number_match:
                    speak("Say it like — convert 100 km to miles.")
                    return
                value = float(number_match.group())
                result = round(fn(value), 4)
                from_unit, to_unit = key.split(" to ")
                speak(f"{value} {from_unit} comes out to {result} {to_unit}.")
                print(f"  {value} {key} = {result}")
                return
        speak("I don't have that conversion yet. I'll add it soon.")
        return
 
    expr = (
        command.replace("calculate", "")
        .replace("what is", "")
        .replace("?", "")
        .replace("plus", "+")
        .replace("minus", "-")
        .replace("multiplied by", "*")
        .replace("times", "*")
        .replace("divided by", "/")
        .strip()
    )
    result = safe_calculate(expr)
    if result is not None:
        speak(f"That's {result}.")
        print(f"  {expr} = {result}")
    else:
        speak("Couldn't work that one out. Try a simpler expression.")
 
 
# ─────────────────────────────────────────────
#  LISTEN
# ─────────────────────────────────────────────
def listen(retries: int = 2) -> str:
    r = sr.Recognizer()
    r.energy_threshold = 300
    r.dynamic_energy_threshold = True
    r.pause_threshold = 0.8
 
    for attempt in range(1, retries + 1):
        try:
            with sr.Microphone() as source:
                r.adjust_for_ambient_noise(source, duration=0.6)
                print(f"Listening... (attempt {attempt}/{retries})")
                audio = r.listen(source, timeout=6, phrase_time_limit=12)
            text = r.recognize_google(audio, language="en-in").lower()
            print(f"You: {text}")
            return text
        except sr.WaitTimeoutError:
            print("No speech detected.")
        except sr.UnknownValueError:
            print("Couldn't make that out.")
        except sr.RequestError as e:
            speak("Having trouble reaching the speech service. Check your internet.")
            logger.error(f"Speech API error: {e}")
            return ""
        except OSError as e:
            speak("Can't find your microphone. Plug it in and try again.")
            logger.error(f"Mic error: {e}")
            return ""
 
    speak("Nothing came through. Try again.")
    return ""
 
 
# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────
def fun():
    try:
        import pyjokes
        speak(pyjokes.get_joke())
    except Exception as e:
        logger.error(f"Joke failure: {e}")
        speak("Ran out of jokes for now.")
 
 
def take_screenshot():
    try:
        pyautogui.screenshot().save("screenshot.png")
        speak("Done, screenshot saved.")
    except Exception as e:
        logger.error(f"Screenshot failure: {e}")
        speak("Couldn't take that screenshot.")
 
 
def cal_day() -> str:
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    return days[datetime.datetime.today().weekday()]
 
 
def wishme():
    hour = datetime.datetime.now().hour
    t = time.strftime("%I:%M %p")
    day = cal_day()
    if hour < 12:
        speak(f"Good morning boss. {day}, {t}. Let's get it.")
    elif hour < 17:
        speak(f"Hey boss. {day} afternoon, {t}. What are we doing?")
    else:
        speak(f"Evening boss. {day}, {t}. Still grinding?")
 
 
def show_time():
    speak(f"It's {datetime.datetime.now().strftime('%I:%M %p')}.")
 
 
def search_wikipedia(query: str):
    try:
        result = wikipedia.summary(query, sentences=2)
        speak(result)
    except wikipedia.exceptions.DisambiguationError:
        speak("That one's a bit ambiguous. Can you be more specific?")
    except wikipedia.exceptions.PageError:
        speak("Couldn't find a Wikipedia page for that.")
    except Exception as e:
        logger.error(f"Wikipedia error: {e}")
        speak("Wikipedia's not cooperating right now.")
 
 
def schedule():
    day = cal_day().lower()
    plans = {
        "monday": "Work till 5, then a workout. After 8, build something or learn something.",
        "tuesday": "Work till 5, then a workout. Evenings are for sharpening a skill.",
        "wednesday": "Work till 5, then a workout. Read a book or study something useful tonight.",
        "thursday": "Work till 5, then a workout. Review your project progress tonight.",
        "friday": "Work till 5, then chill. Light learning or a hobby in the evening.",
        "saturday": "Free day. 3 hours minimum on something you care about. Workout at 7.",
        "sunday": "Rest day. Reflect, plan the week ahead, eat well.",
    }
    speak(plans.get(day, "Nothing planned for today. Go make something happen."))
 
 
WEBSITES = {
    "anime": "https://hianime.to/",
    "discord": "https://discord.com/",
    "type test": "https://www.typingtest.com/",
    "jiocinema": "https://www.jiocinema.com/",
    "snapchat": "https://web.snapchat.com/",
    "w3": "https://www.w3schools.com/",
    "fiverr": "https://www.fiverr.com/",
    "aifinder": "https://theresanaiforthat.com/",
    "mxplayer": "https://www.mxplayer.in/",
    "netflix": "https://www.netflix.com/in/",
    "c compiler": "https://www.programiz.com/c-programming/online-compiler/",
    "paper trading": "https://in.tradingview.com/",
    "github": "https://github.com/",
    "stackoverflow": "https://stackoverflow.com/",
    "leetcode": "https://leetcode.com/",
}
 
# Sort by name length (longest first) so "c compiler" wins over any shorter
# accidental substring match, and match on word boundaries.
_SORTED_SITE_NAMES = sorted(WEBSITES, key=len, reverse=True)
 
 
def open_website(command: str) -> bool:
    for name in _SORTED_SITE_NAMES:
        if re.search(rf"\bopen\s+{re.escape(name)}\b", command):
            try:
                webbrowser.open(WEBSITES[name])
                speak(f"Opening {name}.")
            except Exception as e:
                logger.error(f"Website open error ({name}): {e}")
                speak(f"Couldn't open {name}.")
            return True
    return False
 
 
APPS = {
    "instagram": "C:/Users/dilno/OneDrive/Desktop/Instagram.lnk",
    "brave": "C:/Users/dilno/OneDrive/Desktop/Brave.lnk",
    "spotify": "C:/Users/dilno/OneDrive/Desktop/Spotify.lnk",
    "whatsapp": "C:/Users/dilno/OneDrive/Desktop/WhatsApp.lnk",
    "youtube": "C:/Users/dilno/OneDrive/Desktop/YouTube.lnk",
    "vs code": "C:/Users/dilno/OneDrive/Desktop/Visual Studio Code.lnk",
    "store": "C:/Users/dilno/OneDrive/Desktop/Microsoft Store.lnk",
    "chrome": "C:/Users/Public/Desktop/Google Chrome.lnk",
    "microsoft edge": "C:/Users/Public/Desktop/Microsoft Edge.lnk",
    "copilot": "C:/Users/dilno/OneDrive/Desktop/Copilot.lnk",
    "chatgpt": "C:/Users/dilno/OneDrive/Desktop/ChatGPT.lnk",
    "github desktop": "C:/Users/dilno/OneDrive/Desktop/GitHub.lnk",
    "camera": "C:/Users/dilno/OneDrive/Desktop/Camera.lnk",
    "linkedin": "C:/Users/dilno/OneDrive/Desktop/LinkedIn.lnk",
}
 
_SORTED_APP_NAMES = sorted(APPS, key=len, reverse=True)
 
 
def open_apps(command: str) -> bool:
    for name in _SORTED_APP_NAMES:
        if re.search(rf"\bopen\s+{re.escape(name)}\b", command):
            path = APPS[name]
            if not os.path.exists(path):
                speak(f"Can't find the shortcut for {name}. Check the path.")
                logger.error(f"Missing shortcut: {path}")
                return True
            try:
                os.startfile(path)
                speak(f"Opening {name}.")
            except Exception as e:
                logger.error(f"App open error ({name}): {e}")
                speak(f"Couldn't open {name}.")
            return True
    return False
 
 
def get_weather(city: str = "Delhi"):
    if not FEATURE_FLAGS["weather"]:
        speak("Weather isn't set up yet — no API key configured.")
        return
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric"
    try:
        resp = requests.get(url, timeout=5)
        data = resp.json()
        if data.get("cod") != 200:
            speak(f"Couldn't pull the weather for {city}. {data.get('message', '')}".strip())
            return
        desc = data["weather"][0]["description"]
        temp = data["main"]["temp"]
        hum = data["main"]["humidity"]
        wind = data["wind"]["speed"]
        speak(f"{city} right now — {desc}, {temp} degrees, humidity {hum}%, wind at {wind} metres per second.")
    except requests.exceptions.Timeout:
        speak("Weather request timed out. Internet acting up?")
    except requests.exceptions.RequestException as e:
        logger.error(f"Weather error: {e}")
        speak("Couldn't reach the weather service.")
    except (KeyError, IndexError) as e:
        logger.error(f"Weather parse error: {e}")
        speak("Got a weird response from the weather service.")
 
 
def play_song():
    speak("What do you want to play?")
    song = listen()
    if not song:
        speak("Didn't catch the song name.")
        return
    try:
        kit.playonyt(song)
        speak(f"Playing {song}.")
    except Exception as e:
        logger.error(f"Play song error: {e}")
        speak(f"Couldn't play {song} right now.")
 
 
def get_news():
    if not FEATURE_FLAGS["news"]:
        speak("News isn't set up yet — no API key configured.")
        return
    url = f"https://newsapi.org/v2/top-headlines?country=in&apiKey={NEWS_API_KEY}"
    try:
        data = requests.get(url, timeout=5).json()
        if data.get("status") != "ok":
            speak("News service returned an error.")
            return
        items = data.get("articles", [])[:5]
        if not items:
            speak("Nothing in the news right now.")
            return
        speak("Here's what's happening today.")
        for i, a in enumerate(items, 1):
            title = a.get("title", "Untitled")
            print(f"  {i}. {title}")
            speak(title)
    except requests.exceptions.RequestException as e:
        logger.error(f"News error: {e}")
        speak("Couldn't fetch the news.")
 
 
def chat_with_gemini(prompt: str) -> str:
    if not FEATURE_FLAGS["gemini"]:
        return "Gemini isn't configured — I don't have an API key or URL set."
    headers = {"Content-Type": "application/json"}
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        resp = requests.post(
            f"{GEMINI_URL}?key={GEMINI_API_KEY}" if "key=" not in GEMINI_URL else GEMINI_URL,
            headers=headers, json=data, timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        logger.error(f"Gemini HTTP {resp.status_code}: {resp.text[:300]}")
        return f"Gemini threw a {resp.status_code}."
    except requests.exceptions.Timeout:
        return "Gemini took too long. Try again."
    except (KeyError, IndexError) as e:
        logger.error(f"Gemini parse error: {e}")
        return "Gemini gave back something I couldn't read."
    except requests.exceptions.RequestException as e:
        logger.error(f"Gemini request error: {e}")
        return "Couldn't reach Gemini right now."
 
 
# ─────────────────────────────────────────────
#  MAIN LOOP
# ─────────────────────────────────────────────
def command_prompt():
    global last_response
 
    if not any(FEATURE_FLAGS.values()):
        logger.info("No optional API keys configured — running with core features only.")
 
    reminder_thread = threading.Thread(target=check_reminders, daemon=True)
    reminder_thread.start()
 
    wishme()
    speak("Orion online.")
 
    try:
        while True:
            try:
                command = listen()
                if not command:
                    continue
 
                add_to_history("user", command)
                command = command.strip()
 
                if "open " in command:
                    if not open_website(command) and not open_apps(command):
                        speak("Can't find that one. Want me to search it?")
 
                elif any(kw in command for kw in ["set reminder", "remind me"]):
                    parse_reminder_command(command)
 
                elif "clear reminder" in command or "cancel reminder" in command:
                    clear_reminders()
 
                elif "list reminder" in command or "show reminder" in command:
                    list_reminders()
 
                elif any(kw in command for kw in ["system info", "cpu", "ram", "battery", "disk"]):
                    get_system_info()
 
                elif any(kw in command for kw in ["calculate", "what is", "convert"]):
                    handle_calculator(command)
 
                elif any(kw in command for kw in ["chat history", "show history", "last commands"]):
                    show_history()
 
                elif "repeat" in command:
                    speak(last_response if last_response else "I haven't said anything yet.")
 
                elif "joke" in command or "something funny" in command:
                    fun()
 
                elif "time" in command:
                    show_time()
 
                elif "schedule" in command:
                    schedule()
 
                elif "volume up" in command or "increase volume" in command:
                    pyautogui.press("volumeup")
                    speak("Done.")
 
                elif "volume down" in command or "decrease volume" in command:
                    pyautogui.press("volumedown")
                    speak("Done.")
 
                elif "mute" in command:
                    pyautogui.press("volumemute")
                    speak("Muted.")
 
                elif "weather" in command:
                    get_weather()
 
                elif "play" in command:
                    play_song()
 
                elif "screenshot" in command or "take ss" in command:
                    take_screenshot()
 
                elif "news" in command:
                    get_news()
 
                elif "wikipedia" in command:
                    query = command.replace("wikipedia", "").strip()
                    search_wikipedia(query) if query else speak("What should I look up?")
 
                elif any(kw in command for kw in ["exit", "stop", "shutdown", "bye"]):
                    speak("Shutting down. Later boss.")
                    break
 
                else:
                    response = chat_with_gemini(command)
                    last_response = response
                    add_to_history("orion", response)
                    speak(response)
 
            except Exception as e:
                # A single bad command should never take the whole assistant down.
                logger.exception(f"Unhandled error in command loop: {e}")
                speak("Something went sideways there, but I'm still with you.")
 
    except KeyboardInterrupt:
        speak("Caught that. Shutting down. Later boss.")
    finally:
        _shutdown_event.set()
 
 
if __name__ == "__main__":
    command_prompt()
 
