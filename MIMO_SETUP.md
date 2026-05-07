# MiMo API Setup for Polymarket Pipeline

## API Configuration
- **Base URL**: `https://token-plan-sgp.xiaomimimo.com/v1`
- **API Key**: `tp-svf9i440f463x5kzorbkymjdt0s7fm60ew34belv2tng58i7`
- **Model**: `mimo-v2-omni` (multimodal — supports images + text)

## Current .env Configuration
The MiMo API key is already configured in the pipeline's `.env` file:
```
MIMO_API_KEY=tp-svf9i440f463x5kzorbkymjdt0s7fm60ew34belv2tng58i7
MIMO_MODEL=mimo-v2-omni
MIMO_BASE_URL=https://token-plan-sgp.xiaomimimo.com/v1
```

## Usage in Pipeline
The MiMo model is used in the consensus engine for market analysis:
- **Pass 1**: Analyst classification (bullish/bearish/neutral)
- **Pass 2**: Skeptic / devil's advocate challenge
- **Consensus**: Both passes must agree

## Available Models (via `token-plan-sgp.xiaomimimo.com`)
| Model | Description |
|---|---|
| `mimo-v2-omni` | **Multimodal** — supports images + text (recommended for Cline) |
| `mimo-v2-pro` | Text-only reasoning model |
| `mimo-v2.5` | Text-only reasoning model |
| `mimo-v2.5-pro` | Text-only reasoning model (best quality) |
| `mimo-v2-tts` / `mimo-v2.5-tts` | Text-to-speech models |

## VS Code: Cline Configuration
To use MiMo in VS Code: Cline extension:
1. Open Cline Settings (Ctrl+Shift+P → "Cline: Open Settings")
2. Go to "API Configuration"
3. Select "OpenAI Compatible" as provider
4. Set Base URL: `https://token-plan-sgp.xiaomimimo.com/v1`
5. Set API Key: `tp-svf9i440f463x5kzorbkymjdt0s7fm60ew34belv2tng58i7`
6. Set Model: `mimo-v2-omni` (supports images) or `mimo-v2.5-pro` (text-only, higher quality)

## NVIDIA API (Best for Coding)
- **Base URL**: `https://integrate.api.nvidia.com/v1`
- **API Key**: `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`
- **Best models available (free tier):**

| Model | Best For | Images |
|---|---|---|
| `qwen/qwen3-coder-480b-a35b-instruct` | **Coding** (480B MoE, top coder) | ❌ |
| `deepseek-ai/deepseek-v4-pro` | Reasoning + coding | ❌ |
| `mistralai/mistral-large-3-675b-instruct-2512` | General reasoning (675B) | ❌ |
| `meta/llama-3.2-90b-vision-instruct` | Vision + text | ✅ |
| `microsoft/phi-4-multimodal-instruct` | Multimodal (small, fast) | ✅ |

## Cline Model Switching
Two config files are provided for Cline:

| Config File | Model | Use Case |
|---|---|---|
| `cline-coding-config.json` | Qwen3 Coder 480B (NVIDIA) | Default — best for coding |
| `cline-mimo-config.json` | MiMo v2 Omni (Xiaomi) | When you need image/screenshot support |

**To switch:** Run in terminal:
```bat
switch_cline_model.bat coding    # Qwen3 Coder 480B (best for code)
switch_cline_model.bat image     # MiMo v2 Omni (supports screenshots)
```
Then restart Cline to apply.

## Railway Deployment
Since Railway CLI token is expired, deploy via dashboard:
1. Go to https://railway.com/dashboard
2. Select polymarket-pipeline project
3. Click "Deploy" to redeploy with latest code
