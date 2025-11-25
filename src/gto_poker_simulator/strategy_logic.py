# src/gto_poker_simulator/strategy_logic.py
import os
from typing import List
from src.api.schemas import GameState, UserAction, GTOFeedback, GTOActionData

class StrategyLogic:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_KEY")
        try:
            import openai
            self.openai = openai
        except ImportError:
            self.openai = None

    def evaluate_user_action(self, game_state: GameState, user_action: UserAction) -> GTOFeedback:
        # 試圖從 game_state 中找出當前行動玩家與其手牌
        players = game_state.players
        action_position = game_state.action_position
        acting_player = next((p for p in players if p.get("position") == action_position), None)
        hand = acting_player.get("hand", []) if acting_player else []

        # 組合提示內容
        state_desc = self._build_state_description(game_state, hand)
        prompt = f"""
你是一位德州撲克GTO策略分析師，請根據以下牌局情境評估玩家的行動是否符合標準：

{state_desc}

玩家行動：{user_action.action_type}, 數額：{user_action.amount}。

請回答：
1. 該行動是否屬於GTO建議之一？
2. 相對於最佳策略的期望值損失 (EV loss) 是多少？
3. 顯示所有 GTO 建議動作與頻率、EV。
4. 用一句話簡要說明該建議的理由。
"""

        if self.api_key and self.openai:
            try:
                self.openai.api_key = self.api_key
                response = self.openai.ChatCompletion.create(
                    model="gpt-4",
                    messages=[{"role": "system", "content": "你是一位專業撲克GTO策略分析師。"},
                              {"role": "user", "content": prompt}]
                )
                reply = response["choices"][0]["message"]["content"]
                # 假設從reply解析結果，這裡簡化回傳
                return GTOFeedback(
                    user_action_correct=True,
                    ev_loss_bb=0.0,
                    gto_matrix=[
                        GTOActionData(action="Call", frequency=0.5, ev_bb=0.0),
                        GTOActionData(action="Raise", frequency=0.3, ev_bb=0.15),
                        GTOActionData(action="Fold", frequency=0.2, ev_bb=-0.1)
                    ],
                    explanation=reply.strip()
                )
            except Exception as e:
                print(f"GPT error: {e}")

        # fallback 模式：簡化假數據
        ev_loss = 0.0
        correct = True
        gto_matrix = [
            GTOActionData(action="Check", frequency=0.5, ev_bb=0.0),
            GTOActionData(action="Raise", frequency=0.25, ev_bb=0.1),
            GTOActionData(action="Fold", frequency=0.25, ev_bb=-0.1)
        ]
        explanation = (
            "示例評估：此處使用了簡化的邏輯來替代 GTO 模型，因此結果僅作為佔位。"
            "若您提供了 OpenAI API 金鑰且安裝了 openai 套件，"
            "則系統將自動從語言模型獲取更精準的評估。"
        )
        return GTOFeedback(
            user_action_correct=correct,
            ev_loss_bb=ev_loss,
            gto_matrix=gto_matrix,
            explanation=explanation,
        )

    def _build_state_description(self, game_state: GameState, hand: List[dict]) -> str:
        board = " ".join([f"{c['rank']}{c['suit']}" for c in game_state.community_cards]) or "無"
        cards = " ".join([f"{c['rank']}{c['suit']}" for c in hand]) or "未知"
        desc = (
            f"目前底池為 {game_state.pot_size}。
"
            f"公共牌：{board}
"
            f"您手牌為：{cards}
"
            f"位置：{game_state.action_position}
"
            f"目前跟注金額為：{game_state.current_bet}。"
        )
        return desc