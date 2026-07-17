import re, subprocess, json, sys, time
from urllib.parse import quote
from urllib.request import Request, urlopen
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Apple Music")

# Per-process cache for get_lyrics
_lyrics_cache: dict[tuple[str, str], list[dict]] = {}


def run_applescript(script: str) -> str:
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()


def http_get(url: str, headers: dict = None, timeout: int = 10) -> str | None:
    """HTTP GET with custom headers; returns body or None on any error."""
    try:
        req = Request(url, headers=headers or {})
        with urlopen(req, timeout=timeout) as resp:
            return resp.read().decode()
    except Exception:
        return None

@mcp.tool()
def get_current_track() -> dict:
    """Get info about the currently playing track in Apple Music.

    Returns title, artist, album, duration, position, and player state.
    """
    script = """
tell application "Music"
    if player state is stopped then
        return "STOPPED"
    end if
    set t to name of current track
    set a to artist of current track
    set al to album of current track
    set d to duration of current track
    set p to player position
    set s to player state
    return t & "|||" & a & "|||" & al & "|||" & (d as string) & "|||" & (p as string) & "|||" & (s as string)
end tell
"""
    try:
        output = run_applescript(script)
    except RuntimeError as e:
        return {"error": str(e)}
    if output == "STOPPED":
        return {"state": "stopped"}
    parts = output.split("|||")
    if len(parts) < 6:
        return {"error": "Could not parse track info"}
    duration = float(parts[3])
    position = float(parts[4])
    progress = round((position / duration) * 100, 1) if duration > 0 else 0
    return {
        "state": "playing",
        "title": parts[0],
        "artist": parts[1],
        "album": parts[2],
        "duration_seconds": duration,
        "position_seconds": position,
        "progress_percent": progress
    }

def _window_lrc(lines: list[dict], pos: float) -> list[dict] | None:
    """Slice 8-line window around playback position."""
    if not lines:
        return None
    idx = 0
    for i, l in enumerate(lines):
        if l["time"] <= pos:
            idx = i
    start = max(0, idx - 2)
    end = min(len(lines), start + 8)
    window = lines[start:end]
    for cl in window:
        cl["current"] = abs(cl["time"] - lines[idx]["time"]) < 0.1
    return window


@mcp.tool()
def get_lyrics() -> dict:
    """Get the lyrics of the currently playing track in Apple Music."""
    info_script = """
tell application "Music"
    if player state is stopped then
        return "STOPPED"
    end if
    set t to name of current track
    set a to artist of current track
    set p to player position
    set d to duration of current track
    return t & "|||" & a & "|||" & (p as string) & "|||" & (d as string)
end tell
"""
    try:
        output = run_applescript(info_script)
    except RuntimeError as e:
        return {"error": str(e)}
    if output == "STOPPED":
        return {"error": "Apple Music is not playing"}
    parts = output.split("|||")
    if len(parts) < 4:
        return {"error": "Could not parse track info"}
    title, artist = parts[0].strip(), parts[1].strip()
    pos = float(parts[2].strip())

    def parse_lrc(lrc_text: str) -> list:
        """Parse LRC text into list of {time, text} dicts."""
        lines = []
        for line in lrc_text.strip().split("\n"):
            m = re.match(r"\[(\d+):(\d+\.\d+)\]\s*(.*)", line)
            if m:
                t_sec = int(m.group(1)) * 60 + float(m.group(2))
                text = m.group(3).strip()
                if text:
                    lines.append({"time": t_sec, "text": text})
        return lines

    cache_key = (title, artist)

    # Check cache
    if cache_key in _lyrics_cache:
        synced_lines, translated_lines = _lyrics_cache[cache_key]
        return {
            "title": title,
            "artist": artist,
            "position_seconds": pos,
            "synced_lyrics": _window_lrc(synced_lines, pos),
            "total_lines": len(synced_lines),
            "translated_lyrics": _window_lrc(translated_lines, pos) if translated_lines else None,
            "cached": True,
        }

    synced_lines = []
    translated_lines = []

    # 1. Try LRCLIB (good for English songs)
    try:
        url = f"https://lrclib.net/api/get?track_name={quote(title)}&artist_name={quote(artist)}"
        body = http_get(url, headers={"User-Agent": "apple-music-mcp/1.0"}, timeout=15)
        if body:
            data = json.loads(body)
            lrc = data.get("syncedLyrics") or ""
            if lrc:
                synced_lines = parse_lrc(lrc)
    except Exception as e:
        print(f'LRCLIB ERROR: {type(e).__name__}: {e}', file=sys.stderr)

    # 2. Fallback: NetEase Cloud Music (good for Chinese songs)
    if not synced_lines:
        try:
            qs = f"s={quote(f'{title} {artist}')}&type=1&limit=1"
            search_body = http_get(
                f"https://music.163.com/api/search/get?{qs}",
                headers={"Referer": "https://music.163.com", "User-Agent": "Mozilla/5.0"},
                timeout=10,
            )
            if search_body:
                search_data = json.loads(search_body)
                songs = search_data.get("result", {}).get("songs", [])
                if songs:
                    song_id = songs[0]["id"]
                    lyric_body = http_get(
                        f"https://music.163.com/api/song/lyric?id={song_id}&lv=1&kv=1&tv=-1",
                        headers={"Referer": "https://music.163.com", "User-Agent": "Mozilla/5.0"},
                        timeout=10,
                    )
                    if lyric_body:
                        lyric_data = json.loads(lyric_body)
                        lrc = lyric_data.get("lrc", {}).get("lyric") or ""
                        if lrc:
                            synced_lines = parse_lrc(lrc)
                        tlyric_text = lyric_data.get("tlyric", {}).get("lyric") or ""
                        if tlyric_text:
                            translated_lines = parse_lrc(tlyric_text)
        except Exception as e:
            print(f'NETEASE ERROR: {type(e).__name__}: {e}', file=sys.stderr)

    # Cache the result
    _lyrics_cache[cache_key] = (synced_lines, translated_lines)

    return {
        "title": title,
        "artist": artist,
        "position_seconds": pos,
        "synced_lyrics": _window_lrc(synced_lines, pos),
        "total_lines": len(synced_lines),
        "translated_lyrics": _window_lrc(translated_lines, pos) if translated_lines else None,
    }

@mcp.tool()
def control_playback(action: str) -> dict:
    """Control Apple Music playback.

    Args:
        action: One of "play", "pause", "toggle", "next", "previous", "stop"
    """
    valid = {"play", "pause", "toggle", "next", "previous", "stop"}
    if action not in valid:
        return {"error": f"Invalid action. Use one of: {', '.join(sorted(valid))}"}
    cmd_map = {
        "toggle": "playpause",
        "next": "next track",
        "previous": "previous track",
        "play": "play",
        "pause": "pause",
        "stop": "stop"
    }
    script = f'tell application "Music" to {cmd_map[action]}'
    try:
        run_applescript(script)
        return {"status": "ok", "action": action}
    except RuntimeError as e:
        return {"error": str(e)}



@mcp.tool()
def create_playlist(name: str) -> dict:
    """Create a new playlist in Apple Music.

    Args:
        name: The name of the new playlist
    """
    escaped_name = name.replace('"', '\\"')
    check_script = f'tell application "Music" to (exists user playlist "{escaped_name}")'
    try:
        output = run_applescript(check_script)
        if output == "true":
            return {"status": "exists", "playlist": name}
    except RuntimeError:
        pass

    script = f'tell application "Music" to make new playlist with properties {{name:"{escaped_name}"}}'
    try:
        run_applescript(script)
        return {"status": "ok", "playlist": name}
    except RuntimeError as e:
        return {"error": str(e)}

@mcp.tool()
def add_to_playlist(playlist_name: str) -> dict:
    """Add the currently playing track to a playlist.

    Works with both library tracks and Apple Music subscription tracks.
    For subscription tracks, copies to the library first, then to the playlist.

    Args:
        playlist_name: The name of the playlist to add the current track to
    """
    escaped_pl = playlist_name.replace('"', '\\"')
    script = f"""
tell application "Music"
    if player state is stopped then
        return "STOPPED"
    end if
    set tName to name of current track
    set tArtist to artist of current track
    set p to first playlist whose name is "{escaped_pl}"

    -- Add to library first (needed for subscription tracks)
    try
        duplicate current track to source "Library"
    end try

    -- Poll for the track to appear in library (up to 8 seconds)
    set foundTracks to {{}}
    repeat 16 times
        delay 0.5
        set foundTracks to (every track of library playlist 1 whose artist is tArtist and name is tName)
        if (count of foundTracks) > 0 then exit repeat
    end repeat

    -- Copy first match to playlist
    if (count of foundTracks) > 0 then
        duplicate (item 1 of foundTracks) to p
    end if

    if (count of foundTracks) = 0 then
        return "NOTFOUND|||" & tName & "|||" & tArtist
    end if
    return "OK|||" & tName & "|||" & tArtist
end tell
"""
    try:
        output = run_applescript(script)
    except RuntimeError as e:
        return {"error": str(e)}
    if output == "STOPPED":
        return {"error": "No track playing"}
    parts = output.split("|||")
    status = parts[0].strip()
    if status == "NOTFOUND":
        return {"error": f"Could not find '{parts[1].strip()}' by {parts[2].strip()} in library after adding", "playlist": playlist_name}
    return {"status": "ok", "added": parts[1].strip() if len(parts) > 1 else "", "artist": parts[2].strip() if len(parts) > 2 else "", "playlist": playlist_name}

@mcp.tool()
def list_playlists() -> dict:
    """List all user playlists in Apple Music."""
    script = """
tell application "Music"
    set output to ""
    repeat with p in (every user playlist)
        set output to output & (name of p) & "|||"
    end repeat
    return output
end tell
"""
    try:
        output = run_applescript(script)
    except RuntimeError as e:
        return {"error": str(e)}
    names = [n.strip() for n in output.split("|||") if n.strip()]
    return {"playlists": names, "count": len(names)}


@mcp.tool()
def search_tracks(query: str) -> dict:
    """Search for tracks in Apple Music (library + catalog).

    Args:
        query: The search query (track name, artist, etc.)

    Returns up to 5 results with title, artist, album, and source.
    """
    results = []
    seen = set()

    # 1. Search library via AppleScript
    escaped = query.replace('"', '\\"')
    script = f"""
tell application "Music"
    set results to (tracks of library playlist 1 whose name contains "{escaped}" or artist contains "{escaped}" or album contains "{escaped}")
    set out to ""
    set i to 0
    repeat with t in results
        set i to i + 1
        if i > 5 then exit repeat
        set out to out & name of t & "|||" & artist of t & "|||" & album of t & linefeed
    end repeat
    return out
end tell
"""
    try:
        lib_output = run_applescript(script)
        for line in lib_output.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            parts = line.split("|||")
            if len(parts) >= 2 and parts[0].strip():
                key = (parts[0].strip().lower(), parts[1].strip().lower())
                if key not in seen:
                    seen.add(key)
                    results.append({
                        "title": parts[0].strip(),
                        "artist": parts[1].strip(),
                        "album": parts[2].strip() if len(parts) > 2 else "",
                        "source": "library",
                    })
    except RuntimeError:
        pass

    # 2. Search iTunes/Apple Music catalog
    try:
        url = f"https://itunes.apple.com/search?term={quote(query)}&entity=song&limit=5"
        body = http_get(url, headers={"User-Agent": "apple-music-mcp/1.0"}, timeout=10)
        if body:
            data = json.loads(body)
            for track in data.get("results", []):
                key = (track["trackName"].lower(), track["artistName"].lower())
                if key not in seen:
                    seen.add(key)
                    results.append({
                        "title": track["trackName"],
                        "artist": track["artistName"],
                        "album": track.get("collectionName", ""),
                        "source": "catalog",
                    })
    except Exception:
        pass

    return {"query": query, "results": results[:5], "count": len(results[:5])}


@mcp.tool()
def search_and_add(query: str, playlist_name: str) -> dict:
    """Search for a track and add the first match to a playlist.

    Searches your library first. For tracks already in your library,
    adds them directly to the playlist. For catalog-only tracks,
    returns the top match so you can play it first, then use
    add_to_playlist.

    Args:
        query: The search query (track name, artist, etc.)
        playlist_name: The name of the playlist to add the track to
    """
    escaped = query.replace('"', '\\"')
    escaped_pl = playlist_name.replace('"', '\\"')
    script = f"""
tell application "Music"
    set results to (tracks of library playlist 1 whose name contains "{escaped}" or artist contains "{escaped}" or album contains "{escaped}")
    if (count of results) = 0 then
        return "NOTFOUND"
    end if
    set t to item 1 of results
    set tName to name of t
    set tArtist to artist of t
    set tAlbum to album of t
    set p to first playlist whose name is "{escaped_pl}"
    duplicate t to p
    return "OK|||" & tName & "|||" & tArtist & "|||" & tAlbum & "|||library"
end tell
"""
    try:
        output = run_applescript(script)
    except RuntimeError as e:
        return {"error": str(e)}

    if output == "NOTFOUND":
        # Fall back to catalog search
        try:
            url = f"https://itunes.apple.com/search?term={quote(query)}&entity=song&limit=1"
            body = http_get(url, headers={"User-Agent": "apple-music-mcp/1.0"}, timeout=10)
            if body:
                data = json.loads(body)
                tracks = data.get("results", [])
                if tracks:
                    t = tracks[0]
                    return {
                        "status": "not_in_library",
                        "found": {
                            "title": t["trackName"],
                            "artist": t["artistName"],
                            "album": t.get("collectionName", ""),
                        },
                        "hint": "This track is not in your library. Play it in Music first, then use add_to_playlist to add it.",
                        "playlist": playlist_name,
                    }
        except Exception:
            pass
        return {"error": f"No results found for '{query}'"}

    parts = output.split("|||")
    if len(parts) >= 5 and parts[0] == "OK":
        return {
            "status": "ok",
            "title": parts[1].strip(),
            "artist": parts[2].strip(),
            "album": parts[3].strip(),
            "source": parts[4].strip(),
            "playlist": playlist_name,
        }
    return {"error": f"Unexpected response: {output}"}


def main():
    mcp.run()

if __name__ == "__main__":
    main()
