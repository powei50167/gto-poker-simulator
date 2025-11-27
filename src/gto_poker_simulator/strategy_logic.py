import os
import json
from typing import List, Optional
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
    LEGAL_ACTIONS = ["Check", "Call", "Raise", "Fold", "AllIn"]
    FREQ_TOLERANCE = 0.05
    EV_LOSS_TOLERANCE = 1.0
    MAX_RETRY = 2

    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.org = os.getenv("OPENAI_ORG")

        if self.api_key:
            self.client = OpenAI(api_key=self.api_key, organization=self.org)
        else:
            self.client = None

    def evaluate_user_action(self, game_state: GameState, user_action: UserAction) -> GTOFeedback:
        players = game_state.players
        action_position = game_state.action_position
        acting_player = next((p for p in players if p.position == action_position), None)
        hand = acting_player.hand if acting_player else []
        hero_stack = acting_player.chips if acting_player else 0

        state_desc = self._build_state_description(game_state, hand)
        current_call_amount = max(game_state.current_bet, 0)

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

        numeric_data: Optional[dict] = None
        explanation_text = ""

        if self.api_key and self.client:
            numeric_data = self._generate_numeric_feedback(
                game_state=game_state,
                user_action=user_action,
                hero_stack=hero_stack,
                state_desc=state_desc,
                current_call_amount=current_call_amount,
            )

            if numeric_data:
                explanation_text = self._generate_explanation(
                    numeric_data=numeric_data,
                    state_desc=state_desc,
                    user_action=user_action,
                )
        else:
            logger.warning("OpenAI client not configured; using fallback feedback")

        if numeric_data:
            gto_matrix = [
                GTOActionData(
                    action=item["action"],
                    frequency=item["frequency"],
                    ev_bb=item["ev_bb"],
                )
                for item in numeric_data.get("gto_matrix", [])
            ]

            return GTOFeedback(
                user_action_correct=numeric_data.get("user_action_correct", True),
                ev_loss_bb=numeric_data.get("ev_loss_bb", 0.0),
                gto_matrix=gto_matrix,
                explanation=explanation_text or "AI 生成的說明缺失。",
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
                GTOActionData(action="Call", frequency=0, ev_bb=0),
                GTOActionData(action="Raise", frequency=0, ev_bb=0),
                GTOActionData(action="Fold", frequency=0, ev_bb=0),
                GTOActionData(action="AllIn", frequency=0, ev_bb=0),
            ],
            explanation="AI Agent 異常或回傳非法 JSON，系統回傳預設資料。",
        )

    def _generate_numeric_feedback(
        self,
        game_state: GameState,
        user_action: UserAction,
        hero_stack: int,
        state_desc: str,
        current_call_amount: int,
    ) -> Optional[dict]:
        """
        第一階段：要求模型依照固定規則回傳純 JSON 數值，並驗證合法性。
        若檢查失敗會帶著錯誤訊息重試。
        """

        reply = ""
        normalized_user_action = self._normalize_action_for_matrix(
            user_action.action_type, current_call_amount
        )
        retry_reason = ""

        for attempt in range(self.MAX_RETRY + 1):
            prompt = self._build_numeric_prompt(
                state_desc=state_desc,
                user_action=user_action,
                hero_stack=hero_stack,
                current_call_amount=current_call_amount,
                normalized_user_action=normalized_user_action,
                retry_reason=retry_reason,
            )

            try:
                response = self.client.responses.create(
                    model="gpt-4o-mini",
                    input=[
                        {"role": "system", "content": "你是一位德州撲克6人現金桌 GTO 教練。"},
                        {"role": "user", "content": prompt},
                    ],
                )
                reply = response.output_text
                logger.info(
                    "OpenAI response for numeric GTO feedback",
                    extra={
                        "attempt": attempt + 1,
                        "reply": reply,
                        "stage": game_state.current_stage,
                    },
                )

                data = self._parse_json_reply(reply)
                errors = self._validate_numeric_data(
                    data=data,
                    current_call_amount=current_call_amount,
                    normalized_user_action=normalized_user_action,
                )

                if not errors:
                    return data

                retry_reason = (
                    "你輸出的內容未通過以下檢查，請修正後重新輸出純 JSON："
                    + " ; ".join(errors)
                )
            except Exception as e:
                retry_reason = f"解析或模型回應錯誤：{str(e)}"
                logger.error(
                    "GPT error while handling numeric GTO JSON",
                    extra={"error": str(e), "reply": reply},
                )

        logger.error(
            "Exceeded retry limit for numeric GTO feedback",
            extra={"reason": retry_reason, "reply": reply},
        )
        return None

    def _generate_explanation(
        self,
        numeric_data: dict,
        state_desc: str,
        user_action: UserAction,
    ) -> str:
        """第二階段：使用經驗證的數值請模型生成一致的說明。"""

        payload = json.dumps(numeric_data, ensure_ascii=False)
        instruction = (
            "以下是已驗證的數值，請直接據此撰寫中文說明，不得修改任何數值。"
            "說明需呼應 user_action_correct 與 ev_loss_bb：若為 true，強調選擇仍可接受；"
            "若為 false，要指出該行動在 EV 上明顯劣於其它選項。請引用最高 EV 行動、"
            "玩家行動的 EV 以及大約的 EV 損失。"
        )

        prompt = (
            f"牌局資訊：{state_desc}\n"
            f"玩家行動：{user_action.action_type}，金額：{user_action.amount}\n"
            f"已驗證數值 JSON：{payload}"
        )

        try:
            response = self.client.responses.create(
                model="gpt-4o-mini",
                input=[
                    {"role": "system", "content": "你是一位德州撲克6人現金桌 GTO 教練。"},
                    {"role": "user", "content": instruction},
                    {"role": "user", "content": prompt},
                ],
            )
            explanation = response.output_text.strip()
            logger.info(
                "OpenAI response for explanation",
                extra={"explanation": explanation},
            )
            return explanation
        except Exception as e:
            logger.error(
                "GPT error while generating explanation",
                extra={"error": str(e), "payload": payload},
            )
            return "AI 說明產生失敗，請參考數值結果。"

    def _build_numeric_prompt(
        self,
        state_desc: str,
        user_action: UserAction,
        hero_stack: int,
        current_call_amount: int,
        normalized_user_action: str,
        retry_reason: str = "",
    ) -> str:
        """建立要求模型回傳純 JSON 的提示，包含法律動作限制與檢核規則。"""

        illegal_check_notice = (
            "注意：桌上已有人下注 (current_call_amount > 0)，Check 不是合法動作，不可以出現。"
            if current_call_amount > 0
            else ""
        )

        error_feedback = f"先前錯誤：{retry_reason}\n" if retry_reason else ""

        schema_text = json.dumps(
            {
                "type": "object",
                "properties": {
                    "user_action_correct": {"type": "boolean"},
                    "ev_loss_bb": {"type": "number"},
                    "gto_matrix": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "action": {"type": "string"},
                                "frequency": {"type": "number"},
                                "ev_bb": {"type": "number"},
                            },
                            "required": ["action", "frequency", "ev_bb"],
                        },
                    },
                },
                "required": ["user_action_correct", "ev_loss_bb", "gto_matrix"],
            },
            ensure_ascii=False,
        )

        instructions = f"""
{error_feedback}你是一位德州撲克6人現金桌 GTO 教練，請只回傳可以被 json.loads 解析的合法 JSON，不要加入 ``` 或說明。

1) legal_actions: {self.LEGAL_ACTIONS}。gto_matrix 只能出現這些動作。{illegal_check_notice}
2) 先在 gto_matrix 中列出每個合法行動的 frequency (0~1) 及 ev_bb，frequency 總和約為 1。
3) 找出 best_ev_bb = 所有行動 ev_bb 的最大值；找出玩家實際行動 ({normalized_user_action}) 的 ev_user。
4) 設定 ev_loss_bb = best_ev_bb - ev_user。
5) 規則：若 ev_loss_bb ≤ 30 則 user_action_correct = true，否則 false。不要用「請你評估」，直接依規則填入。
6) 僅輸出 JSON 數值，不要寫說明文字，格式必須符合以下 JSON Schema：{schema_text}
"""

        context = (
            f"牌桌資訊：{state_desc}\n玩家行動：{user_action.action_type}，下注金額："
            f"{user_action.amount}，剩餘籌碼：{hero_stack}\n"
            f"current_call_amount：{current_call_amount}\n"
            "請先決定數值，再輸出 JSON。"
        )

        return instructions + "\n" + context

    def _validate_numeric_data(
        self,
        data: dict,
        current_call_amount: int,
        normalized_user_action: str,
    ) -> List[str]:
        errors: List[str] = []
        gto_matrix = data.get("gto_matrix")
        if not isinstance(gto_matrix, list) or not gto_matrix:
            errors.append("gto_matrix 缺失或不是陣列")
            return errors

        freq_sum = 0.0
        best_ev = None
        user_ev = None

        for item in gto_matrix:
            action = item.get("action")
            frequency = item.get("frequency", 0)
            ev_bb = item.get("ev_bb")

            if action not in self.LEGAL_ACTIONS:
                errors.append(f"出現非法動作: {action}")
                continue

            if current_call_amount > 0 and action == "Check":
                errors.append("current_call_amount > 0 時仍出現 Check")

            try:
                freq_sum += float(frequency)
            except (TypeError, ValueError):
                errors.append(f"frequency 無法轉為數值: {frequency}")

            try:
                ev_value = float(ev_bb)
            except (TypeError, ValueError):
                errors.append(f"ev_bb 無法轉為數值: {ev_bb}")
                continue

            if best_ev is None or ev_value > best_ev:
                best_ev = ev_value

            if action == normalized_user_action:
                user_ev = ev_value

        if abs(freq_sum - 1.0) > self.FREQ_TOLERANCE:
            errors.append("frequency 總和未接近 1")

        if best_ev is None or user_ev is None:
            errors.append("找不到最佳 EV 或玩家行動的 EV")
            return errors

        expected_loss = best_ev - user_ev
        reported_loss = data.get("ev_loss_bb")
        try:
            reported_loss_val = float(reported_loss)
        except (TypeError, ValueError):
            errors.append("ev_loss_bb 不是數值")
            reported_loss_val = None

        if reported_loss_val is not None:
            if abs(reported_loss_val - expected_loss) > self.EV_LOSS_TOLERANCE:
                errors.append("ev_loss_bb 與 best_ev_bb - ev_user 不符")

        expected_correct = expected_loss <= 30
        if data.get("user_action_correct") != expected_correct:
            errors.append("user_action_correct 與規則 (ev_loss_bb ≤ 30) 不符")

        return errors

    def _normalize_action_for_matrix(self, action_type: str, current_call_amount: int) -> str:
        lowered = action_type.lower()
        mapping = {
            "call": "Call",
            "check": "Check",
            "bet": "Raise",
            "raise": "Raise",
            "fold": "Fold",
            "allin": "AllIn",
            "all-in": "AllIn",
            "all_in": "AllIn",
        }
        normalized = mapping.get(lowered, "Call")
        if current_call_amount > 0 and normalized == "Check":
            return "Call"
        if current_call_amount == 0 and normalized == "Call":
            return "Check"
        return normalized

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
