# MiMo API Setup for Polymarket Pipeline

## API Configuration
- **Base URL**: `https://api.xiaomimimo.com/v1`
- **API Key**: `tp-svf9i440f463x5kzorbkymjdt0s7fm60ew34belv2tng58i7`
- **Model**: `mimo-v2.5-pro`

## Current .env Configuration
The MiMo API key is already configured in the pipeline's `.env` file:
```
MIMO_API_KEY=tp-svf9i440f463x5kzorbkymjdt0s7fm60ew34belv2tng58i7
MIMO_MODEL=mimo-v2.5-pro
MIMO_BASE_URL=https://api.xiaomimimo.com/v1
```

## Usage in Pipeline
The MiMo model is used in the consensus engine for market analysis:
- **Pass 1**: Analyst classification (bullish/bearish/neutral)
- **Pass 2**: Skeptic / devil's advocate challenge
- **Consensus**: Both passes must agree

## VS Code: Cline Configuration
To use MiMo in VS Code: Cline extension:
1. Open Cline Settings (Ctrl+Shift+P → "Cline: Open Settings")
2. Go to "API Configuration"
3. Select "OpenAI Compatible" as provider
4. Set Base URL: `https://api.xiaomimimo.com/v1`
5. Set API Key: `tp-svf9i440f463x5kzorbkymjdt0s7fm60ew34belv2tng58i7`
6. Set Model: `mimo-v2.5-pro`

## Railway Deployment
Since Railway CLI token is expired, deploy via dashboard:
1. Go to https://railway.com/dashboard
2. Select polymarket-pipeline project
3. Click "Deploy" to redeploy with latest code
