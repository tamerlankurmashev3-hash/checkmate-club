# Checkmate Club

A chess site built with Python, Flask, and Flask-SocketIO.

## Run locally

1. Install Python 3.10 or newer.
2. Run `python3 -m pip install -r requirements.txt`.
3. Run `python3 app.py`.
4. Open <http://127.0.0.1:5003>.

## Game modes

- Play against the computer at easy, medium, or hard settings.
- Play pass-and-play with another person on the same device.
- Play online with a friend using a room invite link or six-character code. Online moves are validated by the Python server.
- Solve checkmate puzzles and choose from several clock options in local games.

Online games are untimed and need both players connected at once. Room state is kept in memory, so an idle free hosting service can sleep and clear waiting rooms.

## Deploy on Render

The included `render.yaml` configures a free Render web service. To publish it, push this project to a GitHub repository, then create a Blueprint in Render and connect that repository. Render will build from `requirements.txt` and create a public HTTPS link you can send to friends. The free service sleeps after 15 minutes without activity and may take about a minute to wake up. Free hosting is intended for hobby projects and has service limits.
