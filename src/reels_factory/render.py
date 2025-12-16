"""TTS, subtitles, and video rendering."""
from __future__ import annotations

import glob
import hashlib
import logging
import random
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import ffmpeg
import torch
import torchaudio
import soundfile as sf
import webvtt
import whisper
from kokoro import KPipeline
from llama_cpp import Llama, LlamaGrammar
from whisper.utils import get_writer

from .paths import OutputPaths
from .utils import apply_patterns, reel_id_from_title


def ensure_directory_exists(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)


def detect_gender(story_text: str, llm: Llama) -> str:
    gender_grammar = LlamaGrammar.from_string(
        r"""
        root ::= "male" | "female"
        """
    )
    gender_prompt = f"""
Based on the following story, determine the gender of the narrator.
Answer in a single word only.
Assume the narrator is heterosexual, so their gender is the opposite of their partner / romantic interest.

[START OF STORY]
{story_text}
[END OF STORY]

Narrator's gender: """
    gender = llm(
        gender_prompt,
        temperature=0.0,
        max_tokens=1,
        grammar=gender_grammar,
    )["choices"][0]["text"].strip()
    return gender


def format_ass_time(t: str, delta_s: float = 0.0) -> str:
    input_time = datetime.strptime(t, "%H:%M:%S.%f")
    zero_time = datetime.strptime("00:00:00.00", "%H:%M:%S.%f")
    delta_time = timedelta(seconds=delta_s)
    return "00:00:00.00" if (input_time + delta_time) < zero_time else (input_time + delta_time).strftime("%H:%M:%S.%f")[:-4]


def convert_vtt_to_ass(vtt_path: Path, ass_path: Path, config: dict) -> None:
    ass_path.parent.mkdir(parents=True, exist_ok=True)
    with ass_path.open("w", encoding="utf-8") as f:
        f.write(
            """[Script Info]
Title: Styled Subtitles
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Segoe UI Emoji,150,&H00FFFFFF,&H64000000,-1,0,0,0,100,100,0,0,1,15,1,5,150,150,200,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        )

        end = ""
        first = True
        delay = config["video_generation"]["caption_delay"]
        patterns = config.get("caption_censoring", [])
        for caption in webvtt.read(vtt_path):
            start = format_ass_time(caption.start, delta_s=-delay)
            if first:
                first = False
                start = format_ass_time(caption.start)
            elif start == end:
                start = format_ass_time(caption.start, delta_s=-delay + 0.00)
            end = format_ass_time(caption.end, delta_s=-delay)
            text = caption.text.replace("\n", "\\N")
            text = apply_patterns(text, patterns)
            f.write(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n")


def generate_tts(text: str, narrator_gender: str, pipeline: KPipeline, config: dict):
    voice = "af_heart" if narrator_gender == "female" else "am_michael"
    generator = pipeline(text, voice=voice, speed=config["video_generation"]["audio_speed"][narrator_gender], split_pattern=r"\n+")

    total_audio = []
    for _, (_, _, audio) in enumerate(generator):
        total_audio.append(audio)
    audio = torch.concatenate(total_audio)
    return audio


def transcribe_audio(audio: torch.Tensor, model) -> dict:
    waveform = torchaudio.transforms.Resample(orig_freq=24000, new_freq=16000)(audio)
    result = model.transcribe(waveform, language="en", word_timestamps=True, task="transcribe")
    return result


def generate_video(video_path: str, narration_path: Path, subtitle_path: Path, output_path: Path, post_description: str = ""):
    narration_waveform, sample_rate = torchaudio.load(narration_path)
    narration_duration = narration_waveform.shape[1] / sample_rate + 12.0

    probe = ffmpeg.probe(video_path)
    video_duration = float(probe["format"]["duration"])
    has_audio = any(stream["codec_type"] == "audio" for stream in probe["streams"])

    max_start = max(video_duration - narration_duration, 0)
    start_time = round(random.uniform(0.0, max_start), 2)

    video_in = ffmpeg.input(video_path, ss=start_time, t=narration_duration, hwaccel="cuda")
    narration_in = ffmpeg.input(str(narration_path), ss=0, t=narration_duration)

    video = video_in.video
    video_cropped = video.filter("crop", "in_h*9/16", "in_h", "(in_w-out_w)/2", "0")
    video_subtitled = video_cropped.filter("subtitles", str(subtitle_path))

    narr_audio = narration_in.audio.filter("volume", 1.5)

    if has_audio:
        bg_audio = video_in.audio.filter("volume", 0.1)
        mixed_audio = ffmpeg.filter([bg_audio, narr_audio], "amix", inputs=2, duration="shortest", dropout_transition=2)
    else:
        mixed_audio = narr_audio

    (
        ffmpeg.output(
            video_subtitled,
            mixed_audio,
            str(output_path),
            vcodec="h264_nvenc",
            preset="p2",
            cq="23",
            pix_fmt="yuv420p",
            acodec="aac",
            ar=48000,
            movflags="+faststart",
            **{"map_metadata": "-1"},
            shortest=None,
            strict="experimental",
            metadata=f"description={post_description}",
        )
        .overwrite_output()
        .run(capture_stdout=True, capture_stderr=True)
    )


def create_reel(
    post_text: str,
    post_title: str,
    config: dict,
    llm: Optional[Llama] = None,
    pipeline: Optional[KPipeline] = None,
    model=None,
    post_description: str = "",
):
    output_paths = OutputPaths.from_config(config)
    output_paths.ensure_all()

    if pipeline is None:
        pipeline = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
    if model is None:
        model = whisper.load_model(config["video_generation"]["whisper_model_size"])
    private_llm = llm is None
    if private_llm:
        llm = Llama(
            model_path="models/llama-3.1-8b-instruct-q6_k.gguf",
            n_gpu_layers=-1,
            n_ctx=2048,
            verbose=False,
            streaming=False,
            device="cuda",
        )

    narrator_gender = detect_gender(post_text, llm)
    if private_llm and llm is not None:
        llm.close()

    audio = generate_tts(post_text, narrator_gender, pipeline, config)

    reel_id = reel_id_from_title(post_title)

    narration_path = output_paths.narration_dir / f"{reel_id}.wav"
    sf.write(narration_path, audio, 24000)

    transcription = transcribe_audio(audio, model)
    vtt_path = output_paths.subtitles_dir / f"{reel_id}.vtt"
    ass_path = output_paths.subtitles_dir / f"{reel_id}.ass"
    vtt_writer = get_writer(output_format="vtt", output_dir=str(output_paths.subtitles_dir))
    word_options = {"highlight_words": True, "max_line_count": 1, "max_words_per_line": 5}
    vtt_writer(transcription, narration_path, word_options)
    convert_vtt_to_ass(vtt_path, ass_path, config)

    video_glob = config.get("assets", {}).get("background_glob", "videos/*.mp4")
    candidates = glob.glob(video_glob)
    if not candidates:
        raise FileNotFoundError(f"No background videos found for glob: {video_glob}")
    video_path = random.choice(candidates)

    output_path = output_paths.reels_dir / f"{reel_id}.mp4"
    ensure_directory_exists(output_paths.reels_dir)
    generate_video(video_path, narration_path, ass_path, output_path, post_description)

    logging.info("Generated reel %s at %s", reel_id, output_path)
    return output_path
