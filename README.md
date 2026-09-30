# 🎮 Pokémon Auction

A complete, production-ready **multiplayer Pokémon auction game** built with
Flask, Flask-SocketIO, SQLAlchemy and vanilla JavaScript.

Create a private room, invite friends, bid on random Pokémon with virtual coins,
build a team of four, and let the deterministic battle engine crown a winner.

![Home screen](docs/screenshot-home.png)
![Auction screen](docs/screenshot-auction.png)
![Results screen](docs/screenshot-results.png)

> _Screenshot placeholders — add your own under `docs/`._

---

## ✨ Features

| Area | What you get |
|---|---|
| **Rooms** | Private rooms with secure codes (`POKE-7X92`), host controls, kicking, host auto-transfer, reconnect support |
| **Economy** | Server-authoritative wallets, validated bids, no negative/fractional bids, rate limiting |
| **Auctions** | Live timer, configurable duration, anti-snipe extension, bid history, quick-bid buttons |
| **PokéAPI** | Full local cache (1025 base-form Pokémon), zero API calls during gameplay |
| **Team building** | Configurable team size, duplicate blocking, legendary/mythical toggles |
| **Battles** | Deterministic simplified simulator: STAB, type effectiveness, speed order, HP tiebreaks |
| **Scoring** | Round-robin tournament, points table, full per-duel battle logs |
| **UI** | Dark Pokémon-inspired theme, responsive from mobile to desktop, live chat |
| **Persistence** | Full SQLAlchemy models so games can be reconstructed after a restart |

---

## 📦 Installation

```bash
git clone <your-repo-url>
cd pokemon-auction

python -m venv venv

# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

---

## ⚙️ Environment variables

Copy the example file and edit it:

```bash
cp .env.example .env
```

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | dev value | **Change in production.** Signs Flask sessions |
| `DATABASE_URL` | SQLite file | `postgresql://user:pass@host/db` for production |
| `AUTO_CREATE_DB` | `true` | Create tables automatically on boot |
| `STARTING_COINS` | `1000` | Default starting balance |
| `TEAM_SIZE` | `4` | Pokémon per player |
| `MAX_PLAYERS` | `8` | Room capacity |
| `AUCTION_DURATION` | `20` | Seconds per auction |
| `MIN_BID_INCREMENT` | `10` | Minimum raise |
| `ANTI_SNIPE_ENABLED` | `true` | Reset timer on late bids |
| `ANTI_SNIPE_SECONDS` | `5` | Anti-snipe window |
| `ALLOW_DUPLICATES` | `false` | Allow the same Pokémon twice |
| `ALLOW_LEGENDARIES` | `true` | Include legendary Pokémon |
| `ALLOW_MYTHICALS` | `true` | Include mythical Pokémon |
| `SHOW_PLAYER_BALANCES` | `true` | Show other players' coins |
| `POKEMON_LIMIT` | `1025` | Highest national dex id to cache |

> The host can override most of these **per room** in the create-room form.

---

## 🗄️ Database initialisation

```bash
flask --app app init-db
```

(or simply start the app — `AUTO_CREATE_DB=true` creates tables on first boot)

---

## 🐾 Pokémon database initialisation

The game **never** calls PokéAPI during gameplay. Populate the local cache once:

```bash
# All base-form Pokémon (Gen 1–9) — takes a few minutes
python init_pokemon.py

# Just Gen 1, much faster
python init_pokemon.py --limit 151

# Re-fetch everything
python init_pokemon.py --force
```

Progress is printed as it goes, and the script is **resumable** — if it is
interrupted, run it again and it picks up where it left off.

---

## ▶️ Running locally

```bash
python app.py
```

Then open <http://127.0.0.1:5000>.

Open a second browser (or incognito window), create/join the same room code, and
start the game.

---

## 🧪 Running tests

```bash
pytest
```

The suite covers rooms, hosting, bidding, anti-snipe, wallets, the type chart,
battle determinism, team synergy and the tournament ranking.

---

## 🚀 Deployment

### Render

1. Push the repo to GitHub.
2. **New → Web Service**, connect the repo.
3. Build command:
   ```
   pip install -r requirements.txt
   ```
4. Start command (already in `Procfile`):
   ```
   gunicorn -w 1 --threads 100 -b 0.0.0.0:$PORT app:app
   ```
5. Add a **PostgreSQL** instance and set `DATABASE_URL` to its *Internal
   Database URL*.
6. Add `SECRET_KEY` as an environment variable.
7. After the first deploy, open a shell and run:
   ```
   python init_pokemon.py --limit 151
   ```

> **Important:** use **one** gunicorn worker. Socket.IO rooms and the in-memory
> game state are per-process.

### Railway

1. `railway init` in the project folder (or connect via the dashboard).
2. Add a PostgreSQL plugin — Railway injects `DATABASE_URL` automatically.
3. Set `SECRET_KEY`.
4. Railway detects the `Procfile`. Deploy.
5. Run `python init_pokemon.py --limit 151` from the Railway shell.

### PythonAnywhere

1. Upload the project (or `git clone`).
2. Create a virtualenv and `pip install -r requirements.txt`.
3. Create a **Manual configuration** web app (Python 3.10+) and point the WSGI
   file at `wsgi.py`:
   ```python
   import sys
   sys.path.insert(0, "/home/<user>/pokemon-auction")
   from wsgi import app as application
   ```
   > PythonAnywhere's standard WSGI workers do **not** support WebSockets.
   > Install `flask-socketio` with the `polling` fallback (already enabled —
   > the client tries `websocket` then falls back to `polling`), or move to a
   > host that supports WebSockets for the best experience.
4. Open a Bash console and run `python init_pokemon.py --limit 151`.

### Scaling beyond one process

For multiple workers you need a Socket.IO message queue:

```bash
pip install redis
export REDIS_URL=redis://...
```

Then in `app/__init__.py`:

```python
socketio.init_app(app, message_queue=os.environ["REDIS_URL"], ...)
```

…and move the game runtime into Redis (or pin each room to one worker with a
sticky-session load balancer).

---

## 🔧 Troubleshooting

| Problem | Fix |
|---|---|
| `Pokémon database is empty` | Run `python init_pokemon.py --limit 151` |
| `Could not allocate a room code` | Extremely unlikely; restart the app |
| Players can't see each other's bids | Make sure only **one** worker is running |
| `psycopg2` build errors | `pip install psycopg2-binary` |
| PokéAPI rate limits during init | Lower `POKEMON_FETCH_WORKERS` (e.g. `4`) |
| WebSocket connection fails | The client automatically falls back to long-polling |
| Room disappeared after restart | Rooms idle longer than `ROOM_IDLE_TIMEOUT` are purged |

---

## 📁 Project structure

```
pokemon-auction/
├── app.py                 # Dev entry point
├── wsgi.py                # Production entry point
├── config.py              # All configuration & game constants
├── init_pokemon.py        # PokéAPI cache populator
├── requirements.txt
├── Procfile
├── pytest.ini
├── .env.example
├── .gitignore
├── README.md
├── app/
│   ├── __init__.py        # App factory, db, socketio, error handlers
│   ├── models.py          # SQLAlchemy models
│   ├── routes.py          # HTTP routes + JSON API
│   ├── sockets.py         # Socket.IO event handlers
│   ├── game_engine.py     # Authoritative runtime & state machine
│   ├── auction.py         # Bid validation, starting prices
│   ├── battle.py          # Deterministic battle & tournament engine
│   ├── pokemon_api.py     # PokéAPI client + local cache
│   ├── type_chart.py      # 18×18 type effectiveness chart
│   └── utils.py           # Sanitisation, room codes, helpers
├── templates/             # Jinja2 templates
├── static/css/style.css
├── static/js/{common,lobby,auction,results}.js
└── tests/
```

---

## 🧠 How the game works

1. **Create / Join** — the host picks a name and settings; a secure code is
   generated. Friends join with the code until the game starts.
2. **Lobby** — Socket.IO keeps everyone's presence in sync. The host can kick
   players and tweak settings. If the host drops, the longest-connected player
   becomes host after a 20-second grace period.
3. **Auction** — the server picks a random eligible Pokémon, computes a starting
   bid from its BST + rarity, and starts a timer. Every bid is validated
   server-side (balance, increment, team size, timer, rate limit). A bid in the
   last 5 seconds resets the timer to 5 seconds (anti-snipe).
4. **Win** — the highest bidder's coins are deducted and the Pokémon joins their
   team. Players who reach the team size can no longer bid but keep watching.
5. **Battle** — when everyone is full (or the auction stalls), the engine runs
   every pair of teams. Each team battle is four 1-v-1 duels using a simplified
   damage formula with STAB, type effectiveness and speed order. Team winners
   are decided by matchup wins, then remaining HP, then synergy, then total BST.
6. **Leaderboard** — a round-robin awards one point per team battle won. The
   final ranking is derived entirely from the simulated results.

---

## 📜 License

MIT — this is an original educational project inspired by Pokémon. Pokémon and
Pokémon character names are trademarks of Nintendo / Game Freak / Creatures Inc.
Pokémon data is fetched from the public [PokéAPI](https://pokeapi.co/).