// 文件: static/js/main.js

const API_BASE = '/api';

let lastAnalysisAvailable = false;
let explanationCollapsed = true;
let lastPlayersCache = [];
let customHandPanelVisible = false;
let customHandEnabled = false;
let currentTableSize = 6;
let currentSeatOrder = [];
let currentSeatAngles = {};
const scenarioHandSelection = { activeSuit: 's', selectedCards: [] };

const TABLE_LAYOUTS = {
    6: {
        seatOrder: [1, 2, 3, 4, 5, 6],
        seatAngles: {
            1: 270, // 頂部
            2: 330, // 右上
            3: 15,  // 右下
            4: 90,  // 底部
            5: 165, // 左下
            6: 210  // 左上
        },
    },
    9: {
        seatOrder: [1, 2, 3, 4, 5, 6, 7, 8, 9],
        seatAngles: {
            1: 270, // 頂部
            2: 310, // 右上
            3: 350, // 右側偏上
            4: 30,  // 右側偏下
            5: 70,  // 右下
            6: 90,  // 底部偏右 (Hero)
            7: 150, // 左下
            8: 200, // 左側偏下
            9: 240  // 左側偏上
        },
    },
};

const STAGE_LABELS = {
    preflop: '翻前',
    flop: '翻牌',
    turn: '轉牌',
    river: '河牌',
    showdown: '攤牌'
};

const POSITION_OPTIONS = [
    'BTN', 'SB', 'BB', 'UTG', 'UTG+1', 'UTG+2', 'MP', 'LJ', 'HJ', 'CO'
];

function applyTableLayout(tableSize, seatOrderFromState = []) {
    const layout = TABLE_LAYOUTS[tableSize] || TABLE_LAYOUTS[6];
    currentTableSize = layout === TABLE_LAYOUTS[tableSize] ? tableSize : 6;
    currentSeatOrder = Array.isArray(seatOrderFromState) && seatOrderFromState.length
        ? seatOrderFromState
        : [...layout.seatOrder];
    currentSeatAngles = layout.seatAngles;
    updateTableToggleLabel();
    updateTableBadge();
}

function updateTableToggleLabel() {
    const toggleBtn = document.getElementById('toggle-table-size-btn');
    if (!toggleBtn) return;
    const targetSize = currentTableSize === 9 ? 6 : 9;
    toggleBtn.textContent = `切換為 ${targetSize} 人桌`;
}

function updateTableBadge() {
    const badge = document.getElementById('table-size-badge');
    if (!badge) return;
    const descriptor = currentTableSize === 9 ? '全環桌 · 9 人佈局' : '短桌 · 6 人佈局';
    badge.textContent = `${currentTableSize} 人桌｜${descriptor}`;
}


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
    const explanationBox = document.getElementById('error-explanation');
    const toggleBtn = document.getElementById('toggle-explanation-btn');
    if (explanationBox) {
        explanationBox.innerHTML = '';
        explanationBox.classList.add('collapsed');
    }
    if (toggleBtn) {
        toggleBtn.textContent = '展開詳解';
    }
    explanationCollapsed = true;
}

function updateAnalysisButton() {
    const analyzeBtn = document.getElementById('analyze-last-btn');
    if (!analyzeBtn) return;
    analyzeBtn.disabled = !lastAnalysisAvailable;
    analyzeBtn.textContent = lastAnalysisAvailable ? '分析上一手 GTO' : '尚無可分析行動';
}

function updateCustomHandPanelVisibility() {
    const panel = document.getElementById('custom-hand-panel');
    const triggerBtn = document.getElementById('open-custom-hand-btn');
    const shouldShow = customHandEnabled && customHandPanelVisible;

    if (panel) {
        panel.classList.toggle('visible', shouldShow);
    }

    if (triggerBtn) {
        triggerBtn.textContent = shouldShow ? '收合手牌設定' : '設定手牌';
    }
}

function setCustomHandAvailability(enabled) {
    customHandEnabled = enabled;
    if (!enabled) {
        customHandPanelVisible = false;
    }

    const triggerBtn = document.getElementById('open-custom-hand-btn');
    const setHandBtn = document.getElementById('set-hand-btn');

    [triggerBtn, setHandBtn].forEach(btn => {
        if (!btn) return;
        btn.disabled = !enabled;
        btn.title = enabled ? '' : '請先開始新牌局後再設定手牌。';
    });

    updateCustomHandPanelVisibility();
}

// 函數：根據位置計算圓形佈局的座標 (使用百分比和位移)
function positionPlayerSlots() {
    // 圓心在 50% / 50%
    const centerPercent = 50;
    // 調整半徑百分比，使其更靠近圓桌邊緣
    const radiusPercent = currentTableSize === 6 ? 75 : 65;

    currentSeatOrder.forEach(seat => {
        const slot = document.getElementById(`player-slot-seat${seat}`);
        if (!slot) return;

        let angleDeg = currentSeatAngles[seat] || 0;

        // 轉換為弧度
        const angleRad = angleDeg * (Math.PI / 180);
        let radius = radiusPercent;

        const isHeroSlot = slot.classList.contains('hero-seat');

        // ⭐ 例如 seat1 是最上方 → 向圓心靠近 4%
        if (seat === 1) {
            radius -= 8;   // 想靠更多就改大，例如 6、8
        }
        if (seat === 2 || seat === 3) {
            radius += 8;   // 向外擴 4%（可調 2~10）
        }

        if (seat === 5 || seat === 6) {
            radius += 8;   // 向外擴 4%（可調 2~10）
        }
        if (seat === 4) {
            radius -= 18;   // 向外擴 4%（可調 2~10）
        }

        // 計算中心點座標 (使用百分比)
        // COS 配合 LEFT (X 軸)
        const xPercent = centerPercent + radius * Math.cos(angleRad);
        // SIN 配合 TOP (Y 軸) - 順時針角度
        const yPercent = centerPercent + radius * Math.sin(angleRad);

        // 設置 left/top (使用百分比)
        slot.style.left = `${xPercent}%`;
        slot.style.top = `${yPercent}%`;
        
        // 使用 translate 抵消自身的 50% 寬高，實現精確居中
        slot.style.transform = `translate(-50%, -50%)`;
    });
}

function updateHandSelectOptions(players) {
    const select = document.getElementById('hand-player-select');
    if (!select) return;

    const previousValue = select.value;
    const optionsHtml = players.map(p => `
        <option value="${p.name}">${p.name} (Seat ${p.seat_number})</option>
    `).join('');
    select.innerHTML = optionsHtml;

    const hasPrevious = players.some(p => p.name === previousValue);
    if (hasPrevious) {
        select.value = previousValue;
        return;
    }

    const heroPlayer = players.find(p => p.name.toLowerCase() === 'hero');
    if (heroPlayer) {
        select.value = heroPlayer.name;
    } else if (players.length) {
        select.value = players[0].name;
    }
}


// --- 渲染遊戲狀態 (修改為固定 6 個位置的渲染邏輯) ---
function renderGameState(state) {
    lastPlayersCache = state.players || [];
    applyTableLayout(state.table_size || currentTableSize, state.seat_order);
    setCustomHandAvailability(customHandEnabled && !state.hand_over);
    updateHandSelectOptions(lastPlayersCache);
    document.getElementById('pot-size').textContent = `POT: $${state.pot_size}`;
    document.getElementById('community-cards').innerHTML =
        state.community_cards.length
            ? state.community_cards.map(formatCard).join('')
            : '<span class="card-face placeholder">--</span>';
    const stageLabel = STAGE_LABELS[state.current_stage] || state.current_stage?.toUpperCase() || '--';
    document.getElementById('stage-label').textContent = stageLabel;
    const tableIdEl = document.getElementById('table-id');
    if (tableIdEl) {
        tableIdEl.textContent = state.hand_id ? `#${state.hand_id}` : '尚未產生';
    }
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
    currentSeatOrder.forEach(seat => {
        const p = activePlayersMap.get(seat);
        
        let slotContent;
        let slotClass;

        const handToShow = p && p.hand && p.hand.length
            ? p.hand
            : revealedHandsMap.get(seat) || [];

        if (p) {
            // 活躍玩家
            const isTurn = p.position === state.action_position;
            const isHero = p.name.toLowerCase() === 'hero';

            slotClass = p.is_active ? 'active' : 'folded';
            if (isTurn) {
                slotClass += ' is-turn';
            }
            if (isHero) {
                slotClass += ' hero-seat';
            }

            const handHtml = buildHandHtml(handToShow);
            const statusPill = p.is_active
                ? '<span class="status-pill in-hand">在局中</span>'
                : '<span class="status-pill folded">已棄牌</span>';
            const turnBadge = isTurn ? '<span class="turn-indicator">輪到此位</span>' : '';
            const heroBadge = isHero ? '<span class="status-pill hero">Hero</span>' : '';

            slotContent = isHero
                ? `
                    <div class="hero-slot">
                        <div class="hero-info">
                            <div class="seat-header">
                                <div class="seat-label">Seat ${p.seat_number}</div>
                                <div class="position-pill">${p.position}</div>
                                ${heroBadge}
                            </div>
                            <div class="player-name-row">
                                <span class="player-name">${p.name}</span>
                                ${turnBadge}
                            </div>
                            <div class="stack-row">
                                <span class="stack-chip">籌碼 $${p.chips}</span>
                                <span class="stack-pot">進池 $${p.in_pot}</span>
                            </div>
                        </div>
                        <div class="hero-hand">
                            <div class="hand-wrapper">${handHtml}</div>
                        </div>
                    </div>
                `
                : `
                    <div class="seat-header">
                        <div class="seat-label">Seat ${p.seat_number}</div>
                        <div class="position-pill">${p.position}</div>
                        ${heroBadge}
                    </div>
                    <div class="player-name-row">
                        <span class="player-name">${p.name}</span>
                        ${turnBadge}
                    </div>
                    <div class="stack-row">
                        <span class="stack-chip">籌碼 $${p.chips}</span>
                        <span class="stack-pot">進池 $${p.in_pot}</span>
                    </div>
                    <div class="hand-wrapper">${handHtml}</div>
                    <div class="status-row">${statusPill}</div>
                `;
        } else {
            // 閒置位置
            slotClass = 'idle';
            slotContent = `
                <div class="seat-header">
                    <div class="seat-label">Seat ${seat}</div>
                    <div class="position-pill idle">未入座</div>
                </div>
                <div class="empty-seat">等待玩家</div>
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

    const matrixData = Array.isArray(feedback.gto_matrix) ? [...feedback.gto_matrix] : [];
    const sortedMatrix = [...matrixData].sort((a, b) => b.frequency - a.frequency);
    const topAction = sortedMatrix[0];
    const topEv = [...sortedMatrix].sort((a, b) => b.ev_bb - a.ev_bb)[0];

    const statusTag = feedback.user_action_correct
        ? '<span class="tag success">GTO</span>'
        : '<span class="tag error">偏離</span>';

    resultDiv.innerHTML = `
        <div class="summary-card">
            <h4>行動檢查</h4>
            <div class="meta">${statusTag} ${feedback.user_action_correct ? '選擇與 GTO 一致' : '與 GTO 建議不同'}</div>
            <div class="caption">即時標示行動是否符合策略</div>
        </div>
        <div class="summary-card">
            <h4>EV 損失</h4>
            <div class="meta"><span class="tag neutral">${feedback.ev_loss_bb} BB</span></div>
            <div class="caption">顯示此行動相對 GTO 的期望值差距</div>
        </div>
        <div class="summary-card">
            <h4>優先採用</h4>
            <div class="meta">${topAction ? `${topAction.action} · ${(topAction.frequency * 100).toFixed(1)}%` : '無資料'}</div>
            <div class="caption">最高頻率建議。最高 EV: ${topEv ? `${topEv.action} (${topEv.ev_bb.toFixed(2)} BB)` : '無資料'}</div>
        </div>
    `;

    // 渲染 GTO 矩陣
    matrixBody.innerHTML = sortedMatrix.map(item => `
        <tr>
            <td>${item.action}</td>
            <td>${(item.frequency * 100).toFixed(1)}%</td>
            <td>${item.ev_bb.toFixed(2)}</td>
        </tr>
    `).join('');

    renderExplanation(feedback.explanation);
}

function renderExplanation(explanationText) {
    const explanationBox = document.getElementById('error-explanation');
    const toggleBtn = document.getElementById('toggle-explanation-btn');
    if (!explanationBox || !toggleBtn) return;

    const paragraphs = (explanationText || '')
        .split(/\n{2,}/)
        .map(p => p.trim())
        .filter(Boolean);

    explanationBox.innerHTML = paragraphs.length
        ? paragraphs.map(p => `<p>${p.replace(/\n/g, '<br>')}</p>`).join('')
        : '<p>尚無詳細解說。</p>';

    const shouldCollapse = explanationBox.textContent.length > 240;
    explanationCollapsed = shouldCollapse;
    explanationBox.classList.toggle('collapsed', shouldCollapse);
    toggleBtn.textContent = shouldCollapse ? '展開詳解' : '收合詳解';
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

function normalizeCardInput(value) {
    const trimmed = (value || '').trim();
    if (trimmed.length < 2) return trimmed;
    return trimmed[0].toUpperCase() + trimmed[1].toLowerCase();
}

function buildPositionOptions(selectedValue = '') {
    return POSITION_OPTIONS.map(pos => `
        <option value="${pos}" ${selectedValue === pos ? 'selected' : ''}>${pos}</option>
    `).join('');
}

function createOpponentRow(index = 1) {
    const wrapper = document.createElement('div');
    wrapper.className = 'opponent-row';
    wrapper.innerHTML = `
        <div>
            <label>對手名稱</label>
            <input type="text" class="opponent-name" placeholder="Villain${index}">
        </div>
        <div>
            <label>位置</label>
            <select class="opponent-position">${buildPositionOptions()}</select>
        </div>
        <div>
            <label>手牌 (可空白)</label>
            <input type="text" class="opponent-hand" placeholder="9h 9s">
        </div>
    `;
    return wrapper;
}

function parseCardsFromInput(inputValue) {
    const tokens = (inputValue || '')
        .split(/\s+/)
        .map(normalizeCardInput)
        .filter(Boolean);
    return tokens;
}

function parseActionLines(textValue, stage, positionNameMap) {
    const lines = (textValue || '').split(/\n+/).map(l => l.trim()).filter(Boolean);
    return lines.map(line => {
        const parts = line.split(/\s+/);
        const position = parts[0] || '';
        const action = parts[1] || '';
        const amount = parseInt(parts[2]) || 0;
        return {
            stage,
            position,
            name: positionNameMap.get(position) || position || 'Villain',
            action,
            amount,
        };
    });
}

function setScenarioHandInputValue(cards) {
    const heroHandInput = document.getElementById('scenario-hero-hand');
    if (!heroHandInput) return;
    heroHandInput.value = cards.join(' ');
}

function renderScenarioHandSelection() {
    const container = document.getElementById('scenario-selected-cards');
    if (!container) return;

    if (!scenarioHandSelection.selectedCards.length) {
        container.textContent = '點擊花色與牌值快速填入手牌。';
        return;
    }

    container.innerHTML = scenarioHandSelection.selectedCards.map(card => {
        const suit = card.slice(-1);
        const rank = card.slice(0, -1);
        const suitSymbol = { s: '♠', h: '♥', d: '♦', c: '♣' }[suit] || '';
        return `<span class="selected-card">${rank}${suitSymbol}<button class="remove" data-card="${card}" aria-label="移除 ${card}">×</button></span>`;
    }).join('');
}

function highlightScenarioPickerButtons() {
    const suitRow = document.getElementById('scenario-suit-options');
    if (suitRow) {
        suitRow.querySelectorAll('button').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.suit === scenarioHandSelection.activeSuit);
        });
    }

    const rankRow = document.getElementById('scenario-rank-options');
    if (rankRow) {
        rankRow.querySelectorAll('button').forEach(btn => {
            const rank = btn.dataset.rank;
            const card = `${rank}${scenarioHandSelection.activeSuit}`;
            const isSelected = scenarioHandSelection.selectedCards.includes(card);
            btn.classList.toggle('active', isSelected);
        });
    }
}

function syncScenarioHandInput() {
    setScenarioHandInputValue(scenarioHandSelection.selectedCards);
    renderScenarioHandSelection();
    highlightScenarioPickerButtons();
}

function toggleScenarioCard(rank) {
    const suit = scenarioHandSelection.activeSuit || 's';
    const card = `${rank}${suit}`;

    const existingIndex = scenarioHandSelection.selectedCards.indexOf(card);
    if (existingIndex !== -1) {
        scenarioHandSelection.selectedCards.splice(existingIndex, 1);
    } else {
        if (scenarioHandSelection.selectedCards.length >= 2) {
            scenarioHandSelection.selectedCards.shift();
        }
        scenarioHandSelection.selectedCards.push(card);
    }

    syncScenarioHandInput();
}

function setScenarioHandFromInput(inputValue) {
    const parsed = parseCardsFromInput(inputValue).slice(0, 2);
    if (parsed.length) {
        const lastSuit = parsed[parsed.length - 1].slice(-1);
        scenarioHandSelection.activeSuit = lastSuit || scenarioHandSelection.activeSuit;
    }
    scenarioHandSelection.selectedCards = parsed;
    syncScenarioHandInput();
}

function collectScenarioPayload() {
    const heroHandInput = document.getElementById('scenario-hero-hand');
    const heroPositionSelect = document.getElementById('scenario-hero-position');
    const stageSelect = document.getElementById('scenario-stage');
    const communityInput = document.getElementById('scenario-community');
    const actionTypeSelect = document.getElementById('scenario-action-type');
    const actionAmountInput = document.getElementById('scenario-action-amount');

    if (!heroHandInput || !heroPositionSelect || !stageSelect || !actionTypeSelect || !actionAmountInput) {
        throw new Error('情境表單載入失敗，請重新整理頁面。');
    }

    const heroHand = parseCardsFromInput(heroHandInput.value);
    if (heroHand.length !== 2) {
        throw new Error('Hero 手牌請輸入兩張牌，例如：As Kd');
    }

    const heroPosition = heroPositionSelect.value;
    const stage = stageSelect.value;
    const communityCards = parseCardsFromInput(communityInput ? communityInput.value : '');

    const opponents = [];
    const opponentRows = document.querySelectorAll('.opponent-row');
    opponentRows.forEach((row, idx) => {
        const nameInput = row.querySelector('.opponent-name');
        const positionSelect = row.querySelector('.opponent-position');
        const handInput = row.querySelector('.opponent-hand');

        if (!nameInput || !positionSelect || !handInput) return;

        const name = nameInput.value.trim() || `Villain${idx + 1}`;
        const position = positionSelect.value;
        const hand = parseCardsFromInput(handInput.value);

        opponents.push({ name, position, hand });
    });

    const positionNameMap = new Map();
    positionNameMap.set(heroPosition, 'Hero');
    opponents.forEach(opp => positionNameMap.set(opp.position, opp.name));

    const actionLines = [
        ...parseActionLines(document.getElementById('scenario-preflop-actions')?.value, 'preflop', positionNameMap),
        ...parseActionLines(document.getElementById('scenario-flop-actions')?.value, 'flop', positionNameMap),
        ...parseActionLines(document.getElementById('scenario-turn-actions')?.value, 'turn', positionNameMap),
        ...parseActionLines(document.getElementById('scenario-river-actions')?.value, 'river', positionNameMap),
    ].filter(entry => entry.position && entry.action);

    const heroAction = {
        action_type: actionTypeSelect.value,
        amount: parseInt(actionAmountInput.value) || 0,
    };

    return {
        hero_hand: heroHand,
        hero_position: heroPosition,
        stage,
        community_cards: communityCards,
        opponents,
        hero_action: heroAction,
        action_lines: actionLines,
    };
}

function setScenarioStatus(message, isError = false) {
    const status = document.getElementById('scenario-status');
    if (!status) return;
    status.textContent = message;
    status.style.color = isError ? '#c0392b' : '#475467';
}

async function submitScenarioAnalysis() {
    try {
        setScenarioStatus('情境分析中...', false);
        const payload = collectScenarioPayload();

        const response = await fetch(`${API_BASE}/scenario_evaluate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });

        const data = await response.json();
        if (!response.ok) {
            setScenarioStatus(`分析失敗：${data.detail || '請檢查輸入格式。'}`, true);
            return;
        }

        renderFeedback(data);
        setScenarioStatus('情境分析完成。');
    } catch (error) {
        console.error('Scenario evaluation error', error);
        setScenarioStatus('無法完成情境分析，請稍後再試。', true);
    }
}

async function submitCustomHand() {
    const select = document.getElementById('hand-player-select');
    const card1Input = document.getElementById('card1-input');
    const card2Input = document.getElementById('card2-input');

    if (!select || !card1Input || !card2Input) return;

    if (!customHandEnabled) {
        alert('請先開始新牌局後再設定手牌。');
        return;
    }

    const playerName = select.value;
    const card1 = normalizeCardInput(card1Input.value);
    const card2 = normalizeCardInput(card2Input.value);

    if (!playerName) {
        alert('請先選擇玩家。');
        return;
    }

    if (!card1 || !card2) {
        alert('請輸入兩張手牌，例如 As、Kd');
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/set_hand`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ player_name: playerName, cards: [card1, card2] })
        });

        const data = await response.json();
        if (!response.ok) {
            alert(`設定手牌失敗：${data.detail || '請確認輸入格式。'}`);
            return;
        }

        renderGameState(data);
        alert('手牌已更新！');
    } catch (error) {
        console.error('Error setting hand:', error);
        alert('無法設定手牌，請稍後再試。');
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
    const analyzeBtn = document.getElementById('analyze-last-btn');
    if (analyzeBtn) {
        analyzeBtn.disabled = true;
        analyzeBtn.textContent = '分析中...';
    }

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
    } finally {
        updateAnalysisButton();
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

        setCustomHandAvailability(true);

        const response = await fetch(`${API_BASE}/new_hand`, { method: 'POST' });
        const state = await response.json();
        renderGameState(state);
        console.log("新牌局已開始！");
    } catch (error) {
        console.error("Error starting new hand:", error);
        alert("無法開始新牌局。請檢查後端伺服器。");
    }
}

async function switchTableSize() {
    const targetSize = currentTableSize === 9 ? 6 : 9;

    resetFeedbackDisplay();
    lastAnalysisAvailable = false;
    updateAnalysisButton();
    setCustomHandAvailability(true);

    try {
        const response = await fetch(`${API_BASE}/table_size`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ table_size: targetSize }),
        });

        const state = await response.json();
        if (!response.ok) {
            alert(`切換牌桌失敗：${state.detail || '請稍後再試。'}`);
            return;
        }

        renderGameState(state);
    } catch (error) {
        console.error('Error switching table size:', error);
        alert('無法切換牌桌人數，請稍後再試。');
    } finally {
        updateAnalysisButton();
    }
}

function toggleExplanation() {
    const explanationBox = document.getElementById('error-explanation');
    const toggleBtn = document.getElementById('toggle-explanation-btn');
    if (!explanationBox || !toggleBtn) return;

    explanationCollapsed = !explanationCollapsed;
    explanationBox.classList.toggle('collapsed', explanationCollapsed);
    toggleBtn.textContent = explanationCollapsed ? '展開詳解' : '收合詳解';
}


// --- 初始化和事件監聽 (保持不變) ---
document.addEventListener('DOMContentLoaded', () => {
    applyTableLayout(6);
    document.getElementById('start-hand-btn').addEventListener('click', startNewHand);
    document.getElementById('analyze-last-btn').addEventListener('click', fetchLastFeedback);
    document.getElementById('toggle-explanation-btn').addEventListener('click', toggleExplanation);

    const toggleTableBtn = document.getElementById('toggle-table-size-btn');
    if (toggleTableBtn) {
        toggleTableBtn.addEventListener('click', switchTableSize);
    }

    const toggleCustomHandBtn = document.getElementById('open-custom-hand-btn');
    if (toggleCustomHandBtn) {
        toggleCustomHandBtn.addEventListener('click', () => {
            if (!customHandEnabled) {
                alert('請先開始新牌局後再設定手牌。');
                return;
            }

            customHandPanelVisible = !customHandPanelVisible;
            updateCustomHandPanelVisibility();
        });
    }

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

    const setHandBtn = document.getElementById('set-hand-btn');
    if (setHandBtn) {
        setHandBtn.addEventListener('click', submitCustomHand);
    }

    // 初始化情境分析表單
    const heroPosSelect = document.getElementById('scenario-hero-position');
    if (heroPosSelect) {
        heroPosSelect.innerHTML = buildPositionOptions('BTN');
    }

    const heroHandInput = document.getElementById('scenario-hero-hand');
    if (heroHandInput) {
        heroHandInput.addEventListener('input', (event) => setScenarioHandFromInput(event.target.value));
    }

    const suitRow = document.getElementById('scenario-suit-options');
    if (suitRow) {
        suitRow.addEventListener('click', (event) => {
            const btn = event.target.closest('button[data-suit]');
            if (!btn) return;
            scenarioHandSelection.activeSuit = btn.dataset.suit;
            highlightScenarioPickerButtons();
        });
    }

    const rankRow = document.getElementById('scenario-rank-options');
    if (rankRow) {
        rankRow.addEventListener('click', (event) => {
            const btn = event.target.closest('button[data-rank]');
            if (!btn) return;
            toggleScenarioCard(btn.dataset.rank);
        });
    }

    const selectedCards = document.getElementById('scenario-selected-cards');
    if (selectedCards) {
        selectedCards.addEventListener('click', (event) => {
            const btn = event.target.closest('button.remove');
            if (!btn) return;
            const card = btn.dataset.card;
            const idx = scenarioHandSelection.selectedCards.indexOf(card);
            if (idx !== -1) {
                scenarioHandSelection.selectedCards.splice(idx, 1);
                syncScenarioHandInput();
            }
        });
    }

    const clearHandBtn = document.getElementById('scenario-clear-hand');
    if (clearHandBtn) {
        clearHandBtn.addEventListener('click', () => {
            scenarioHandSelection.selectedCards = [];
            syncScenarioHandInput();
        });
    }

    const opponentList = document.getElementById('opponent-list');
    let opponentCount = 0;
    const addOpponentBtn = document.getElementById('add-opponent-btn');

    const addOpponentRow = () => {
        if (!opponentList) return;
        opponentCount += 1;
        opponentList.appendChild(createOpponentRow(opponentCount));
    };

    if (addOpponentBtn) {
        addOpponentBtn.addEventListener('click', addOpponentRow);
    }

    addOpponentRow();

    syncScenarioHandInput();
    const submitScenarioBtn = document.getElementById('submit-scenario-btn');
    if (submitScenarioBtn) {
        submitScenarioBtn.addEventListener('click', submitScenarioAnalysis);
    }

    updateAnalysisButton();
    setCustomHandAvailability(false);

    // 首次載入時啟動新牌局
    // startNewHand();

    // 初始化玩家選單
    fetchState();
});
