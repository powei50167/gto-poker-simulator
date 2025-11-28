// 文件: static/js/main.js

const API_BASE = '/api';

let lastAnalysisAvailable = false;

// 固定的 6 人牌桌座位 (1 號在最上方、4 號在最下方)
const SEAT_ORDER = [1, 2, 3, 4, 5, 6];

// 預定義的座位角度 (CSS 座標系：0 度在右，順時針增加)
const SEAT_ANGLES_CSS = {
    1: 270, // 頂部
    2: 330, // 右上
    3: 30,  // 右下
    4: 90,  // 底部
    5: 150, // 左下
    6: 210  // 左上
};

const STAGE_LABELS = {
    preflop: '翻前',
    flop: '翻牌',
    turn: '轉牌',
    river: '河牌',
    showdown: '攤牌'
};


// --- 輔助函數 ---
function formatCard(card) {
    const suits = { 's': '♠', 'h': '♥', 'd': '♦', 'c': '♣' };
    const suit = suits[card.suit] || '?';
    const color = (card.suit === 'h' || card.suit === 'd') ? 'red' : 'black';
    return `<span class="card-face ${color}">${card.rank}${suit}</span>`;
}

function buildHandHtml(hand) {
    if (!hand || !hand.length) return '';
    const cards = hand.map(card => `<div class="card-slot small">${formatCard(card)}</div>`).join('');
    return `<div class="player-hand">${cards}</div>`;
}

function resetFeedbackDisplay() {
    document.getElementById('feedback-result').innerHTML = '';
    document.getElementById('gto-matrix-body').innerHTML = '';
    document.getElementById('error-explanation').textContent = '';
}

function updateAnalysisButton() {
    const analyzeBtn = document.getElementById('analyze-last-btn');
    if (!analyzeBtn) return;
    analyzeBtn.disabled = !lastAnalysisAvailable;
    analyzeBtn.textContent = lastAnalysisAvailable ? '分析上一手 GTO' : '尚無可分析行動';
}

// 函數：根據位置計算圓形佈局的座標 (使用百分比和位移)
function positionPlayerSlots() {
    // 圓心在 50% / 50%
    const centerPercent = 50; 
    // 調整半徑百分比，使其更靠近圓桌邊緣
    const radiusPercent = 45; 
    
    SEAT_ORDER.forEach(seat => {
        const slot = document.getElementById(`player-slot-seat${seat}`);
        if (!slot) return;

        let angleDeg = SEAT_ANGLES_CSS[seat] || 0;
        
        // 轉換為弧度
        const angleRad = angleDeg * (Math.PI / 180);

        // 計算中心點座標 (使用百分比)
        // COS 配合 LEFT (X 軸)
        const xPercent = centerPercent + radiusPercent * Math.cos(angleRad);
        // SIN 配合 TOP (Y 軸) - 順時針角度
        const yPercent = centerPercent + radiusPercent * Math.sin(angleRad);

        // 設置 left/top (使用百分比)
        slot.style.left = `${xPercent}%`;
        slot.style.top = `${yPercent}%`;
        
        // 使用 translate 抵消自身的 50% 寬高，實現精確居中
        slot.style.transform = `translate(-50%, -50%)`;
    });
}


// --- 渲染遊戲狀態 (修改為固定 6 個位置的渲染邏輯) ---
function renderGameState(state) {
    document.getElementById('pot-size').textContent = `POT: $${state.pot_size}`;
    document.getElementById('community-cards').innerHTML =
        state.community_cards.length
            ? state.community_cards.map(formatCard).join('')
            : '<span class="card-face placeholder">--</span>';
    document.getElementById('stage-label').textContent = state.current_stage.toUpperCase();
    document.getElementById('current-position').textContent = state.action_position;
    document.getElementById('hand-status').textContent = state.hand_over ? '牌局已結束，請開始新局。' : '輪到您行動。';

    const heroPlayer = state.players.find(p => p.name.toLowerCase() === 'hero');
    const actionPlayer = state.players.find(p => p.position === state.action_position);
    const isHeroTurn = !!(heroPlayer && heroPlayer.position === state.action_position && !state.hand_over);
    const disableActions = state.hand_over || !isHeroTurn;
    toggleActionAvailability(disableActions);

    // 更新 Call 按鈕狀態
    const heroCommit = heroPlayer ? heroPlayer.current_round_bet || 0 : 0;
    const heroStack = heroPlayer ? heroPlayer.chips || 0 : 0;
    const maxTotal = heroCommit + heroStack;
    const toCallRaw = Math.max(state.current_bet - heroCommit, 0);
    const toCall = Math.min(toCallRaw, maxTotal);
    const callBtn = document.getElementById('call-btn');
    const callLabelPrefix = toCallRaw > heroStack ? '跟注 / 全下' : '跟注';
    callBtn.textContent = `${callLabelPrefix} ($${Math.max(toCall, 0)})`;
    callBtn.dataset.amount = toCall;
    callBtn.disabled = toCall <= 0 || disableActions;

    const checkBtn = document.getElementById('check-btn');
    if (checkBtn) {
        checkBtn.disabled = toCall > 0 || disableActions;
    }

    const allInBtn = document.getElementById('allin-btn');
    if (allInBtn) {
        allInBtn.textContent = `全下 (All-in $${heroStack})`;
        allInBtn.disabled = disableActions || heroStack <= 0;
    }

    const betInput = document.getElementById('bet-amount-input');
    if (betInput) {
        betInput.max = maxTotal;
        const currentValue = parseInt(betInput.value) || 0;
        const clampedValue = Math.min(Math.max(currentValue, 1), maxTotal);
        betInput.value = clampedValue;
    }

    // 以座位為鍵記錄翻牌後揭露的手牌
    const revealedHandsMap = new Map();
    (state.opponent_hands || []).forEach(opp => {
        revealedHandsMap.set(opp.seat_number, opp.hand);
    });

    // 將後端返回的活躍玩家數據轉換為以座位為鍵的 Map
    const activePlayersMap = new Map(state.players.map(p => [p.seat_number, p]));

    let playerHtml = '';

    // 遍歷所有固定位置，渲染插槽
    SEAT_ORDER.forEach(seat => {
        const p = activePlayersMap.get(seat);
        
        let slotContent;
        let slotClass;

        const handToShow = p && p.hand && p.hand.length
            ? p.hand
            : revealedHandsMap.get(seat) || [];

        if (p) {
            // 活躍玩家
            const isTurn = p.position === state.action_position;

            slotClass = p.is_active ? 'active' : 'folded';
            if (isTurn) {
                slotClass += ' is-turn';
            }

            const handHtml = buildHandHtml(handToShow);
            slotContent = `
                <div class="player-info">
                    <strong>Seat ${p.seat_number}【${p.position}】</strong>  ${p.name}
                   <div class="info-row">
                        <span>籌碼: $${p.chips}</span>
                        <span class="in-pot-badge">In Pot: $${p.in_pot}</span>
                    </div>
                </div>
                ${handHtml}
            `;
        } else {
            // 閒置位置
            slotClass = 'idle';
            slotContent = `
                <strong>Seat ${seat}</strong><br>
                <span style="font-size:12px;">(空閒)</span>
            `;
        }

        playerHtml += `
            <div class="player-slot ${slotClass}" id="player-slot-seat${seat}">
                ${slotContent}
            </div>
        `;
    });
    
    document.getElementById('player-slots-container').innerHTML = playerHtml;
    

    // 調用定位函數
    positionPlayerSlots();
    renderActionLog(state.action_log || []);
    renderHandResult(state.hand_result, state.hand_over);
}

// --- 渲染 GTO 反饋 (保持不變) ---
function renderFeedback(feedback) {
    const resultDiv = document.getElementById('feedback-result');
    const matrixBody = document.getElementById('gto-matrix-body');
    
    resultDiv.innerHTML = `
        <h3>您的行動評估</h3>
        <p class="${feedback.user_action_correct ? 'correct' : 'error'}">
            ${feedback.user_action_correct ? '✅ 符合 GTO' : '❌ 偏離 GTO'}
        </p>
        <p>EV Loss: <strong>${feedback.ev_loss_bb} </strong></p>
    `;
    document.getElementById('error-explanation').textContent = feedback.explanation;

    // 渲染 GTO 矩陣
    matrixBody.innerHTML = feedback.gto_matrix.map(item => `
        <tr>
            <td>${item.action}</td>
            <td>${(item.frequency * 100).toFixed(1)}%</td>
            <td>${item.ev_bb.toFixed(2)}</td>
        </tr>
    `).join('');
}

// --- API 呼叫 (保持不變) ---
async function fetchState() {
    try {
        const response = await fetch(`${API_BASE}/state`);
        const state = await response.json();
        renderGameState(state);
    } catch (error) {
        console.error("Error fetching state:", error);
    }
}


function renderActionLog(logEntries) {
    const container = document.getElementById('action-log');
    if (!container) return;

    if (!logEntries.length) {
        container.innerHTML = '<p>尚無行動紀錄。</p>';
        return;
    }

    const stageOrder = ['preflop', 'flop', 'turn', 'river', 'showdown'];
    const groupedHtml = stageOrder.map(stage => {
        const entries = logEntries.filter(entry => entry.stage === stage);
        if (!entries.length) return '';

        const stageLabel = STAGE_LABELS[stage] || stage.toUpperCase();
        const entryHtml = entries.map(entry => {
            const amountPart = entry.amount > 0 ? ` $${entry.amount}` : '';
            const isHero = entry.name.toLowerCase() === 'hero';
            const heroClass = isHero ? ' hero-action' : '';
            return `<div class="action-entry${heroClass}"><span class="actor">Seat ${entry.seat_number} ${entry.position} (${entry.name})</span>：<span class="action-type">${entry.action}</span>${amountPart}</div>`;
        }).join('');

        return `
            <div class="action-stage">
                <div class="stage-title">${stageLabel}</div>
                <div class="stage-entries">${entryHtml}</div>
            </div>
        `;
    }).join('');

    container.innerHTML = groupedHtml;
    container.scrollTop = container.scrollHeight;
}

function renderHandResult(result, handOver) {
    const container = document.getElementById('hand-result');
    if (!container) return;

    if (!handOver) {
        container.textContent = '本局尚未結束。';
        return;
    }

    if (!result) {
        container.textContent = '牌局結束，未能計算結果。';
        return;
    }

    container.innerHTML = `
        <p>${result.description}</p>
        <p><strong>Seat ${result.seat_number}</strong> (${result.position}) – 獲得 $${result.amount_won}</p>
    `;
}

function toggleActionAvailability(disabled) {
    const actionable = document.querySelectorAll('#action-buttons button, #submit-bet-btn, #bet-amount-input');
    actionable.forEach(btn => {
        btn.disabled = disabled;
    });
}

async function fetchLastFeedback() {
    try {
        const response = await fetch(`${API_BASE}/analyze_last_action`);
        const data = await response.json();

        if (!response.ok) {
            alert(`錯誤: ${data.detail || '無法取得上一手分析。'}`);
            return;
        }

        renderFeedback(data);
        lastAnalysisAvailable = false;
        updateAnalysisButton();
    } catch (error) {
        console.error('Error fetching last feedback:', error);
        alert('取得上一手 GTO 分析時發生錯誤。');
    }
}

async function postAction(actionType, amount = 0) {
    const userAction = { action_type: actionType, amount: amount };
    toggleActionAvailability(true);

    try {
        const response = await fetch(`${API_BASE}/action`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(userAction)
        });

        const data = await response.json();

        if (!response.ok) {
            alert(`錯誤: ${data.detail}`);
            return;
        }

        lastAnalysisAvailable = true;
        updateAnalysisButton();

    } catch (error) {
        console.error("Error submitting action:", error);
        alert("提交行動時發生網路錯誤。");
    } finally {
        await fetchState();
    }
}

async function startNewHand() {
     try {
        // 重置反饋區與上一手分析狀態
        resetFeedbackDisplay();
        lastAnalysisAvailable = false;
        updateAnalysisButton();

        const response = await fetch(`${API_BASE}/new_hand`, { method: 'POST' });
        const state = await response.json();
        renderGameState(state);
        console.log("新牌局已開始！");
    } catch (error) {
        console.error("Error starting new hand:", error);
        alert("無法開始新牌局。請檢查後端伺服器。");
    }
}


// --- 初始化和事件監聽 (保持不變) ---
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('start-hand-btn').addEventListener('click', startNewHand);
    document.getElementById('analyze-last-btn').addEventListener('click', fetchLastFeedback);

    // 處理 Fold 和 Call/Check
    document.getElementById('action-buttons').addEventListener('click', (event) => {
        const btn = event.target;
        const actionType = btn.dataset.type;

        if (!actionType) return;

        if (actionType === 'Fold') {
            postAction('Fold');
        } else if (actionType === 'Check') {
            postAction('Check');
        } else if (actionType === 'Call') {
            const amount = parseInt(btn.dataset.amount);
            if (isNaN(amount) || amount <= 0) {
                alert('目前無需跟注。');
                return;
            }
            postAction('Call', amount);
        }
    });

    // 處理 Bet/Raise 提交
    document.getElementById('submit-bet-btn').addEventListener('click', () => {
        const betInput = document.getElementById('bet-amount-input');
        const amount = parseInt(betInput.value);
        const max = parseInt(betInput.max) || amount;
        const sanitizedAmount = Math.min(Math.max(amount, 1), max);

        if (isNaN(sanitizedAmount) || sanitizedAmount <= 0) {
            alert("請輸入有效的下注金額。");
            return;
        }
        betInput.value = sanitizedAmount;
        postAction('Raise', sanitizedAmount);
    });

    const allInBtn = document.getElementById('allin-btn');
    allInBtn.addEventListener('click', () => {
        postAction('AllIn');
    });

    updateAnalysisButton();

    // 首次載入時啟動新牌局
    // startNewHand();
});
