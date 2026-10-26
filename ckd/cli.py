"""Command-line interface (also used by the notebook's shell-free helpers).

    python -m ckd info
    python -m ckd topics
    python -m ckd script --topic "solar energy" --langs en,ur --out story.json
    python -m ckd preview --topic "wifi" --formats landscape,vertical
    python -m ckd render --topic "bridge engineering" --langs en --formats landscape \
        --quality draft --duration 30 --project-dir projects
    python -m ckd resume --project-dir projects/bridge-engineering
    python -m ckd voices
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .content.composer import available_topics, compose_story
from .content.options import QUALITY_PRESETS, RenderOptions
from .util.logging import setup_logging
from .util.system import system_info


def _split(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def _options(args) -> RenderOptions:
    return RenderOptions(
        topic=args.topic,
        languages=_split(getattr(args, "langs", "en")) or ["en"],
        formats=_split(getattr(args, "formats", "landscape")) or ["landscape"],
        duration=float(getattr(args, "duration", 45)),
        quality=getattr(args, "quality", "standard"),
        fps=int(getattr(args, "fps", 24)),
        include_captions=not getattr(args, "no_captions", False),
        include_character=not getattr(args, "no_character", False),
        voice_en=getattr(args, "voice_en", "auto"),
        voice_ur=getattr(args, "voice_ur", "auto"),
        allow_espeak_fallback=not getattr(args, "no_fallback", False),
        master_audio=not getattr(args, "no_master", False),
        llm=getattr(args, "llm", "none"),
        seed=int(getattr(args, "seed", 7)),
        notes=getattr(args, "notes", ""),
        palette=getattr(args, "palette", "auto"),
    )


def _progress(stage: str, frac: float, msg: str) -> None:
    bar = "#" * int(frac * 24)
    sys.stdout.write(f"\r[{stage:<26}] {bar:<24} {frac * 100:3.0f}% {msg[:70]:<70}")
    sys.stdout.flush()
    if frac >= 1.0:
        sys.stdout.write("\n")


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    ap = argparse.ArgumentParser(prog="ckd", description="CKD topic-to-video studio (offline)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("info", help="system + environment report")
    sub.add_parser("topics", help="list curated topics")
    sub.add_parser("voices", help="list TTS voices and cache state")

    p_script = sub.add_parser("script", help="compose and save the script/plan only")
    p_script.add_argument("--topic", required=True)
    p_script.add_argument("--langs", default="en")
    p_script.add_argument("--duration", type=float, default=45)
    p_script.add_argument("--notes", default="")
    p_script.add_argument("--llm", default="none")
    p_script.add_argument("--out", default="story.json")

    def add_render_args(p):
        p.add_argument("--topic", required=True)
        p.add_argument("--langs", default="en")
        p.add_argument("--formats", default="landscape")
        p.add_argument("--duration", type=float, default=45)
        p.add_argument("--quality", default="standard", choices=sorted(QUALITY_PRESETS))
        p.add_argument("--fps", type=int, default=24)
        p.add_argument("--no-captions", action="store_true")
        p.add_argument("--no-character", action="store_true")
        p.add_argument("--voice-en", default="auto")
        p.add_argument("--voice-ur", default="auto")
        p.add_argument("--no-fallback", action="store_true")
        p.add_argument("--no-master", action="store_true",
                       help="skip dialogue mastering (EQ/compression/loudness)")
        p.add_argument("--llm", default="none")
        p.add_argument("--seed", type=int, default=7)
        p.add_argument("--notes", default="")
        p.add_argument("--palette", default="auto")
        p.add_argument("--project-dir", default="projects")
        p.add_argument("--force", default="", help="comma list: scenes,video")

    p_prev = sub.add_parser("preview", help="storyboard stills / contact sheets")
    add_render_args(p_prev)
    p_prev.add_argument("--samples", type=int, default=2)

    p_rend = sub.add_parser("render", help="render final MP4(s)")
    add_render_args(p_rend)
    p_rend.add_argument("--compile-only", action="store_true",
                        help="script + narration only (fast review step)")

    p_res = sub.add_parser("resume", help="resume a project directory")
    p_res.add_argument("--project-dir", required=True)
    p_res.add_argument("--force", default="")

    args = ap.parse_args(argv)

    if args.cmd == "info":
        info = system_info()
        print(json.dumps(info.to_dict(), indent=2))
        from .render.ffmpeg import ffmpeg_version
        from .voice.registry import describe_voices

        print("ffmpeg:", ffmpeg_version())
        print("voices:", json.dumps(describe_voices(), indent=2))
        return 0

    if args.cmd == "topics":
        print(json.dumps(available_topics(), indent=2, ensure_ascii=False))
        return 0

    if args.cmd == "voices":
        from .voice.registry import describe_voices

        print(json.dumps(describe_voices(), indent=2))
        return 0

    if args.cmd == "script":
        story = compose_story(args.topic, languages=_split(args.langs),
                              target_seconds=args.duration, notes=args.notes,
                              llm=args.llm if args.llm != "none" else None)
        Path(args.out).write_text(json.dumps(story.to_dict(), indent=1, ensure_ascii=False),
                                  encoding="utf-8")
        print(f"wrote {args.out}: {len(story.scenes)} scenes, world={story.world}")
        for w in story.warnings:
            print("WARNING:", w)
        return 0

    if args.cmd == "preview":
        from .pipeline.run import Pipeline

        opts = _options(args)
        pipe = Pipeline(options=opts, root=Path(args.project_dir), progress=_progress)
        story = pipe.build_story()
        tracks = pipe.narrate(story)
        for lang in opts.languages:
            for fmt in opts.formats:
                sheet = pipe.preview_sheet(story, tracks, lang, fmt, samples=args.samples, ss=1)
                print(f"\npreview: {sheet}")
        return 0

    if args.cmd == "render":
        from .pipeline.run import Pipeline

        opts = _options(args)
        pipe = Pipeline(options=opts, root=Path(args.project_dir), progress=_progress,
                        force=tuple(_split(getattr(args, "force", ""))))
        res = pipe.run(compile_only=args.compile_only)
        print("\nproject:", res["project"])
        if not args.compile_only:
            for key, meta in res.get("videos", {}).items():
                status = "OK" if meta.get("verified") else "ISSUES"
                print(f"  {status} {key}: {meta['path']} "
                      f"({meta['duration']:.1f}s {meta['width']}x{meta['height']} {meta['fps']}fps)")
                for problem in meta.get("problems", []):
                    print("     !", problem)
        return 0

    if args.cmd == "resume":
        from .pipeline.project import Project
        from .pipeline.run import Pipeline

        root = Path(args.project_dir)
        state = json.loads((root / "project.json").read_text(encoding="utf-8"))
        opts = RenderOptions.from_dict(state["options"])
        pipe = Pipeline(options=opts, root=root.parent, project_dir=root, progress=_progress,
                        force=tuple(_split(args.force)))
        res = pipe.run()
        print("\nresumed:", res["project"], f"in {res['seconds']}s")
        return 0

    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
