from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from src.core.game_state import Table
from src.gto_poker_simulator.strategy_logic import StrategyLogic
from .schemas import GameState, UserAction, GTOFeedback, AIActionResponse

app = FastAPI()

# 初始化核心組件
players_init = {'hero': 10000, 'Player2': 10000, 'Player3': 10000, 
                'Player4': 10000, 'Player5': 10000, 'Player6': 10000}
game_table = Table(players_init, big_blind=100)
gto_logic = StrategyLogic()

# 定義靜態文件路徑
STATIC_DIR = Path(__file__).parent.parent.parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/", response_class=FileResponse)
async def serve_index():
    """根路由：返回 HTML 應用程式主頁面"""
    return FileResponse(STATIC_DIR / "index.html", media_type="text/html")

@app.post("/api/new_hand")
async def start_new_hand():
    """啟動新的牌局"""
    game_table.start_hand()
    # 返回新的狀態
    return game_table.get_state_for_frontend()

@app.get("/api/state", response_model=GameState)
async def get_current_state():
    """獲取當前牌局的所有狀態數據"""
    return game_table.get_state_for_frontend()

@app.post("/api/action", response_model=GTOFeedback)
async def submit_action(action: UserAction):
    """用戶提交行動，並返回 GTO 評估"""
    
    # 獲取當前玩家的手牌和情境
    current_state = GameState(**game_table.get_state_for_frontend())

    # 1. 遊戲狀態更新
    try:
        game_table.process_action(action)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # 2. GTO 評估
    feedback = gto_logic.evaluate_user_action(
        game_state=current_state,
        user_action=action
    )

    return feedback


@app.post("/api/ai_action", response_model=AIActionResponse)
async def decide_ai_action():
    """呼叫 OpenAI 為非 Hero 玩家做出行動決策"""
    if game_table.hand_over:
        raise HTTPException(status_code=400, detail="牌局已結束，請先開始新牌局。")

    acting_player = game_table.get_current_player()
    if acting_player.name.lower() == 'hero':
        raise HTTPException(status_code=400, detail="目前輪到 Hero 行動，請由玩家操作。")

    current_state = GameState(**game_table.get_state_for_frontend())
    ai_decision = gto_logic.decide_opponent_action(current_state)

    try:
        game_table.process_action(ai_decision)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return AIActionResponse(
        actor=acting_player.name,
        action_type=ai_decision.action_type,
        amount=ai_decision.amount,
    )