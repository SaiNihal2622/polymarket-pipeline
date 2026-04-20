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
CLASSIFICATION_PROMPT = """You are a prediction market analyst with access to live web search.

## Market Question
{question}

## Current Market Price
YES: {yes_price:.2f} (implied probability: {yes_price:.0%})

## News Headline to Evaluate
{headline}
Source: {source}

## Your Task
Use your search access to find the CURRENT price, latest developments, and context for this market.
Then determine: does this news make the market question MORE likely to resolve YES, MORE likely to resolve NO, or is it NOT RELEVANT?

Rate MATERIALITY (how much should this move the price?):
- 0.0 = completely irrelevant
- 0.3 = somewhat relevant, minor impact
- 0.6 = clearly relevant, meaningful impact
- 1.0 = definitive evidence, major impact

Consider: Is this news already priced in? Is the current market price accurate given what you now know?

Respond with ONLY valid JSON (no markdown, no explanation outside the JSON):
{{
  "direction": "bullish" | "bearish" | "neutral",
  "materiality": <float 0.0 to 1.0>,
  "reasoning": "<1 sentence max>"
}}"""

# Devil's advocate prompt (skeptic perspective — used for consensus pass 2)
SKEPTIC_PROMPT = """You are a SKEPTICAL prediction market analyst with access to live web search.

## Market Question
{question}

## Current Market Price
YES: {yes_price:.2f} (implied probability: {yes_price:.0%})

## News Headline Under Review
{headline}
Source: {source}

## Your Task
Search for the current state of this market. Then challenge the initial reaction to this headline:
- Is this news ALREADY priced in by the market?
- Is the current YES price of {yes_price:.0%} already reflecting this?
- Does this news DIRECTLY affect the outcome, or is it tangential noise?
- Could the opposite scenario still easily happen?

Only rate above 0.4 materiality if the news genuinely changes the odds significantly from the current price.

Respond with ONLY valid JSON (no markdown, no explanation outside the JSON):
{{
  "direction": "bullish" | "bearish" | "neutral",
  "materiality": <float 0.0 to 1.0>,
  "reasoning": "<1 sentence max>"
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


def _single_classify(prompt_template: str, headline: str, market: Market, source: str, temperature: float = 0.1, use_search: bool = False) -> dict:
    """Run a single classification pass. Returns raw result dict."""
    prompt = prompt_template.format(
        question=market.question,
        yes_price=market.yes_price,
        headline=headline,
        source=source,
    )

    # For Gemini provider, pass use_search flag; other providers ignore it
    if config.LLM_PROVIDER == "gemini" or (not config.LLM_PROVIDER and config.GEMINI_API_KEY):
        text = _call_gemini(prompt, temperature=temperature, max_tokens=200, use_search=use_search)
    else:
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


def classify(headline: str, market: Market, source: str = "unknown", use_search: bool = False) -> Classification:
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
            result = _single_classify(prompt, headline, market, source, temperature=temp, use_search=use_search)
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
        # Use avg materiality of non-neutral passes only — skeptic returning neutral
        # shouldn't zero out a strong analyst signal, but does reduce confidence.
        non_neutral_mats = [m for m, d in zip(materialities, directions) if d != "neutral"]
        avg_materiality = (sum(non_neutral_mats) / len(non_neutral_mats)) if (agreed and non_neutral_mats) else 0.0

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


def research_market(market: Market) -> Classification:
    """
    MiroFish 2-pass research with Gemini live web search.
      Pass 1 (Analyst): searches web, calls direction + materiality
      Pass 2 (Skeptic): challenges — is edge already priced in?
    Both must agree on direction OR skeptic says neutral for signal to pass.
    """
    start = time.time()
    model_name = "gemini/" + config.GEMINI_MODEL + "+search+miro"

    analyst_prompt = (
        f"You are a prediction market FACT-CHECKER with live web search.\n\n"
        f"Market Question: {market.question}\n"
        f"Current YES price: {market.yes_price:.2f} ({market.yes_price:.0%} implied probability)\n\n"
        f"Search the web RIGHT NOW. STRICT RULES:\n\n"
        f"RULE 1 — ONLY trade if the outcome is ALREADY DETERMINED:\n"
        f"  - Event has ALREADY HAPPENED → you know the result for certain\n"
        f"  - Price/metric is RIGHT NOW at a level that makes YES/NO mathematically certain\n"
        f"    (e.g. BTC is at $87,000 and market asks 'will BTC be above $70,000?' → YES certain)\n"
        f"  - Official result has been announced (election called, law signed, etc.)\n\n"
        f"RULE 2 — Return neutral (0.0) for EVERYTHING ELSE:\n"
        f"  - Any future event not yet determined → neutral 0.0\n"
        f"  - Any sports match not yet played → neutral 0.0\n"
        f"  - If you are not 80%+ certain → neutral 0.0\n\n"
        f"RULE 3 — Crypto/price markets: Look up the CURRENT live price.\n"
        f"  If current price is already above/below the threshold with >5% margin → give direction.\n"
        f"  e.g. ETH is $1,580, market asks 'above $2,000?' → bearish (price is 21% below threshold)\n\n"
        f"RULE 4 — Materiality scale:\n"
        f"  0.80-0.95 = outcome is very certain (strong confirmed data)\n"
        f"  0.55-0.79 = outcome is likely based on current data\n"
        f"  0.35-0.54 = moderate signal\n"
        f"  0.0       = uncertain — DO NOT GUESS\n\n"
        f"Respond ONLY with valid JSON:\n"
        f'{{"direction": "bullish"|"bearish"|"neutral", '
        f'"materiality": <0.0-1.0>, "reasoning": "<1 sentence with the SPECIFIC FACT you found and its source>"}}'
    )

    try:
        # Pass 1: Analyst
        a_text = _call_gemini(analyst_prompt, temperature=0.1, max_tokens=250, use_search=True)
        a_res  = _parse_json_response(a_text)
        a_dir  = a_res.get("direction", "neutral")
        if a_dir not in ("bullish", "bearish", "neutral"):
            a_dir = "neutral"
        a_mat  = max(0.0, min(1.0, float(a_res.get("materiality", 0))))
        a_reason = a_res.get("reasoning", "")

        # If analyst is neutral or weak, don't bother with skeptic
        if a_dir == "neutral" or a_mat < 0.45:
            latency = int((time.time() - start) * 1000)
            return Classification(
                direction=a_dir, materiality=a_mat,
                reasoning="[Research] " + a_reason,
                latency_ms=latency, model=model_name,
                consensus_passes=1, consensus_agreed=(a_dir == "neutral"),
            )

        # Pass 2: Skeptic — challenges the analyst's call
        skeptic_prompt = (
            f"You are a SKEPTICAL prediction market analyst. Another analyst says:\n"
            f'  Direction: {a_dir}, Materiality: {a_mat:.2f}\n'
            f'  Reasoning: "{a_reason}"\n\n'
            f"Market: {market.question}\n"
            f"Current YES price: {market.yes_price:.2f} ({market.yes_price:.0%})\n\n"
            f"Search the web and CHALLENGE the analyst:\n"
            f"- Is this already priced in at {market.yes_price:.0%}?\n"
            f"- Could the opposite outcome easily happen?\n"
            f"- Is there conflicting recent evidence?\n"
            f"- Only rate > 0.4 if you genuinely agree with a strong directional edge.\n\n"
            f"Respond ONLY with valid JSON:\n"
            f'{{"direction": "bullish"|"bearish"|"neutral", '
            f'"materiality": <0.0-1.0>, "reasoning": "<1 sentence>"}}'
        )
        s_text = _call_gemini(skeptic_prompt, temperature=0.2, max_tokens=250, use_search=True)
        s_res  = _parse_json_response(s_text)
        s_dir  = s_res.get("direction", "neutral")
        if s_dir not in ("bullish", "bearish", "neutral"):
            s_dir = "neutral"
        s_mat  = max(0.0, min(1.0, float(s_res.get("materiality", 0))))
        s_reason = s_res.get("reasoning", "")

        # Consensus logic
        agreed = (a_dir == s_dir) or (s_dir == "neutral" and s_mat < 0.4)
        if a_dir == s_dir:
            # Both agree → use min materiality (conservative)
            final_dir = a_dir
            final_mat = min(a_mat, s_mat) if s_mat > 0 else a_mat * 0.8
            final_reason = f"[MiroFish ✓] {a_reason} | Skeptic: {s_reason}"
        elif s_dir == "neutral" and s_mat < 0.4:
            # Skeptic weakly neutral → keep analyst but haircut materiality
            final_dir = a_dir
            final_mat = a_mat * 0.7
            final_reason = f"[MiroFish ~] {a_reason} | Skeptic neutral: {s_reason}"
        else:
            # Skeptic actively disagrees → DAMPEN (not kill) analyst signal
            # Only kill if skeptic is very confident in the opposite direction
            if s_mat >= 0.45:
                # Skeptic is confident in opposite → KILL signal
                final_dir = "neutral"
                final_mat = 0.0
                final_reason = f"[MiroFish ✗ KILLED] Analyst:{a_dir} vs Skeptic:{s_dir}({s_mat:.2f})"
            else:
                # Weak skeptic disagreement → keep analyst but cut materiality by 60%
                final_dir = a_dir
                final_mat = a_mat * 0.4
                final_reason = f"[MiroFish ? weak-split] {a_reason} | Skeptic weakly: {s_reason}"

        latency = int((time.time() - start) * 1000)
        return Classification(
            direction=final_dir,
            materiality=final_mat,
            reasoning=final_reason,
            latency_ms=latency,
            model=model_name,
            consensus_passes=2,
            consensus_agreed=agreed,
        )
    except Exception as e:
        latency = int((time.time() - start) * 1000)
        log.warning(f"[research] Error for '{market.question[:40]}': {e}")
        return Classification(
            direction="neutral",
            materiality=0.0,
            reasoning=f"Research error: {type(e).__name__}",
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
