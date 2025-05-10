"""Rewrite stories and generate hooks/hashtags."""
from __future__ import annotations

import re
from typing import Optional, Tuple

import torch
from llama_cpp import Llama


def create_llm(model_path: str | None = None, device: Optional[str] = None) -> Llama:
    resolved_device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    return Llama(
        model_path=model_path or "models/llama-3.1-8b-instruct-q6_k.gguf",
        n_gpu_layers=-1,
        n_ctx=8192,
        verbose=False,
        streaming=False,
        device=resolved_device,
    )


def _default_llm() -> Llama:
    return create_llm()


def is_story_interesting(story_text: str, llm) -> bool:
    """
    Return True if the story is strong enough for a 60-second reel.
    """
    prompt = f"""<|User|>
You are a senior viral-content curator for TikTok & Instagram Reels.
You are presented with many posts, and only those that pass your very high bar are published.

**Task**
Evaluate the Reddit post below and decide if it is a gripping,
100-300-word first-person narration video that viewers will watch to the end, and worth publishing.
The viewers are very picky about watching reels, and have very high standards for what's interesting.

When you're done, wrap your one-word verdict inside the <answer> tags below:

<answer>YES</answer>   -> if the story is suitable and interesting
<answer>NO</answer>    -> if it is not

Before reaching your conclusion, also estimate the probability (numeric value between 0 and 1) the instagram reel will go viral.
After thinking, output the tags and the single word only.

[START OF STORY]
{story_text}
[END OF STORY]

<|Assistant|>"""
    resp = llm(prompt, temperature=0.05, max_tokens=512)
    text = resp["choices"][0]["text"]
    try:
        answer = text.split("<answer>")[1].split("</answer>")[0].strip().upper()
    except IndexError:
        return False
    return answer == "YES"


def rewrite_story(story_text: str, llm: Llama) -> str:
    """Rewrite the story to make it suitable for short-form video content."""
    prompt = f"""<ЛлoUserЛлo> You are a viral storytelling expert specializing in writing emotionally powerful, suspenseful, and punchy first-person stories for short-form videos (TikTok, Instagram).

Your task is to rewrite the following Reddit-style story:

- First and foremost - the story should be interesting and captivating, so that the video will go viral.
- Start with an attention-grabbing hook (shock, contradiction, question, striking visual) that focuses on the most interesting part of the story. The first few seconds are crucial to capture the viewer's attention.
- Use **first-person** storytelling ("I", "my", "we", etc.).
- Keep sentences short and punchy, natural for spoken narration, sustain curiosity every 2 seconds.
- Feel free to spice up the details in a believable way, to make the story more interesting but still believable.
- Near the end, reach some conclusion, call-to-action or end with a cliffhanger.
- Keep the total length between **100 and 300 words**.

IMPORTANT:
- Do not explain the whole background slowly – start with action immediately.
- Do not ramble or overexplain – each sentence must move the story forward.
- Do not repeat yourself too much.
- Do not exceed 250 words. It must fit in a 1-minute voiceover.
- Do not continue rambling after the story has reached its conclusion or peak.

Here is the original story:

[START OF STORY]
{story_text}
[END OF STORY]

Rewrite it following these rules.
Think and plan a little before rewriting, and then output "[START OF REWRITTEN STORY]" to signal the beginning of the rewritten story, ending with "[END OF REWRITTEN STORY]" to signal completion
<ЛлoAssistantЛлo>
"""
    output = llm(prompt, temperature=0.6, max_tokens=4096, stop=["[END "])
    rewrite = output["choices"][0]["text"].split("[START OF REWRITTEN STORY]")[-1].strip()
    return rewrite


def generate_hook(story_text: str, llm: Llama) -> str:
    """Generate an attention-grabbing opening line for the story."""
    prompt = f"""You are a viral content expert specializing in writing extremely attention-grabbing opening lines for short video content on TikTok and Instagram.

Given the following Reddit-style story, your task is to write a **single**, **very short** (5–15 words) opening line that would immediately grab a scrolling viewer's attention.

Here is the story:

[START OF STORY]
{story_text}
[END OF STORY]

Generate **only the attention-grabbing opening line**, and nothing else.
Output "[START OF OPENING LINE]" ... "[END OF OPENING LINE]" around your text.
"""
    output = llm(prompt, temperature=0.6, max_tokens=1024, stop=["[END "])
    hook = output["choices"][0]["text"].split("[START OF OPENING LINE]")[-1].strip()
    return hook


def generate_hashtags(story_text: str, subreddit_name: str, llm: Optional[Llama] = None) -> str:
    """Generate a list of relevant hashtags for the story."""
    private_llm = llm is None
    if private_llm:
        llm = _default_llm()

    prompt = f"""You are an expert in viral social media content, specializing in creating short-form videos for platforms like TikTok, Instagram Reels, and YouTube Shorts.

Your job is to generate **a list of relevant hashtags** (2 to 5 total) that will help this story reach a large audience.
The hashtags should:
- Be short and commonly used (like #storytime, #cheating, #toxicrelationship).
- Not too repetitive.
- Reflect the core themes, emotions, or events in the story.
- Be platform-friendly: lowercase, no spaces, no punctuation, no slurs.

[START OF STORY]
{story_text}
[END OF STORY]

Generate only hashtags, ending with "[END OF HASHTAGS]".
[START OF HASHTAGS]
"""
    raw_response = llm(prompt, temperature=0.3, max_tokens=256, stop=["[END "])
    raw_response = raw_response["choices"][0]["text"].strip()
    tags = re.findall(r"#\w+", raw_response.lower())
    unique_tags = list(dict.fromkeys(tags))
    base_tags = ["#storytime", "#redditstories", f"#{subreddit_name.replace('_','')}"]
    tags = base_tags + [tag for tag in unique_tags if tag not in base_tags]

    if private_llm:
        llm.close()
    return " ".join(tags[:8])


def process_text(
    text: str,
    llm: Optional[Llama] = None,
    return_hook: bool = False,
) -> Optional[str]:
    """
    Rewrite text and optionally prepend a hook.
    """
    private_llm = llm is None
    if private_llm:
        llm = _default_llm()

    rewritten_story = rewrite_story(text, llm)
    if not rewritten_story:
        if private_llm:
            llm.close()
        return None

    hook = generate_hook(rewritten_story, llm) if return_hook else None
    result = f"{hook};-\n{rewritten_story}" if hook else rewritten_story

    if private_llm:
        llm.close()

    return result
