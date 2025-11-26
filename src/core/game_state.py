import random
from typing import List, Dict, Any
from src.api.schemas import UserAction

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

    def to_model(self, is_current_player: bool = False):
        hand_model = [c.to_model() for c in self.hand] if is_current_player else []
        return {
            'name': self.name,
            'position': self.position,
            'seat_number': self.seat_number,
            'chips': self.chips,
            'in_pot': self.in_pot,
            'is_active': self.is_active,
            'hand': hand_model
        }

class Table:
    POSITIONS = ['BB', 'SB', 'BTN', 'CO', 'MP', 'UTG']
    HERO_SEAT = 4
    SEAT_ORDER = [1, 2, 3, 4, 5, 6]

    def __init__(self, players_data: Dict[str, int], big_blind: int = 20):
        self.big_blind = big_blind
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

    def _build_deck(self) -> List[Card]:
        ranks = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2']
        suits = ['s', 'h', 'd', 'c']
        deck = [Card(rank, suit) for rank in ranks for suit in suits]
        random.shuffle(deck)
        return deck

    def _assign_seats(self):
        """將玩家分配到 1-6 號座位，Hero 固定在 4 號。"""
        hero_player = self.get_hero()
        available_seats = [seat for seat in self.SEAT_ORDER if seat != self.HERO_SEAT]
        random.shuffle(available_seats)

        for p in self.players:
            p.in_pot = 0
            p.is_active = True
            p.hand = []

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

    def _deal_cards(self):
        self.deck = self._build_deck()

        # 依照 Hero 開始的座位順序發給每位玩家兩張不重複的手牌
        for seat in self._seat_sequence_from_hero():
            player = self._player_in_seat(seat)
            if player:
                player.hand = [self.deck.pop(), self.deck.pop()]

        # 翻前開始，因此公共牌為空
        self.community_cards = []

    def get_hero(self) -> Player | None:
        return next((p for p in self.players if p.name.lower() == 'hero'), None)

    def start_hand(self):
        self.hand_over = False
        self.current_stage = 'preflop'
        self.opponent_hands = []

        self._assign_seats()
        self._assign_positions()
        self._deal_cards()

        self.pot = 0
        self.current_bet = self.big_blind

        hero_player = self.get_hero()
        if hero_player:
            self.current_player_index = self.players.index(hero_player)
        else:
            self.current_player_index = 0

        print("新的牌局已啟動，Hero 等待行動...")
        
    def get_current_player(self) -> Player:
        """獲取當前行動的玩家"""
        if self.current_player_index < 0 or self.current_player_index >= len(self.players):
            self.current_player_index = 0
        return self.players[self.current_player_index]

    def process_action(self, action: UserAction):
        """處理用戶行動 (簡化版)"""
        if self.hand_over:
            print("本局已結束，請開始新牌局。")
            return

        player = self.get_current_player()

        if action.action_type == 'Fold':
            player.fold()
            self.hand_over = True
            self._reveal_opponents()
        elif action.action_type == 'Call':
            to_call = self.current_bet - player.in_pot
            if to_call < 0:
                raise ValueError("無法跟注，應該 Check 或 Bet。")
            if to_call > 0:
                self.pot += player.bet(to_call)
        elif action.action_type in ['Bet', 'Raise', 'Check']:
            amount = action.amount
            if action.action_type in ['Bet', 'Raise']:
                to_put_in = max(amount - player.in_pot, 0)
                self.pot += player.bet(to_put_in)
                self.current_bet = max(self.current_bet, amount)
        else:
            raise ValueError("無效的行動類型。")

        if not self.hand_over:
            self._advance_stage()
            if self.current_stage == 'showdown':
                self.hand_over = True
                self._reveal_opponents()

        print(f"處理了 {player.position} 的行動: {action.action_type} {action.amount}")

    def _advance_stage(self):
        """Hero 行動後自動推進牌局直到河牌決策。"""
        if self.current_stage == 'preflop':
            self.community_cards.extend([self.deck.pop() for _ in range(3)])
            self.current_stage = 'flop'
        elif self.current_stage == 'flop':
            self.community_cards.append(self.deck.pop())
            self.current_stage = 'turn'
        elif self.current_stage == 'turn':
            self.community_cards.append(self.deck.pop())
            self.current_stage = 'river'
        elif self.current_stage == 'river':
            self.current_stage = 'showdown'

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

    def get_state_for_frontend(self) -> Dict[str, Any]:
        """將 Table 狀態轉換為 Pydantic 模型需要的字典"""

        action_player = self.get_current_player()

        players_state = []
        for i, p in enumerate(self.players):
            is_current = (i == self.current_player_index)
            players_state.append(p.to_model(is_current))

        return {
            'pot_size': self.pot,
            'community_cards': [c.to_model() for c in self.community_cards],
            'action_position': action_player.position,
            'players': players_state,
            'current_bet': self.current_bet,
            'current_stage': self.current_stage,
            'hand_over': self.hand_over,
            'opponent_hands': self.opponent_hands
        }