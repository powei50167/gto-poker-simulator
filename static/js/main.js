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

// 新增函數：根據玩家位置計算圓形佈局的座標
function positionPlayerSlots(players) {
    const container = document.getElementById('player-slots-container');
    const containerSize = container.offsetWidth; // 圓桌直徑 (600px in CSS)
    const center = containerSize / 2; // 圓心座標
    const radius = center * 0.8; // 佈局半徑 (稍微靠內一點)
    
    // 定義牌桌位置的順序和對應的弧度（假設有 6 個位置）
    // 角度從最下方開始 (270度 = -90度 = -pi/2), 逆時針分佈
    // UTG, MP, CO, BTN, SB, BB
    // 這裡我們假設玩家陣列的順序即為位置順序，並平均分佈
    const numPlayers = players.length;
    
    // 預定義的撲克位置角度（以 BB 在正下方為基準，逆時針排列）
    const positionAngles = {
        'BB': 0, // 0 點 (數學角度 270)
        'SB': 60, // 1 點
        'BTN': 120, // 2 點
        'CO': 180, // 3 點
        'MP': 240, // 4 點
        'UTG': 300 // 5 點
        // 如果有更多，請調整
    };

    players.forEach((p, index) => {
        const slot = document.getElementById(`player-slot-${p.position}`);
        if (!slot) return;
        
        let angleDeg = 0;
        
        if (positionAngles.hasOwnProperty(p.position)) {
            // 使用預定義的角度
            // 將角度轉換為數學座標系（0度在右，逆時針）
            // 這裡將撲克角度（0度在下，逆時針）轉換為 CSS top/left 所需的數學角度
            // 0度（BB）對應數學的 270度 = -90度
            angleDeg = 270 - positionAngles[p.position]; 
        } else {
            // 如果位置不在預定義列表中，則平均分佈
            angleDeg = 360 - (index * (360 / numPlayers)) - 90;
        }

        // 轉換為弧度
        const angleRad = angleDeg * (Math.PI / 180);

        // 計算座標 (x = r * cos(a), y = r * sin(a))
        const x = center + radius * Math.cos(angleRad);
        const y = center + radius * Math.sin(angleRad);
        
        // 玩家插槽寬度/高度
        const slotWidth = slot.offsetWidth;
        const slotHeight = slot.offsetHeight;

        // 調整座標讓玩家插槽居中於計算點
        slot.style.left = `${x - slotWidth / 2}px`;
        slot.style.top = `${y - slotHeight / 2}px`;
    });
}


// --- 渲染遊戲狀態 ---
function renderGameState(state) {
    document.getElementById('pot-size').textContent = `POT: $${state.pot_size}`;
    document.getElementById('community-cards').innerHTML = 
        state.community_cards.map(formatCard).join(' ');
    document.getElementById('current-position').textContent = state.action_position;
    
    const actionPlayer = state.players.find(p => p.position === state.action_position);
    
    // 渲染手牌 (只有當前行動的玩家會看到)
    document.getElementById('current-hand').innerHTML = actionPlayer ? actionPlayer.hand.map(formatCard).join(' ') : '--';
    
    // 更新 Call 按鈕狀態
    const toCall = actionPlayer ? state.current_bet - actionPlayer.in_pot : 0;
    const callBtn = document.getElementById('call-btn');
    callBtn.textContent = toCall <= 0 ? 'Check' : `Call $${toCall}`;
    callBtn.dataset.amount = toCall;

    // 渲染玩家狀態 - 必須先創建 DOM 元素才能定位
    let playerHtml = '';
    state.players.forEach(p => {
        const isActiveClass = p.is_active ? 'active' : 'folded';
        const isTurn = p.position === state.action_position ? 'is-turn' : '';
        // 為每個插槽添加唯一的 ID，以便定位
        playerHtml += `
            <div class="player-slot ${isActiveClass} ${isTurn}" id="player-slot-${p.position}">
                <strong>${p.position}</strong> (${p.name})<br>
                籌碼: $${p.chips} / In Pot: $${p.in_pot}
            </div>
        `;
    });
    document.getElementById('player-slots-container').innerHTML = playerHtml;
    
    // 調用新的定位函數
    positionPlayerSlots(state.players);
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
    
    // 確保視窗大小改變時重新定位（雖然牌桌是固定大小，但這是一個好的實踐）
    window.addEventListener('resize', () => {
        // 只有在 players-slots-container 有內容時才嘗試重新定位
        const players = Array.from(document.getElementById('player-slots-container').children).map(el => ({ position: el.id.replace('player-slot-', '') }));
        if (players.length > 0) {
            // 由於沒有 state.players 數據，這裡需要一個簡易的方法來獲取位置
            // 理想情況下應該從 state 重新獲取
             // 暫時不做 window resize 處理，避免沒有狀態數據時出錯
        }
    });
});