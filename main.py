import datetime
import time
import threading
import psutil
import pyautogui
import pyttsx3
import speech_recognition as sr
import webbrowser
import os
import requests
import pyjokes
import wikipedia
import pywhatkit as kit

# ─────────────────────────────────────────────
#  CONFIG  —  replace with your actual keys
# ─────────────────────────────────────────────
GEMINI_API_KEY  = "put your own api key"
GEMINI_URL      = "put your gemini url"
WEATHER_API_KEY = "put your own api key"
NEWS_API_KEY    = "put your own api key"

# ─────────────────────────────────────────────
#  TTS ENGINE
# ─────────────────────────────────────────────
engine = pyttsx3.init("sapi5")
voices = engine.getProperty("voices")
engine.setProperty("voice", voices[1].id)
engine.setProperty("rate", engine.getProperty("rate") - 50)
engine.setProperty("volume", min(engine.getProperty("volume") + 0.25, 1.0))

def speak(text: str):
    print(f"Orion: {text}")
    engine.say(text)
    engine.runAndWait()

# ─────────────────────────────────────────────
#  CHAT HISTORY  (last 10 exchanges)
# ─────────────────────────────────────────────
chat_history = []

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
#  REMINDERS
# ─────────────────────────────────────────────
reminders = []

def add_reminder(message: str, minutes: int):
    fire_at = datetime.datetime.now() + datetime.timedelta(minutes=minutes)
    reminders.append({"time": fire_at, "message": message, "fired": False})
    speak(f"Sure, I'll remind you to {message} in {minutes} minute{'s' if minutes != 1 else ''}.")

def check_reminders():
    while True:
        now = datetime.datetime.now()
        for r in reminders:
            if not r["fired"] and now >= r["time"]:
                speak(f"Hey boss, reminder — {r['message']}")
                r["fired"] = True
        time.sleep(15)

threading.Thread(target=check_reminders, daemon=True).start()

def parse_reminder_command(command: str):
    try:
        words = command.split()
        minutes = None
        for w in words:
            if w.isdigit():
                minutes = int(w)
                break
        if minutes is None:
            speak("How many minutes should I set the reminder for?")
            return

        if "remind me to" in command:
            msg_raw = command.split("remind me to")[1]
        elif "set reminder" in command:
            msg_raw = command.split("set reminder")[1]
        else:
            msg_raw = command

        for kw in [f"in {minutes} minutes", f"in {minutes} minute"]:
            msg_raw = msg_raw.replace(kw, "").strip()

        message = msg_raw.strip() or "that thing you wanted"
        add_reminder(message, minutes)
    except Exception as e:
        speak("Couldn't quite parse that. Try saying — remind me to drink water in 10 minutes.")
        print(f"[reminder error] {e}")

def list_reminders():
    pending = [r for r in reminders if not r["fired"]]
    if not pending:
        speak("Nothing on the reminder list right now.")
        return
    speak(f"You've got {len(pending)} pending reminder{'s' if len(pending) > 1 else ''}.")
    print("\n--- Pending Reminders ---")
    for r in pending:
        t = r["time"].strftime("%I:%M %p")
        print(f"  - {r['message']} at {t}")
        speak(f"{r['message']} at {t}")
    print("-------------------------\n")

# ─────────────────────────────────────────────
#  SYSTEM INFO
# ─────────────────────────────────────────────
def get_system_info():
    cpu     = psutil.cpu_percent(interval=1)
    ram     = psutil.virtual_memory()
    disk    = psutil.disk_usage("/")
    battery = psutil.sensors_battery()

    ram_used   = round(ram.used  / (1024**3), 1)
    ram_total  = round(ram.total / (1024**3), 1)
    disk_used  = round(disk.used  / (1024**3), 1)
    disk_total = round(disk.total / (1024**3), 1)

    print("\n--- System Status ---")
    print(f"  CPU   : {cpu}%")
    print(f"  RAM   : {ram_used} / {ram_total} GB  ({ram.percent}%)")
    print(f"  Disk  : {disk_used} / {disk_total} GB")

    info = f"CPU is at {cpu}%. RAM usage is {ram.percent}%, that's {ram_used} out of {ram_total} gigs."

    if battery:
        charge  = round(battery.percent)
        plugged = "plugged in" if battery.power_plugged else "running on battery"
        print(f"  Batt  : {charge}% ({'charging' if battery.power_plugged else 'discharging'})")
        info += f" Battery is at {charge}%, {plugged}."
    else:
        print("  Batt  : not available")

    print("---------------------\n")
    speak(info)

# ─────────────────────────────────────────────
#  CALCULATOR / UNIT CONVERTER
# ─────────────────────────────────────────────
def safe_calculate(expression: str):
    allowed = set("0123456789+-*/(). ")
    if not all(c in allowed for c in expression):
        return None
    try:
        return str(eval(expression))
    except Exception:
        return None

UNIT_CONVERSIONS = {
    "km to miles":           lambda v: v * 0.621371,
    "miles to km":           lambda v: v * 1.60934,
    "meters to feet":        lambda v: v * 3.28084,
    "feet to meters":        lambda v: v / 3.28084,
    "cm to inches":          lambda v: v / 2.54,
    "inches to cm":          lambda v: v * 2.54,
    "kg to pounds":          lambda v: v * 2.20462,
    "pounds to kg":          lambda v: v / 2.20462,
    "grams to ounces":       lambda v: v * 0.035274,
    "ounces to grams":       lambda v: v / 0.035274,
    "celsius to fahrenheit": lambda v: (v * 9/5) + 32,
    "fahrenheit to celsius": lambda v: (v - 32) * 5/9,
    "mb to gb":              lambda v: v / 1024,
    "gb to mb":              lambda v: v * 1024,
    "gb to tb":              lambda v: v / 1024,
    "tb to gb":              lambda v: v * 1024,
}

def handle_calculator(command: str):
    command = command.lower()

    if "convert" in command:
        for key, fn in UNIT_CONVERSIONS.items():
            if key in command:
                parts = command.replace("convert", "").strip().split()
                try:
                    value  = float(parts[0])
                    result = round(fn(value), 4)
                    from_unit, to_unit = key.split(" to ")
                    speak(f"{value} {from_unit} comes out to {result} {to_unit}.")
                    print(f"  {value} {key} = {result}")
                    return
                except (ValueError, IndexError):
                    speak("Say it like — convert 100 km to miles.")
                    return
        speak("I don't have that conversion yet. I'll add it soon.")
        return

    expr = (command
            .replace("calculate", "").replace("what is", "").replace("?", "")
            .replace("plus", "+").replace("minus", "-")
            .replace("multiplied by", "*").replace("times", "*")
            .replace("divided by", "/")
            .strip())
    result = safe_calculate(expr)
    if result:
        speak(f"That's {result}.")
        print(f"  {expr} = {result}")
    else:
        speak("Couldn't work that one out. Try a simpler expression.")

# ─────────────────────────────────────────────
#  LISTEN
# ─────────────────────────────────────────────
def listen(retries: int = 2) -> str:
    r = sr.Recognizer()
    r.energy_threshold        = 300
    r.dynamic_energy_threshold = True
    r.pause_threshold          = 0.8

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
            print(f"[speech api error] {e}")
            return ""
        except OSError as e:
            speak("Can't find your microphone. Plug it in and try again.")
            print(f"[mic error] {e}")
            return ""

    speak("Nothing came through. Try again.")
    return ""

# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────
def fun():
    speak(pyjokes.get_joke())

def take_screenshot():
    pyautogui.screenshot().save("screenshot.png")
    speak("Done, screenshot saved.")

def cal_day() -> str:
    days = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    return days[datetime.datetime.today().weekday()]

def wishme():
    hour = int(datetime.datetime.now().hour)
    t    = time.strftime("%I:%M %p")
    day  = cal_day()
    if hour < 12:
        speak(f"Good morning boss. {day}, {t}. Let's get it.")
    elif hour < 17:
        speak(f"Hey boss. {day} afternoon, {t}. What are we doing?")
    else:
        speak(f"Evening boss. {day}, {t}. Still grinding?")

def show_time():
    t = datetime.datetime.now().strftime("%I:%M %p")
    speak(f"It's {t}.")

def search_wikipedia(query: str):
    try:
        result = wikipedia.summary(query, sentences=2)
        speak(result)
    except wikipedia.exceptions.DisambiguationError:
        speak("That one's a bit ambiguous. Can you be more specific?")
    except wikipedia.exceptions.PageError:
        speak("Couldn't find a Wikipedia page for that.")
    except Exception as e:
        speak("Wikipedia's not cooperating right now.")
        print(f"[wikipedia error] {e}")

def schedule():
    day = cal_day().lower()
    plans = {
        "monday":    "Work till 5, then a workout. After 8, build something or learn something.",
        "tuesday":   "Work till 5, then a workout. Evenings are for sharpening a skill.",
        "wednesday": "Work till 5, then a workout. Read a book or study something useful tonight.",
        "thursday":  "Work till 5, then a workout. Review your project progress tonight.",
        "friday":    "Work till 5, then chill. Light learning or a hobby in the evening.",
        "saturday":  "Free day. 3 hours minimum on something you care about. Workout at 7.",
        "sunday":    "Rest day. Reflect, plan the week ahead, eat well.",
    }
    speak(plans.get(day, "Nothing planned for today. Go make something happen."))

def open_website(command: str) -> bool:
    websites = {
        "anime":         "https://hianime.to/",
        "discord":       "https://discord.com/",
        "type test":     "https://www.typingtest.com/",
        "jiocinema":     "https://www.jiocinema.com/",
        "snapchat":      "https://web.snapchat.com/",
        "w3":            "https://www.w3schools.com/",
        "fiverr":        "https://www.fiverr.com/",
        "aifinder":      "https://theresanaiforthat.com/",
        "mxplayer":      "https://www.mxplayer.in/",
        "netflix":       "https://www.netflix.com/in/",
        "c compiler":    "https://www.programiz.com/c-programming/online-compiler/",
        "paper trading": "https://in.tradingview.com/",
        "github":        "https://github.com/",
        "stackoverflow": "https://stackoverflow.com/",
        "leetcode":      "https://leetcode.com/",
    }
    for name, url in websites.items():
        if f"open {name}" in command:
            try:
                webbrowser.open(url)
                speak(f"Opening {name}.")
            except Exception as e:
                speak(f"Couldn't open {name}.")
                print(f"[website error] {e}")
            return True
    return False

def open_apps(command: str) -> bool:
    apps = {
        "instagram":      "C:/Users/dilno/OneDrive/Desktop/Instagram.lnk",
        "brave":          "C:/Users/dilno/OneDrive/Desktop/Brave.lnk",
        "spotify":        "C:/Users/dilno/OneDrive/Desktop/Spotify.lnk",
        "whatsapp":       "C:/Users/dilno/OneDrive/Desktop/WhatsApp.lnk",
        "youtube":        "C:/Users/dilno/OneDrive/Desktop/YouTube.lnk",
        "vs code":        "C:/Users/dilno/OneDrive/Desktop/Visual Studio Code.lnk",
        "store":          "C:/Users/dilno/OneDrive/Desktop/Microsoft Store.lnk",
        "chrome":         "C:/Users/Public/Desktop/Google Chrome.lnk",
        "microsoft edge": "C:/Users/Public/Desktop/Microsoft Edge.lnk",
        "copilot":        "C:/Users/dilno/OneDrive/Desktop/Copilot.lnk",
        "chatgpt":        "C:/Users/dilno/OneDrive/Desktop/ChatGPT.lnk",
        "github desktop": "C:/Users/dilno/OneDrive/Desktop/GitHub.lnk",
        "camera":         "C:/Users/dilno/OneDrive/Desktop/Camera.lnk",
        "linkedin":       "C:/Users/dilno/OneDrive/Desktop/LinkedIn.lnk",
    }
    for name, path in apps.items():
        if f"open {name}" in command:
            try:
                os.startfile(path)
                speak(f"Opening {name}.")
            except Exception as e:
                speak(f"Couldn't open {name}. Double check the shortcut path.")
                print(f"[app error] {e}")
            return True
    return False

def get_weather(city: str = "Delhi"):
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric"
    try:
        data = requests.get(url, timeout=5).json()
        if data.get("cod") != 200:
            speak("Couldn't pull the weather. Check the API key.")
            return
        desc = data["weather"][0]["description"]
        temp = data["main"]["temp"]
        hum  = data["main"]["humidity"]
        wind = data["wind"]["speed"]
        speak(f"{city} right now — {desc}, {temp} degrees, humidity {hum}%, wind at {wind} metres per second.")
    except requests.exceptions.Timeout:
        speak("Weather request timed out. Internet acting up?")
    except Exception as e:
        speak("Couldn't get the weather.")
        print(f"[weather error] {e}")

def play_song():
    speak("What do you want to play?")
    song = listen()
    if song:
        kit.playonyt(song)
        speak(f"Playing {song}.")
    else:
        speak("Didn't catch the song name.")

def get_news():
    url = f"https://newsapi.org/v2/top-headlines?country=in&apiKey={NEWS_API_KEY}"
    try:
        data  = requests.get(url, timeout=5).json()
        items = data.get("articles", [])[:5]
        if not items:
            speak("Nothing in the news right now.")
            return
        speak("Here's what's happening today.")
        for i, a in enumerate(items, 1):
            print(f"  {i}. {a['title']}")
            speak(a["title"])
    except Exception as e:
        speak("Couldn't fetch the news.")
        print(f"[news error] {e}")

def chat_with_gemini(prompt: str) -> str:
    headers = {"Content-Type": "application/json"}
    data    = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        resp = requests.post(GEMINI_URL, headers=headers, json=data, timeout=10)
        if resp.status_code == 200:
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        return f"Gemini threw a {resp.status_code}."
    except requests.exceptions.Timeout:
        return "Gemini took too long. Try again."
    except Exception as e:
        return f"Something went wrong with Gemini: {e}"

# ─────────────────────────────────────────────
#  MAIN LOOP
# ─────────────────────────────────────────────
def command_prompt():
    wishme()
    speak("Orion online.")

    while True:
        command = listen()
        if not command:
            continue

        add_to_history("user", command)

        if "open " in command:
            if not open_website(command):
                if not open_apps(command):
                    speak("Can't find that one. Want me to search it?")

        elif any(kw in command for kw in ["set reminder", "remind me"]):
            parse_reminder_command(command)

        elif "list reminder" in command or "show reminder" in command:
            list_reminders()

        elif any(kw in command for kw in ["system info", "cpu", "ram", "battery", "disk"]):
            get_system_info()

        elif any(kw in command for kw in ["calculate", "what is", "convert"]):
            handle_calculator(command)

        elif any(kw in command for kw in ["chat history", "show history", "last commands"]):
            show_history()

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
            if query:
                search_wikipedia(query)
            else:
                speak("What should I look up?")

        elif any(kw in command for kw in ["exit", "stop", "shutdown", "bye"]):
            speak("Shutting down. Later boss.")
            break

        else:
            response = chat_with_gemini(command)
            add_to_history("orion", response)
            speak(response)


if __name__ == "__main__":
    command_prompt()
