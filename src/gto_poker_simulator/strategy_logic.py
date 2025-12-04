import os
import json
from typing import Any, List, Tuple
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
        """
        改寫後版本：
        - 使用 response_format={"type": "json_object"} 強制模型回傳合法 JSON
        - prompt 拆段降低混亂
        - 保證 gto_matrix 結構統一
        - 移除易出錯的 _parse_json_reply
        """

        players = game_state.players
        action_position = game_state.action_position
        acting_player = next((p for p in players if p.position == action_position), None)
        hand = acting_player.hand if acting_player else []
        hero_stack = acting_player.chips if acting_player else 0

        # 敘述牌局狀態
        state_desc = self._build_state_description(
            game_state, hand, include_action_log=True
        )

        # 依據你的合法行動規則重新整理一次（簡化版）
        stage = game_state.current_stage
        position = action_position

        if stage == "preflop":
            if position in ["UTG", "HJ", "CO", "BTN", "SB"]:
                legal_actions = ["Call", "Raise", "Fold"]
            elif position == "BB":
                legal_actions = ["Check", "Call", "Raise", "Fold"]
            else:
                legal_actions = ["Call", "Raise", "Fold"]
        else:
            legal_actions = ["Check", "Call", "Raise", "Fold"]

        legal_action_str = ", ".join([f'"{a}"' for a in legal_actions])

        system_prompt = (
            "你是一位頂尖的德州撲克 6-max 現金桌 GTO 教練，"
            "必須嚴格依照 JSON schema 回覆，且不能產生任何額外文字。"
        )

        context_prompt = f"""
    以下是當前牌局資訊：

    {state_desc}

    Hero 行動：{user_action.action_type}
    下注金額：{user_action.amount}
    剩餘籌碼：{hero_stack}

    合法行動為：{legal_actions}

    請根據 GTO 理論：
    1. 判斷 Hero 行動是否合理
    2. 計算相對於 GTO 的 EV 損失（可概略估算）
    3. 提供每個行動 (Check / Call / Raise / Fold) 的 GTO 頻率 與 EV（非行動填 0）
    """

        json_schema_prompt = f"""
    請務必輸出完全符合以下 JSON 格式（不能加入註解、不能加入 ```）：

    {{
    "user_action_correct": true 或 false,
    "ev_loss_bb": 0,
    "gto_matrix": [
        {{"action": "Check", "frequency": 0, "ev_bb": 0}},
        {{"action": "Call", "frequency": 0, "ev_bb": 0}},
        {{"action": "Raise", "frequency": 0, "ev_bb": 0}},
        {{"action": "Fold", "frequency": 0, "ev_bb": 0}}
    ],
    "explanation": "原因說明"
    }}

    重要規則：
    - 只能使用合法行動：{legal_action_str}
    - 不合法行動的 frequency = 0 且 ev_bb = 0
    - frequency 必須介於 0~1
    - JSON 之外不能有任何文字
    """

        logger.info(
            "OpenAI prompt for user action evaluation",
            extra={"context": context_prompt, "schema": json_schema_prompt},
        )

        reply_json = {}

        if self.api_key and self.client:
            try:
                response = self.client.responses.create(
                    model="gpt-5.1",
                    response_format={"type": "json_object"},  # ⭐ 強制 JSON
                    input=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": context_prompt},
                        {"role": "assistant", "content": json_schema_prompt},
                    ],
                )

                # 這裡會盡可能取得 OpenAI 回傳的 JSON 字串
                response_text = self._extract_response_text(response)
                if not response_text:
                    raise ValueError("Empty response from OpenAI")

                reply_json = json.loads(response_text)

                logger.info(
                    "AI Generated JSON for user action evaluation",
                    extra={"JSON": reply_json},
                )

            except Exception as e:
                logger.error(
                    "GPT JSON error in evaluate_user_action",
                    extra={"error": str(e)},
                )

        # ----------------------------
        # Fallback 機制（模型失敗時）
        # ----------------------------
        if not reply_json:
            logger.warning("Falling back to default GTO feedback")

            return self._default_feedback()

        # ----------------------------
        # 將 JSON 組成物件
        # ----------------------------
        try:
            gto_matrix, sanitized = self._normalize_gto_matrix(reply_json.get("gto_matrix", []))

            if sanitized:
                logger.warning(
                    "Sanitized AI gto_matrix output",
                    extra={"raw": reply_json.get("gto_matrix", [])},
                )

            return GTOFeedback(
                user_action_correct=bool(reply_json.get("user_action_correct", True)),
                ev_loss_bb=float(reply_json.get("ev_loss_bb", 0.0)),
                gto_matrix=gto_matrix,
                explanation=reply_json.get(
                    "explanation",
                    "AI 回傳資料格式不完整，已自動補齊缺漏欄位。",
                ),
            )
        except Exception as e:
            logger.warning(
                "Invalid JSON structure from AI, using default feedback",
                extra={"error": str(e)},
            )

            return self._default_feedback()

    def _default_feedback(self) -> GTOFeedback:
        return GTOFeedback(
            user_action_correct=True,
            ev_loss_bb=0,
            gto_matrix=[
                GTOActionData(action="Check", frequency=0, ev_bb=0),
                GTOActionData(action="Call", frequency=0, ev_bb=0),
                GTOActionData(action="Raise", frequency=0, ev_bb=0),
                GTOActionData(action="Fold", frequency=0, ev_bb=0),
            ],
            explanation="AI 回傳不合法 JSON，使用預設資料。"
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
                    model="gpt-5.1",
                    input=[
                        {"role": "system", "content": "你是一位德州撲克6人現金桌玩家，請根據gto策略給出合理行動。"},
                        {"role": "user", "content": prompt},
                    ],
                )

                reply = self._extract_response_text(response)

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

    def _extract_response_text(self, response: Any) -> str:
        """
        嘗試從不同的 OpenAI Response 版本中取得文字內容，避免因屬性差異導致回傳空值。
        """

        text = getattr(response, "output_text", None)
        if text:
            return text

        try:
            outputs = getattr(response, "output", None) or getattr(response, "outputs", None)
            if outputs:
                first_output = outputs[0]
                content = getattr(first_output, "content", None)
                if content:
                    first_content = content[0]
                    text_obj = getattr(first_content, "text", None)
                    if isinstance(text_obj, str):
                        return text_obj
                    if text_obj:
                        value = getattr(text_obj, "value", None) or getattr(text_obj, "text", None)
                        if value:
                            return value
        except Exception as exc:
            logger.debug(
                "Failed to extract response text from structured output",
                extra={"error": str(exc)},
            )

        return ""

    def _normalize_gto_matrix(self, gto_matrix_raw: Any) -> Tuple[List[GTOActionData], bool]:
        """
        將模型回傳的 gto_matrix 標準化為完整的四個行動，缺漏或格式錯誤的欄位以 0 補齊。

        Returns tuple (gto_matrix, sanitized) where sanitized 表示是否對輸入進行了修正。
        """

        allowed_actions = ["Check", "Call", "Raise", "Fold"]
        sanitized = False

        # 初始預設值
        matrix_map = {
            action: GTOActionData(action=action, frequency=0.0, ev_bb=0.0)
            for action in allowed_actions
        }

        if not isinstance(gto_matrix_raw, list):
            return list(matrix_map.values()), True

        for item in gto_matrix_raw:
            if not isinstance(item, dict):
                sanitized = True
                continue

            action = item.get("action")
            if action not in matrix_map:
                sanitized = True
                continue

            frequency = item.get("frequency")
            ev_bb = item.get("ev_bb")

            if not isinstance(frequency, (int, float)) or not isinstance(ev_bb, (int, float)):
                sanitized = True
                continue

            sanitized = sanitized or frequency < 0 or frequency > 1
            clamped_frequency = min(max(float(frequency), 0.0), 1.0)

            matrix_map[action] = GTOActionData(
                action=action,
                frequency=clamped_frequency,
                ev_bb=float(ev_bb),
            )

        return [matrix_map[action] for action in allowed_actions], sanitized

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
