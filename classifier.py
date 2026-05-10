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
import asyncio
import logging
import random
from dataclasses import dataclass

import config
from markets import Market

log = logging.getLogger(__name__)


# ============================================================
# LLM Backend Abstraction
# ============================================================

async def _call_llm_async(prompt: str, temperature: float = 0.1, max_tokens: int = 200) -> str:
    """Call the configured LLM backend asynchronously."""
    provider = config.LLM_PROVIDER

    if provider == "gemini":
        return await _call_gemini_async(prompt, temperature, max_tokens)
    elif provider == "groq":
        return await _call_groq_async(prompt, temperature, max_tokens)
    elif provider == "nvidia":
        return await _call_nvidia_async(prompt, temperature, max_tokens)
    elif provider == "ollama":
        return await _call_ollama_async(prompt, temperature, max_tokens)
    elif provider == "mimo":
        return await _call_mimo_async(prompt, temperature, max_tokens)
    elif provider == "anthropic":
        return await _call_anthropic_async(prompt, temperature, max_tokens)
    elif provider == "mixed":
        # Priority: MiMo → NVIDIA → Groq (Gemini removed — permanent 429s)
        if config.MIMO_API_KEY:
            return await _call_mimo_async(prompt, temperature, max_tokens)
        elif config.NVIDIA_API_KEY:
            return await _call_nvidia_async(prompt, temperature, max_tokens)
        elif config.GROQ_API_KEY:
            return await _call_groq_async(prompt, temperature, max_tokens)
        return await _call_mimo_async(prompt, temperature, max_tokens)
    else:
        # Default fallback: MiMo → NVIDIA → Groq (Gemini removed)
        if config.MIMO_API_KEY:
            return await _call_mimo_async(prompt, temperature, max_tokens)
        elif config.NVIDIA_API_KEY:
            return await _call_nvidia_async(prompt, temperature, max_tokens)
        elif config.GROQ_API_KEY:
            return await _call_groq_async(prompt, temperature, max_tokens)
        elif config.ANTHROPIC_API_KEY:
            return await _call_anthropic_async(prompt, temperature, max_tokens)
        else:
            raise RuntimeError("No LLM configured")


def _call_llm(prompt: str, temperature: float = 0.1, max_tokens: int = 200) -> str:
    """Synchronous fallback (calls async version and runs it)."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # This is tricky from within a running loop, but _call_llm should ideally not be used in V2
            import nest_asyncio
            nest_asyncio.apply()
        return loop.run_until_complete(_call_llm_async(prompt, temperature, max_tokens))
    except:
        # Fallback to a truly synchronous way if needed, but we want to move to async
        return asyncio.run(_call_llm_async(prompt, temperature, max_tokens))


_gemini_last_call    = 0.0
_GEMINI_MIN_INTERVAL = 6.0   # 6s spacing ≈ 10 RPM — safer for free tier (MiroFish doubles calls)


async def _call_gemini_async(prompt: str, temperature: float, max_tokens: int, use_search: bool = False) -> str:
    """Async Gemini call — DISABLED (permanent 429 on this project).
    
    Goes straight to MiMo → NVIDIA → Groq fallback chain.
    """
    # Gemini is permanently 429'd — skip entirely to avoid wasting time
    if config.MIMO_API_KEY:
        return await _call_mimo_async(prompt, temperature, max_tokens)
    elif config.NVIDIA_API_KEY:
        return await _call_nvidia_async(prompt, temperature, max_tokens)
    return await _call_groq_async(prompt, temperature, max_tokens)


def _call_gemini(prompt: str, temperature: float, max_tokens: int, use_search: bool = False) -> str:
    """Legacy sync wrapper."""
    return asyncio.run(_call_gemini_async(prompt, temperature, max_tokens, use_search))


async def _call_groq_async(prompt: str, temperature: float, max_tokens: int) -> str:
    """Async Groq call."""
    from groq import AsyncGroq
    client = AsyncGroq(api_key=config.GROQ_API_KEY)
    model = config.CLASSIFICATION_MODEL
    if not model or "claude" in model or "sonnet" in model:
        model = "llama-3.3-70b-versatile"

    for attempt in range(3):
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            if "429" in str(e):
                await asyncio.sleep(5 * (attempt + 1))
            else:
                raise
    raise RuntimeError("Groq failed")


def _call_groq(prompt: str, temperature: float, max_tokens: int) -> str:
    """Legacy sync wrapper."""
    return asyncio.run(_call_groq_async(prompt, temperature, max_tokens))


async def _call_mimo_async(prompt: str, temperature: float, max_tokens: int) -> str:
    """Async Mimo call."""
    import httpx
    api_key = config.MIMO_API_KEY
    if not api_key:
        return await _call_gemini_async(prompt, temperature, max_tokens)

    url = f"{config.MIMO_BASE_URL}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": config.MIMO_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    async with httpx.AsyncClient(timeout=45) as client:
        for attempt in range(3):
            try:
                resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"].strip()
            except Exception as e:
                if attempt < 2:
                    await asyncio.sleep(2)
                else:
                    # Fallback: NVIDIA → Groq (NOT Gemini to avoid circular loop)
                    if config.NVIDIA_API_KEY:
                        return await _call_nvidia_async(prompt, temperature, max_tokens)
                    return await _call_groq_async(prompt, temperature, max_tokens)
    # Fallback: NVIDIA → Groq
    if config.NVIDIA_API_KEY:
        return await _call_nvidia_async(prompt, temperature, max_tokens)
    return await _call_groq_async(prompt, temperature, max_tokens)


def _call_mimo(prompt: str, temperature: float, max_tokens: int) -> str:
    """Legacy sync wrapper."""
    return asyncio.run(_call_mimo_async(prompt, temperature, max_tokens))


async def _call_nvidia_async(prompt: str, temperature: float, max_tokens: int) -> str:
    """Async NVIDIA NIM call."""
    import httpx
    api_key = config.NVIDIA_API_KEY
    if not api_key:
        return await _call_groq_async(prompt, temperature, max_tokens)

    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": config.NVIDIA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        for attempt in range(2):
            try:
                resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"].strip()
            except Exception:
                await asyncio.sleep(2)
        return await _call_groq_async(prompt, temperature, max_tokens)


async def _call_anthropic_async(prompt: str, temperature: float, max_tokens: int) -> str:
    """Async Anthropic call."""
    from anthropic import AsyncAnthropic
    client = AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
    response = await client.messages.create(
        model=config.CLASSIFICATION_MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def _call_anthropic(prompt: str, temperature: float, max_tokens: int) -> str:
    """Legacy sync wrapper."""
    return asyncio.run(_call_anthropic_async(prompt, temperature, max_tokens))


async def _call_ollama_async(prompt: str, temperature: float, max_tokens: int) -> str:
    """Async Ollama call."""
    import ollama
    # Note: ollama-python doesn't have an official async client yet, but we can wrap it
    # Or use httpx to call the API directly. Let's use httpx for true async.
    import httpx
    url = f"{config.OLLAMA_BASE_URL}/api/chat"
    payload = {
        "model": config.CLASSIFICATION_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()["message"]["content"].strip()


def _call_ollama(prompt: str, temperature: float, max_tokens: int) -> str:
    """Legacy sync wrapper."""
    return asyncio.run(_call_ollama_async(prompt, temperature, max_tokens))


# ============================================================
# Classification Prompts
# ============================================================

# Primary classification prompt (analyst perspective)
CLASSIFICATION_PROMPT = """You are an elite prediction market analyst. 

## Market Question
{question}

## Current Market Price
YES: {yes_price:.2f} (implied probability: {yes_price:.0%})

## News Headline to Evaluate
{headline}
Source: {source}

## Your Task
Determine if this news headline is DIRECTLY and SIGNIFICANTLY relevant to the market question.

A news item is ONLY relevant if it changes the fundamental probability of the specific event occurring. 
Tangential connections (e.g. "inflation" for "baseball") are NOT relevant.

Direction rules:
- "bullish": The news makes a YES resolution substantially MORE likely.
- "bearish": The news makes a YES resolution substantially LESS likely.
- "neutral": The news is irrelevant, minor, already priced in, or ambiguous.

Rate MATERIALITY (impact on probability):
- 0.0 to 0.3: Irrelevant or minor noise (ALWAYS use "neutral" direction)
- 0.4 to 0.7: Meaningful impact, changes the odds
- 0.8 to 1.0: Definitive, major development

Respond with ONLY valid JSON. 
CRICKET/IPL NOTE: A toss result, a major injury to a key player (e.g. Kohli, Dhoni, Bumrah), or a change in the playing XI is often a HIGH materiality (0.8+) event for match-winner markets.

IMPORTANT: Include a "probability" field — your BEST ESTIMATE of the actual chance the market resolves YES (0.0 to 1.0).
This should NOT be the same as materiality. Materiality = how important the news is. Probability = actual chance of YES.
Examples: If market is "Will India win?" and India just won the toss, probability might be 0.55 (slight edge). If India scored 250/3 chasing 200, probability might be 0.95.

{{
  "direction": "bullish" | "bearish" | "neutral",
  "materiality": <float 0.0 to 1.0>,
  "probability": <float 0.0 to 1.0 — your actual YES probability estimate>,
  "reasoning": "<1 concise sentence explaining the direct causal link or lack thereof>"
}}"""

# Devil's advocate prompt (skeptic perspective)
SKEPTIC_PROMPT = """You are a skeptical prediction market analyst. Your job is to prevent false positive trades.

## Market Question
{question}

## Current Price
YES: {yes_price:.2f}

## News Headline
{headline}

## Your Task
Challenge the relevance of this news:
1. Is the connection to the market question direct or purely speculative?
2. Is this news already fully reflected in the price of {yes_price:.2f}?
3. Does the headline actually provide new information, or is it just a recap?

If there is ANY doubt about relevance or impact, you MUST return "neutral".

Respond with ONLY valid JSON.
SKEPTIC TIP: If the news is just a "preview" or "speculation" about a toss/injury that hasn't happened yet, it is likely "neutral" or already priced in.

Include a "probability" field — your actual estimate of YES chance (NOT materiality).

{{
  "direction": "bullish" | "bearish" | "neutral",
  "materiality": <float 0.0 to 1.0>,
  "probability": <float 0.0 to 1.0 — your actual YES probability estimate>,
  "reasoning": "<1 sentence explaining why this might be noise or priced-in>"
}}"""

# Reflector prompt (unbiased 3rd pass)
REFLECTOR_PROMPT = """You are a final judge in a prediction market committee.
Analyze the market and news with extreme precision.

## Market Question
{question}

## Current Price
YES: {yes_price:.2f}

## News Headline
{headline}

## Your Duty
1. Does this headline actually answer the question or meaningfully change the odds?
2. Is the "materiality" truly high, or is this just noise?
3. Reject any speculative or tangential reasoning.

If you are not 80% certain of the direction, return "neutral".

Respond with ONLY valid JSON:
{{
  "direction": "bullish" | "bearish" | "neutral",
  "materiality": <float 0.0 to 1.0>,
  "probability": <float 0.0 to 1.0 — your actual YES probability estimate>,
  "reasoning": "<1 sentence final verdict>"
}}"""

PROMPTS = [CLASSIFICATION_PROMPT, SKEPTIC_PROMPT, REFLECTOR_PROMPT]


# ============================================================
# Classification Logic
# ============================================================

@dataclass
class Classification:
    direction: str  # "bullish", "bearish", or "neutral"
    materiality: float  # 0.0 - 1.0
    reasoning: str
    latency_ms: int = 0
    model: str = ""
    consensus_passes: int = 1
    consensus_agreed: bool = True
    probability: float | None = None  # model's actual probability estimate for YES outcome (0.0-1.0)


def _parse_json_response(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown blocks and common Gemini formatting issues."""
    import re

    # Strip markdown code fences
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            if part.startswith("json"):
                part = part[4:]
            part = part.strip()
            if part.startswith("{"):
                text = part
                break

    # Extract JSON object
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        text = text[start:end]

    # Fix common Gemini issues:
    # 1. Remove trailing commas before } or ]
    text = re.sub(r",\s*([}\]])", r"\1", text)
    # 2. Replace single-quoted strings with double-quoted
    text = re.sub(r"'([^']*)'", r'"\1"', text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Last resort: extract fields with regex
        direction_match = re.search(r'"direction"\s*:\s*"(bullish|bearish|neutral)"', text, re.IGNORECASE)
        materiality_match = re.search(r'"materiality"\s*:\s*([0-9.]+)', text)
        reasoning_match = re.search(r'"reasoning"\s*:\s*"([^"]*)"', text)

        probability_match = re.search(r'"probability"\s*:\s*([0-9.]+)', text)
        if direction_match:
            return {
                "direction": direction_match.group(1).lower(),
                "materiality": float(materiality_match.group(1)) if materiality_match else 0.0,
                "reasoning": reasoning_match.group(1) if reasoning_match else "parsed via regex",
                "probability": float(probability_match.group(1)) if probability_match else None,
            }
        raise  # re-raise if we can't extract anything useful


async def _single_classify_with_provider_async(prompt_template: str, headline: str, market: Market, source: str,
                                              temperature: float = 0.1, use_search: bool = False,
                                              force_provider: str | None = None) -> dict:
    """Run a single classification pass with a specific provider asynchronously."""
    prompt = prompt_template.format(
        question=market.question,
        yes_price=market.yes_price,
        headline=headline,
        source=source,
    )

    try:
        if force_provider == "gemini":
            text = await _call_gemini_async(prompt, temperature=temperature, max_tokens=200, use_search=use_search)
        elif force_provider == "groq":
            text = await _call_groq_async(prompt, temperature=temperature, max_tokens=200)
        elif force_provider == "nvidia":
            text = await _call_nvidia_async(prompt, temperature=temperature, max_tokens=200)
        elif force_provider == "mimo":
            text = await _call_mimo_async(prompt, temperature=temperature, max_tokens=200)
        elif config.LLM_PROVIDER in ("gemini", "mixed") or (not config.LLM_PROVIDER and config.GEMINI_API_KEY):
            text = await _call_gemini_async(prompt, temperature=temperature, max_tokens=200, use_search=use_search)
        else:
            text = await _call_llm_async(prompt, temperature=temperature, max_tokens=200)

        result = _parse_json_response(text)
    except Exception as e:
        log.warning(f"[classifier] Error in {force_provider or 'default'}: {e}")
        return {"direction": "neutral", "materiality": 0.0, "reasoning": f"Error: {e}", "provider": force_provider}

    direction = result.get("direction", "neutral")
    if direction not in ("bullish", "bearish", "neutral"):
        direction = "neutral"

    try:
        materiality = float(result.get("materiality", 0))
    except (TypeError, ValueError):
        materiality = 0.0
    materiality = max(0.0, min(1.0, materiality))

    # Extract probability if provided (model's actual YES probability estimate)
    prob = result.get("probability")
    if prob is not None:
        try:
            prob = max(0.0, min(1.0, float(prob)))
        except (TypeError, ValueError):
            prob = None

    return {
        "direction": direction,
        "materiality": materiality,
        "reasoning": result.get("reasoning", ""),
        "provider": force_provider or config.LLM_PROVIDER,
        "probability": prob,
    }


def _single_classify_with_provider(prompt_template: str, headline: str, market: Market, source: str,
                                     temperature: float = 0.1, use_search: bool = False,
                                     force_provider: str | None = None) -> dict:
    """Legacy sync wrapper."""
    return asyncio.run(_single_classify_with_provider_async(prompt_template, headline, market, source, temperature, use_search, force_provider))


# Legacy wrapper for backward compatibility
def _single_classify(prompt_template: str, headline: str, market: Market, source: str,
                     temperature: float = 0.1, use_search: bool = False) -> dict:
    return _single_classify_with_provider(prompt_template, headline, market, source, temperature, use_search)


async def classify_async(headline: str, market: Market, source: str = "unknown", use_search: bool = False) -> Classification:
    """
    Classify a news headline against a market question asynchronously.
    Runs consensus passes in parallel for maximum performance.
    """
    start = time.time()
    num_passes = config.CONSENSUS_PASSES if config.CONSENSUS_ENABLED else 1
    provider = config.LLM_PROVIDER
    is_mixed = provider == "mixed"

    if is_mixed:
        model_name = "mixed/parallel-consensus"
        # Priority order: MiMo → NVIDIA → Groq → Gemini (Gemini last due to 429s)
        providers = []
        if config.MIMO_API_KEY:
            providers.append("mimo")
        if config.NVIDIA_API_KEY:
            providers.append("nvidia")
        if config.GROQ_API_KEY:
            providers.append("groq")
        if not providers:
            providers = ["groq"]
        labels_map = {"mimo": "MiMo-Analyst", "nvidia": "NVIDIA-Skeptic", "groq": "Groq-Reflector"}
        pass_configs = [
            {"provider": providers[i % len(providers)], "prompt": PROMPTS[i % len(PROMPTS)], "temp": 0.1 + (0.05 * i), "label": labels_map.get(providers[i % len(providers)], f"Pass-{i+1}")}
            for i in range(min(3, len(providers)))
        ]
    else:
        model_name = provider
        pass_configs = [
            {"provider": provider, "prompt": PROMPTS[i % len(PROMPTS)], "temp": 0.1 + (0.05 * i), "label": f"Pass-{i+1}"}
            for i in range(num_passes)
        ]

    # Run all passes in PARALLEL
    tasks = [
        _single_classify_with_provider_async(
            cfg["prompt"], headline, market, source,
            temperature=cfg["temp"],
            use_search=(cfg["provider"] == "gemini"),
            force_provider=cfg["provider"]
        )
        for cfg in pass_configs
    ]
    
    results = await asyncio.gather(*tasks)
    
    # Attach labels for logging
    for i, res in enumerate(results):
        res["label"] = pass_configs[i]["label"]
        log.info(f"[consensus] {res['label']}: {res['direction']} mat={res['materiality']:.2f}")

    latency = int((time.time() - start) * 1000)

    # Check consensus
    directions = [r["direction"] for r in results]
    materialities = [r["materiality"] for r in results]
    non_neutral = [d for d in directions if d != "neutral"]

    if not non_neutral:
        return Classification(
            direction="neutral", materiality=0.0, reasoning="All passes neutral",
            latency_ms=latency, model=model_name, consensus_passes=len(results), consensus_agreed=True
        )

    try:
        from collections import Counter
        counts = Counter(directions)
        non_neutral_counts = {d: c for d, c in counts.items() if d != "neutral"}
        dominant_direction, count = max(non_neutral_counts.items(), key=lambda x: x[1])
        total_passes = len(results)
        agreement_ratio = count / total_passes
        agreed = agreement_ratio >= config.CONSENSUS_MIN_AGREEMENT

        # === MIXED MODE EXTRA GUARD: minimum materiality per-model ===
        if is_mixed and agreed and dominant_direction != "neutral":
            min_mat = min(r["materiality"] for r in results if r["direction"] == dominant_direction)
            if min_mat < 0.70:
                agreed = False
                dominant_direction = "neutral"
                labels = " | ".join([f"[{r.get('label','?')}] {r['direction']} mat={r['materiality']:.2f}" for r in results])
                combined_reasoning = f"MIXED_MATERIALITY_FAIL (weakest={min_mat:.2f} < 0.70) — {labels}"
                return Classification(
                    direction="neutral",
                    materiality=0.0,
                    reasoning=combined_reasoning,
                    latency_ms=latency,
                    model=model_name,
                    consensus_passes=total_passes,
                    consensus_agreed=False,
                )

        # STRICT_CONSENSUS: override if not all passes are non-neutral
        if config.STRICT_CONSENSUS and len(non_neutral) < total_passes:
            agreed = False
            dominant_direction = "neutral"
            combined_reasoning = f"STRICT_CONSENSUS FAIL ({len(non_neutral)}/{total_passes} active) — no trade. " + " | ".join([f"[{r.get('label', f'Pass {i+1}')}] {r['direction']}" for i, r in enumerate(results)])
        elif not agreed:
            dominant_direction = "neutral"
            combined_reasoning = f"AGREEMENT_FAIL ({count}/{total_passes} for {dominant_direction}) — no trade. " + " | ".join([f"[{r.get('label', f'Pass {i+1}')}] {r['direction']}" for i, r in enumerate(results)])
        else:
            combined_reasoning = " | ".join([f"[{r.get('label', f'Pass {i+1}')}] {r['reasoning']}" for i, r in enumerate(results)])

        # Use avg materiality of the dominant direction passes
        dominant_mats = [m for m, d in zip(materialities, directions) if d == dominant_direction]
        avg_materiality = (sum(dominant_mats) / len(dominant_mats)) if (agreed and dominant_mats) else 0.0

        # Aggregate probability from dominant direction passes
        dominant_probs = [r.get("probability") for r in results
                          if r["direction"] == dominant_direction and r.get("probability") is not None]
        avg_probability = (sum(dominant_probs) / len(dominant_probs)) if dominant_probs else None
        if avg_probability is not None:
            avg_probability = round(avg_probability, 3)
            log.info(f"[consensus] Aggregated probability={avg_probability:.3f} from {len(dominant_probs)} passes")

        return Classification(
            direction=dominant_direction,
            materiality=avg_materiality,
            reasoning=combined_reasoning,
            latency_ms=latency,
            model=model_name,
            consensus_passes=total_passes,
            consensus_agreed=agreed,
            probability=avg_probability,
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


def _build_analyst_prompt(market: Market, search_results: list[str]) -> str:
    """Build the analyst prompt with optional web search results."""
    context = ""
    if search_results:
        context = "\n\nLive web search results:\n" + "\n".join(f"  - {r[:200]}" for r in search_results[:5])

    return (
        f"You are a prediction market analyst. Today is April 2026.\n\n"
        f"Market: {market.question}\n"
        f"Current YES price: {market.yes_price:.2f} ({market.yes_price:.0%} implied probability)\n"
        f"{context}\n\n"
        f"Analyze this market using the search results above (if any) plus your knowledge.\n\n"
        f"Direction rules:\n"
        f"  bullish = YES is likely to resolve YES (you think outcome > {market.yes_price:.0%})\n"
        f"  bearish = NO is likely (you think outcome < {market.yes_price:.0%})\n"
        f"  neutral = genuinely uncertain, skip\n\n"
        f"Materiality:\n"
        f"  0.80-0.95 = very confident (90%+)\n"
        f"  0.55-0.79 = confident (70-90%)\n"
        f"  0.35-0.54 = moderate edge (60-70%)\n"
        f"  0.0       = uncertain, return neutral\n\n"
        f"Respond ONLY with valid JSON:\n"
        f'{{"direction":"bullish"|"bearish"|"neutral","materiality":0.0-1.0,"reasoning":"1 sentence fact"}}'
    )


def research_market(market: Market, news_context: list[str] | None = None) -> Classification:
    """
    MiroFish research: MiMo/NVIDIA primary → Gemini search fallback.
    Strategy:
      1. Live web search (DDG → Apify → Gemini grounding)
      2. MiMo or NVIDIA with web context (primary — fast, no 429s)
      3. Gemini with search grounding as fallback (when MiMo/NVIDIA fail)

    news_context: optional pre-matched headlines from scraper (used as extra context)
    """
    start = time.time()

    a_dir, a_mat, a_reason = "neutral", 0.0, ""
    model_used = "none"

    # ── Step 1: Live web search (DDG → Apify → Gemini grounding) ──────────
    web_results: list[str] = []
    try:
        from apify_search import search_market as _search_market
        web_results = _search_market(market.question, market.yes_price)
    except Exception as e:
        log.debug(f"[research] web search failed: {e}")

    # If DDG + Apify both failed, use Gemini's built-in search grounding
    if not web_results:
        try:
            from apify_search import _gemini_grounding_search
            web_results = _gemini_grounding_search(market.question)
            if web_results:
                log.info(f"[research] Gemini grounding returned {len(web_results)} results")
        except Exception as e:
            log.debug(f"[research] Gemini grounding fallback failed: {e}")

    # Prepend any pre-matched news headlines as extra context
    if news_context:
        extra = [f"[news] {h}" for h in news_context[:3]]
        web_results = extra + web_results

    # ── Step 2: MiMo/NVIDIA primary (fast, no rate limits) ────────────────
    primary_prompt = _build_analyst_prompt(market, web_results)
    for provider_name, call_fn in [
        ("MiMo", lambda p: _call_mimo_async(p, 0.1, 300)),
        ("NVIDIA", lambda p: _call_nvidia_async(p, 0.1, 300)),
    ]:
        if a_dir != "neutral" and a_mat >= 0.40:
            break
        try:
            p_text = asyncio.run(call_fn(primary_prompt))
            p_res  = _parse_json_response(p_text)
            p_dir  = p_res.get("direction", "neutral")
            if p_dir not in ("bullish", "bearish", "neutral"):
                p_dir = "neutral"
            p_mat    = max(0.0, min(1.0, float(p_res.get("materiality", 0))))
            p_reason = p_res.get("reasoning", "")
            src_tag  = f"DDG+{provider_name}" if web_results else provider_name
            conf_mul = 0.95 if web_results else 0.80

            if p_dir != "neutral" and p_mat >= 0.28:
                if a_dir == "neutral" or p_mat * conf_mul > a_mat:
                    a_dir    = p_dir
                    a_mat    = p_mat * conf_mul
                    a_reason = f"[{src_tag}] {p_reason}"
                    model_used = src_tag
                    log.info(f"[research] {src_tag}: {p_dir} {p_mat:.2f} '{market.question[:35]}'")
        except Exception as e:
            log.debug(f"[research] {provider_name} failed: {e}")

    # ── Step 3: Groq last resort ──────────────────────────────────────────
    if a_dir == "neutral" or a_mat < 0.40:
        try:
            groq_prompt = _build_analyst_prompt(market, web_results)
            g_text   = _call_groq(groq_prompt, temperature=0.15, max_tokens=300)
            g_res    = _parse_json_response(g_text)
            g_dir    = g_res.get("direction", "neutral")
            if g_dir not in ("bullish", "bearish", "neutral"):
                g_dir = "neutral"
            g_mat    = max(0.0, min(1.0, float(g_res.get("materiality", 0))))
            g_reason = g_res.get("reasoning", "")
            src_tag  = "DDG+Groq" if web_results else "Groq"
            conf_mul = 0.92 if web_results else 0.80

            if g_dir != "neutral" and g_mat >= 0.28:
                if a_dir == "neutral" or g_mat * conf_mul > a_mat:
                    a_dir    = g_dir
                    a_mat    = g_mat * conf_mul
                    a_reason = f"[{src_tag}] {g_reason}"
                    model_used = src_tag
                    log.info(f"[research] {src_tag}: {g_dir} {g_mat:.2f} '{market.question[:35]}'")
        except Exception as e:
            log.debug(f"[research] Groq failed: {e}")

    latency = int((time.time() - start) * 1000)
    return Classification(
        direction=a_dir,
        materiality=round(a_mat, 3),
        reasoning=f"[MiroFish/{model_used}] {a_reason}",
        latency_ms=latency,
        model=model_used,
        consensus_passes=1,
        consensus_agreed=True,
    )


def classify(headline: str, market: Market, source: str = "unknown", use_search: bool = False) -> Classification:
    """Sync wrapper around classify_async."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
        return loop.run_until_complete(classify_async(headline, market, source, use_search))
    except:
        return asyncio.run(classify_async(headline, market, source, use_search))


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
