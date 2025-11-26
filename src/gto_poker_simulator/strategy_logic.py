import os
import json
from typing import List
from src.api.schemas import (
    GameState,
    UserAction,
    GTOFeedback,
    GTOActionData,
    CardModel,
)
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


class StrategyLogic:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.org = os.getenv("OPENAI_ORG")

        if self.api_key:
            self.client = OpenAI(api_key=self.api_key, organization=self.org)
        else:
            self.client = None

    def evaluate_user_action(self, game_state: GameState, user_action: UserAction) -> GTOFeedback:
        # 找出 acting player 與手牌
        players = game_state.players
        action_position = game_state.action_position
        acting_player = next((p for p in players if p.position == action_position), None)
        hand = acting_player.hand if acting_player else []

        # 組合分析描述
        state_desc = self._build_state_description(game_state, hand)

        # 要求 GPT 回傳 JSON（強調不要使用 ```）
        prompt = f"""
你是一位德州撲克 GTO 策略分析師，請依據以下牌局資訊提供完整的 GTO 評估：

{state_desc}

玩家行動：{user_action.action_type}, 數額：{user_action.amount}

請以「純 JSON」格式輸出以下欄位（不要加任何 ``` 符號，也不要加多餘說明文字）：

{{
  "user_action_correct": true 或 false,
  "ev_loss_bb": 數字,
  "gto_matrix": [
    {{"action": "Call", "frequency": 0~1, "ev_bb": 數字}},
    {{"action": "Raise", "frequency": 0~1, "ev_bb": 數字}},
    {{"action": "Fold", "frequency": 0~1, "ev_bb": 數字}}
  ],
  "explanation": "策略說明文字"
}}

請務必保證這是一段可以被 Python json.loads() 解析的合法 JSON。
只輸出 JSON，本身不要任何註解、markdown 或其他文字。
"""

        reply = ""  # 先定義，避免例外時變成未定義變數

        if self.api_key and self.client:
            try:
                response = self.client.responses.create(
                    model="gpt-4o-mini",
                    input=[
                        {"role": "system", "content": "你是一位專業德州撲克 GTO 策略分析師。"},
                        {"role": "user", "content": prompt}
                    ]
                )

                # 這裡依照你 SDK 的用法，如果不是 output_text 可以換成對應欄位
                reply = response.output_text

                data = self._parse_json_reply(reply)

                # 組裝 gto_matrix
                gto_matrix = [
                    GTOActionData(
                        action=item["action"],
                        frequency=item["frequency"],
                        ev_bb=item["ev_bb"]
                    )
                    for item in data.get("gto_matrix", [])
                ]

                return GTOFeedback(
                    user_action_correct=data.get("user_action_correct", True),
                    ev_loss_bb=data.get("ev_loss_bb", 0.0),
                    gto_matrix=gto_matrix,
                    explanation=data.get("explanation", "")
                )

            except Exception as e:
                # 解析或 API 錯誤，印出來方便你在 server log 看問題
                print("GPT error while handling GTO JSON:", e)
                print("GPT raw reply:")
                print(reply)

        # fallback 模式：AI 壞掉時至少有東西回傳
        return GTOFeedback(
            user_action_correct=True,
            ev_loss_bb=0.0,
            gto_matrix=[
                GTOActionData(action="Check", frequency=0, ev_bb=0),
                GTOActionData(action="Raise", frequency=0, ev_bb=0),
                GTOActionData(action="Fold", frequency=0, ev_bb=0),
            ],
            explanation="AI Agent 異常或回傳非法 JSON，系統回傳預設資料。",
        )

    def decide_opponent_action(self, game_state: GameState) -> UserAction:
        """使用 OpenAI 決策目前行動玩家（非 Hero）的行動"""

        players = game_state.players
        acting_player = next((p for p in players if p.position == game_state.action_position), None)
        to_call = 0
        if acting_player:
            to_call = max(game_state.current_bet - acting_player.in_pot, 0)

        prompt = f"""
你現在扮演德州撲克玩家，根據以下桌面資訊給出你的行動並回傳 JSON：

{self._build_state_description(game_state, acting_player.hand if acting_player else [])}

可用行動：Fold、Call、Check、Bet、Raise。
請只輸出 JSON，格式如下：
{{"action_type": "Call/Check/Raise/Bet/Fold", "amount": 數字}}
不要包含額外說明、markdown 或程式碼框。
"""

        reply = ""
        if self.api_key and self.client:
            try:
                response = self.client.responses.create(
                    model="gpt-4o-mini",
                    input=[
                        {"role": "system", "content": "你是一位冷靜理性的德州撲克玩家，請給出合理行動。"},
                        {"role": "user", "content": prompt},
                    ],
                )

                reply = response.output_text
                data = self._parse_json_reply(reply)
                action_type = data.get("action_type", "Call")
                amount = int(data.get("amount", to_call))
                return UserAction(action_type=action_type, amount=amount)
            except Exception as e:
                print("GPT error while deciding opponent action:", e)
                print("GPT raw reply:")
                print(reply)

        # fallback 邏輯：沒有 OpenAI 或解析失敗時使用簡單策略
        if to_call > 0:
            return UserAction(action_type="Call", amount=to_call)
        return UserAction(action_type="Check", amount=0)

    def _parse_json_reply(self, reply: str) -> dict:
        """
        將 GPT 回覆的字串轉為 dict：
        1. 去掉 ``` 區塊
        2. 擷取第一個 '{' 到最後一個 '}' 之間的內容
        3. 丟給 json.loads 解析
        """
        if not reply:
            raise ValueError("Empty reply from GPT")

        text = reply.strip()

        # ① 如果有 ```，先把可能的 JSON 區塊抓出來
        if "```" in text:
            segments = text.split("```")
            candidates = []
            for seg in segments:
                seg_stripped = seg.strip()
                if "{" in seg_stripped and "}" in seg_stripped:
                    candidates.append(seg_stripped)
            if candidates:
                text = candidates[0]

        # ② 擷取最外層 { ... } 區間
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            # 沒有找到合理的 JSON 區段
            raise ValueError(f"Cannot find JSON object in reply: {text[:200]}")

        json_str = text[start:end + 1]

        # ③ 丟給 json.loads 解析
        return json.loads(json_str)

    def _build_state_description(self, game_state: GameState, hand: List[CardModel]) -> str:
        board = " ".join([f"{c.rank}{c.suit}" for c in game_state.community_cards]) or "無"
        cards = " ".join([f"{c.rank}{c.suit}" for c in hand]) or "未知"
        desc = (
            f"目前底池：{game_state.pot_size}\n"
            f"公共牌：{board}\n"
            f"手牌：{cards}\n"
            f"行動位置：{game_state.action_position}\n"
            f"當前跟注金額：{game_state.current_bet}"
        )
        return desc
