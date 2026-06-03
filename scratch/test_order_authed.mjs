import { privateKeyToAccount } from "viem/accounts";
import { createWalletClient, http } from "viem";
import { polygon } from "viem/chains";
import crypto from "crypto";

const PRIVATE_KEY = "0xb0984a253593290e99ff725851929c5bed779805d300aa316b9a368727f5498b";
const EXCHANGE_ADDR = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E";
const CHAIN_ID = 137;
const HOST = "https://clob.polymarket.com";

async function main() {
    const account = privateKeyToAccount(PRIVATE_KEY);
    const walletClient = createWalletClient({ account, chain: polygon, transport: http() });

    // Derive API creds using L1 auth
    const timestamp = Math.floor(Date.now() / 1000).toString();
    const nonce = "0";
    const deriveMsg = `I am signing to derive API credentials on Polymarket CLOB\nTimestamp: ${timestamp}\nNonce: ${nonce}`;
    
    const l1Sig = await account.signMessage({ message: deriveMsg });
    
    const deriveResp = await fetch(`${HOST}/derive-api-key`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            signature: l1Sig,
            timestamp: timestamp,
            nonce: nonce,
        }),
    });
    const deriveText = await deriveResp.text();
    console.log("Derive status:", deriveResp.status, "body:", deriveText.substring(0, 200));
    let creds;
    try {
        creds = JSON.parse(deriveText);
    } catch (e) {
        console.log("Using known creds from CONTEXT_FULL_LOCAL.md");
        creds = {
            key: "0fab4802-7d8b-7ffc-07e3-184a71866916",
            secret: "gVA59Ga6f_B4hZ9G7lftegfbGowFKsBeF0bpiivwBEw=",
            passphrase: "3f438bf56cbc4cbfbe6ecea3456dc4f9bc8b83ec087eb115505c22f807dfd891",
        };
    }
    console.log("API Key:", creds.apiKey?.substring(0, 16) || creds.key?.substring(0, 16) || "N/A");

    // Build order
    const resp = await fetch("https://gamma-api.polymarket.com/markets?limit=5&active=true&closed=false&order=volume&ascending=false");
    const markets = await resp.json();
    let tokenId = null;
    let marketQ = "";
    for (const m of markets) {
        let clobIds = m.clobTokenIds;
        if (typeof clobIds === "string") clobIds = JSON.parse(clobIds);
        if (clobIds && clobIds.length >= 1 && String(clobIds[0]).length > 10) {
            tokenId = String(clobIds[0]);
            marketQ = m.question.substring(0, 60);
            break;
        }
    }
    console.log("Market:", marketQ);

    const order = {
        salt: String(crypto.randomInt(1, 2147483647)),
        maker: account.address,
        signer: account.address,
        taker: "0x0000000000000000000000000000000000000000",
        tokenId: tokenId,
        makerAmount: "50000",
        takerAmount: "500000",
        side: 0,
        expiration: "0",
        nonce: "0",
        feeRateBps: "1000",
        signatureType: 0,
    };

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

    const apiKey = creds.apiKey || creds.key;
    const apiSecret = creds.secret;
    const apiPassphrase = creds.passphrase;

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
            version: 2,
        },
        owner: apiKey,
        orderType: "GTC",
        version: 2,
    };

    // Build L2 HMAC headers
    const ts = Math.floor(Date.now() / 1000).toString();
    const bodyStr = JSON.stringify(payload);
    const message = ts + "POST" + "/order" + bodyStr;
    const secretBuf = Buffer.from(apiSecret, "base64");
    const hmac = crypto.createHmac("sha256", secretBuf).update(message).digest();
    const sig = Buffer.from(hmac).toString("base64");

    const headers = {
        "Content-Type": "application/json",
        "POLY_API_KEY": apiKey,
        "POLY_SIGNATURE": sig,
        "POLY_TIMESTAMP": ts,
        "POLY_NONCE": "0",
    };
    if (apiPassphrase) {
        headers["POLY_PASSPHRASE"] = apiPassphrase;
    }

    console.log("Posting order with HMAC auth...");
    const postResp = await fetch(`${HOST}/order`, {
        method: "POST",
        headers,
        body: bodyStr,
    });
    const result = await postResp.json();
    console.log("Result:", JSON.stringify(result));
}

main().catch(console.error);