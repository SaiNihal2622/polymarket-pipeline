/**
 * Test order placement using Polymarket's official TypeScript SDK.
 * This uses the @polymarket/order-utils package which should have
 * correct V2 signing.
 */
import { ClobClient } from "@polymarket/clob-client";
import { ethers } from "ethers";
import { createWalletClient, http } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { polygon } from "viem/chains";

const PRIVATE_KEY = "0xb0984a253593290e99ff725851929c5bed779805d300aa316b9a368727f5498b";
const HOST = "https://clob.polymarket.com";
const CHAIN_ID = 137;

async function main() {
    console.log("Creating ClobClient...");
    
    const account = privateKeyToAccount(PRIVATE_KEY);
    const walletClient = createWalletClient({
        account,
        chain: polygon,
        transport: http(),
    });
    
    // Derive API key first
    const tempClient = new ClobClient(HOST, CHAIN_ID, walletClient);
    console.log("Deriving API key...");
    const creds = await tempClient.createOrDeriveApiKey();
    console.log("API key:", JSON.stringify(creds).substring(0, 80));
    
    // Create client with creds
    const client = new ClobClient(
        HOST,
        CHAIN_ID,
        walletClient,
        {
            key: creds.key,
            secret: creds.secret,
            passphrase: creds.passphrase,
        }
    );
    
    // Get a market with a real token ID
    console.log("Fetching markets...");
    const resp = await fetch("https://gamma-api.polymarket.com/markets?limit=5&active=true&closed=false&order=volume&ascending=false");
    const markets = await resp.json();
    
    let tokenId = null;
    let marketQuestion = "";
    for (const m of markets) {
        let clobIds = m.clobTokenIds;
        if (typeof clobIds === "string") {
            clobIds = JSON.parse(clobIds);
        }
        if (clobIds && clobIds.length >= 1 && String(clobIds[0]).length > 10) {
            tokenId = String(clobIds[0]);
            marketQuestion = m.question?.substring(0, 60);
            break;
        }
    }
    
    if (!tokenId) {
        console.error("No valid token ID found!");
        process.exit(1);
    }
    
    console.log(`Market: ${marketQuestion}`);
    console.log(`Token ID: ${tokenId.substring(0, 30)}...`);
    
    // Create and post order
    const orderArgs = {
        price: 0.10,
        size: 0.50,
        side: "BUY",
        tokenID: tokenId,
    };
    
    try {
        console.log("Creating order...");
        const signedOrder = await client.createOrder(orderArgs);
        console.log("Signed order created successfully");
        
        console.log("Posting order...");
        const result = await client.postOrder(signedOrder, "GTC");
        console.log("✅ ORDER SUCCESS:", JSON.stringify(result, null, 2));
    } catch (e) {
        console.error("❌ Error:", e.message || e);
        if (e.response) {
            console.error("Response:", e.response.status, e.response.data);
        }
    }
}

main().catch(console.error);