"""
ermp_core.templates – výchozí šablony ERMP aplikací.

Každá šablona je slovník s klíči:
  - name:         název šablony
  - description:  popis aplikace
  - html_skeleton: kompletní, funkční HTML/CSS/JS kód (self-contained)
"""

TEMPLATES = [
    {
        "name": "Snake Game",
        "description": "Jednoduchá hra had (Snake) v HTML/CSS/JS s ovládáním šipkami.",
        "html_skeleton": """<!DOCTYPE html>
<html lang="cs">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Snake Game</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  background: #1a1a2e;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  font-family: 'Segoe UI', Arial, sans-serif;
  color: #eee;
}
h1 { margin-bottom: 10px; color: #0f0; text-shadow: 0 0 10px #0f0; }
#score { font-size: 20px; margin-bottom: 10px; color: #feca57; }
canvas {
  border: 2px solid #16213e;
  border-radius: 8px;
  background: #0f0f1a;
  box-shadow: 0 0 30px rgba(0,255,0,0.15);
}
#controls {
  margin-top: 15px;
  display: flex;
  gap: 10px;
}
button {
  padding: 10px 24px;
  font-size: 16px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  background: #0f0;
  color: #1a1a2e;
  font-weight: bold;
  transition: transform 0.15s;
}
button:hover { transform: scale(1.05); }
#mobile-controls {
  display: none;
  margin-top: 15px;
  grid-template-areas:
    ". up ."
    "left . right"
    ". down .";
  gap: 5px;
}
#mobile-controls button {
  width: 60px; height: 60px; font-size: 22px;
  background: #16213e; color: #0f0;
}
#btnUp { grid-area: up; }
#btnDown { grid-area: down; }
#btnLeft { grid-area: left; }
#btnRight { grid-area: right; }
#gameOver {
  display: none;
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%,-50%);
  font-size: 28px;
  color: #ff6b6b;
  text-align: center;
  background: rgba(0,0,0,0.8);
  padding: 30px 50px;
  border-radius: 12px;
}
@media (max-width: 768px) {
  #mobile-controls { display: grid; }
}
</style>
</head>
<body>
<h1>🐍 Snake</h1>
<div id="score">Score: <span id="scoreVal">0</span></div>
<canvas id="game" width="400" height="400"></canvas>
<div id="gameOver">
  Game Over!<br>
  <button onclick="restart()">Hrát znovu</button>
</div>
<div id="mobile-controls">
  <button id="btnUp">▲</button>
  <button id="btnLeft">◀</button>
  <button id="btnRight">▶</button>
  <button id="btnDown">▼</button>
</div>
<div id="controls">
  <button onclick="restart()">Restart</button>
</div>
<p style="font-size:12px;color:#666;margin-top:10px;">Šipkami nebo WASD ovládej hada.</p>
<script>
var canvas = document.getElementById('game');
var ctx = canvas.getContext('2d');
var GRID = 20;
var CELL = canvas.width / GRID;
var snake, dx, dy, food, score, gameLoop, isOver;

function init() {
  snake = [{x:10,y:10}];
  dx = 1; dy = 0;
  score = 0;
  isOver = false;
  document.getElementById('scoreVal').textContent = score;
  document.getElementById('gameOver').style.display = 'none';
  placeFood();
  if (gameLoop) clearInterval(gameLoop);
  gameLoop = setInterval(tick, 100);
}

function placeFood() {
  food = {
    x: Math.floor(Math.random()*GRID),
    y: Math.floor(Math.random()*GRID)
  };
}

function tick() {
  var head = {x: snake[0].x + dx, y: snake[0].y + dy};
  // Srazit se se zdí
  if (head.x < 0 || head.x >= GRID || head.y < 0 || head.y >= GRID) {
    gameOver(); return;
  }
  // Srazit se sám se sebou
  for (var i = 0; i < snake.length; i++) {
    if (snake[i].x === head.x && snake[i].y === head.y) {
      gameOver(); return;
    }
  }
  snake.unshift(head);
  if (head.x === food.x && head.y === food.y) {
    score += 10;
    document.getElementById('scoreVal').textContent = score;
    placeFood();
  } else {
    snake.pop();
  }
  draw();
}

function draw() {
  ctx.fillStyle = '#0f0f1a';
  ctx.fillRect(0,0,canvas.width,canvas.height);
  // Food
  ctx.fillStyle = '#feca57';
  ctx.beginPath();
  ctx.arc(food.x*CELL + CELL/2, food.y*CELL + CELL/2, CELL/2-2, 0, Math.PI*2);
  ctx.fill();
  // Snake
  for (var i = 0; i < snake.length; i++) {
    if (i === 0) {
      ctx.fillStyle = '#0f0';
    } else {
      ctx.fillStyle = 'hsl('+(120+i*5)+',80%,'+(40 - i)+'%)';
    }
    ctx.fillRect(snake[i].x*CELL+1, snake[i].y*CELL+1, CELL-2, CELL-2);
  }
}

function gameOver() {
  isOver = true;
  clearInterval(gameLoop);
  document.getElementById('gameOver').style.display = 'block';
}

function restart() { init(); }

function setDir(nx, ny) {
  if (isOver) return;
  // Zabraň otočení do protisměru
  if (dx === -nx && dy === -ny) return;
  dx = nx; dy = ny;
}

document.addEventListener('keydown', function(e) {
  switch(e.key) {
    case 'ArrowUp': case 'w': case 'W': setDir(0,-1); break;
    case 'ArrowDown': case 's': case 'S': setDir(0,1); break;
    case 'ArrowLeft': case 'a': case 'A': setDir(-1,0); break;
    case 'ArrowRight': case 'd': case 'D': setDir(1,0); break;
  }
});

document.getElementById('btnUp').onclick = function(){setDir(0,-1);};
document.getElementById('btnDown').onclick = function(){setDir(0,1);};
document.getElementById('btnLeft').onclick = function(){setDir(-1,0);};
document.getElementById('btnRight').onclick = function(){setDir(1,0);};

init();
</script>
</body>
</html>""",
    },
    {
        "name": "Quiz App",
        "description": "Kvíz aplikace s 5 otázkami, skóre a hodnocením na konci.",
        "html_skeleton": """<!DOCTYPE html>
<html lang="cs">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Kvíz</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  background: linear-gradient(135deg, #667eea, #764ba2);
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  font-family: 'Segoe UI', Arial, sans-serif;
  color: #333;
}
.quiz-container {
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 10px 40px rgba(0,0,0,0.3);
  width: 90%;
  max-width: 500px;
  padding: 30px;
}
h1 { text-align: center; color: #667eea; margin-bottom: 10px; }
#progress {
  text-align: center;
  font-size: 14px;
  color: #999;
  margin-bottom: 20px;
}
#question {
  font-size: 22px;
  font-weight: 600;
  margin-bottom: 20px;
  min-height: 60px;
}
.options { display: flex; flex-direction: column; gap: 12px; }
.option {
  padding: 14px 20px;
  border: 2px solid #e0e0e0;
  border-radius: 10px;
  cursor: pointer;
  font-size: 16px;
  transition: all 0.2s;
  background: #fafafa;
}
.option:hover { border-color: #667eea; background: #f0f0ff; }
.option.correct {
  border-color: #28a745;
  background: #d4edda;
  color: #155724;
}
.option.wrong {
  border-color: #dc3545;
  background: #f8d7da;
  color: #721c24;
}
.option:disabled { cursor: default; }
#score-display {
  text-align: center;
  display: none;
}
#score-display h2 { font-size: 28px; margin-bottom: 10px; }
#score-display p { font-size: 18px; color: #666; margin-bottom: 20px; }
#restart-btn {
  display: block;
  margin: 20px auto 0;
  padding: 12px 32px;
  font-size: 18px;
  border: none;
  border-radius: 8px;
  background: #667eea;
  color: #fff;
  cursor: pointer;
  font-weight: bold;
  transition: transform 0.15s;
}
#restart-btn:hover { transform: scale(1.05); }
.feedback {
  text-align: center;
  margin-top: 15px;
  font-size: 16px;
  font-weight: bold;
  min-height: 24px;
}
</style>
</head>
<body>
<div class="quiz-container">
  <h1>🧠 Kvíz</h1>
  <div id="progress">Otázka 1 / 5</div>
  <div id="question"></div>
  <div class="options" id="options"></div>
  <div class="feedback" id="feedback"></div>
  <div id="score-display">
    <h2>🎉 Kvíz dokončen!</h2>
    <p id="final-score"></p>
    <p id="rating"></p>
    <button id="restart-btn" onclick="restart()">Hrát znovu</button>
  </div>
</div>
<script>
var questions = [
  {
    q: "Jaká je hlavní město České republiky?",
    options: ["Brno", "Praha", "Ostrava", "Plzeň"],
    answer: 1
  },
  {
    q: "Kolik planet je ve sluneční soustavě?",
    options: ["7", "8", "9", "10"],
    answer: 1
  },
  {
    q: "Kdo napsal román Babička?",
    options: ["Karel Čapek", "Božena Němcová", "Jan Neruda", "Jaroslav Seifert"],
    answer: 1
  },
  {
    q: "Jaký je chemický symbol pro zlato?",
    options: ["Au", "Ag", "Go", "Gd"],
    answer: 0
  },
  {
    q: "Který oceán je největší?",
    options: ["Atlantský", "Indický", "Tichý", "Severní ledový"],
    answer: 2
  }
];

var currentQ = 0;
var score = 0;
var answered = false;

function renderQuestion() {
  answered = false;
  var q = questions[currentQ];
  document.getElementById('progress').textContent =
    'Otázka ' + (currentQ + 1) + ' / ' + questions.length;
  document.getElementById('question').textContent = q.q;
  document.getElementById('feedback').textContent = '';
  var optsDiv = document.getElementById('options');
  optsDiv.innerHTML = '';
  q.options.forEach(function(opt, i) {
    var div = document.createElement('div');
    div.className = 'option';
    div.textContent = opt;
    div.onclick = function() { selectOption(i, div); };
    optsDiv.appendChild(div);
  });
}

function selectOption(idx, el) {
  if (answered) return;
  answered = true;
  var q = questions[currentQ];
  var allOpts = document.querySelectorAll('.option');
  allOpts.forEach(function(o) { o.style.pointerEvents = 'none'; });
  if (idx === q.answer) {
    el.classList.add('correct');
    score++;
    document.getElementById('feedback').textContent = '✅ Správně!';
    document.getElementById('feedback').style.color = '#28a745';
  } else {
    el.classList.add('wrong');
    allOpts[q.answer].classList.add('correct');
    document.getElementById('feedback').textContent = '❌ Špatně. Správná odpověď je označena zeleně.';
    document.getElementById('feedback').style.color = '#dc3545';
  }
  setTimeout(nextQuestion, 1500);
}

function nextQuestion() {
  currentQ++;
  if (currentQ < questions.length) {
    renderQuestion();
  } else {
    showScore();
  }
}

function showScore() {
  document.getElementById('progress').style.display = 'none';
  document.getElementById('question').style.display = 'none';
  document.getElementById('options').style.display = 'none';
  document.getElementById('feedback').style.display = 'none';
  document.getElementById('score-display').style.display = 'block';
  document.getElementById('final-score').textContent =
    'Skóre: ' + score + ' / ' + questions.length;
  var pct = (score / questions.length) * 100;
  var rating;
  if (pct === 100) rating = '🏆 Perfektní! Jsi génius!';
  else if (pct >= 80) rating = '🌟 Výborně! Máš to v malíčku!';
  else if (pct >= 60) rating = '👍 Dobré! Zkus to ještě jednou.';
  else if (pct >= 40) rating = '🙂 Solidní, ale jde to lépe.';
  else rating = '💪 Zkus to znovu, cvení dělá mistra!';
  document.getElementById('rating').textContent = rating;
}

function restart() {
  currentQ = 0;
  score = 0;
  document.getElementById('progress').style.display = 'block';
  document.getElementById('question').style.display = 'block';
  document.getElementById('options').style.display = 'flex';
  document.getElementById('feedback').style.display = 'block';
  document.getElementById('score-display').style.display = 'none';
  renderQuestion();
}

renderQuestion();
</script>
</body>
</html>""",
    },
    {
        "name": "Clicker Game",
        "description": "Klikací idle hra (clicker) – klikni pro body, kup vylepšení, zvyš příjem.",
        "html_skeleton": """<!DOCTYPE html>
<html lang="cs">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Cookie Clicker</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  background: linear-gradient(180deg, #2c1810, #4a2c1a);
  display: flex;
  flex-direction: column;
  align-items: center;
  min-height: 100vh;
  font-family: 'Segoe UI', Arial, sans-serif;
  color: #fff;
  padding: 20px;
}
h1 { margin: 10px 0; font-size: 32px; color: #f4a460; text-shadow: 0 2px 8px rgba(0,0,0,0.5); }
#counter {
  font-size: 48px;
  font-weight: bold;
  color: #ffd700;
  margin: 10px 0;
  text-shadow: 0 2px 10px rgba(255,215,0,0.3);
}
#per-sec {
  font-size: 16px;
  color: #aaa;
  margin-bottom: 20px;
}
#cookie {
  width: 200px; height: 200px;
  border-radius: 50%;
  background: radial-gradient(circle at 30% 30%, #d2691e, #8b4513);
  border: 6px solid #a0522d;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 80px;
  user-select: none;
  box-shadow: 0 8px 30px rgba(0,0,0,0.4), inset 0 -10px 20px rgba(0,0,0,0.3);
  transition: transform 0.1s;
  position: relative;
}
#cookie:hover { transform: scale(1.05); }
#cookie:active { transform: scale(0.95); }
.shop {
  margin-top: 30px;
  width: 100%;
  max-width: 400px;
  background: rgba(0,0,0,0.3);
  border-radius: 12px;
  padding: 20px;
}
.shop h2 { font-size: 20px; margin-bottom: 15px; color: #f4a460; }
.upgrade {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  margin-bottom: 8px;
  background: rgba(255,255,255,0.08);
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s;
}
.upgrade:hover { background: rgba(255,255,255,0.15); }
.upgrade.disabled { opacity: 0.4; cursor: not-allowed; }
.upgrade-info { flex: 1; }
.upgrade-name { font-weight: bold; font-size: 16px; }
.upgrade-desc { font-size: 12px; color: #aaa; }
.upgrade-cost { font-size: 14px; color: #ffd700; font-weight: bold; }
#click-power {
  font-size: 14px;
  color: #888;
  margin-top: 5px;
}
.float-text {
  position: absolute;
  font-size: 24px;
  font-weight: bold;
  color: #ffd700;
  pointer-events: none;
  animation: floatUp 1s ease-out forwards;
}
@keyframes floatUp {
  0% { opacity: 1; transform: translateY(0); }
  100% { opacity: 0; transform: translateY(-60px); }
}
</style>
</head>
<body>
<h1>🍪 Cookie Clicker</h1>
<div id="counter">0</div>
<div id="per-sec">0 / sec</div>
<div id="cookie" onclick="clickCookie()">🍪</div>
<div id="click-power">Síla kliku: 1</div>
<div class="shop">
  <h2>🛒 Obchod</h2>
  <div class="upgrade" onclick="buyUpgrade(0)">
    <div class="upgrade-info">
      <div class="upgrade-name">🖱️ Lepší klik</div>
      <div class="upgrade-desc">+1 k síle kliku</div>
    </div>
    <div class="upgrade-cost" id="cost0">15</div>
  </div>
  <div class="upgrade" onclick="buyUpgrade(1)">
    <div class="upgrade-info">
      <div class="upgrade-name">👵 Babička</div>
      <div class="upgrade-desc">+1 / sec</div>
    </div>
    <div class="upgrade-cost" id="cost1">100</div>
  </div>
  <div class="upgrade" onclick="buyUpgrade(2)">
    <div class="upgrade-info">
      <div class="upgrade-name">🏭 Továrna</div>
      <div class="upgrade-desc">+10 / sec</div>
    </div>
    <div class="upgrade-cost" id="cost2">500</div>
  </div>
  <div class="upgrade" onclick="buyUpgrade(3)">
    <div class="upgrade-info">
      <div class="upgrade-name">🏦 Banka</div>
      <div class="upgrade-desc">+50 / sec</div>
    </div>
    <div class="upgrade-cost" id="cost3">2000</div>
  </div>
  <div class="upgrade" onclick="buyUpgrade(4)">
    <div class="upgrade-info">
      <div class="upgrade-name">🚀 Raketoplán</div>
      <div class="upgrade-desc">+200 / sec</div>
    </div>
    <div class="upgrade-cost" id="cost4">10000</div>
  </div>
</div>
<script>
var cookies = 0;
var clickPower = 1;
var perSec = 0;

var upgrades = [
  { name: 'click', baseCost: 15, effect: 'click', amount: 1, owned: 0 },
  { name: 'grandma', baseCost: 100, effect: 'sec', amount: 1, owned: 0 },
  { name: 'factory', baseCost: 500, effect: 'sec', amount: 10, owned: 0 },
  { name: 'bank', baseCost: 2000, effect: 'sec', amount: 50, owned: 0 },
  { name: 'rocket', baseCost: 10000, effect: 'sec', amount: 200, owned: 0 }
];

function getCost(i) {
  return Math.floor(upgrades[i].baseCost * Math.pow(1.5, upgrades[i].owned));
}

function clickCookie(e) {
  cookies += clickPower;
  updateDisplay();
  // Floating text
  var cookie = document.getElementById('cookie');
  var rect = cookie.getBoundingClientRect();
  var ft = document.createElement('div');
  ft.className = 'float-text';
  ft.textContent = '+' + clickPower;
  ft.style.left = (rect.left + rect.width/2 - 20) + 'px';
  ft.style.top = (rect.top + 20) + 'px';
  ft.style.position = 'fixed';
  document.body.appendChild(ft);
  setTimeout(function() { ft.remove(); }, 1000);
}

function buyUpgrade(i) {
  var cost = getCost(i);
  if (cookies < cost) return;
  cookies -= cost;
  upgrades[i].owned++;
  if (upgrades[i].effect === 'click') {
    clickPower += upgrades[i].amount;
  } else {
    perSec += upgrades[i].amount;
  }
  updateDisplay();
}

function updateDisplay() {
  document.getElementById('counter').textContent = Math.floor(cookies).toLocaleString('cs');
  document.getElementById('per-sec').textContent = perSec + ' / sec';
  document.getElementById('click-power').textContent = 'Síla kliku: ' + clickPower;
  for (var i = 0; i < upgrades.length; i++) {
    var cost = getCost(i);
    document.getElementById('cost' + i).textContent = cost.toLocaleString('cs');
    var el = document.querySelectorAll('.upgrade')[i];
    if (cookies < cost) {
      el.classList.add('disabled');
    } else {
      el.classList.remove('disabled');
    }
  }
}

// Idle income
setInterval(function() {
  if (perSec > 0) {
    cookies += perSec / 10;
    updateDisplay();
  }
}, 100);

updateDisplay();
</script>
</body>
</html>""",
    },
]
