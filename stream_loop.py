
import argparse
import os
import subprocess
import sys
from pathlib import Path


DEFAULT_INPUT = Path("videos") / "EC.webm"
DEFAULT_FFMPEG = Path("stream") / "ffmpeg.exe"
DEFAULT_URL = "rtsp://0.0.0.0:8554/live"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Loop a video file and publish it as an RTSP stream via ffmpeg.",
    )
    parser.add_argument(
        "--input",
        default=str(DEFAULT_INPUT),
        help="Path to video file (default: videos/EC.webm)",
    )
    parser.add_argument(
        "--ffmpeg",
        default=str(DEFAULT_FFMPEG),
        help="Path to ffmpeg executable (default: stream/ffmpeg.exe)",
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help="RTSP URL to listen on (default: rtsp://0.0.0.0:8554/live)",
    )
    parser.add_argument(
        "--preset",
        default="veryfast",
        help="x264 preset (default: veryfast)",
    )
    parser.add_argument(
        "--transport",
        default="tcp",
        choices=["tcp", "udp"],
        help="RTSP transport for the server (default: tcp)",
    )
    parser.add_argument(
        "--with-audio",
        action="store_true",
        help="Enable audio re-encode (AAC). Default is no audio.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ffmpeg_path = Path(args.ffmpeg)
    input_path = Path(args.input)

    if not ffmpeg_path.exists():
        print(f"ffmpeg not found: {ffmpeg_path}")
        return 1
    if not input_path.exists():
        print(f"input video not found: {input_path}")
        return 1

    cmd = [
        str(ffmpeg_path),
        "-hide_banner",
        "-loglevel",
        "info",
        "-stream_loop",
        "-1",
        "-re",
        "-i",
        str(input_path),
    ]

    if args.with_audio:
        cmd += ["-c:a", "aac", "-b:a", "128k", "-ar", "44100"]
    else:
        cmd += ["-an"]

    cmd += [
        "-c:v",
        "libx264",
        "-preset",
        args.preset,
        "-tune",
        "zerolatency",
        "-pix_fmt",
        "yuv420p",
        "-f",
        "rtsp",
        "-rtsp_transport",
        args.transport,
        "-rtsp_flags",
        "listen",
        args.url,
    ]

    print("Starting stream...")
    print("Command:", subprocess.list2cmdline(cmd))
    print("\nUse this URL in the app:")
    print("rtsp://127.0.0.1:8554/live")
    print("\nPress Ctrl+C to stop.\n")

    try:
        return subprocess.call(cmd)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
