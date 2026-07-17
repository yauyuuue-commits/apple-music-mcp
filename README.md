# Apple Music MCP

An [MCP (Model Context Protocol)](https://modelcontextprotocol.io) server that lets AI agents control **Apple Music** on macOS — play/pause/skip, read lyrics, manage playlists, and search for songs.

## Features

- 🎵 **Now Playing** — get current track info (title, artist, album, progress)
- 📝 **Synced Lyrics** — fetches time-synced lyrics from LRCLIB and NetEase Cloud Music
- ⏯️ **Playback Control** — play, pause, toggle, next, previous, stop
- 📋 **Playlist Management** — create playlists, add tracks, list all playlists
- 🔍 **Search** — search your library + Apple Music catalog with a single query
- ➕ **Search & Add** — find a song and add it to a playlist in one call

## Requirements

- **macOS** (uses `osascript` / AppleScript under the hood)
- **Python 3.10+**
- **Apple Music.app** with an active library (some features require tracks to be in your library)
- **curl** (bundled with macOS; used for API calls)

## Installation

```bash
git clone https://github.com/yauyuuue-commits/apple-music-mcp.git
cd apple-music-mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Usage

Add the server to your MCP client configuration:

### Claude Desktop

In `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "apple-music": {
      "command": "/path/to/apple-music-mcp/.venv/bin/python",
      "args": ["-m", "apple_music_mcp"]
    }
  }
}
```

### Claude Code (CLI)

```bash
claude mcp add apple-music -- .venv/bin/python -m apple_music_mcp
```

## Available Tools

| Tool | Description |
|------|-------------|
| `get_current_track` | Get info about the currently playing track |
| `get_lyrics` | Get synced lyrics for the current track (LRCLIB → NetEase fallback) |
| `control_playback` | Control playback: play / pause / toggle / next / previous / stop |
| `create_playlist` | Create a new playlist |
| `add_to_playlist` | Add the current track to a playlist (works with subscription tracks) |
| `list_playlists` | List all user playlists |
| `search_tracks` | Search library + Apple Music catalog (up to 5 results) |
| `search_and_add` | Search for a track and add the first match to a playlist |

## Lyrics Sources

The `get_lyrics` tool uses a two-tier fallback:

1. **LRCLIB** — free community lyrics database, covers most English songs
2. **NetEase Cloud Music** — covers Chinese / Asian songs not on LRCLIB

No API keys required for either source.

## Project Structure

```
apple-music-mcp/
├── README.md
├── LICENSE
├── pyproject.toml
└── src/
    └── apple_music_mcp/
        ├── __init__.py
        ├── __main__.py
        └── server.py
```

## License

MIT — see [LICENSE](LICENSE).
