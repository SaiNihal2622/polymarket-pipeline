import { privateKeyToAccount } from "viem/accounts";
import { createWalletClient, http } from "viem";
import { polygon } from "viem/chains";
import crypto from "crypto";

const PRIVATE_KEY = "0xb0984a253593290e99ff725851929c5bed779805d300aa316b9a368727f5498b";
const EXCHANGE_ADDR = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E";
const CHAIN_ID = 137;

async function main() {
    const account = privateKeyToAccount(PRIVATE_KEY);
    const walletClient = createWalletClient({ account, chain: polygon, transport: http() });
    
    // Get token
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
    console.log("Token:", tokenId.substring(0, 30) + "...");
    
    // Build order manually
    const order = {
        salt: String(crypto.randomInt(1, 2147483647)),
        maker: account.address,
        signer: account.address,
        taker: "0x0000000000000000000000000000000000000000",
        tokenId: tokenId,
        makerAmount: "50000",
        takerAmount: "500000",
        side: 0, // BUY
        expiration: "0",
        nonce: "0",
        feeRateBps: "1000",
        signatureType: 0,
    };
    
    // Sign with explicit version=2 domain
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
    
    console.log("Signature:", signature.substring(0, 30) + "...");
    
    // Build payload
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
        owner: "0fab4802-7d8b-7ffc-07e3-184a71866916",
        orderType: "GTC",
        version: 2,
    };
    
    console.log("Payload:", JSON.stringify(payload, null, 2).substring(0, 500));
    
    // Post directly via fetch
    const postResp = await fetch("https://clob.polymarket.com/order", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });
    const result = await postResp.json();
    console.log("Result:", JSON.stringify(result));
}

main().catch(console.error);
