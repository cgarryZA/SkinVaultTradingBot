// robust_trade_bot.js

// ========== CONFIG ==========
const config = require('../config.json');
const PORT = 3333;
const INVENTORY_CSV = '../Inventory.csv';
const QUEUE_FILE    = './pending_trades.json';

const { ethers } = require('ethers');
const fs        = require('fs');
const path      = require('path');
const { spawn } = require('child_process');
const axios     = require('axios');
const express   = require('express');
const bodyParser = require('body-parser');
const SteamTotp   = require('steam-totp');
const SteamUser   = require('steam-user');
const SteamCommunity = require('steamcommunity');
const TradeOfferManager = require('steam-tradeoffer-manager');

// ========== ETH CONFIG ==========
const PRIVATE_KEY      = config.private_key;
const ETH_RPC_URL      = config.eth_rpc_url;
const CONTRACT_ADDRESS = config.contract_address;
const VAULT_ABI        = [
  'function mintTo(address,uint256)',
  'function EthToSkins(uint256)',
];

// ========== FILE UTILITIES ==========
function safeWriteFile(p, data) {
  const tmp = p + '.tmp';
  fs.writeFileSync(tmp, data);
  fs.renameSync(tmp, p);
}

// ========== PRICE SCRAPER HELPER ==========
function getPriceForSkin(skin) {
  return new Promise((resolve, reject) => {
    const scraper = path.resolve(__dirname, '..', '..', 'Price Scraper', 'pe_scrape_price.py');
    const py = spawn('python', [ scraper, skin ], { stdio: ['ignore', 'pipe', 'pipe'] });

    let out = '', err = '';
    py.stdout.on('data', d => out += d.toString());
    py.stderr.on('data', d => err += d.toString());

    py.on('close', code => {
      if (code !== 0) {
        return reject(new Error(`scraper exited ${code}: ${err.trim()}`));
      }
      const m = out.match(/\$([\d\.]+)/);
      if (!m) {
        return reject(new Error(`Invalid price from scraper: "${out.trim()}"`));
      }
      const num = parseFloat(m[1]);
      if (isNaN(num)) {
        return reject(new Error(`Parsed NaN from "${m[1]}"`));
      }
      resolve(num);
    });
  });
}

// ========== FULL-PYTHON UPDATER ==========
function runPythonUpdater() {
  const updater = path.resolve(__dirname, '..', 'update_inventory.py');
  const cwd     = path.dirname(updater);
  const py = spawn('python', [ updater ], { cwd, stdio:['ignore','pipe','pipe'] });
  py.stdout.on('data', d => console.log(`Python stdout: ${d}`));
  py.stderr.on('data', d => console.error(`Python stderr: ${d}`));
  py.on('close', code => {
    if (code !== 0) console.error(`update_inventory.py exited with code ${code}`);
  });
}

// ========== INVENTORY CSV HANDLING ==========
if (!fs.existsSync(INVENTORY_CSV)) {
  fs.writeFileSync(INVENTORY_CSV, "Skin,QTY,Price,LastUpdated\n");
}
function updateInventoryCSV(skin, qtyDelta, price = "") {
  const lines = fs.readFileSync(INVENTORY_CSV, 'utf8').split('\n').slice(1);
  const inv = {};
  for (const line of lines) {
    if (!line.trim()) continue;
    const [name, qtyStr, val, last] = line.split(',');
    inv[name] = { qty: parseInt(qtyStr), price: val, lastUpdated: last || "" };
  }
  if (!inv[skin]) {
    inv[skin] = { qty: 0, price, lastUpdated: new Date().toISOString() };
  }
  inv[skin].qty += qtyDelta;
  if (price) inv[skin].price = price;
  if (inv[skin].qty <= 0) delete inv[skin];

  const out = ["Skin,QTY,Price,LastUpdated"];
  for (const k of Object.keys(inv)) {
    const e = inv[k];
    out.push(`${k},${e.qty},${e.price},${e.lastUpdated}`);
  }
  safeWriteFile(INVENTORY_CSV, out.join('\n'));
}

// ========== QUEUE MANAGEMENT ==========
const tradeQueue = [];
function persistQueue() {
  safeWriteFile(QUEUE_FILE, JSON.stringify(tradeQueue, null, 2));
}
function loadQueue() {
  if (fs.existsSync(QUEUE_FILE)) {
    tradeQueue.push(...JSON.parse(fs.readFileSync(QUEUE_FILE)));
  }
}
function enqueueTradeEvent(offer, type) {
  tradeQueue.push({
    id: offer.id,
    type,
    state: offer.state,
    message: offer.message,
    time: Date.now(),
    itemsToReceive: offer.itemsToReceive,
    itemsToGive:   offer.itemsToGive
  });
  persistQueue();
}

// ========== ETH/STEAM SETUP ==========
const provider = new ethers.JsonRpcProvider(ETH_RPC_URL);
const wallet   = new ethers.Wallet(PRIVATE_KEY, provider);
const vault    = new ethers.Contract(CONTRACT_ADDRESS, VAULT_ABI, wallet);

const client    = new SteamUser();
const community = new SteamCommunity();
const manager   = new TradeOfferManager({ steam: client, community, language: 'en', pollInterval: 5000 });

client.logOn({
  accountName: config.username,
  password:    config.password,
  twoFactorCode: SteamTotp.generateAuthCode(config.shared_secret)
});
client.on('loggedOn', () => {
  console.log('Logged into Steam');
  client.setPersona(SteamUser.EPersonaState.Online);
});
client.on('webSession', (sid, cookies) => {
  manager.setCookies(cookies, err => err ? console.error(err) : console.log('TradeOfferManager ready.'));
  community.setCookies(cookies);
});
manager.on('sentOfferChanged', (o, old) => {
  if (o.state === TradeOfferManager.ETradeOfferState.Accepted) enqueueTradeEvent(o, 'sent');
});
manager.on('receivedOfferChanged', (o, old) => {
  if (o.state === TradeOfferManager.ETradeOfferState.Accepted) enqueueTradeEvent(o, 'received');
});

// ========== PROCESSING LOOP ==========
async function processQueue() {
  while (true) {
    if (tradeQueue.length === 0) {
      await new Promise(r => setTimeout(r, 1000));
      continue;
    }
    const ev = tradeQueue.shift();
    persistQueue();
    try {
      await handleTrade(ev);
    } catch (err) {
      console.error('Error processing trade event:', err);
      tradeQueue.unshift(ev);
      await new Promise(r => setTimeout(r, 5000));
    }
  }
}

async function handleTrade(event) {
  // 1) scrape USD price for each received item
  let totalUsd = 0;
  const prices = {};
  for (const item of event.itemsToReceive || []) {
    const name = item.market_hash_name;
    try {
      const usd = await getPriceForSkin(name);
      prices[name] = usd;
      totalUsd += usd;
      console.log(`[PRICE] ${name} → $${usd.toFixed(2)}`);
    } catch (e) {
      console.error(`[PRICE] failed for ${name}:`, e.message);
    }
  }

  // 2) mint on-chain for 'sent' trades, skipping if below 1 wei
  if (event.type === 'sent') {
    const addr = (event.message || '').match(/0x[a-fA-F0-9]{40}/)?.[0];
    if (addr && totalUsd > 0) {
      const ethPrice = await getEthPriceUSD();
      const minUsd   = ethPrice * 1e-18;
      if (totalUsd < minUsd) {
        console.log(`[MINT] totalUsd $${totalUsd.toFixed(6)} < minUsd $${minUsd.toExponential()} → skipping mint`);
      } else {
        const ethAmt = totalUsd / ethPrice;
        const ethStr = ethAmt.toFixed(18);
        console.log(`Minting ${ethStr} ETH ($${totalUsd.toFixed(2)}) to ${addr}`);
        await vault.mintTo(addr, ethers.parseEther(ethStr));
        await vault.EthToSkins(ethers.parseEther(ethStr));
      }
    }
  }

  // 3) update CSV with scraped prices & quantities
  for (const item of event.itemsToReceive || []) {
    updateInventoryCSV(item.market_hash_name, 1, prices[item.market_hash_name]?.toFixed(2) || "");
  }
  for (const item of event.itemsToGive || []) {
    updateInventoryCSV(item.market_hash_name, -1);
  }

  // 4) run full Python inventory/history updater
  runPythonUpdater();
}

// helper to fetch ETH/USD
async function getEthPriceUSD() {
  try {
    const r = await axios.get('https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd');
    return r.data.ethereum.usd;
  } catch (e) {
    console.error(e);
    return 3500;
  }
}

// ========== API ==========
const app = express();
app.use(bodyParser.json());
app.post('/deposit', (req, res) => {
  const { tradeUrl, assetids, ethAddress } = req.body;
  if (!tradeUrl || !assetids || !ethAddress) {
    return res.status(400).json({ error: 'Missing fields' });
  }
  const offer = manager.createOffer(tradeUrl);
  offer.addTheirItems(assetids.map(id => ({ appid: 730, contextid: 2, assetid: id })));
  offer.setMessage('Ethereum address: ' + ethAddress);
  offer.send(err => {
    if (err) console.error('Send error:', err);
  });
  res.json({ status: 'sent' });
});
app.listen(PORT, () => console.log(`API listening on ${PORT}`));

loadQueue();
processQueue();
