/**
 * Node.js order placement helper for Polymarket Pipeline (CLOB V2).
 * Called by Python via subprocess: node node_order_helper.mjs <token_id> <price> <size> <side>
 * 
 * Uses deposit wallet (proxy wallet) as maker address — required for CLOB V2.
 */
import { privateKeyToAccount } from "viem/accounts";
import { createWalletClient, http } from "viem";
import { polygon } from "viem/chains";
import crypto from "crypto";

const PRIVATE_KEY = process.env.POLYMARKET_PRIVATE_KEY || "0xb0984a253593290e99ff725851929c5bed779805d300aa316b9a368727f5498b";
const EXCHANGE_ADDR = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E";
const CHAIN_ID = 137;
const HOST = process.env.POLYMARKET_HOST || "https://clob.polymarket.com";

// V2: Deposit wallet (proxy wallet) — different from EOA address
// Polymarket auto-creates this when you connect wallet and go to "Deposit"
const DEPOSIT_WALLET = process.env.POLYMARKET_DEPOSIT_WALLET || "0x390b653efa68e83d6509e064e8b07a536036daeb";

async function deriveApiKey(account) {
    const timestamp = Math.floor(Date.now() / 1000).toString();
    const nonce = "0";
    const deriveMsg = `I am signing to derive API credentials on Polymarket CLOB\nTimestamp: ${timestamp}\nNonce: ${nonce}`;
    
    const l1Sig = await account.signMessage({ message: deriveMsg });
    
    const resp = await fetch(`${HOST}/derive-api-key`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ signature: l1Sig, timestamp, nonce }),
    });
    
    if (resp.status === 200) {
        return await resp.json();
    }
    throw new Error(`derive-api-key failed: ${resp.status} ${await resp.text()}`);
}

async function placeOrder(tokenId, price, size, side) {
    const account = privateKeyToAccount(PRIVATE_KEY);
    const walletClient = createWalletClient({ account, chain: polygon, transport: http() });

    // Derive API creds
    let creds;
    try {
        creds = await deriveApiKey(account);
    } catch (e) {
        console.error(`Derive failed: ${e.message}`);
        // Use known creds as fallback
        creds = {
            key: "0fab4802-7d8b-7ffc-07e3-184a71866916",
            secret: "gVA59Ga6f_B4hZ9G7lftegfbGowFKsBeF0bpiivwBEw=",
            passphrase: "3f438bf56cbc4cbfbe6ecea3456dc4f9bc8b83ec087eb115505c22f807dfd891",
        };
    }

    const apiKey = creds.apiKey || creds.key;
    const apiSecret = creds.secret;
    const apiPassphrase = creds.passphrase;

    // Calculate amounts from price and size
    const sideInt = side === "BUY" ? 0 : 1;
    const takerAmount = Math.round(size * 1e6); // USDC has 6 decimals
    const makerAmount = Math.round(size * price * 1e6);

    // V2: Use deposit wallet as maker (not the EOA address)
    const order = {
        salt: String(crypto.randomInt(1, 2147483647)),
        maker: DEPOSIT_WALLET,   // <-- V2: deposit wallet, not account.address
        signer: account.address,
        taker: "0x0000000000000000000000000000000000000000",
        tokenId: String(tokenId),
        makerAmount: String(makerAmount),
        takerAmount: String(takerAmount),
        side: sideInt,
        expiration: "0",
        nonce: "0",
        feeRateBps: "1000",
        signatureType: 0,
    };

    // Sign with version=2 domain (V2 requirement)
    const domain = {
        name: "Polymarket CTF Exchange",
        version: "2",
        chainId: 137,
        verifyingContract: EXCHANGE_ADDR,
    };
    const types = {
        Order: [
            { name: "salt", type: "uint256" },
            { name: "maker", type: "address" },
            { name: "signer", type: "address" },
            { name: "taker", type: "address" },
            { name: "tokenId", type: "uint256" },
            { name: "makerAmount", type: "uint256" },
            { name: "takerAmount", type: "uint256" },
            { name: "expiration", type: "uint256" },
            { name: "nonce", type: "uint256" },
            { name: "feeRateBps", type: "uint256" },
            { name: "side", type: "uint8" },
            { name: "signatureType", type: "uint8" },
        ],
    };

    const signature = await walletClient.signTypedData({
        primaryType: "Order",
        domain,
        types,
        message: order,
    });

    const payload = {
        order: {
            salt: Number.parseInt(order.salt, 10),
            maker: order.maker,
            signer: order.signer,
            taker: order.taker,
            tokenId: order.tokenId,
            makerAmount: order.makerAmount,
            takerAmount: order.takerAmount,
            side: "BUY",
            expiration: order.expiration,
            nonce: order.nonce,
            feeRateBps: order.feeRateBps,
            signatureType: order.signatureType,
            signature: signature,
        },
        owner: apiKey,
        orderType: "GTC",
        version: 2,   // V2 indicator at top level
    };

    // Build L2 HMAC headers (exact SDK format)
    const ts = Math.floor(Date.now() / 1000).toString();
    const requestPath = "/order";
    const bodyStr = JSON.stringify(payload);
    const hmacMessage = ts + "POST" + requestPath + bodyStr;
    
    // HMAC-SHA256 with base64 secret, URL-safe base64 output
    const secretBuf = Buffer.from(apiSecret, "base64");
    const hmac = crypto.createHmac("sha256", secretBuf).update(hmacMessage).digest();
    const hmacSig = Buffer.from(hmac).toString("base64")
        .replace(/\+/g, "-")
        .replace(/\//g, "_");

    const headers = {
        "Content-Type": "application/json",
        "POLY_ADDRESS": account.address,
        "POLY_SIGNATURE": hmacSig,
        "POLY_TIMESTAMP": ts,
        "POLY_API_KEY": apiKey,
        "POLY_PASSPHRASE": apiPassphrase,
    };

    const resp = await fetch(`${HOST}/order`, {
        method: "POST",
        headers,
        body: bodyStr,
    });
    
    return await resp.json();
}

// CLI mode
const args = process.argv.slice(2);
if (args.length >= 3) {
    const [tokenId, price, size, side = "BUY"] = args;
    try {
        const result = await placeOrder(tokenId, parseFloat(price), parseFloat(size), side);
        console.log(JSON.stringify(result));
    } catch (e) {
        console.error(e.message);
        process.exit(1);
    }
} else {
    console.error("Usage: node node_order_helper.mjs <token_id> <price> <size> [side]");
    process.exit(1);
}