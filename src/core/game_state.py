import random
from collections import Counter
from typing import List, Dict, Any
from src.api.schemas import UserAction
from src.core.logger import get_logger

logger = get_logger(__name__)

# 假設 Card 和 Player 類已定義 (如前所述)
class Card:
    def __init__(self, rank, suit):
        self.rank = rank
        self.suit = suit
    def to_model(self):
        return {'rank': self.rank, 'suit': self.suit}

class Player:
    def __init__(self, name, chips):
        self.name = name
        self.chips = chips
        self.hand = []
        self.position = ""
        self.seat_number = 0
        self.in_pot = 0
        self.is_active = True

    def fold(self):
        """玩家棄牌"""
        self.is_active = False

    def bet(self, amount: int) -> int:
        """玩家投入籌碼"""
        if amount > self.chips:
            amount = self.chips  # 全下
        self.chips -= amount
        self.in_pot += amount
        return amount

    def to_model(self, is_current_player: bool = False, current_round_bet: int = 0):
        hero_can_see_hand = self.name.lower() == 'hero'
        hand_model = [c.to_model() for c in self.hand] if (is_current_player or hero_can_see_hand) else []
        return {
            'name': self.name,
            'position': self.position,
            'seat_number': self.seat_number,
            'chips': self.chips,
            'in_pot': self.in_pot,
            'current_round_bet': current_round_bet,
            'is_active': self.is_active,
            'hand': hand_model
        }

class Table:
    POSITIONS = ['🅱️BTN', 'SB', 'BB', 'UTG', 'MP', 'CO']
    HERO_SEAT = 4
    SEAT_ORDER = [1, 2, 3, 4, 5, 6]
    RANK_ORDER = ['2', '3', '4', '5', '6', '7', '8', '9', 'T', 'J', 'Q', 'K', 'A']
    RANK_VALUE = {rank: idx for idx, rank in enumerate(RANK_ORDER)}

    def __init__(self, players_data: Dict[str, int], big_blind: int = 100):
        self.big_blind = big_blind
        self.initial_stacks = dict(players_data)
        self.players = [Player(name, chips) for name, chips in players_data.items()]
        self.button_index = random.randint(0, len(self.players) - 1)
        self.pot = 0
        self.community_cards: List[Card] = []
        self.current_bet = 0
        self.current_player_index = -1 # 當前行動的玩家索引
        self.deck: List[Card] = []
        self.current_stage: str = 'preflop'
        self.hand_over: bool = False
        self.opponent_hands: List[Dict[str, Any]] = []
        self.current_round_bets: Dict[str, int] = {}
        self.action_queue: List[int] = []
        self.action_log: List[Dict[str, Any]] = []
        self.hand_result: Dict[str, Any] | None = None

    def _build_deck(self) -> List[Card]:
        ranks = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2']
        suits = ['s', 'h', 'd', 'c']
        deck = [Card(rank, suit) for rank in ranks for suit in suits]
        random.shuffle(deck)
        return deck

    def _reset_players_for_new_hand(self):
        for p in self.players:
            p.chips = self.initial_stacks.get(p.name, p.chips)
            p.in_pot = 0
            p.is_active = True
            p.hand = []

    def _assign_seats(self):
        """將玩家分配到 1-6 號座位，Hero 固定在 4 號。"""
        hero_player = self.get_hero()
        available_seats = [seat for seat in self.SEAT_ORDER if seat != self.HERO_SEAT]
        random.shuffle(available_seats)

        if hero_player:
            hero_player.seat_number = self.HERO_SEAT

        other_players = [p for p in self.players if p is not hero_player]
        for p, seat in zip(other_players, available_seats):
            p.seat_number = seat

    def _rotated_positions(self, hero_pos: str) -> List[str]:
        """依照座位順序，從 Hero 的位置開始循環分配其餘位置。"""
        start = self.POSITIONS.index(hero_pos)
        return self.POSITIONS[start:] + self.POSITIONS[:start]

    def _seat_sequence_from_hero(self) -> List[int]:
        hero_seat = self.HERO_SEAT
        start_idx = self.SEAT_ORDER.index(hero_seat)
        return self.SEAT_ORDER[start_idx:] + self.SEAT_ORDER[:start_idx]

    def _player_in_seat(self, seat_number: int) -> Player | None:
        return next((p for p in self.players if p.seat_number == seat_number), None)

    def _assign_positions(self):
        """隨機賦予 Hero 任意位置，並按座位順序分配剩餘位置。"""
        hero_player = self.get_hero()
        hero_position = random.choice(self.POSITIONS)

        ordered_positions = self._rotated_positions(hero_position)
        seats_in_order = self._seat_sequence_from_hero()

        for seat, pos in zip(seats_in_order, ordered_positions):
            player = self._player_in_seat(seat)
            if player:
                player.position = pos

    def _seat_sequence_from_position(self, position: str) -> List[int]:
        """回傳從指定位置開始的座位循環順序。"""
        # 找出指定位置的座位號
        start_seat = next(
            (p.seat_number for p in self.players if p.position == position),
            self.HERO_SEAT  # 如果沒找到則預設用 HERO_SEAT
        )
        start_idx = self.SEAT_ORDER.index(start_seat)
        # 從該座位開始旋轉
        return self.SEAT_ORDER[start_idx:] + self.SEAT_ORDER[:start_idx]

    def _player_by_position(self, position: str) -> Player | None:
        return next((p for p in self.players if p.position == position), None)
    
    def _deal_cards(self):
        self.deck = self._build_deck()

        ranks_order = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2']

        for seat in self._seat_sequence_from_position('SB'):
            player = self._player_in_seat(seat)
            if player:
                # 發兩張牌
                dealt = [self.deck.pop(), self.deck.pop()]
                # 排序（由大到小）
                player.hand = sorted(
                    dealt,
                    key=lambda c: ranks_order.index(c.rank),
                )

        # 翻前開始，因此公共牌為空
        self.community_cards = []

    def get_hero(self) -> Player | None:
        return next((p for p in self.players if p.name.lower() == 'hero'), None)

    def start_hand(self):
        self.hand_over = False
        self.current_stage = 'preflop'
        self.opponent_hands = []
        self.action_log = []
        self.hand_result = None

        self._reset_players_for_new_hand()
        self._assign_seats()
        self._assign_positions()
        self._deal_cards()

        self.pot = 0
        self.current_bet = 0
        self.current_round_bets = {p.name: 0 for p in self.players}
        self.action_queue = []
        self.community_cards = []

        self._post_blinds()
        self._start_preflop_action()
        logger.info(
            "Hand initialized",
            extra={
                "button_index": self.button_index,
                "hero_seat": self.HERO_SEAT,
                "positions": {p.name: p.position for p in self.players},
            },
        )

    def _log_action(self, player: Player | None, action: str, amount: int = 0):
        if not player:
            return
        self.action_log.append({
            'name': player.name,
            'position': player.position,
            'seat_number': player.seat_number,
            'action': action,
            'stage': self.current_stage,
            'amount': amount,
        })
        logger.info(
            "Action logged",
            extra={
                "player_name": player.name,
                "position": player.position,
                "seat_number": player.seat_number,
                "action": action,
                "stage": self.current_stage,
                "amount": amount,
            },
        )
        
    def get_current_player(self) -> Player:
        """獲取當前行動的玩家"""
        if self.current_player_index < 0 or self.current_player_index >= len(self.players):
            self.current_player_index = 0
        return self.players[self.current_player_index]

    def process_action(self, action: UserAction):
        """處理用戶行動 (簡化版)"""
        if self.hand_over:
            logger.warning("Action received after hand over")
            return

        player = self.get_current_player()
        current_commit = self.current_round_bets.get(player.name, 0)
        to_call = max(self.current_bet - current_commit, 0)
        available_total = player.chips + current_commit

        if action.action_type == 'Fold':
            player.fold()
            self._log_action(player, 'Fold', 0)
            if player.name.lower() == 'hero':
                self._end_hand_on_hero_fold()
                return
        elif action.action_type == 'Check':
            if to_call != 0:
                raise ValueError("無法過牌，必須至少跟注當前下注。")
            self._log_action(player, 'Check', 0)
        elif action.action_type == 'Call':
            if to_call <= 0:
                raise ValueError("目前無需跟注，請選擇過牌或下注。")
            contributed = player.bet(to_call)
            self.pot += contributed
            self.current_round_bets[player.name] = current_commit + contributed
            self._log_action(player, 'Call', contributed)
        elif action.action_type in ['Bet', 'Raise']:
            if action.action_type == 'Bet' and self.current_bet > 0:
                raise ValueError("當前已有下注，請選擇跟注或加注。")
            amount = min(action.amount, available_total)
            if amount <= self.current_bet:
                raise ValueError("下注/加注金額必須大於當前下注。")
            to_put_in = max(amount - current_commit, 0)
            contributed = player.bet(to_put_in)
            self.pot += contributed
            self.current_round_bets[player.name] = current_commit + contributed
            self.current_bet = self.current_round_bets[player.name]
            self._reset_queue_after_raise(player)
            self._log_action(player, action.action_type, self.current_bet)
            logger.info(
                "Raise/Bet processed",
                extra={
                    "position": player.position,
                    "action": action.action_type,
                    "amount": self.current_bet,
                    "pot": self.pot,
                },
            )
            return
        elif action.action_type == 'AllIn':
            if player.chips <= 0:
                raise ValueError("沒有可用籌碼可全下。")

            contributed = player.bet(player.chips)
            self.pot += contributed
            new_commit = current_commit + contributed
            self.current_round_bets[player.name] = new_commit

            if new_commit > self.current_bet:
                self.current_bet = new_commit
                self._reset_queue_after_raise(player)
                self._log_action(player, 'AllIn', new_commit)
                logger.info(
                    "All-in processed",
                    extra={
                        "position": player.position,
                        "amount": new_commit,
                        "pot": self.pot,
                    },
                )
                return
            else:
                self._log_action(player, 'AllIn', new_commit)
        else:
            raise ValueError("無效的行動類型。")

        logger.info(
            "Action processed",
            extra={
                "position": player.position,
                "action": action.action_type,
                "amount": action.amount,
                "pot": self.pot,
            },
        )
        self._advance_to_next_player()

    def _advance_stage(self):
        """依序進入翻牌、轉牌、河牌的下注流程"""
        logger.info("Advancing stage", extra={"from_stage": self.current_stage})
        if self.current_stage == 'preflop':
            self._deal_community_cards(3)
            self._start_postflop_round('flop')
        elif self.current_stage == 'flop':
            self._deal_community_cards(1)
            self._start_postflop_round('turn')
        elif self.current_stage == 'turn':
            self._deal_community_cards(1)
            self._start_postflop_round('river')
        elif self.current_stage == 'river':
            self.current_stage = 'showdown'
            self.hand_over = True
            self._reveal_opponents()
            self._finalize_showdown()

    def _deal_community_cards(self, count: int):
        self.community_cards.extend([self.deck.pop() for _ in range(count)])
        logger.info(
            "Community cards dealt",
            extra={
                "count": count,
                "community_cards": [c.to_model() for c in self.community_cards],
            },
        )

    def _start_preflop_action(self):
        """建立翻前的行動隊列，從 UTG 開始"""
        self.current_stage = 'preflop'
        self.action_queue = self._build_action_queue('UTG')
        self._advance_to_next_player()
        logger.info(
            "Preflop action started",
            extra={"current_player": self.get_current_player().name},
        )

    def _start_postflop_round(self, stage_name: str):
        """開始翻牌/轉牌/河牌階段並建立新的下注隊列"""
        if self.hand_over:
            return

        self.current_stage = stage_name
        self.current_bet = 0
        self.current_round_bets = {p.name: 0 for p in self.players if p.is_active}
        self.action_queue = self._build_action_queue('SB')
        if not self.action_queue:
            self.hand_over = True
            self.current_stage = 'showdown'
            active_players = [p for p in self.players if p.is_active]
            winner = active_players[0] if active_players else None
            self._set_hand_result(winner)
            self._reveal_opponents()
            return
        self._advance_to_next_player()
        logger.info(
            "Postflop round started",
            extra={
                "stage": self.current_stage,
                "current_player": self.get_current_player().name,
            },
        )

    def _build_action_queue(self, start_position: str) -> List[int]:
        seats = self._seat_sequence_from_position(start_position)
        queue: List[int] = []
        for seat in seats:
            player = self._player_in_seat(seat)
            if player and player.is_active:
                queue.append(self.players.index(player))
        return queue

    def _reset_queue_after_raise(self, raiser: Player):
        seats = self._seat_sequence_from_position(raiser.position)[1:]
        queue: List[int] = []
        for seat in seats:
            player = self._player_in_seat(seat)
            if player and player.is_active and player is not raiser:
                queue.append(self.players.index(player))
        self.action_queue = queue
        if not self.action_queue:
            self._end_betting_round()
        else:
            self._advance_to_next_player()
        logger.info(
            "Queue reset after raise",
            extra={
                "raiser": raiser.name,
                "queue": [self.players[i].name for i in self.action_queue],
            },
        )

    def _advance_to_next_player(self):
        while self.action_queue:
            next_index = self.action_queue.pop(0)
            player = self.players[next_index]
            if player.is_active:
                self.current_player_index = next_index
                logger.info(
                    "Next player",
                    extra={"player_name": player.name, "position": player.position},
                )
                return
        self._end_betting_round()

    def _end_betting_round(self):
        active_players = [p for p in self.players if p.is_active]
        if len(active_players) <= 1:
            winner = active_players[0] if active_players else None
            self._refund_uncalled_chips(winner)
            self.hand_over = True
            self.current_stage = 'showdown'
            self._set_hand_result(winner)
            self._reveal_opponents()
            return
        self._advance_stage()
        logger.info(
            "Betting round ended",
            extra={"stage": self.current_stage, "pot": self.pot},
        )

    def _end_hand_on_hero_fold(self):
        """Hero 棄牌時直接結束牌局並發放底池。"""
        active_opponents = [p for p in self.players if p.is_active and p.name.lower() != 'hero']
        winner = active_opponents[0] if active_opponents else None
        self._refund_uncalled_chips(winner)
        self.hand_over = True
        self.current_stage = 'showdown'
        self._set_hand_result(winner)
        self._reveal_opponents()
        logger.info(
            "Hand ended due to hero fold",
            extra={
                "winner": winner.name if winner else None,
                "pot": self.pot,
            },
        )

    def _post_blinds(self):
        """SB/BB 支付盲注，更新底池與當前注額"""
        small_blind = max(self.big_blind // 2, 1)
        sb_player = self._player_by_position('SB')
        bb_player = self._player_by_position('BB')

        if sb_player:
            posted = sb_player.bet(small_blind)
            self.pot += posted
            self.current_round_bets[sb_player.name] = posted
            self._log_action(sb_player, 'Post SB', posted)

        if bb_player:
            posted = bb_player.bet(self.big_blind)
            self.pot += posted
            self.current_round_bets[bb_player.name] = posted
            self.current_bet = self.big_blind
            self._log_action(bb_player, 'Post BB', posted)
        logger.info(
            "Blinds posted",
            extra={
                "sb": sb_player.name if sb_player else None,
                "bb": bb_player.name if bb_player else None,
                "small_blind": small_blind,
                "big_blind": self.big_blind,
                "pot": self.pot,
            },
        )

    def _reveal_opponents(self):
        """在牌局結束時揭露對手手牌供前端顯示。"""
        self.opponent_hands = []
        for p in self.players:
            if p.name.lower() == 'hero':
                continue
            self.opponent_hands.append({
                'name': p.name,
                'position': p.position,
                'seat_number': p.seat_number,
                'hand': [c.to_model() for c in p.hand]
            })

    def _refund_uncalled_chips(self, winner: Player | None):
        """將未被跟注的籌碼退還給最後的下注者。"""
        if not winner:
            return

        highest_other_bet = max(
            (bet for name, bet in self.current_round_bets.items() if name != winner.name),
            default=0
        )
        winner_bet = self.current_round_bets.get(winner.name, 0)
        uncalled = max(winner_bet - highest_other_bet, 0)

        if uncalled > 0:
            refund = min(uncalled, self.pot)
            winner.chips += refund
            winner.in_pot = max(winner.in_pot - refund, 0)
            self.pot -= refund
            self.current_round_bets[winner.name] = winner_bet - refund
            self.current_bet = highest_other_bet
            logger.info(
                "Refunded uncalled chips",
                extra={"winner": winner.name, "refund": refund, "pot": self.pot},
            )

    def _set_hand_result(self, winner: Player | None):
        """記錄牌局結果並將底池分配給贏家。"""
        if not winner:
            self.hand_result = None
            return

        amount_won = self.pot
        winner.chips += amount_won
        self.pot = 0
        self.hand_result = {
            'winner_name': winner.name,
            'seat_number': winner.seat_number,
            'position': winner.position,
            'amount_won': amount_won,
            'description': f"{winner.position} ({winner.name}) 贏得了 ${amount_won} 底池",
        }
        logger.info(
            "Hand result set",
            extra={
                "winner": winner.name,
                "amount_won": amount_won,
                "position": winner.position,
            },
        )

    def _finalize_showdown(self):
        """根據公共牌與手牌強度決定贏家。"""
        active_players = [p for p in self.players if p.is_active]
        if not active_players:
            self._set_hand_result(None)
            logger.info("Showdown finalized", extra={"winner": None})
            return

        best_strength: tuple | None = None
        winners: List[Player] = []

        for player in active_players:
            strength = self._evaluate_hand_strength(player)
            if best_strength is None or strength > best_strength:
                best_strength = strength
                winners = [player]
            elif strength == best_strength:
                winners.append(player)

        # 若有平手情況，選擇座位號較小的玩家作為贏家以維持一致性
        winner = sorted(winners, key=lambda p: p.seat_number)[0]
        self._set_hand_result(winner)
        logger.info(
            "Showdown finalized",
            extra={
                "winner": winner.name if winner else None,
                "winning_hand": best_strength,
            },
        )

    def _evaluate_hand_strength(self, player: Player) -> tuple:
        """回傳用於比較的牌型強度元組 (依賴德州撲克 7 張牌最佳牌型)。"""
        cards = player.hand + self.community_cards
        rank_values = [self.RANK_VALUE[c.rank] for c in cards]
        rank_counter = Counter(rank_values)

        suits: Dict[str, List[int]] = {}
        for c in cards:
            suits.setdefault(c.suit, []).append(self.RANK_VALUE[c.rank])

        flush_suit = next((s for s, ranks in suits.items() if len(ranks) >= 5), None)
        flush_ranks = sorted(suits.get(flush_suit, []), reverse=True)

        straight_high = self._find_straight_high(rank_values)
        straight_flush_high = self._find_straight_high(flush_ranks) if flush_suit else None

        if straight_flush_high is not None:
            return (8, straight_flush_high)

        four_kind = [r for r, cnt in rank_counter.items() if cnt == 4]
        if four_kind:
            quad_rank = max(four_kind)
            kicker = max(r for r in rank_values if r != quad_rank)
            return (7, quad_rank, kicker)

        trips = sorted([r for r, cnt in rank_counter.items() if cnt == 3], reverse=True)
        pairs = sorted([r for r, cnt in rank_counter.items() if cnt == 2], reverse=True)

        if trips and (pairs or len(trips) > 1):
            top_trip = trips[0]
            top_pair = trips[1] if len(trips) > 1 else pairs[0]
            return (6, top_trip, top_pair)

        if flush_suit:
            top_five_flush = flush_ranks[:5]
            return (5, *top_five_flush)

        if straight_high is not None:
            return (4, straight_high)

        if trips:
            top_trip = trips[0]
            kickers = self._top_kickers(rank_values, exclude=[top_trip], count=2)
            return (3, top_trip, *kickers)

        if len(pairs) >= 2:
            top_two_pairs = pairs[:2]
            kicker = self._top_kickers(rank_values, exclude=top_two_pairs, count=1)[0]
            return (2, *top_two_pairs, kicker)

        if pairs:
            pair_rank = pairs[0]
            kickers = self._top_kickers(rank_values, exclude=[pair_rank], count=3)
            return (1, pair_rank, *kickers)

        high_cards = self._top_kickers(rank_values, exclude=[], count=5)
        return (0, *high_cards)

    def _find_straight_high(self, rank_values: List[int]) -> int | None:
        """回傳順子的最高牌值 (無順子則為 None)。"""
        unique = list(set(rank_values))
        if self.RANK_VALUE['A'] in unique:
            unique.append(-1)  # 處理 A 作為 1 的順子 (A-2-3-4-5)
        unique = sorted(unique)

        run = 1
        best_high: int | None = None
        for i in range(1, len(unique)):
            if unique[i] - unique[i - 1] == 1:
                run += 1
                if run >= 5:
                    best_high = unique[i]
            else:
                run = 1
        return best_high

    def _top_kickers(self, rank_values: List[int], exclude: List[int], count: int) -> List[int]:
        """取得排除特定牌值後最高的 kicker 列表。"""
        filtered = [r for r in sorted(rank_values, reverse=True) if r not in exclude]
        kickers: List[int] = []
        for r in filtered:
            if r not in kickers:
                kickers.append(r)
            if len(kickers) >= count:
                break
        return kickers

    def get_state_for_frontend(self) -> Dict[str, Any]:
        """將 Table 狀態轉換為 Pydantic 模型需要的字典"""

        action_player = self.get_current_player()

        players_state = []
        for i, p in enumerate(self.players):
            is_current = (i == self.current_player_index)
            players_state.append(p.to_model(is_current, self.current_round_bets.get(p.name, 0)))

        return {
            'pot_size': self.pot,
            'community_cards': [c.to_model() for c in self.community_cards],
            'action_position': action_player.position,
            'players': players_state,
            'current_bet': self.current_bet,
            'current_stage': self.current_stage,
            'hand_over': self.hand_over,
            'opponent_hands': self.opponent_hands,
            'action_log': self.action_log,
            'hand_result': self.hand_result
        }
