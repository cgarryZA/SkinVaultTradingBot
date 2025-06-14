// bot/Nodes/bot.js

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

// ========== CONFIG ==========
const configPath = path.resolve(__dirname, '..', 'config.json');
const config     = require(configPath);

const PORT           = 3333;
const INVENTORY_CSV  = path.resolve(__dirname, '..', 'Inventory.csv');
const QUEUE_FILE     = path.resolve(__dirname, 'pending_trades.json');

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

// ========== VENV PYTHON PATH ==========
const venvPython = path.resolve(
  __dirname, '..', 'venv', 'bin', 'python3'
);
console.log('Using Python at:', venvPython);

// ========== PRICE SCRAPER ==========
function getPriceForSkin(skin) {
  return new Promise((resolve, reject) => {
    const scraper = path.resolve(__dirname, '..', 'Price Scraper', 'pe_scrape_price.py');
    const py = spawn(venvPython, [ scraper, skin ], { stdio: ['ignore','pipe','pipe'] });

    py.on('error', err => reject(err));

    let out = '', errBuf = '';
    py.stdout.on('data', d => out += d);
    py.stderr.on('data', d => errBuf += d);

    py.on('close', code => {
      if (code !== 0) return reject(new Error(`scraper exited ${code}: ${errBuf.trim()}`));
      const m = out.match(/\$([\d\.]+)/);
      if (!m) return reject(new Error('Invalid price from scraper'));
      resolve(parseFloat(m[1]));
    });
  });
}

// ========== PYTHON UPDATER ==========
function runPythonUpdater() {
  const updater = path.resolve(__dirname, '..', 'update_inventory.py');
  const py = spawn(venvPython, [ updater ], { cwd: path.dirname(updater), stdio: ['ignore','pipe','pipe'] });
  py.stdout.on('data', d => console.log(`Updater stdout: ${d}`));
  py.stderr.on('data', d => console.error(`Updater stderr: ${d}`));
}

// ========== INVENTORY CSV HANDLING ==========
if (!fs.existsSync(INVENTORY_CSV)) {
  fs.writeFileSync(INVENTORY_CSV, 'Skin,QTY,Price,LastUpdated\n');
}
function updateInventoryCSV(skin, qtyDelta, price='') {
  const lines = fs.readFileSync(INVENTORY_CSV,'utf8').split('\n').slice(1);
  const inv = {};
  for (const line of lines) {
    if (!line) continue;
    const [name,qtyStr,val,last] = line.split(',');
    inv[name] = { qty: parseInt(qtyStr), price: val, lastUpdated: last||'' };
  }
  if (!inv[skin]) inv[skin] = { qty:0, price, lastUpdated:new Date().toISOString() };
  inv[skin].qty += qtyDelta;
  if (price) inv[skin].price = price;
  if (inv[skin].qty<=0) delete inv[skin];

  const out = ['Skin,QTY,Price,LastUpdated'];
  for (const k of Object.keys(inv)) {
    const e = inv[k];
    out.push(`${k},${e.qty},${e.price},${e.lastUpdated}`);
  }
  safeWriteFile(INVENTORY_CSV, out.join('\n'));
}

// ========== QUEUE ==========
const tradeQueue = [];
function persistQueue() {
  safeWriteFile(QUEUE_FILE, JSON.stringify(tradeQueue,null,2));
}
function loadQueue() {
  if (fs.existsSync(QUEUE_FILE)) {
    tradeQueue.push(...JSON.parse(fs.readFileSync(QUEUE_FILE)));
  }
}
function enqueueTradeEvent(offer,type) {
  tradeQueue.push({
    id: offer.id,
    type,
    state: offer.state,
    message: offer.message,
    time: Date.now(),
    itemsToReceive: offer.itemsToReceive,
    itemsToGive: offer.itemsToGive
  });
  persistQueue();
}

// ========== ETH & STEAM SETUP ==========
const provider = new ethers.JsonRpcProvider(ETH_RPC_URL);
const wallet   = new ethers.Wallet(PRIVATE_KEY, provider);
const vault    = new ethers.Contract(CONTRACT_ADDRESS, VAULT_ABI, wallet);

const client    = new SteamUser();
const community = new SteamCommunity();
const manager   = new TradeOfferManager({ steam:client, community, language:'en', pollInterval:1000 });

// Steam login with loginKey persistence
const logOnOpts = {
  accountName: config.username,
  password:    config.password,
  rememberPassword: true,
  loginKey:    config.login_key||null,
  twoFactorCode: SteamTotp.generateAuthCode(config.shared_secret)
};

client.on('loginKey', key => {
  config.login_key = key;
  fs.writeFileSync(configPath, JSON.stringify(config,null,2));
});
client.on('error', err => {
  if (err.eresult===SteamUser.EResult.AccountLoginDeniedThrottle) {
    console.log('Throttled – retrying in 30s');
    setTimeout(()=>client.logOn(logOnOpts),30000);
  } else console.error(err);
});

client.logOn(logOnOpts);
client.on('loggedOn',()=>client.setPersona(SteamUser.EPersonaState.Online));
client.on('webSession',(sid,cookies)=>{
  manager.setCookies(cookies,err=>err?console.error(err):console.log('Manager ready.'));
  community.setCookies(cookies);
});

manager.on('sentOfferChanged',(o,_)=>{
  if (o.state===TradeOfferManager.ETradeOfferState.Accepted) enqueueTradeEvent(o,'sent');
});
manager.on('receivedOfferChanged',(o,_)=>{
  if (o.state===TradeOfferManager.ETradeOfferState.Accepted) enqueueTradeEvent(o,'received');
});

// ========== PROCESS LOOP ==========
async function processQueue(){
  while(true){
    if(!tradeQueue.length){
      await new Promise(r=>setTimeout(r,1000));
      continue;
    }
    const ev = tradeQueue.shift();
    persistQueue();
    try { await handleTrade(ev); }
    catch(e){ console.error(e); tradeQueue.unshift(ev); await new Promise(r=>setTimeout(r,5000)); }
  }
}

async function handleTrade(event){
  let totalUsd=0, prices={};
  for(const item of event.itemsToReceive||[]){
    try {
      const usd = await getPriceForSkin(item.market_hash_name);
      prices[item.market_hash_name]=usd;
      totalUsd+=usd;
    } catch(e){ console.error(e.message); }
  }
  if(event.type==='sent'){
    const addr = (event.message||'').match(/0x[a-fA-F0-9]{40}/)?.[0];
    if(addr && totalUsd>0){
      const ethPrice = await getEthPriceUSD();
      const minUsd   = ethPrice*1e-18;
      if(totalUsd>=minUsd){
        const ethAmt = totalUsd/ethPrice, ethStr = ethAmt.toFixed(18);
        await vault.mintTo(addr,ethers.parseEther(ethStr));
        await vault.EthToSkins(ethers.parseEther(ethStr));
      }
    }
  }
  for(const item of event.itemsToReceive||[]){
    updateInventoryCSV(item.market_hash_name,1,prices[item.market_hash_name]?.toFixed(2)||'');
  }
  for(const item of event.itemsToGive||[]){
    updateInventoryCSV(item.market_hash_name,-1);
  }
  runPythonUpdater();
}

async function getEthPriceUSD(){
  try {
    const r=await axios.get('https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd');
    return r.data.ethereum.usd;
  } catch {
    return 3500;
  }
}

// ========== API ==========
const app = express();
app.use(bodyParser.json());
app.post('/deposit',(req,res)=>{
  const {tradeUrl,assetids,ethAddress}=req.body;
  if(!tradeUrl||!assetids||!ethAddress) return res.status(400).json({error:'Missing'});
  const offer=manager.createOffer(tradeUrl);
  offer.addTheirItems(assetids.map(id=>({appid:730,contextid:2,assetid:id})));
  offer.setMessage('Ethereum address: '+ethAddress);
  offer.send(err=>err&&console.error(err));
  res.json({status:'sent'});
});
app.listen(PORT,'0.0.0.0',()=>console.log(`API listening on ${PORT}`));

loadQueue();
processQueue();
