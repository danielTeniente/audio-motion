"""Command-line arguments and user-facing errors; no animation algorithms."""
import argparse
from pathlib import Path
import sys
from .config import RenderConfig, PALETTES, BRAIN_SPHERE_MODES
from .logic.pipeline import render_audio
from .logic.styles import STYLES


def main(argv=None):
    parser = argparse.ArgumentParser(description="Turn audio into an MP4 animation with its original sound.")
    parser.add_argument("audio", type=Path, help="Input audio file (WAV, MP3, FLAC, etc.)")
    parser.add_argument("output", type=Path, help="Output .mp4 path")
    parser.add_argument("--style", choices=STYLES, default="line")
    parser.add_argument("--brain-mode", choices=BRAIN_SPHERE_MODES, default="connected",
                        help="Brain sphere mode: connected structures (default) or audio rings")
    parser.add_argument("--palette", choices=PALETTES, default="aurora",
                        help="Shared color palette for every style (default: aurora)")
    parser.add_argument("--orbit-seed", type=int,
                        help="Repeat automata orbit's initial state; random when omitted")
    parser.add_argument("--quality", choices=("fast", "balanced"), default="fast",
                        help="Fast (default) encoding; balanced is slower but can produce smaller files")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--gain", type=float, default=3, help="Visual sensitivity; does not change audio volume")
    parser.add_argument("--duration", type=float, help="Render only the first N seconds")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    try:
        config = RenderConfig(**{key: getattr(args, key) for key in RenderConfig.__dataclass_fields__})
        def progress(done, total):
            print(f"\rRendering {done}/{total} frames ({done / total:.0%})", end="", file=sys.stderr, flush=True)
        output = render_audio(args.audio, args.output, config, args.overwrite, None if args.quiet else progress)
    except (ValueError, OSError, RuntimeError) as error:
        print(f"\nError: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nRender cancelled; incomplete video removed.", file=sys.stderr)
        return 130
    if not args.quiet:
        print(f"\nSaved {output}")
    return 0
