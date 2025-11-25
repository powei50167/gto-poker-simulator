from src.core.game_state import Card
from src.api.schemas import UserAction, GTOFeedback, GTOActionData
from typing import List

class StrategyLogic:
    def __init__(self):
        # 這裡應該初始化數據庫連接和 GTO 數據載入
        pass

    def _query_gto_data(self, hand: List[Card], situation: str) -> List[GTOActionData]:
        """
        [⚠️ 概念性] 模擬從數據庫查詢 GTO 策略數據
        """
        
        # 根據手牌和情境，從數據庫中獲取策略
        # 這裡返回一個硬編碼的示例數據
        if hand[0].rank == 'A' and hand[1].rank == 'K': # 假設當前是 AK
            return [
                GTOActionData(action='Call', frequency=0.8, ev_bb=1.5),
                GTOActionData(action='Raise 3x', frequency=0.2, ev_bb=1.45),
                GTOActionData(action='Fold', frequency=0.0, ev_bb=-1.0)
            ]
        else:
            return [
                GTOActionData(action='Fold', frequency=0.6, ev_bb=-0.5),
                GTOActionData(action='Call', frequency=0.4, ev_bb=-0.4)
            ]


    def evaluate_user_action(self, hand: List[Card], situation: str, user_action: UserAction) -> GTOFeedback:
        """
        評估用戶行動相對於 GTO 策略的優劣。
        """
        gto_actions = self._query_gto_data(hand, situation)
        
        # 1. 找到 GTO 最佳行動和 EV
        best_ev = max(a.ev_bb for a in gto_actions)
        
        # 2. 找到用戶行動的 GTO 數據和 EV
        user_action_str = f"{user_action.action_type}{' ' + str(user_action.amount) if user_action.amount > 0 else ''}"
        
        user_gto_data = next((a for a in gto_actions if a.action.lower().startswith(user_action.action_type.lower())), None)

        if not user_gto_data:
            # 假設用戶行動完全不在 GTO 範圍內
            user_ev = -999.0
            is_correct = False
        else:
            user_ev = user_gto_data.ev_bb
            is_correct = user_gto_data.frequency > 0.1 # 假設頻率 > 10% 就算在 GTO 範圍內
            
        # 3. 計算 EV Loss
        ev_loss = round(best_ev - user_ev, 2)
        
        explanation = "您的行動是 GTO 策略的一部分 (頻率 > 10%)。" if is_correct else "您的行動嚴重偏離 GTO 策略，損失了期望值。"

        return GTOFeedback(
            user_action_correct=is_correct,
            ev_loss_bb=ev_loss,
            gto_matrix=gto_actions,
            explanation=explanation
        )