import { ClobClient } from "@polymarket/clob-client";
import { privateKeyToAccount } from "viem/accounts";
import { createWalletClient, http } from "viem";
import { polygon } from "viem/chains";

const PRIVATE_KEY = "0xb0984a253593290e99ff725851929c5bed779805d300aa316b9a368727f5498b";
const HOST = "https://clob.polymarket.com";
const CHAIN_ID = 137;

async function main() {
    const account = privateKeyToAccount(PRIVATE_KEY);
    const walletClient = createWalletClient({ account, chain: polygon, transport: http() });
    
    const creds = {
        key: "0fab4802-7d8b-7ffc-07e3-184a71866916",
        secret: "gVA59Ga6f_B4hZ9G7lftegfbGowFKsBeF0bpiivwBEw=",
        passphrase: "3f438bf56cbc4cbfbe6ecea3456dc4f9bc8b83ec087eb115505c22f807dfd891",
    };
    
    const client = new ClobClient(HOST, CHAIN_ID, walletClient, creds);
    
    // Get market
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
    console.log("Token:", tokenId.substring(0, 30));
    
    // Use SDK createOrder - this handles tick_size, fee_rate, etc.
    const orderArgs = {
        price: 0.10,
        size: 0.50,
        side: "BUY",
        tokenID: tokenId,
    };
    
    try {
        const signedOrder = await client.createOrder(orderArgs);
        console.log("\nSDK signed order:", JSON.stringify(signedOrder, null, 2).substring(0, 800));
        
        // Now try postOrder
        const result = await client.postOrder(signedOrder, "GTC");
        console.log("\nPost result:", JSON.stringify(result));
    } catch (e) {
        console.log("Error:", e.message);
    }
}

main();