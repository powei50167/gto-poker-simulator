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
from src.core.logger import get_logger

load_dotenv()


logger = get_logger(__name__, log_type="openai")


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
        hero_stack = acting_player.chips if acting_player else 0

        # 組合分析描述
        state_desc = self._build_state_description(
            game_state, hand, include_action_log=True
        )

        # 決定合法行動（避免模型亂給 UTG Check 類錯誤）
        stage = game_state.current_stage
        position = action_position

        # Preflop 行動規則
        if stage == "preflop":
            if position in ["UTG", "HJ", "CO", "BTN"]:  # 第一輪非盲注不能 check
                legal_actions = ["Call", "Raise", "Fold"]
            elif position == "SB":
                legal_actions = ["Call", "Raise", "Fold"]
            elif position == "BB":
                # BB 在 preflop 才能 check
                legal_actions = ["Check", "Call", "Raise", "Fold"]
            else:
                legal_actions = ["Call", "Raise", "Fold"]
        else:
            # flop/turn/river 都能 Check
            legal_actions = ["Check", "Call", "Raise", "Fold"]

        legal_action_str = ", ".join([f'"{a}"' for a in legal_actions])
        
        # 要求 GPT 回傳 JSON（強調不要使用 ```）
        prompt = f"""
你是一位德州撲克6人現金桌 GTO 教練，請依據以下牌局資訊提供完整的 GTO 建議與原因，並給出各行動的 frequency 與 ev_bb。

牌桌資訊: {state_desc}, 玩家行動：{user_action.action_type}, 下注金額：{user_action.amount}, 剩餘籌碼:{hero_stack}

⚠️ 請務必遵守以下規則：

- 僅能使用「此局面合法的行動」：{legal_action_str}
- preflop 若只有大小盲（POT=150）且尚未有人加注，合法行動為：
  - Call（補到大盲額度）
  - Raise（Open Raise）
  - Fold
  - Check 不合法，請 frequency=0、ev_bb=0。
- 若某行動不在 {legal_action_str} 中，必須將 frequency=0 且 ev_bb=0。
- 必須回傳可被 json.loads() 解析的純 JSON。
- 不得加入 ```、額外評論、格式化語法或 JSON 外內容。
請輸出以下格式（務必為合法 JSON）：
{{
  "user_action_correct": true 或 false,
  "ev_loss_bb": 數字,
  "gto_matrix": [
    {{"action": "Check", "frequency": 0~1, "ev_bb": 數字}},
    {{"action": "Call", "frequency": 0~1, "ev_bb": 數字}},
    {{"action": "Raise", "frequency": 0~1, "ev_bb": 數字}},
    {{"action": "Fold", "frequency": 0~1, "ev_bb": 數字}}
  ],
  "explanation": " GTO 教練建議說明文字"
}}

注意：
- 若某行動在此局面不合法，請 frequency=0, ev_bb=0。
- 確保 JSON 能用 Python json.loads() 成功解析。
"""

        reply = ""  # 先定義，避免例外時變成未定義變數

        logger.info(
            "OpenAI prompt for user action evaluation",
            extra={
                "【牌桌資訊】": state_desc,
                "【玩家行動：】": user_action.action_type,
                "【數額：】": user_action.amount,
                "stage": game_state.current_stage,
                "action": user_action.model_dump(),
            },
        )

        if self.api_key and self.client:
            try:
                response = self.client.responses.create(
                    model="gpt-5.1",
                    input=[
                        {"role": "system", "content": "你是一位德州撲克6人現金桌 GTO 教練。"},
                        {"role": "user", "content": prompt}
                    ]
                )

                # 這裡依照你 SDK 的用法，如果不是 output_text 可以換成對應欄位
                reply = response.output_text

                logger.info(
                    "OpenAI response for user action evaluation",
                    extra={
                        "【AI生成內容】": reply,
                        "stage": game_state.current_stage,
                        "action": user_action.model_dump(),
                    },
                )

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
                logger.error(
                    "GPT error while handling GTO JSON",
                    extra={"error": str(e), "reply": reply},
                )

        # fallback 模式：AI 壞掉時至少有東西回傳
        logger.warning(
            "Falling back to default GTO feedback",
            extra={"action": user_action.action_type},
        )
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
        acting_commit = acting_player.current_round_bet if acting_player else 0
        acting_stack = acting_player.chips if acting_player else 0
        to_call = 0
        if acting_player:
            to_call = max(game_state.current_bet - acting_player.current_round_bet, 0)

        prompt = f"""
你現在扮演德州撲克6人現金桌玩家，根據以下桌面資訊給出你的行動並回傳 JSON：

{self._build_state_description(game_state, acting_player.hand if acting_player else [])}
剩餘籌碼：{acting_stack}

可用行動：Fold、Call、Check、Bet、Raise、AllIn。
請只輸出 JSON，格式如下：
{{"action_type": "Call/Check/Raise/Bet/Fold", "amount": 數字}}
不要包含額外說明、markdown 或程式碼框。
"""

        reply = ""

        logger.info(
            "OpenAI prompt for opponent action",
            extra={
                "【牌桌資訊】": {self._build_state_description(game_state, acting_player.hand if acting_player else [])},
                "剩餘籌碼：": acting_stack,
                "actor": acting_player.name if acting_player else None,
                "stage": game_state.current_stage,
            },
        )
        if self.api_key and self.client:
            try:
                response = self.client.responses.create(
                    model="gpt-4o-mini",
                    input=[
                        {"role": "system", "content": "你是一位德州撲克6人現金桌玩家，請根據gto策略給出合理行動。"},
                        {"role": "user", "content": prompt},
                    ],
                )

                reply = response.output_text

                logger.info(
                    "OpenAI response for opponent action",
                    extra={
                        "【AI生成內容】": reply,
                        "actor": acting_player.name if acting_player else None,
                        "stage": game_state.current_stage,
                    },
                )
                data = self._parse_json_reply(reply)
                action_type = data.get("action_type", "Call")
                amount = int(data.get("amount", to_call))
                action_type, amount = self._sanitize_ai_action(
                    action_type=action_type,
                    amount=amount,
                    to_call=to_call,
                    current_bet=game_state.current_bet,
                    max_commit=acting_commit + acting_stack,
                )
                logger.info(
                    "AI opponent action decided",
                    extra={
                        "actor": acting_player.name if acting_player else None,
                        "action_type": action_type,
                        "amount": amount,
                    },
                )
                return UserAction(action_type=action_type, amount=amount)
            except Exception as e:
                logger.error(
                    "GPT error while deciding opponent action",
                    extra={"error": str(e), "reply": reply},
                )

        # fallback 邏輯：沒有 OpenAI 或解析失敗時使用簡單策略
        if to_call > 0:
            logger.warning(
                "Fallback opponent action (call)",
                extra={"to_call": to_call},
            )
            return UserAction(action_type="Call", amount=to_call)
        logger.warning("Fallback opponent action (check)")
        return UserAction(action_type="Check", amount=0)

    def _sanitize_ai_action(
        self,
        action_type: str,
        amount: int,
        to_call: int,
        current_bet: int,
        max_commit: int,
    ) -> tuple[str, int]:
        """確保 AI 行動符合桌面規則，避免觸發非法下注錯誤。"""

        lowered = action_type.lower()
        normalization_map = {
            "call": "Call",
            "check": "Check",
            "bet": "Bet",
            "raise": "Raise",
            "fold": "Fold",
            "allin": "AllIn",
            "all-in": "AllIn",
        }
        normalized_type = normalization_map.get(lowered, "Call")
        safe_amount = max(amount, 0)

        if to_call > 0:
            if normalized_type == "Check":
                normalized_type = "Call"
                safe_amount = to_call
            elif normalized_type == "Bet":
                normalized_type = "Raise"
            elif normalized_type == "Call":
                safe_amount = to_call

            if normalized_type == "Raise":
                min_total = max(current_bet + 1, to_call)
                safe_amount = max(safe_amount, min_total)
        else:
            if normalized_type == "Call":
                normalized_type = "Check"
                safe_amount = 0
            elif normalized_type == "Raise":
                normalized_type = "Bet"
            if normalized_type == "Bet":
                safe_amount = max(safe_amount, current_bet + 1)

        safe_amount = min(safe_amount, max_commit)
        return normalized_type, safe_amount

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

    def _build_state_description(
        self,
        game_state: GameState,
        hand: List[CardModel],
        include_action_log: bool = False,
    ) -> str:
        board = " ".join([f"{c.rank}{c.suit}" for c in game_state.community_cards]) or "無"
        cards = " ".join([f"{c.rank}{c.suit}" for c in hand]) or "未知"
        action_log_desc = ""
        if include_action_log and getattr(game_state, "action_log", None):
            formatted_actions = []
            for log in game_state.action_log:
                amount = getattr(log, "amount", None)
                if amount is None and isinstance(log, dict):
                    amount = log.get("amount", 0)
                amount_note = f" {amount}" if amount else ""
                stage = getattr(log, "stage", None) or (
                    log.get("stage") if isinstance(log, dict) else ""
                )
                position = getattr(log, "position", None) or (
                    log.get("position") if isinstance(log, dict) else ""
                )
                name = getattr(log, "name", None) or (
                    log.get("name") if isinstance(log, dict) else ""
                )
                action = getattr(log, "action", None) or (
                    log.get("action") if isinstance(log, dict) else ""
                )
                formatted_actions.append(
                    f"[{stage}] {position} {name}: {action}{amount_note}"
                )
            action_log_desc = "歷史行動：" + " | ".join(formatted_actions) + "\n"

        desc = (
            f"目前底池：{game_state.pot_size}\n"
            f"公共牌：{board}\n"
            f"手牌：{cards}\n"
            f"行動位置：{game_state.action_position}\n"
            f"當前跟注金額：{game_state.current_bet}\n"
            f"{action_log_desc}"
        )
        return desc
