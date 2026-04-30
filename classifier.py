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
    elif provider == "nvidia":
        return _call_nvidia(prompt, temperature, max_tokens)
    elif provider == "ollama":
        return _call_ollama(prompt, temperature, max_tokens)
    elif provider == "anthropic":
        return _call_anthropic(prompt, temperature, max_tokens)
    elif provider == "mixed":
        # Mixed mode: default to Gemini for single calls
        return _call_gemini(prompt, temperature, max_tokens)
    else:
        # Auto-detect
        if config.GEMINI_API_KEY:
            return _call_gemini(prompt, temperature, max_tokens)
        elif config.GROQ_API_KEY:
            return _call_groq(prompt, temperature, max_tokens)
        elif config.NVIDIA_API_KEY:
            return _call_nvidia(prompt, temperature, max_tokens)
        elif config.OLLAMA_BASE_URL:
            return _call_ollama(prompt, temperature, max_tokens)
        elif config.ANTHROPIC_API_KEY:
            return _call_anthropic(prompt, temperature, max_tokens)
        else:
            raise RuntimeError("No LLM configured — set GEMINI_API_KEY, GROQ_API_KEY, NVIDIA_API_KEY, ANTHROPIC_API_KEY, or OLLAMA_BASE_URL")


_gemini_last_call    = 0.0
_GEMINI_MIN_INTERVAL = 6.0   # 6s spacing ≈ 10 RPM — safer for free tier (MiroFish doubles calls)


def _call_gemini(prompt: str, temperature: float, max_tokens: int, use_search: bool = False) -> str:
    """
    Call Gemini with 4s spacing + jitter.
    429 handling per Google docs (pay-as-you-go):
      - Attempt 1: wait with truncated exponential backoff (2s)
      - Attempt 2: wait 4s
      - Attempt 3+: instant Groq fallback — never stall the scan
    503 (UNAVAILABLE): 1 retry after 5s, then Groq fallback.
    """
    import time as _time
    import random as _random
    global _gemini_last_call

    from google import genai
    client = genai.Client(api_key=config.GEMINI_API_KEY)

    jitter  = _random.uniform(0.1, 0.8)
    elapsed = _time.time() - _gemini_last_call
    wait    = max(0.0, _GEMINI_MIN_INTERVAL + jitter - elapsed)
    if wait > 0:
        _time.sleep(wait)

    _429_backoffs = [2, 5]   # short backoff — fall to Groq fast (2s, 5s, then Groq)

    for attempt in range(3):
        try:
            _gemini_last_call = _time.time()
            gen_config = {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            }
            # Search grounding: let Gemini look up live info about the market
            # Only used for fast-closing markets where RSS has no coverage
            call_kwargs = {"model": config.GEMINI_MODEL, "contents": prompt, "config": gen_config}
            if use_search and config.USE_SEARCH_GROUNDING:
                from google.genai import types as _gtypes
                call_kwargs["config"] = {**gen_config, "tools": [_gtypes.Tool(google_search=_gtypes.GoogleSearch())]}
            response = client.models.generate_content(**call_kwargs)
            return response.text.strip()
        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                if attempt < len(_429_backoffs):
                    wait_s = _429_backoffs[attempt] + _random.uniform(0, 1)
                    log.warning(f"[gemini] 429 — backoff {wait_s:.1f}s (attempt {attempt+1}/3)")
                    _time.sleep(wait_s)
                else:
                    log.warning("[gemini] 429 persists → falling back to Groq")
                    return _call_groq(prompt, temperature, max_tokens)
            elif "503" in err or "UNAVAILABLE" in err:
                if attempt == 0:
                    log.warning("[gemini] 503 — retrying once after 5s")
                    _time.sleep(5)
                else:
                    log.warning("[gemini] 503 retry failed → falling back to Groq")
                    return _call_groq(prompt, temperature, max_tokens)
            else:
                raise

    # All retries exhausted — Groq fallback
    log.warning("[gemini] All retries exhausted → Groq fallback")
    return _call_groq(prompt, temperature, max_tokens)


def _call_groq(prompt: str, temperature: float, max_tokens: int) -> str:
    """Call Groq API (fast inference) with 429 retry logic."""
    import time as _time
    from groq import Groq
    client = Groq(api_key=config.GROQ_API_KEY)
    model = config.CLASSIFICATION_MODEL
    # Map non-groq model names to a safe default
    if not model or "claude" in model or "haiku" in model or "sonnet" in model or "gemma" in model:
        model = "llama-3.3-70b-versatile"  # best free Groq model — much better than 8b

    max_retries = 4
    backoff = 15

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            err = str(e)
            if "429" in err or "rate_limit" in err.lower() or "resource_exhausted" in err.lower():
                wait = backoff * (2 ** attempt)
                log.warning(f"[groq] 429 rate limit — waiting {wait}s before retry {attempt+1}/{max_retries}")
                _time.sleep(wait)
            else:
                raise

    raise RuntimeError(f"Groq API failed after {max_retries} retries")


def _call_nvidia(prompt: str, temperature: float, max_tokens: int) -> str:
    """Call NVIDIA NIM API (Nemotron-70B). OpenAI-compatible endpoint."""
    import time as _time
    import httpx

    api_key = config.NVIDIA_API_KEY
    if not api_key:
        log.warning("[nvidia] No NVIDIA_API_KEY — falling back to Groq")
        return _call_groq(prompt, temperature, max_tokens)

    model = config.NVIDIA_MODEL
    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    max_retries = 3
    for attempt in range(max_retries):
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            err = str(e)
            if "429" in err or "rate" in err.lower():
                wait = 5 * (attempt + 1)
                log.warning(f"[nvidia] 429 — waiting {wait}s (attempt {attempt+1}/{max_retries})")
                _time.sleep(wait)
            elif attempt < max_retries - 1:
                log.warning(f"[nvidia] Error: {e} — retrying")
                _time.sleep(2)
            else:
                log.warning(f"[nvidia] All retries failed — falling back to Groq")
                return _call_groq(prompt, temperature, max_tokens)

    log.warning("[nvidia] Exhausted retries — Groq fallback")
    return _call_groq(prompt, temperature, max_tokens)


def _call_ollama(prompt: str, temperature: float, max_tokens: int) -> str:
    """Call Ollama local model."""
    import ollama
    model = config.CLASSIFICATION_MODEL

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

{{
  "direction": "bullish" | "bearish" | "neutral",
  "materiality": <float 0.0 to 1.0>,
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

{{
  "direction": "bullish" | "bearish" | "neutral",
  "materiality": <float 0.0 to 1.0>,
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
  "reasoning": "<1 sentence final verdict>"
}}"""

PROMPTS = [CLASSIFICATION_PROMPT, SKEPTIC_PROMPT, REFLECTOR_PROMPT]


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

        if direction_match:
            return {
                "direction": direction_match.group(1).lower(),
                "materiality": float(materiality_match.group(1)) if materiality_match else 0.0,
                "reasoning": reasoning_match.group(1) if reasoning_match else "parsed via regex",
            }
        raise  # re-raise if we can't extract anything useful


def _single_classify_with_provider(prompt_template: str, headline: str, market: Market, source: str,
                                     temperature: float = 0.1, use_search: bool = False,
                                     force_provider: str | None = None) -> dict:
    """Run a single classification pass with a specific provider. Returns raw result dict."""
    prompt = prompt_template.format(
        question=market.question,
        yes_price=market.yes_price,
        headline=headline,
        source=source,
    )

    # Route to the specified provider
    if force_provider == "gemini":
        text = _call_gemini(prompt, temperature=temperature, max_tokens=200, use_search=use_search)
    elif force_provider == "groq":
        text = _call_groq(prompt, temperature=temperature, max_tokens=200)
    elif force_provider == "nvidia":
        text = _call_nvidia(prompt, temperature=temperature, max_tokens=200)
    elif config.LLM_PROVIDER in ("gemini", "mixed") or (not config.LLM_PROVIDER and config.GEMINI_API_KEY):
        text = _call_gemini(prompt, temperature=temperature, max_tokens=200, use_search=use_search)
    else:
        text = _call_llm(prompt, temperature=temperature, max_tokens=200)

    result = _parse_json_response(text)

    direction = result.get("direction", "neutral")
    if direction not in ("bullish", "bearish", "neutral"):
        direction = "neutral"

    try:
        materiality = float(result.get("materiality", 0))
    except (TypeError, ValueError):
        materiality = 0.0
    materiality = max(0.0, min(1.0, materiality))

    return {
        "direction": direction,
        "materiality": materiality,
        "reasoning": result.get("reasoning", ""),
        "provider": force_provider or config.LLM_PROVIDER,
    }


# Legacy wrapper for backward compatibility
def _single_classify(prompt_template: str, headline: str, market: Market, source: str,
                     temperature: float = 0.1, use_search: bool = False) -> dict:
    return _single_classify_with_provider(prompt_template, headline, market, source, temperature, use_search)


def classify(headline: str, market: Market, source: str = "unknown", use_search: bool = False) -> Classification:
    """
    Classify a news headline against a market question.

    MODE: "mixed" (default) — Heterogeneous AI Consensus
      Pass 1: Gemini 2.0 Flash (Analyst) — fast, web-grounded
      Pass 2: Groq Llama-3.3-70B (Skeptic) — independent model family
      Pass 3: NVIDIA Nemotron-70B (Reflector) — third independent model

    ALL THREE must agree on direction AND each must score materiality >= 0.70
    for a trade to execute. This eliminates model-specific hallucinations.
    """
    start = time.time()
    num_passes = config.CONSENSUS_PASSES if config.CONSENSUS_ENABLED else 1
    provider = config.LLM_PROVIDER

    # In mixed mode: use 3 different AI providers
    is_mixed = provider == "mixed"

    if is_mixed:
        model_name = "mixed/gemini+groq+nvidia"
        # Each pass uses a DIFFERENT provider + DIFFERENT prompt
        pass_configs = [
            {"provider": "gemini",  "prompt": PROMPTS[0], "temp": 0.1, "label": "Gemini-Analyst"},
            {"provider": "groq",    "prompt": PROMPTS[1], "temp": 0.15, "label": "Groq-Skeptic"},
            {"provider": "nvidia",  "prompt": PROMPTS[2], "temp": 0.1, "label": "Nvidia-Reflector"},
        ]
    else:
        if provider == "gemini":
            model_name = "gemini/" + config.GEMINI_MODEL
        elif provider == "groq":
            model_name = "groq/" + config.CLASSIFICATION_MODEL
        elif provider == "nvidia":
            model_name = "nvidia/" + config.NVIDIA_MODEL
        elif provider == "ollama":
            model_name = "ollama/" + config.CLASSIFICATION_MODEL
        else:
            model_name = config.CLASSIFICATION_MODEL
        pass_configs = None

    try:
        results = []

        if is_mixed and pass_configs:
            # === HETEROGENEOUS CONSENSUS: 3 different AI models ===
            for cfg in pass_configs:
                try:
                    result = _single_classify_with_provider(
                        cfg["prompt"], headline, market, source,
                        temperature=cfg["temp"],
                        use_search=(cfg["provider"] == "gemini"),
                        force_provider=cfg["provider"],
                    )
                    result["label"] = cfg["label"]
                    results.append(result)
                    log.info(f"[consensus] {cfg['label']}: {result['direction']} mat={result['materiality']:.2f}")
                except Exception as e:
                    log.warning(f"[consensus] {cfg['label']} failed: {e} — marking neutral")
                    results.append({
                        "direction": "neutral",
                        "materiality": 0.0,
                        "reasoning": f"{cfg['label']} error: {e}",
                        "provider": cfg["provider"],
                        "label": cfg["label"],
                    })
        else:
            # === SINGLE-PROVIDER MODE (legacy) ===
            for i in range(num_passes):
                prompt = PROMPTS[i % len(PROMPTS)]
                temp = 0.1 if i == 0 else 0.2
                result = _single_classify_with_provider(prompt, headline, market, source, temperature=temp, use_search=use_search)
                result["label"] = f"Pass-{i+1}"
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
                consensus_passes=len(results),
                consensus_agreed=True,
            )

        # Count occurrences of each direction
        from collections import Counter
        counts = Counter(directions)
        non_neutral_counts = {d: c for d, c in counts.items() if d != "neutral"}

        if not non_neutral_counts:
            dominant_direction = "neutral"
            count = 0
        else:
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

        return Classification(
            direction=dominant_direction,
            materiality=avg_materiality,
            reasoning=combined_reasoning,
            latency_ms=latency,
            model=model_name,
            consensus_passes=total_passes,
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
    MiroFish research: Gemini search → Apify+Groq fallback.
    Strategy:
      1. Try Gemini with live web search (fast, accurate)
      2. If Gemini 429/fails → Apify Google Search + Groq llama-3.3-70b
      3. Return best signal found

    news_context: optional pre-matched headlines from scraper (used as extra context)
    """
    start = time.time()

    a_dir, a_mat, a_reason = "neutral", 0.0, ""
    model_used = "groq"

    # ── Step 1: Live web search (DDG → Apify) ─────────────────────────────
    web_results: list[str] = []
    try:
        from apify_search import search_market as _search_market
        web_results = _search_market(market.question, market.yes_price)
    except Exception as e:
        log.debug(f"[research] web search failed: {e}")

    # Prepend any pre-matched news headlines as extra context
    if news_context:
        extra = [f"[news] {h}" for h in news_context[:3]]
        web_results = extra + web_results

    # ── Step 2: Try Gemini with built-in search grounding ─────────────────
    # Gemini is best when not rate-limited because it searches with context
    try:
        gemini_prompt = _build_analyst_prompt(market, web_results)
        a_text = _call_gemini(gemini_prompt, temperature=0.1, max_tokens=300, use_search=True)
        a_res  = _parse_json_response(a_text)
        g_dir  = a_res.get("direction", "neutral")
        if g_dir not in ("bullish", "bearish", "neutral"):
            g_dir = "neutral"
        g_mat    = max(0.0, min(1.0, float(a_res.get("materiality", 0))))
        g_reason = a_res.get("reasoning", "")
        if g_dir != "neutral" and g_mat >= 0.30:
            a_dir, a_mat, a_reason = g_dir, g_mat, g_reason
            model_used = "gemini+search"
            log.info(f"[research] Gemini: {g_dir} {g_mat:.2f} '{market.question[:35]}'")
    except Exception as e:
        log.debug(f"[research] Gemini unavailable: {e}")

    # ── Step 3: Groq with DDG context (always runs as primary or supplement) ─
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
