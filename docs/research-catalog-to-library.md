# Research: Can AppleScript add catalog tracks to library without playing first?

**Date**: 2026-07-18
**Conclusion**: No — no viable bypass exists within AppleScript's capability boundary.

## Test matrix

| Method | Command | Result |
|--------|---------|--------|
| `open location` (itmss://) | `open location "itmss://..."` | Does not start playback, player state stays stopped |
| `open location` (music://) | `open location "music://..."` | Same |
| `play track "name"` | `play track "Blinding Lights"` | "Can't convert data to expected type" — library-only |
| GUI menu click | `click menu item "Add to Library"` | Chinese Music.app has no standalone menu item |
| Keyboard shortcut | `keystroke "l" using command down` | Library track count unchanged |

## Root cause

Apple Music's AppleScript dictionary does not expose catalog tracks as operable objects. `current track` is the only handle that gives a reference to a streaming track — it becomes available only when Music.app is actively playing that track. URL schemes, `play track`, and GUI scripting all hit the same wall.

## Minimal verification script

```applescript
tell application "Music"
    -- Does not start playback
    open location "itmss://itunes.apple.com/cn/album/id1488408555?i=1488408568"

    -- Does not accept catalog track names
    play track "Blinding Lights"

    -- Only valid path: must already be current track
    duplicate current track to source "Library"
end tell
```

## Risk of alternative approaches

- **GUI scripting** risks breakage on non-Chinese systems (menu labels differ)
- **Apple has acknowledged** this as a known bug since 2017, with no committed fix timeline
- The current workaround (`duplicate → poll library → add to playlist`) is community-verified and at the AppleScript capability boundary

## Verdict

**Do not pursue this further.** v0.2's polling optimization is the best achievable within current constraints. Revisit only if Apple ships a fix to `Music.app`'s AppleScript dictionary.
