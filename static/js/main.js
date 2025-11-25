// 文件: static/js/main.js

const API_BASE = '/api';

// --- 輔助函數 ---
function formatCard(card) {
    // 將後端數據轉換為顯示格式 (e.g., A♠)
    const suits = { 's': '♠', 'h': '♥', 'd': '♦', 'c': '♣' };
    const suit = suits[card.suit] || '?';
    
    // 撲克花色顏色判斷
    const color = (card.suit === 'h' || card.suit === 'd') ? 'red' : 'black';
    
    return `<span style="color:${color};">${card.rank}${suit}</span>`;
}

// --- 渲染遊戲狀態 ---
function renderGameState(state) {
    document.getElementById('pot-size').textContent = `POT: $${state.pot_size}`;
    document.getElementById('community-cards').innerHTML = 
        state.community_cards.map(formatCard).join(' ');
    document.getElementById('current-position').textContent = state.action_position;
    
    const actionPlayer = state.players.find(p => p.position === state.action_position);
    
    // 渲染手牌 (只有當前行動的玩家會看到)
    document.getElementById('current-hand').innerHTML = actionPlayer.hand.map(formatCard).join(' ');
    
    // 更新 Call 按鈕狀態
    const toCall = state.current_bet - actionPlayer.in_pot;
    const callBtn = document.getElementById('call-btn');
    callBtn.textContent = toCall <= 0 ? 'Check' : `Call $${toCall}`;
    callBtn.dataset.amount = toCall;

    // 渲染玩家狀態
    let playerHtml = '';
    state.players.forEach(p => {
        const isActiveClass = p.is_active ? 'active' : 'folded';
        const isTurn = p.position === state.action_position ? 'is-turn' : '';
        playerHtml += `
            <div class="player-slot ${isActiveClass} ${isTurn}">
                <strong>${p.position}</strong> (${p.name})<br>
                籌碼: $${p.chips} / In Pot: $${p.in_pot}
            </div>
        `;
    });
    document.getElementById('player-slots-container').innerHTML = playerHtml;
}

// --- 渲染 GTO 反饋 ---
function renderFeedback(feedback) {
    const resultDiv = document.getElementById('feedback-result');
    const matrixBody = document.getElementById('gto-matrix-body');
    
    resultDiv.innerHTML = `
        <h3>您的行動評估</h3>
        <p class="${feedback.user_action_correct ? 'correct' : 'error'}">
            ${feedback.user_action_correct ? '✅ 符合 GTO' : '❌ 偏離 GTO'}
        </p>
        <p>EV Loss: <strong>${feedback.ev_loss_bb} BB</strong></p>
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

// --- API 呼叫 ---
async function fetchState() {
    try {
        const response = await fetch(`${API_BASE}/state`);
        const state = await response.json();
        renderGameState(state);
    } catch (error) {
        console.error("Error fetching state:", error);
    }
}

async function postAction(actionType, amount = 0) {
    const userAction = { action_type: actionType, amount: amount };

    try {
        const response = await fetch(`${API_BASE}/action`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(userAction)
        });

        const data = await response.json();
        
        if (!response.ok) {
            // 處理 FastAPI 返回的 HTTPException 錯誤
            alert(`錯誤: ${data.detail}`);
            return;
        }
        
        renderFeedback(data);
        
        // 行動後更新遊戲狀態
        await fetchState();

    } catch (error) {
        console.error("Error submitting action:", error);
        alert("提交行動時發生網路錯誤。");
    }
}

async function startNewHand() {
     try {
        // 重置反饋區
        document.getElementById('feedback-result').innerHTML = '';
        document.getElementById('gto-matrix-body').innerHTML = '';
        document.getElementById('error-explanation').textContent = '';
        
        const response = await fetch(`${API_BASE}/new_hand`, { method: 'POST' });
        const state = await response.json();
        renderGameState(state);
        console.log("新牌局已開始！");
    } catch (error) {
        console.error("Error starting new hand:", error);
        alert("無法開始新牌局。請檢查後端伺服器。");
    }
}


// --- 初始化和事件監聽 ---
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('start-hand-btn').addEventListener('click', startNewHand);
    
    // 處理 Fold 和 Call/Check
    document.getElementById('action-buttons').addEventListener('click', (event) => {
        const btn = event.target;
        const actionType = btn.dataset.type;
        
        if (!actionType) return;
        
        if (actionType === 'Fold') {
            postAction('Fold');
        } else if (actionType === 'Call') {
            const amount = parseInt(btn.dataset.amount);
            if (amount === 0) {
                postAction('Check');
            } else {
                postAction('Call', amount);
            }
        }
    });

    // 處理 Bet/Raise 提交
    document.getElementById('submit-bet-btn').addEventListener('click', () => {
        const amount = parseInt(document.getElementById('bet-amount-input').value);
        if (isNaN(amount) || amount <= 0) {
            alert("請輸入有效的下注金額。");
            return;
        }
        // 這裡簡化為 'Raise' (因為在目前的 Table 邏輯中，Bet 和 Raise 的處理相似)
        postAction('Raise', amount); 
    });

    // 首次載入時啟動新牌局
    startNewHand(); 
});