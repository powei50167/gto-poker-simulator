from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from src.core.game_state import Table
from src.core.history_repository import HistoryRepository
from src.core.logger import get_logger
from src.gto_poker_simulator.strategy_logic import StrategyLogic
from .schemas import (
    GameState,
    UserAction,
    GTOFeedback,
    AIActionResponse,
    ActionProcessResponse,
    SetHandRequest,
    TableSizeRequest,
    HandHistorySummary,
    HandHistoryRecord,
    CardModel,
    PlayerState,
    ActionLogEntry,
    ScenarioEvaluateRequest,
)

app = FastAPI()
logger = get_logger(__name__)

# 初始化核心組件
TABLE_CONFIGS: dict[int, dict[str, object]] = {
    6: {
        "positions": ['🅱️BTN', 'SB', 'BB', 'UTG', 'MP', 'CO'],
        "seat_order": [1, 2, 3, 4, 5, 6],
        "hero_seat": 4,
    },
    9: {
        "positions": ['🅱️BTN', 'SB', 'BB', 'UTG', 'UTG+1', 'UTG+2', 'LJ', 'HJ', 'CO'],
        "seat_order": [1, 2, 3, 4, 5, 6, 7, 8, 9],
        "hero_seat": 6,
    },
}

history_repo = HistoryRepository()


def _build_players(table_size: int) -> dict[str, int]:
    stacks = {'hero': 10000}
    for i in range(2, table_size + 1):
        stacks[f'Player{i}'] = 10000
    return stacks


def _create_table(table_size: int) -> Table:
    if table_size not in TABLE_CONFIGS:
        raise ValueError("目前僅支援 6 人或 9 人桌。")
    config = TABLE_CONFIGS[table_size]
    return Table(
        _build_players(table_size),
        big_blind=100,
        history_repo=history_repo,
        positions=config["positions"],
        seat_order=config["seat_order"],
        hero_seat=config["hero_seat"],
    )


current_table_size = 6
game_table = _create_table(current_table_size)
gto_logic = StrategyLogic()
last_user_action_context: dict | None = None


def _parse_card_str(card: str) -> CardModel:
    """將簡短字串（如 As）轉換為 CardModel。"""

    if len(card) != 2:
        raise ValueError(f"牌面格式錯誤：{card}")

    rank = card[0].upper()
    suit = card[1].lower()
    if suit not in {"s", "h", "d", "c"}:
        raise ValueError(f"未知花色：{card}")

    return CardModel(rank=rank, suit=suit)


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


def _build_scenario_state(request: ScenarioEvaluateRequest) -> GameState:
    """根據情境分析輸入拼裝 GameState，以便沿用 evaluate_user_action。"""

    seat_number = 1
    hero_hand = [_parse_card_str(c) for c in request.hero_hand]
    players: list[PlayerState] = [
        PlayerState(
            name="Hero",
            position=request.hero_position,
            seat_number=seat_number,
            chips=10000,
            in_pot=0,
            current_round_bet=0,
            is_active=True,
            hand=hero_hand,
        )
    ]

    for opp in request.opponents:
        seat_number += 1
        players.append(
            PlayerState(
                name=opp.name,
                position=opp.position,
                seat_number=seat_number,
                chips=10000,
                in_pot=0,
                current_round_bet=0,
                is_active=True,
                hand=[_parse_card_str(c) for c in opp.hand] if opp.hand else [],
            )
        )

    community_cards = [_parse_card_str(c) for c in request.community_cards]
    position_to_seat = {player.position: player.seat_number for player in players}

    action_log = [
        ActionLogEntry(
            name=line.name,
            position=line.position,
            seat_number=position_to_seat.get(line.position, 0),
            action=line.action,
            stage=line.stage,
            amount=line.amount,
        )
        for line in request.action_lines
    ]

    table_size = request.table_size or len(players)
    if table_size not in TABLE_CONFIGS:
        raise ValueError("情境牌桌人數目前僅支援 6 或 9 人桌。")
    if len(players) > table_size:
        raise ValueError("情境中的玩家數量超過選擇的牌桌人數。")

    return GameState(
        pot_size=0,
        community_cards=community_cards,
        action_position=request.hero_position,
        players=players,
        current_bet=0,
        current_stage=request.stage,
        hand_over=False,
        opponent_hands=[],
        action_log=action_log,
        hand_result=None,
        hand_id=None,
        table_size=table_size,
        seat_order=list(range(1, table_size + 1)),
    )

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


@app.post("/api/table_size", response_model=GameState)
async def switch_table_size(request: TableSizeRequest):
    """切換牌桌人數並重新開始新牌局。"""
    global game_table, last_user_action_context, current_table_size

    if request.table_size not in TABLE_CONFIGS:
        raise HTTPException(status_code=400, detail="目前僅支援 6 人或 9 人桌。")

    try:
        game_table = _create_table(request.table_size)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    current_table_size = request.table_size
    last_user_action_context = None
    game_table.start_hand()
    logger.info(
        "Table size switched",
        extra={
            "table_size": request.table_size,
            "button_index": game_table.button_index,
        },
    )
    _auto_play_until_hero()
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


@app.post("/api/scenario_evaluate", response_model=GTOFeedback)
async def evaluate_custom_scenario(request: ScenarioEvaluateRequest):
    """接收情境分析輸入並返回 evaluate_user_action 的結果。"""

    try:
        scenario_state = _build_scenario_state(request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    feedback = gto_logic.evaluate_user_action(
        game_state=scenario_state,
        user_action=request.hero_action,
    )

    logger.info(
        "Scenario evaluation generated",
        extra={"stage": request.stage, "hero_position": request.hero_position},
    )

    return feedback


@app.post("/api/set_hand")
async def set_player_hand(request: SetHandRequest):
    """允許手動覆寫 Hero 或任意玩家的手牌 (僅翻前)。"""

    try:
        game_table.set_player_hand(request.player_name, request.cards)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    logger.info(
        "Player hand overridden via API",
        extra={"player": request.player_name, "cards": request.cards},
    )
    return game_table.get_state_for_frontend()


@app.get("/api/history", response_model=list[HandHistorySummary])
async def list_hand_history(limit: int = 20, offset: int = 0):
    """取得歷史牌局列表，預設最多返回 20 筆。"""
    records = history_repo.list_hands(limit=limit, offset=offset)
    return [
        HandHistorySummary(
            id=rec["id"],
            created_at=rec["created_at"],
            hand_result=rec["state"].get("hand_result"),
        )
        for rec in records
    ]


@app.get("/api/history/{hand_id}", response_model=HandHistoryRecord)
async def get_hand_history(hand_id: int):
    """取得指定牌局的完整歷史資料。"""
    record = history_repo.get_hand(hand_id)
    if not record:
        raise HTTPException(status_code=404, detail="找不到指定的歷史牌局。")

    return HandHistoryRecord(
        id=record["id"],
        created_at=record["created_at"],
        state=GameState(**record["state"]),
    )
