# Orion v1 — AI Voice Assistant

> The successor to [Friday](https://github.com/dilnoor19/friday).  
> Smarter, more reliable, and built to actually feel like a personal assistant — not a demo project.

---

## Background

Friday was the starting point — a voice assistant built from scratch to handle daily tasks through voice commands. It worked, but it had rough edges: mic crashes, no error handling, and a very robotic feel.

Orion v1 is the rewrite. Same idea, done properly.

---

## What's Different from Friday

| Thing | Friday | Orion v1 |
|---|---|---|
| Mic handling | Crashed on noise / timeout | Retry logic, dynamic threshold, graceful errors |
| Error handling | Bare except, silent failures | Per-function handling with useful messages |
| Personality | Stiff, robotic responses | Casual, natural, sounds like a real assistant |
| Reminders | Not available | Background thread, natural language parsing |
| System info | Not available | CPU, RAM, disk, battery in one command |
| Calculator | Not available | Math eval + 15+ unit conversions |
| Chat history | Not available | Last 10 exchanges stored in memory |
| Terminal output | Emoji-heavy, cluttered | Clean, readable, no fluff |

---

## Features

**Voice & AI**
- Natural speech recognition with retry logic and noise adaptation
- Google Gemini as the AI brain for open-ended conversations
- Conversation history — remembers the last 10 exchanges

**Productivity**
- Reminders with natural language — "remind me to call mom in 20 minutes"
- Daily schedule by day of the week
- Calculator — "calculate 150 divided by 6"
- Unit converter — km to miles, celsius to fahrenheit, kg to pounds, and more

**System**
- Live system stats — CPU, RAM, disk, battery
- Volume control by voice
- Screenshot on command

**Info & Media**
- Live weather via OpenWeatherMap
- Top 5 Indian news headlines via NewsAPI
- Play any song on YouTube by voice
- Wikipedia search

**Apps & Websites**
- Open desktop apps and websites by voice
- Easily extendable — just add to the dictionaries in `open_apps()` or `open_website()`

---

## Installation

**1. Clone the repo**
```bash
git clone https://github.com/dilnoor19/orion-v1.git
cd orion-v1
```

**2. Install dependencies**
```bash
pip install pyttsx3 SpeechRecognition pyautogui pyjokes wikipedia pywhatkit requests psutil pyaudio
```

If `pyaudio` fails on Windows:
```bash
pip install pipwin
pipwin install pyaudio
```

**3. Add your API keys**

Open `main.py` and fill these in at the top:
```python
GEMINI_API_KEY  = "your_gemini_api_key"
GEMINI_URL      = "your_gemini_endpoint_url"
WEATHER_API_KEY = "your_openweathermap_api_key"
NEWS_API_KEY    = "your_newsapi_key"
```

**4. Update app paths**

In `open_apps()`, update the `.lnk` paths to match shortcuts on your machine.

**5. Run**
```bash
python main.py
```

---

## Example Commands

```
open netflix
open vs code
weather
remind me to drink water in 15 minutes
list reminders
system info
calculate 25 times 8
convert 100 km to miles
play song Tum Se Hi
news
wikipedia artificial intelligence
show history
take screenshot
time
schedule
mute
bye
```

---

## Project Structure

```
orion-v1/
├── main.py        # Core assistant
├── screenshot.png # Created when you say "take screenshot"
└── README.md
```

---

## Orion v2 — What's Next

Orion v1 is a single-file voice assistant. v2 will be a proper application.

Planned for v2:
- GUI dashboard — live status panel, command history, reminders UI
- Modular architecture — each feature in its own file
- Persistent memory — preferences and history saved across sessions
- Wake word — always-on listening, activates on "Hey Orion"
- Offline mode — local LLM fallback when there's no internet

> v1 is the engine. v2 is the car.

---

## Author

**Dilnoor** — BCA Student, Python Developer  
GitHub: [github.com/dilnoor19](https://github.com/dilnoor19)

---

## License

MIT
