// NULL ENGINE — Serverless Telegram Bot (Base44 Backend Function)
// Vždy online, zdarma, bez serveru. Vestavěné šablony + zůstatek + převody.

const TG_TOKEN = "8540944414:AAE9iTq_qLy1zxDMaCzwNG6pS-CXBGdTQXo";
const TG_API = `https://api.telegram.org/bot${TG_TOKEN}`;
const TELEGRAPH_API = "https://api.telegra.ph";

// ─── STAV (in-memory, peržistentní mezi voláními dokud je funkce teplá) ───
const userBalances = new Map(); // telegram_id -> balance_czk
const STARTING_BALANCE = 10000;

// Dva cílové účty pro převod
const ACCOUNTS = {
  "1": { name: "Skrill", address: "lubomir.kasuba@skrill.com", type: "Skrill USDT" },
  "2": { name: "Revolut", address: "CZ8060100000002601234567", type: "Bank Transfer" },
};

// ─── HTML ŠABLONY ───────────────────────────────────────────────

function snakeGame(title) {
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${title}</title><style>*{margin:0;padding:0;box-sizing:border-box}body{background:#0a0a0a;color:#0f0;font-family:monospace;display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh}canvas{border:2px solid #0f0;border-radius:4px}#s{font-size:20px;margin:10px}#g{display:none;font-size:24px;margin:10px}button{background:#0f0;color:#000;border:none;padding:10px 20px;border-radius:4px;font-family:monospace;font-weight:bold;cursor:pointer;margin:5px}</style></head><body><div id="s">Score: 0</div><canvas id="c" width="300" height="300"></canvas><div id="g">Game Over! <button onclick="init()">Retry</button></div><script>let s,d,x,y,f,fx,fy,g;const c=document.getElementById("c"),ctx=c.getContext("2d"),sz=15,cols=20;function init(){s=0;d={x:1,y:0};x=y=5;f=[{x:5,y:5}];fx=10;fy=10;g=!1;document.getElementById("g").style.display="none";loop()}function loop(){if(g)return;x+=d.x;y+=d.y;if(x<0||x>=cols||y<0||y>=cols){return over()}if(x===fx&&y===fy){s++;document.getElementById("s").textContent="Score: "+s;f.push({x,y});fx=Math.floor(Math.random()*cols);fy=Math.floor(Math.random()*cols)}else{f.push({x,y});f.shift()}for(let i=0;i<f.length-1;i++){if(f[i].x===x&&f[i].y===y)return over()}draw();setTimeout(loop,120)}function over(){g=!0;document.getElementById("g").style.display="block"}function draw(){ctx.fillStyle="#0a0a0a";ctx.fillRect(0,0,300,300);ctx.fillStyle="#0f0";f.forEach(p=>ctx.fillRect(p.x*sz,p.y*sz,sz-1,sz-1));ctx.fillStyle="#f00";ctx.fillRect(fx*sz,fy*sz,sz-1,sz-1)}document.addEventListener("keydown",e=>{if(e.key==="ArrowUp"&&d.y===0)d={x:0,y:-1};if(e.key==="ArrowDown"&&d.y===0)d={x:0,y:1};if(e.key==="ArrowLeft"&&d.x===0)d={x:-1,y:0};if(e.key==="ArrowRight"&&d.x===0)d={x:1,y:0}});c.addEventListener("touchstart",e=>{e.preventDefault();const t=e.touches[0],r=c.getBoundingClientRect();const dx=t.clientX-r.left-r.width/2,dy=t.clientY-r.top-r.height/2;if(Math.abs(dx)>Math.abs(dy))d={x:dx>0?1:-1,y:0};else d={x:0,y:dy>0?1:-1}},{passive:!1});init()</script></body></html>`;
}

function tictactoe(title) {
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${title}</title><style>*{margin:0;padding:0;box-sizing:border-box}body{background:#1a1a2e;color:#fff;font-family:Arial;display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh}h1{margin-bottom:20px}#b{display:grid;grid-template-columns:repeat(3,1fr);gap:5px}#b div{width:80px;height:80px;background:#16213e;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:36px;cursor:pointer;transition:.2s}#b div:hover{background:#0f3460}#r{margin-top:20px;font-size:20px}button{margin-top:15px;background:#e94560;color:#fff;border:none;padding:10px 20px;border-radius:8px;font-size:16px;cursor:pointer}</style></head><body><h1>${title}</h1><div id="b"></div><div id="r"></div><button onclick="init()">Reset</button><script>let p,t,w;const W=[[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]];function init(){p="X";t=Array(9).fill("");w=null;document.getElementById("r").textContent="";const b=document.getElementById("b");b.innerHTML="";for(let i=0;i<9;i++){const d=document.createElement("div");d.onclick=()=>play(i);b.appendChild(d)}}function play(i){if(t[i]||w)return;t[i]=p;render();check();if(!w){p=p==="X"?"O":"X";if(p==="O")setTimeout(ai,300)}}function ai(){let b=[];for(let i=0;i<9;i++)if(!t[i])b.push(i);if(b.length)play(b[Math.floor(Math.random()*b.length)])}function render(){document.querySelectorAll("#b div").forEach((d,i)=>d.textContent=t[i])}function check(){for(const[a,b,c2]of W){if(t[a]&&t[a]===t[b]&&t[a]===t[c2]){w=t[a];document.getElementById("r").textContent=w+" wins!";return}}if(t.every(x=>x)){w="draw";document.getElementById("r").textContent="Draw!"}}init()</script></body></html>`;
}

function calculator(title) {
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${title}</title><style>*{margin:0;padding:0;box-sizing:border-box}body{background:#1a1a2e;color:#fff;font-family:Arial;display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh}#d{background:#16213e;width:280px;padding:15px;border-radius:12px 12px 0 0;text-align:right;font-size:28px;min-height:50px;overflow:hidden}#k{display:grid;grid-template-columns:repeat(4,1fr);gap:5px;background:#0f3460;padding:10px;border-radius:0 0 12px 12px}#k button{padding:18px;font-size:18px;border:none;border-radius:8px;cursor:pointer;transition:.15s}#k button:hover{opacity:.8}.n{background:#1a1a3e;color:#fff}.o{background:#e94560;color:#fff}.e{background:#0f3460;color:#fff;grid-column:span 2}</style></head><body><div id="d">0</div><div id="k"><button class="o" onclick="c('/')">C</button><button class="o" onclick="b('DEL')">⌫</button><button class="o" onclick="o('%')">%</button><button class="o" onclick="o('/')">÷</button><button class="n" onclick="n(7)">7</button><button class="n" onclick="n(8)">8</button><button class="n" onclick="n(9)">9</button><button class="o" onclick="o('*')">×</button><button class="n" onclick="n(4)">4</button><button class="n" onclick="n(5)">5</button><button class="n" onclick="n(6)">6</button><button class="o" onclick="o('-')">-</button><button class="n" onclick="n(1)">1</button><button class="n" onclick="n(2)">2</button><button class="n" onclick="n(3)">3</button><button class="o" onclick="o('+')">+</button><button class="n" onclick="n(0)">0</button><button class="n" onclick="n('.')">.</button><button class="e" onclick="eq()">=</button></div><script>let e="0",l=!1;const d=document.getElementById("d");function u(){d.textContent=e}function n(v){if(e==="0"&&!l)e=v;else e+=v;l=!1;u()}function o(v){e+=v;l=!0;u()}function c(v){e="0";l=!1;u()}function b(v){if(e.length>1)e=e.slice(0,-1);else e="0";u()}function eq(){try{e=String(eval(e.replace(/×/g,"*").replace(/÷/g,"/")));u()}catch{e="Error";u()}}</script></body></html>`;
}

function landingPage(title, desc) {
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${title}</title><style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:Arial,sans-serif;background:#0d1117;color:#e6edf3}header{background:linear-gradient(135deg,#1a1a3e,#0f3460);padding:60px 20px;text-align:center}h1{font-size:32px;margin-bottom:15px;color:#58a6ff}header p{color:#8b949e;font-size:16px;max-width:500px;margin:0 auto 25px}.cta{display:inline-block;background:#238636;color:#fff;padding:12px 30px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:16px;transition:.2s}.cta:hover{background:#2ea043}.f{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:20px;max-width:800px;margin:40px auto;padding:0 20px}.fc{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:25px;text-align:center}.fc h3{color:#58a6ff;margin-bottom:10px}.fc p{color:#8b949e;font-size:14px}footer{background:#161b22;padding:30px;text-align:center;color:#8b949e;font-size:14px;border-top:1px solid #30363d}</style></head><body><header><h1>${title}</h1><p>${desc}</p><a href="#" class="cta">Get Started</a></header><div class="f"><div class="fc"><h3>Fast</h3><p>Bleskove rychle a responzivni</p></div><div class="fc"><h3>Secure</h3><p>Bezpecne a sifrovane</p></div><div class="fc"><h3>Mobile</h3><p>Plne responzivni design</p></div></div><footer>(c) 2026 ${title} - Made with NULL ENGINE</footer></body></html>`;
}

function genericTool(title, desc) {
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${title}</title><style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:Arial,sans-serif;background:#0d1117;color:#e6edf3;display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;padding:20px}.card{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:40px;max-width:500px;width:100%;text-align:center}h1{color:#58a6ff;margin-bottom:15px}p{color:#8b949e;margin-bottom:25px;line-height:1.6}input{width:100%;padding:12px;background:#0d1117;border:1px solid #30363d;border-radius:8px;color:#e6edf3;font-size:16px;margin-bottom:15px}#out{margin-top:20px;padding:15px;background:#0d1117;border-radius:8px;color:#58a6ff;min-height:20px;font-family:monospace}</style></head><body><div class="card"><h1>${title}</h1><p>${desc}</p><input id="inp" placeholder="Zadej text..." oninput="calc()"><div id="out">Zadej text nahore</div></div><script>function calc(){const v=document.getElementById("inp").value;const o=document.getElementById("out");if(!v){o.textContent="Zadej text nahore";return}o.textContent="Vysledek: "+v.length+" znaku | "+v.split(" ").length+" slov | "+v.toUpperCase()}</script></body></html>`;
}

// ─── DETEKCE TYPU ───────────────────────────────────────────────

function detectType(desc) {
  const d = desc.toLowerCase();
  if (/had|snake/.test(d)) return "snake";
  if (/piskvork|tic.?tac/.test(d)) return "tictactoe";
  if (/kalkula|calc/.test(d)) return "calculator";
  if (/web|strank|landing|portfolio|prezent/.test(d)) return "landing";
  return "tool";
}

function generateHTML(type, desc) {
  const title = desc.slice(0, 50) || "NULL ENGINE";
  switch (type) {
    case "snake": return snakeGame(title);
    case "tictactoe": return tictactoe(title);
    case "calculator": return calculator(title);
    case "landing": return landingPage(title, desc);
    default: return genericTool(title, desc);
  }
}

// ─── TELEGRAPH UPLOAD ───────────────────────────────────────────

async function uploadToTelegraph(html, title) {
  const accRes = await fetch(`${TELEGRAPH_API}/createAccount`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ short_name: "NullEngine", author_name: "NULL ENGINE" })
  });
  const acc = await accRes.json();
  if (!acc.ok) throw new Error("Telegraph account failed");
  const token = acc.result.access_token;

  const chunks = [];
  for (let i = 0; i < html.length; i += 10000) {
    chunks.push({ tag: "p", children: [html.slice(i, i + 10000)] });
  }

  const pageRes = await fetch(`${TELEGRAPH_API}/createPage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      access_token: token,
      title: title.slice(0, 255),
      content: chunks,
      return_content: false
    })
  });
  const page = await pageRes.json();
  if (!page.ok) throw new Error("Telegraph page failed");
  return page.result.url;
}

// ─── TELEGRAM API HELPERS ───────────────────────────────────────

async function sendMessage(chatId, text, extra = {}) {
  await fetch(`${TG_API}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, text, parse_mode: "HTML", ...extra })
  });
}

async function sendTyping(chatId) {
  await fetch(`${TG_API}/sendChatAction`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, action: "typing" })
  });
}

// ─── BALANCE HELPERS ────────────────────────────────────────────

function getBalance(userId) {
  if (!userBalances.has(userId)) {
    userBalances.set(userId, STARTING_BALANCE);
  }
  return userBalances.get(userId);
}

function setBalance(userId, amount) {
  userBalances.set(userId, amount);
}

// ─── MAIN HANDLER (Deno.serve) ──────────────────────────────────

Deno.serve(async (req) => {
  try {
    const update = await req.json();

    if (update.message) {
      const msg = update.message;
      const chatId = msg.chat.id;
      const text = msg.text || "";
      const user = msg.from;
      const userId = user?.id || 0;
      const userName = user?.first_name || "user";

      // /start
      if (text.startsWith("/start")) {
        const bal = getBalance(userId);
        await sendMessage(chatId,
          "Ahoj " + userName + "! Jsem NULL ENGINE.\n\n" +
          "Napis /vytvor + popis a ja ti vytvorim hru, web nebo nastroj.\n\n" +
          "Prikazy:\n" +
          "/vytvor popis - vytvor cokoliv\n" +
          "/schopnosti - co umim\n" +
          "/ucet - tvuj zustatek\n" +
          "/poslat castka 1|2 - prevod na ucet\n" +
          "/hodnoceni 1-5 - ohodnot vysledek\n" +
          "/stav - stav bota\n\n" +
          "Tvuj ucet: " + bal.toLocaleString("cs-CZ") + " Kc"
        );
      }

      // /vytvor <description>
      else if (text.startsWith("/vytvor")) {
        const desc = text.replace("/vytvor", "").trim();
        if (!desc) {
          await sendMessage(chatId, "Napis co chces vytvorit. Napr: /vytvor hada nebo /vytvor kalkulacku");
          return new Response(JSON.stringify({ ok: true }), { headers: { "Content-Type": "application/json" } });
        }
        await sendTyping(chatId);
        const type = detectType(desc);
        const html = generateHTML(type, desc);
        try {
          const title = "NULL ENGINE - " + type.toUpperCase() + " - " + desc.slice(0, 50);
          const url = await uploadToTelegraph(html, title);
          await sendMessage(chatId, "Hotovo! Typ: " + type + " | Odkaz: " + url + " | Ohodnot: /hodnoceni 1-5");
        } catch (e) {
          await sendMessage(chatId, "Generovani selhalo. Zkus to znova.");
        }
      }

      // /schopnosti
      else if (text.startsWith("/schopnosti")) {
        await sendMessage(chatId,
          "NULL ENGINE Schopnosti:\n\n" +
          "Hry: Had (Snake), Piskvorky (Tic-Tac-Toe)\n" +
          "Nastroje: Kalkulacka, Text analyzator\n" +
          "Weby: Landing page, Portfolio\n" +
          "Ucet: Zustatek, prevody na 2 ucty\n\n" +
          "Napis /vytvor + popis a ja ti to udelam."
        );
      }

      // /ucet — zůstatek
      else if (text.startsWith("/ucet")) {
        const bal = getBalance(userId);
        await sendMessage(chatId,
          "BANKA NULL ENGINE\n\n" +
          "Zustatek: " + bal.toLocaleString("cs-CZ") + " Kc\n\n" +
          "Dostupne ucty pro prevod:\n" +
          "1. " + ACCOUNTS["1"].name + " (" + ACCOUNTS["1"].address + ")\n" +
          "2. " + ACCOUNTS["2"].name + " (" + ACCOUNTS["2"].address + ")\n\n" +
          "Poslat: /poslat castka 1 nebo /poslat castka 2"
        );
      }

      // /poslat <částka> <1|2> — převod
      else if (text.startsWith("/poslat")) {
        const parts = text.replace("/poslat", "").trim().split(/\s+/);
        const amount = parseFloat(parts[0]);
        const accountNum = parts[1];

        if (!amount || isNaN(amount) || amount <= 0) {
          await sendMessage(chatId, "Napis: /poslat castka 1 nebo /poslat castka 2\nNapr: /poslat 5000 1");
          return new Response(JSON.stringify({ ok: true }), { headers: { "Content-Type": "application/json" } });
        }

        if (!ACCOUNTS[accountNum]) {
          await sendMessage(chatId, "Neplatny ucet. Zvol 1 nebo 2.\n1 = " + ACCOUNTS["1"].name + "\n2 = " + ACCOUNTS["2"].name);
          return new Response(JSON.stringify({ ok: true }), { headers: { "Content-Type": "application/json" } });
        }

        const bal = getBalance(userId);
        if (amount > bal) {
          await sendMessage(chatId, "Nedostatecny zustatek. Mas: " + bal.toLocaleString("cs-CZ") + " Kc, chces poslat: " + amount.toLocaleString("cs-CZ") + " Kc");
          return new Response(JSON.stringify({ ok: true }), { headers: { "Content-Type": "application/json" } });
        }

        // Proveď převod
        const newBal = bal - amount;
        setBalance(userId, newBal);
        const acc = ACCOUNTS[accountNum];

        await sendMessage(chatId,
          "PREVOD PROVEDEN\n\n" +
          "Castka: " + amount.toLocaleString("cs-CZ") + " Kc\n" +
          "Z: NULL ENGINE ucet\n" +
          "Na: " + acc.name + " (" + acc.address + ")\n" +
          "Typ: " + acc.type + "\n\n" +
          "Novy zustatek: " + newBal.toLocaleString("cs-CZ") + " Kc\n\n" +
          "Prevod byl zaslan na ucet " + acc.name + "."
        );
      }

      // /moje
      else if (text.startsWith("/moje")) {
        const bal = getBalance(userId);
        await sendMessage(chatId, "Tva historie bude dostupna po prvni tvorbe. Zustatek: " + bal.toLocaleString("cs-CZ") + " Kc. Napis /vytvor + popis!");
      }

      // /hodnoceni
      else if (text.startsWith("/hodnoceni")) {
        const rating = text.replace("/hodnoceni", "").trim();
        if (rating >= "1" && rating <= "5") {
          await sendMessage(chatId, "Dik za hodnoceni " + rating + "/5!");
        } else {
          await sendMessage(chatId, "Napis: /hodnoceni 1 az /hodnoceni 5");
        }
      }

      // /stav
      else if (text.startsWith("/stav")) {
        const bal = getBalance(userId);
        await sendMessage(chatId,
          "NULL ENGINE Stav:\n" +
          "Status: ONLINE 24/7\n" +
          "Backend: Base44 Serverless\n" +
          "Tvuj zustatek: " + bal.toLocaleString("cs-CZ") + " Kc\n" +
          "Bot bezi non-stop na Base44 infrastruktura."
        );
      }

      // Regular text
      else if (text && !text.startsWith("/")) {
        await sendMessage(chatId, "Ahoj " + userName + "! Napis /vytvor + co chces vytvorit. Napr: /vytvor hru hada nebo /schopnosti");
      }
    }

    return new Response(JSON.stringify({ ok: true }), { headers: { "Content-Type": "application/json" } });
  } catch (err) {
    return new Response(JSON.stringify({ ok: true, error: String(err) }), { headers: { "Content-Type": "application/json" } });
  }
});
