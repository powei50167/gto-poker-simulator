from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from src.core.game_state import Table
from src.core.logger import get_logger
from src.gto_poker_simulator.strategy_logic import StrategyLogic
from .schemas import (
    GameState,
    UserAction,
    GTOFeedback,
    AIActionResponse,
    ActionProcessResponse,
)

app = FastAPI()
logger = get_logger(__name__)

# 初始化核心組件
players_init = {'hero': 10000, 'Player2': 10000, 'Player3': 10000, 
                'Player4': 10000, 'Player5': 10000, 'Player6': 10000}
game_table = Table(players_init, big_blind=100)
gto_logic = StrategyLogic()
last_user_action_context: dict | None = None


def _auto_play_until_hero():
    """自動處理非 Hero 玩家行動，直到輪到 Hero 或牌局結束。"""
    actions = []

    while not game_table.hand_over:
        acting_player = game_table.get_current_player()
        if acting_player.name.lower() == 'hero':
            break

        current_state = GameState(**game_table.get_state_for_frontend())
        ai_decision = gto_logic.decide_opponent_action(current_state)

        try:
            game_table.process_action(ai_decision)
            actions.append({
                'actor': acting_player.name,
                'action_type': ai_decision.action_type,
                'amount': ai_decision.amount,
            })
            logger.info(
                "AI action processed",
                extra={
                    "actor": acting_player.name,
                    "action_type": ai_decision.action_type,
                    "amount": ai_decision.amount,
                    "stage": game_table.current_stage,
                },
            )
        except ValueError as e:
            # AI 回傳的行動無效時終止自動行動，避免陷入無限循環
            logger.warning("AI action invalid", extra={"error": str(e)})
            break

    return actions

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
    global last_user_action_context
    game_table.start_hand()
    last_user_action_context = None
    logger.info("New hand started", extra={"button_index": game_table.button_index})
    _auto_play_until_hero()
    # 返回新的狀態
    return game_table.get_state_for_frontend()

@app.get("/api/state", response_model=GameState)
async def get_current_state():
    """獲取當前牌局的所有狀態數據"""
    logger.info("State requested", extra={"stage": game_table.current_stage})
    return game_table.get_state_for_frontend()

@app.post("/api/action", response_model=ActionProcessResponse)
async def submit_action(action: UserAction):
    """用戶提交行動，僅處理狀態更新並保留分析上下文"""

    global last_user_action_context

    current_state = GameState(**game_table.get_state_for_frontend())

    try:
        game_table.process_action(action)
    except ValueError as e:
        logger.warning(
            "Invalid user action",
            extra={"error": str(e), "action": action.model_dump()},
        )
        raise HTTPException(status_code=400, detail=str(e))

    last_user_action_context = {"game_state": current_state, "user_action": action}

    _auto_play_until_hero()

    logger.info(
        "User action processed",
        extra={"action": action.model_dump(), "stage": game_table.current_stage},
    )
    return ActionProcessResponse(
        success=True,
        detail="行動已提交，點擊分析按鈕查看上一手 GTO 評估。",
    )


@app.post("/api/ai_action", response_model=AIActionResponse)
async def decide_ai_action():
    """呼叫 OpenAI 為非 Hero 玩家做出行動決策"""
    if game_table.hand_over:
        raise HTTPException(status_code=400, detail="牌局已結束，請先開始新牌局。")

    actions = _auto_play_until_hero()
    if not actions:
        raise HTTPException(status_code=400, detail="目前輪到 Hero 行動，無需 AI 決策。")

    last_action = actions[-1]
    logger.info(
        "AI action returned",
        extra={
            "actor": last_action['actor'],
            "action_type": last_action['action_type'],
            "amount": last_action['amount'],
            "stage": game_table.current_stage,
        },
    )
    return AIActionResponse(
        actor=last_action['actor'],
        action_type=last_action['action_type'],
        amount=last_action['amount'],
    )


@app.get("/api/analyze_last_action", response_model=GTOFeedback)
async def analyze_last_action():
    """按需對上一手用戶行動進行 GTO 分析"""

    if not last_user_action_context:
        raise HTTPException(status_code=400, detail="尚未有可分析的上一手行動。")

    feedback = gto_logic.evaluate_user_action(
        game_state=last_user_action_context["game_state"],
        user_action=last_user_action_context["user_action"],
    )

    logger.info(
        "On-demand GTO analysis generated",
        extra={"stage": game_table.current_stage},
    )

    return feedback
