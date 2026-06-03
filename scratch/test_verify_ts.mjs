// Verify the patched constant is actually used
import { PROTOCOL_VERSION, PROTOCOL_NAME } from "@polymarket/order-utils";
console.log("PROTOCOL_NAME:", PROTOCOL_NAME);
console.log("PROTOCOL_VERSION:", PROTOCOL_VERSION);

// Also test: sign with version="1" domain
import { privateKeyToAccount } from "viem/accounts";
import { createWalletClient, http } from "viem";
import { polygon } from "viem/chains";
import crypto from "crypto";

const PRIVATE_KEY = "0xb0984a253593290e99ff725851929c5bed779805d300aa316b9a368727f5498b";
const EXCHANGE_ADDR = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E";

const account = privateKeyToAccount(PRIVATE_KEY);
const walletClient = createWalletClient({ account, chain: polygon, transport: http() });

const order = {
    salt: String(crypto.randomInt(1, 2147483647)),
    maker: account.address,
    signer: account.address,
    taker: "0x0000000000000000000000000000000000000000",
    tokenId: "69024779234100418825265716746602929644796752945259475286197657688432971405592",
    makerAmount: "50000",
    takerAmount: "500000",
    side: 0,
    expiration: "0",
    nonce: "0",
    feeRateBps: "1000",
    signatureType: 0,
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

// Sign with version="1"
const sig1 = await walletClient.signTypedData({
    primaryType: "Order",
    domain: { name: "Polymarket CTF Exchange", version: "1", chainId: 137, verifyingContract: EXCHANGE_ADDR },
    types,
    message: order,
});

// Sign with version="2"
const sig2 = await walletClient.signTypedData({
    primaryType: "Order",
    domain: { name: "Polymarket CTF Exchange", version: "2", chainId: 137, verifyingContract: EXCHANGE_ADDR },
    types,
    message: order,
});

console.log("Sig v1:", sig1.substring(0, 30) + "...");
console.log("Sig v2:", sig2.substring(0, 30) + "...");
console.log("Sigs different:", sig1 !== sig2);

// Test both against the API with proper HMAC auth
const apiKey = "0fab4802-7d8b-7ffc-07e3-184a71866916";
const apiSecret = "gVA59Ga6f_B4hZ9G7lftegfbGowFKsBeF0bpiivwBEw=";
const apiPassphrase = "3f438bf56cbc4cbfbe6ecea3456dc4f9bc8b83ec087eb115505c22f807dfd891";

for (const [label, sig] of [["v1", sig1], ["v2", sig2]]) {
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
            signature: sig,
            version: 2,
        },
        owner: apiKey,
        orderType: "GTC",
        version: 2,
    };

    const ts = Math.floor(Date.now() / 1000).toString();
    const bodyStr = JSON.stringify(payload);
    const hmacMessage = ts + "POST" + "/order" + bodyStr;
    const secretBuf = Buffer.from(apiSecret, "base64");
    const hmacSig = Buffer.from(
        crypto.createHmac("sha256", secretBuf).update(hmacMessage).digest()
    ).toString("base64").replace(/\+/g, "-").replace(/\//g, "_");

    const resp = await fetch("https://clob.polymarket.com/order", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "POLY_ADDRESS": account.address,
            "POLY_SIGNATURE": hmacSig,
            "POLY_TIMESTAMP": ts,
            "POLY_API_KEY": apiKey,
            "POLY_PASSPHRASE": apiPassphrase,
        },
        body: bodyStr,
    });
    const result = await resp.json();
    console.log(`Signed with ${label}: ${JSON.stringify(result)}`);
}