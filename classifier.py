"""
Claude/Groq/Ollama classification engine — replaces probability estimation with direction classification.
Asks "does this news confirm or deny the market question?" instead of "what's the probability?"

Supports multiple LLM backends: Anthropic Claude, Groq (fast), Ollama (local).
V3 upgrade: Consensus classification — runs multiple passes with varied prompts
and only trades when all passes agree on direction.
"""
from __future__ import annotations

import json
import time
import logging
from dataclasses import dataclass

import config
from markets import Market

log = logging.getLogger(__name__)


# ============================================================
# LLM Backend Abstraction
# ============================================================

def _call_llm(prompt: str, temperature: float = 0.1, max_tokens: int = 200) -> str:
    """Call the configured LLM backend. Returns raw text response."""
    provider = config.LLM_PROVIDER

    if provider == "gemini":
        return _call_gemini(prompt, temperature, max_tokens)
    elif provider == "groq":
        return _call_groq(prompt, temperature, max_tokens)
    elif provider == "ollama":
        return _call_ollama(prompt, temperature, max_tokens)
    elif provider == "anthropic":
        return _call_anthropic(prompt, temperature, max_tokens)
    else:
        # Auto-detect: try gemini first (fast+cheap), then groq, ollama, anthropic
        if config.GEMINI_API_KEY:
            return _call_gemini(prompt, temperature, max_tokens)
        elif config.GROQ_API_KEY:
            return _call_groq(prompt, temperature, max_tokens)
        elif config.OLLAMA_BASE_URL:
            return _call_ollama(prompt, temperature, max_tokens)
        elif config.ANTHROPIC_API_KEY:
            return _call_anthropic(prompt, temperature, max_tokens)
        else:
            raise RuntimeError("No LLM configured — set GEMINI_API_KEY, GROQ_API_KEY, ANTHROPIC_API_KEY, or OLLAMA_BASE_URL")


_gemini_last_call = 0.0
_GEMINI_MIN_INTERVAL = 4.0  # seconds between calls (free tier: 15 RPM)

def _call_gemini(prompt: str, temperature: float, max_tokens: int) -> str:
    """Call Google Gemini API (fast + cheap). Rate-limited for free tier."""
    import time as _time
    global _gemini_last_call

    # Enforce rate limit
    elapsed = _time.time() - _gemini_last_call
    if elapsed < _GEMINI_MIN_INTERVAL:
        _time.sleep(_GEMINI_MIN_INTERVAL - elapsed)

    from google import genai
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    _gemini_last_call = _time.time()
    response = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=prompt,
        config={
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        },
    )
    return response.text.strip()


def _call_groq(prompt: str, temperature: float, max_tokens: int) -> str:
    """Call Groq API (fast inference)."""
    from groq import Groq
    client = Groq(api_key=config.GROQ_API_KEY)
    model = config.CLASSIFICATION_MODEL
    # Map anthropic model names to groq-compatible ones
    if "claude" in model or "haiku" in model or "sonnet" in model:
        model = "llama-3.3-70b-versatile"

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content.strip()


def _call_ollama(prompt: str, temperature: float, max_tokens: int) -> str:
    """Call Ollama local model."""
    import ollama
    model = config.CLASSIFICATION_MODEL
    # Map anthropic model names to ollama ones if needed
    if "claude" in model or "haiku" in model or "sonnet" in model:
        model = "gemma3:12b"

    response = ollama.chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": temperature, "num_predict": max_tokens},
    )
    return response["message"]["content"].strip()


def _call_anthropic(prompt: str, temperature: float, max_tokens: int) -> str:
    """Call Anthropic Claude API."""
    import anthropic
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=config.CLASSIFICATION_MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


# ============================================================
# Classification Prompts
# ============================================================

# Primary classification prompt (analyst perspective)
CLASSIFICATION_PROMPT = """You are a news classifier for prediction markets.

## Market Question
{question}

## Current Market Price
YES: {yes_price:.2f} (implied probability: {yes_price:.0%})

## Breaking News
{headline}
Source: {source}

## Task
Does this news make the market question MORE likely to resolve YES, MORE likely to resolve NO, or is it NOT RELEVANT?

Also rate the MATERIALITY — how much should this move the price? 0.0 means no impact, 1.0 means this is definitive evidence.

Respond with ONLY valid JSON:
{{
  "direction": "bullish" | "bearish" | "neutral",
  "materiality": <float 0.0 to 1.0>,
  "reasoning": "<1 sentence>"
}}"""

# Devil's advocate prompt (skeptic perspective — used for consensus pass 2)
SKEPTIC_PROMPT = """You are a SKEPTICAL prediction market analyst. Your job is to challenge knee-jerk reactions to news.

## Market Question
{question}

## Current Market Price
YES: {yes_price:.2f} (implied probability: {yes_price:.0%})

## Breaking News
{headline}
Source: {source}

## Task
Think critically: Is this news ACTUALLY material to this market, or is it noise?
- Could this be old news already priced in?
- Is the source reliable?
- Does this DIRECTLY affect the outcome, or is it tangential?

Classify: does this news make the market MORE likely YES, MORE likely NO, or NOT RELEVANT?
Rate materiality conservatively — only rate above 0.5 if this is genuinely significant.

Respond with ONLY valid JSON:
{{
  "direction": "bullish" | "bearish" | "neutral",
  "materiality": <float 0.0 to 1.0>,
  "reasoning": "<1 sentence>"
}}"""

PROMPTS = [CLASSIFICATION_PROMPT, SKEPTIC_PROMPT]


# ============================================================
# Classification Logic
# ============================================================

@dataclass
class Classification:
    direction: str  # "bullish", "bearish", "neutral"
    materiality: float  # 0.0-1.0
    reasoning: str
    latency_ms: int
    model: str
    consensus_passes: int = 1
    consensus_agreed: bool = True


def _parse_json_response(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown code blocks."""
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    # Try to find JSON object in the text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        text = text[start:end]

    return json.loads(text)


def _single_classify(prompt_template: str, headline: str, market: Market, source: str, temperature: float = 0.1) -> dict:
    """Run a single classification pass. Returns raw result dict."""
    prompt = prompt_template.format(
        question=market.question,
        yes_price=market.yes_price,
        headline=headline,
        source=source,
    )

    text = _call_llm(prompt, temperature=temperature, max_tokens=200)
    result = _parse_json_response(text)

    direction = result.get("direction", "neutral")
    if direction not in ("bullish", "bearish", "neutral"):
        direction = "neutral"

    materiality = max(0.0, min(1.0, float(result.get("materiality", 0))))

    return {
        "direction": direction,
        "materiality": materiality,
        "reasoning": result.get("reasoning", ""),
    }


def classify(headline: str, market: Market, source: str = "unknown") -> Classification:
    """
    Classify a news headline against a market question.
    If CONSENSUS_ENABLED, runs multiple passes and requires agreement.
    """
    start = time.time()
    num_passes = config.CONSENSUS_PASSES if config.CONSENSUS_ENABLED else 1

    # Determine which model name to log
    provider = config.LLM_PROVIDER
    if provider == "gemini":
        model_name = "gemini/" + config.GEMINI_MODEL
    elif provider == "groq":
        model_name = "groq/" + config.CLASSIFICATION_MODEL
    elif provider == "ollama":
        model_name = "ollama/" + config.CLASSIFICATION_MODEL
    else:
        model_name = config.CLASSIFICATION_MODEL

    try:
        results = []
        for i in range(num_passes):
            prompt = PROMPTS[i % len(PROMPTS)]
            temp = 0.1 if i == 0 else 0.2
            result = _single_classify(prompt, headline, market, source, temperature=temp)
            results.append(result)

        latency = int((time.time() - start) * 1000)

        # Check consensus
        directions = [r["direction"] for r in results]
        materialities = [r["materiality"] for r in results]

        non_neutral = [d for d in directions if d != "neutral"]

        if not non_neutral:
            return Classification(
                direction="neutral",
                materiality=0.0,
                reasoning="All classification passes returned neutral",
                latency_ms=latency,
                model=model_name,
                consensus_passes=num_passes,
                consensus_agreed=True,
            )

        agreed = len(set(non_neutral)) == 1
        dominant_direction = non_neutral[0] if agreed else "neutral"
        avg_materiality = min(materialities) if agreed else 0.0

        reasonings = [f"[Pass {i+1}] {r['reasoning']}" for i, r in enumerate(results)]
        combined_reasoning = " | ".join(reasonings)

        if not agreed:
            combined_reasoning = f"DISAGREEMENT ({', '.join(directions)}) — no trade. {combined_reasoning}"

        return Classification(
            direction=dominant_direction,
            materiality=avg_materiality,
            reasoning=combined_reasoning,
            latency_ms=latency,
            model=model_name,
            consensus_passes=num_passes,
            consensus_agreed=agreed,
        )

    except Exception as e:
        latency = int((time.time() - start) * 1000)
        log.warning(f"[classifier] Error: {e}")
        return Classification(
            direction="neutral",
            materiality=0.0,
            reasoning=f"Classification error: {type(e).__name__}: {e}",
            latency_ms=latency,
            model=model_name,
            consensus_passes=1,
            consensus_agreed=False,
        )


async def classify_async(headline: str, market: Market, source: str = "unknown") -> Classification:
    """Async wrapper around classify()."""
    import asyncio
    return await asyncio.get_event_loop().run_in_executor(
        None, classify, headline, market, source
    )


if __name__ == "__main__":
    test_market = Market(
        condition_id="test",
        question="Will OpenAI release GPT-5 before August 2026?",
        category="ai",
        yes_price=0.62,
        no_price=0.38,
        volume=500000,
        end_date="2026-08-01",
        active=True,
        tokens=[],
    )

    print(f"LLM Provider: {config.LLM_PROVIDER}")
    result = classify(
        headline="OpenAI reportedly testing GPT-5 internally with select partners",
        market=test_market,
        source="The Information",
    )
    print(f"Direction: {result.direction}")
    print(f"Materiality: {result.materiality}")
    print(f"Reasoning: {result.reasoning}")
    print(f"Latency: {result.latency_ms}ms")
    print(f"Model: {result.model}")
    print(f"Consensus: {result.consensus_passes} passes, agreed={result.consensus_agreed}")
