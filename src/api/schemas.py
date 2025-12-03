from pydantic import BaseModel
from typing import List, Dict, Any

class CardModel(BaseModel):
    """單張牌的模型 (e.g., {'rank': 'A', 'suit': 's'})"""
    rank: str
    suit: str

class PlayerState(BaseModel):
    """單個玩家的當前狀態"""
    name: str
    position: str
    seat_number: int
    chips: int
    in_pot: int
    current_round_bet: int
    is_active: bool
    hand: List[CardModel] = [] # 只有當前行動的玩家會看到自己的手牌


class ActionLogEntry(BaseModel):
    """紀錄玩家行動的簡易結構，便於前端顯示"""
    name: str
    position: str
    seat_number: int
    action: str
    stage: str
    amount: int = 0


class OpponentHand(BaseModel):
    """牌局結束時揭露的對手手牌資料"""
    name: str
    position: str
    seat_number: int
    hand: List[CardModel]


class HandResult(BaseModel):
    """簡易的牌局結果資訊"""
    winner_name: str
    seat_number: int
    position: str
    amount_won: int
    description: str

class GameState(BaseModel):
    """牌局的完整狀態 (發送給前端)"""
    pot_size: int
    community_cards: List[CardModel]
    action_position: str # 輪到誰行動 (e.g., 'BTN')
    players: List[PlayerState]
    current_bet: int # 當前必須跟注的金額 (Call Amount)
    current_stage: str
    hand_over: bool
    opponent_hands: List[OpponentHand] = []
    action_log: List[ActionLogEntry] = []
    hand_result: HandResult | None = None

class UserAction(BaseModel):
    """用戶從前端發送的行動請求"""
    action_type: str # 'Fold', 'Call', 'Raise', 'Bet', 'Check'
    amount: int = 0  # 僅 Bet/Raise 時需要，代表總投入的金額


class SetHandRequest(BaseModel):
    """手動設定玩家手牌的請求"""
    player_name: str
    cards: List[str]


class AIActionResponse(BaseModel):
    """AI 幫助決策的行動回應"""
    actor: str
    action_type: str
    amount: int


class ActionProcessResponse(BaseModel):
    """用戶行動提交後的確認回應"""
    success: bool
    detail: str

class GTOActionData(BaseModel):
    """GTO 建議的單個行動數據"""
    action: str
    frequency: float
    ev_bb: float

class GTOFeedback(BaseModel):
    """後端返回給前端的 GTO 評估結果"""
    user_action_correct: bool # 判斷用戶行動是否在可接受範圍
    ev_loss_bb: float         # 相對於 GTO 最佳行動的 EV 損失
    gto_matrix: List[GTOActionData] # GTO 建議的所有可行行動及其頻率
    explanation: str          # 對 EV Loss 的簡短文字解釋