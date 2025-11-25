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
            'name': self.name, 'position': self.position, 'chips': self.chips,
            'in_pot': self.in_pot, 'is_active': self.is_active, 'hand': hand_model
        }

class Table:
    POSITIONS = ['BB', 'SB', 'BTN', 'CO', 'MP', 'UTG']
    HERO_POSITION = 'CO'
    
    def __init__(self, players_data: Dict[str, int], big_blind: int = 20):
        self.big_blind = big_blind
        self.players = [Player(name, chips) for name, chips in players_data.items()]
        self.button_index = random.randint(0, len(self.players) - 1)
        self.pot = 0
        self.community_cards: List[Card] = []
        self.current_bet = 0
        self.current_player_index = -1 # 當前行動的玩家索引

    def _assign_positions(self):
        """隨機分配位置，但確保 Hero 永遠位於底部插槽。"""
        hero_player = next((p for p in self.players if p.name.lower() == 'hero'), None)
        remaining_positions = [pos for pos in self.POSITIONS if pos != self.HERO_POSITION]
        random.shuffle(remaining_positions)

        for p in self.players:
            p.in_pot = 0
            p.is_active = True
            p.hand = []

        if hero_player:
            hero_player.position = self.HERO_POSITION

        other_players = [p for p in self.players if p is not hero_player]
        for p, pos in zip(other_players, remaining_positions):
            p.position = pos

    def _deal_cards(self):
        ranks = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2']
        suits = ['s', 'h', 'd', 'c']
        deck = [Card(rank, suit) for rank in ranks for suit in suits]
        random.shuffle(deck)

        hero_player = self.get_hero()
        if hero_player:
            hero_player.hand = [deck.pop(), deck.pop()]

        self.community_cards = [deck.pop() for _ in range(3)]

    def get_hero(self) -> Player | None:
        return next((p for p in self.players if p.name.lower() == 'hero'), None)
    
    def start_hand(self):
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
        player = self.get_current_player()
        
        if action.action_type == 'Fold':
            player.fold()
        elif action.action_type == 'Call':
            to_call = self.current_bet - player.in_pot
            if to_call <= 0: raise ValueError("無法跟注，應該 Check 或 Bet。")
            self.pot += player.bet(to_call)
        elif action.action_type in ['Bet', 'Raise']:
            amount = action.amount
            # if amount <= self.current_bet: raise ValueError("下注/加注金額必須大於當前注額。")
            
            to_put_in = amount - player.in_pot
            self.pot += player.bet(to_put_in)
            self.current_bet = amount
        else:
            raise ValueError("無效的行動類型。")
        
        # 這裡應該有邏輯來決定誰是下一個行動者，並更新 self.current_player_index
        print(f"處理了 {player.position} 的行動: {action.action_type} {action.amount}")

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
            'current_bet': self.current_bet
        }