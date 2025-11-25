// 文件: static/js/main.js

const API_BASE = '/api';

// 固定的 6 人牌桌位置順序
const FIXED_POSITIONS = ['BB', 'SB', 'BTN', 'CO', 'MP', 'UTG'];

// 預定義的撲克位置角度 (CSS 座標系：0度在右，順時針增加)
// 角度根據圖像的對稱佈局進行精確定義 (60度間隔)
const POSITION_ANGLES_CSS = {
    'BB': 270,    // 頂部中心 (向上)
    'SB': 210,    // 左上
    'BTN': 150,   // 左下
    'CO': 90,     // 底部中心 (向下)
    'MP': 30,     // 右下
    'UTG': 330    // 右上
};


// --- 輔助函數 ---
function formatCard(card) {
    const suits = { 's': '♠', 'h': '♥', 'd': '♦', 'c': '♣' };
    const suit = suits[card.suit] || '?';
    const color = (card.suit === 'h' || card.suit === 'd') ? 'red' : 'black';
    return `<span style="color:${color};">${card.rank}${suit}</span>`;
}

// 函數：根據位置計算圓形佈局的座標 (使用百分比和位移)
function positionPlayerSlots() {
    // 圓心在 50% / 50%
    const centerPercent = 50; 
    // 調整半徑百分比，使其更靠近圓桌邊緣
    const radiusPercent = 45; 
    
    FIXED_POSITIONS.forEach(position => {
        const slot = document.getElementById(`player-slot-${position}`);
        if (!slot) return;
        
        let angleDeg = POSITION_ANGLES_CSS[position] || 0;
        
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
        state.community_cards.map(formatCard).join(' ');
    document.getElementById('current-position').textContent = state.action_position;
    
    const actionPlayer = state.players.find(p => p.position === state.action_position);
    
    // 渲染手牌
    const handDisplay = document.getElementById('current-hand');
    if (actionPlayer) {
        const cardHtml = actionPlayer.hand.map(card => {
            const formatted = formatCard(card);
            return `<div class="card-slot">${formatted}</div>`;
        }).join('');
        handDisplay.innerHTML = cardHtml;
    } else {
         // 如果沒有玩家信息（例如剛開始牌局），顯示問號卡背
        handDisplay.innerHTML = `
            <div class="card-slot">?</div>
            <div class="card-slot">?</div>
        `;
    }
    
    // 更新 Call 按鈕狀態
    const toCall = actionPlayer ? state.current_bet - actionPlayer.in_pot : 0;
    const callBtn = document.getElementById('call-btn');
    callBtn.textContent = toCall <= 0 ? 'Check' : `Call $${toCall}`;
    callBtn.dataset.amount = toCall;

    // 將後端返回的活躍玩家數據轉換為以 position 為鍵的 Map
    const activePlayersMap = new Map(state.players.map(p => [p.position, p]));

    let playerHtml = '';
    
    // 遍歷所有固定位置，渲染插槽
    FIXED_POSITIONS.forEach(position => {
        const p = activePlayersMap.get(position); 
        
        let slotContent;
        let slotClass;

        if (p) {
            // 活躍玩家
            const isTurn = p.position === state.action_position;
            
            slotClass = p.is_active ? 'active' : 'folded';
            if (isTurn) {
                slotClass += ' is-turn';
            }
            
            slotContent = `
                <strong>${p.position}</strong> (${p.name})<br>
                籌碼: $${p.chips} / In Pot: $${p.in_pot}
            `;
        } else {
            // 閒置位置
            slotClass = 'idle';
            slotContent = `
                <strong>${position}</strong><br>
                <span style="font-size:12px;">(空閒)</span>
            `;
        }
        
        playerHtml += `
            <div class="player-slot ${slotClass}" id="player-slot-${position}">
                ${slotContent}
            </div>
        `;
    });
    
    document.getElementById('player-slots-container').innerHTML = playerHtml;
    
    // 調用定位函數
    positionPlayerSlots();
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
            alert(`錯誤: ${data.detail}`);
            return;
        }
        
        renderFeedback(data);
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


// --- 初始化和事件監聽 (保持不變) ---
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
        postAction('Raise', amount); 
    });

    // 首次載入時啟動新牌局
    startNewHand(); 
});