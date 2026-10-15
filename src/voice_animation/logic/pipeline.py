"""Connect audio analysis and style rendering on one shared frame clock."""
import math
from pathlib import Path
from ..config import RenderConfig
from ..media import SAMPLE_RATE, decoded_audio, encode_video
from .analysis import AudioAnalyzer
from .styles import create_renderer


def render_audio(source: Path, output: Path, config: RenderConfig, overwrite=False, progress=None):
    source, output = Path(source).resolve(), Path(output).resolve()
    if not source.is_file():
        raise ValueError(f"Input file does not exist: {source}")
    if source == output:
        raise ValueError("Input and output must be different files.")
    if output.suffix.lower() != ".mp4":
        raise ValueError("Output must have an .mp4 extension.")
    if output.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {output}. Use --overwrite to replace it.")
    renderer = create_renderer(config)
    with decoded_audio(source, config.duration) as samples:
        duration = len(samples) / SAMPLE_RATE
        count = max(1, math.ceil(duration * config.fps))
        analyzer = AudioAnalyzer(samples, SAMPLE_RATE, config.gain)

        def frames():
            for index in range(count):
                yield renderer.render(analyzer.frame(index, config.fps))
                if progress and (index % config.fps == 0 or index == count - 1):
                    progress(index + 1, count)

        encode_video(frames(), source, output, config, duration, overwrite)
    return output
