"""
Sistema de Chaves IBJJF - Geração Automática de Chaveamentos
============================================================

Sistema para geração automática de chaves de torneio seguindo padrões IBJJF,
com interface web usando Streamlit e integração com Google Sheets.

Autor: Bruno Mendes
Versão: 2.0
"""

import streamlit as st
import random
import math
import pandas as pd
import requests
from io import StringIO
from typing import List, Optional, Dict, Tuple
import unicodedata


# ========================================================================
# CONFIGURAÇÃO DA APLICAÇÃO
# ========================================================================

def configure_streamlit() -> None:
    """Configura as opções básicas do Streamlit."""
    st.set_page_config(
        page_title="Sistema de Chaves IBJJF", 
        layout="wide", 
        initial_sidebar_state="expanded"
    )


# ========================================================================
# UTILITÁRIOS DE DADOS
# ========================================================================

def sanitize_text(text: str) -> str:
    """
    Sanitiza texto removendo acentos e padronizando formato.
    
    Args:
        text: Texto a ser sanitizado
        
    Returns:
        Texto sanitizado em maiúsculas sem acentos
    """
    if not isinstance(text, str):
        return ""
    
    # Remove acentos usando normalização Unicode
    normalized_text = unicodedata.normalize('NFD', text)
    accent_free_text = "".join(
        char for char in normalized_text 
        if unicodedata.category(char) != 'Mn'
    )
    
    return accent_free_text.upper().strip()


# ========================================================================
# CLASSES DE DADOS
# ========================================================================

class Athlete:
    """
    Representa um atleta no sistema de chaveamento.
    
    Attributes:
        name: Nome do atleta
        team: Nome da equipe
        seed: Posição no seeding (1 = melhor seed)
        age_category: Categoria de idade (ex: "ADULTO", "MASTER")
        weight_category: Categoria de peso (ex: "LEVE", "MEDIO")
        belt: Faixa do atleta (ex: "BRANCA", "AZUL")
        gender: Gênero ("MASCULINO", "FEMININO")
    """
    
    def __init__(
        self, 
        name: str, 
        team: str, 
        seed: int = 0,
        age_category: str = "", 
        weight_category: str = "", 
        belt: str = "", 
        gender: str = ""
    ):
        self.name = name
        self.team = team
        self.seed = seed
        self.age_category = age_category
        self.weight_category = weight_category
        self.belt = belt
        self.gender = gender

    def __str__(self) -> str:
        return f"{self.name} ({self.team}) - Seed #{self.seed}"


class Match:
    """
    Representa uma luta no chaveamento.
    
    Attributes:
        athlete1: Primeiro atleta da luta
        athlete2: Segundo atleta da luta
        winner: Vencedor da luta (None se não definido)
        number: Número identificador da luta
    """
    
    def __init__(
        self, 
        athlete1: Optional[Athlete] = None, 
        athlete2: Optional[Athlete] = None
    ):
        self.athlete1 = athlete1
        self.athlete2 = athlete2
        self.winner: Optional[Athlete] = None
        self.number: int = 0

    def process_bye(self) -> Optional[Athlete]:
        """
        Processa automaticamente lutas com bye (apenas um atleta).
        
        Returns:
            Atleta vencedor por bye, ou None se ambos presentes
        """
        if self.athlete1 and not self.athlete2:
            self.winner = self.athlete1
        elif self.athlete2 and not self.athlete1:
            self.winner = self.athlete2
        
        return self.winner

    def is_bye(self) -> bool:
        """Verifica se a luta é um bye."""
        return bool(self.athlete1) != bool(self.athlete2)

    def has_both_athletes(self) -> bool:
        """Verifica se a luta tem ambos atletas."""
        return bool(self.athlete1 and self.athlete2)


# ========================================================================
# LÓGICA DE CHAVEAMENTO
# ========================================================================

class SeedingGenerator:
    """Gerador de ordens de seeding para diferentes tamanhos de chave."""
    
    @staticmethod
    def generate_seeding_order(bracket_size: int) -> List[int]:
        """
        Gera ordem de seeding padrão para eliminação simples.
        
        Args:
            bracket_size: Tamanho da chave (potência de 2)
            
        Returns:
            Lista com ordem de posicionamento dos seeds
        """
        seeding_orders = {
            1: [0],
            2: [0, 1],
            4: [0, 3, 1, 2],
            8: [0, 7, 3, 4, 1, 6, 2, 5],
            16: [0, 15, 7, 8, 3, 12, 4, 11, 1, 14, 6, 9, 2, 13, 5, 10],
            32: [0, 31, 15, 16, 7, 24, 8, 23, 3, 28, 12, 19, 4, 27, 11, 20,
                 1, 30, 14, 17, 6, 25, 9, 22, 2, 29, 13, 18, 5, 26, 10, 21],
            64: [0, 63, 31, 32, 15, 48, 16, 47, 7, 56, 24, 39, 8, 55, 23, 40,
                 3, 60, 28, 35, 12, 51, 19, 44, 4, 59, 27, 36, 11, 52, 20, 43,
                 1, 62, 30, 33, 14, 49, 17, 46, 6, 57, 25, 38, 9, 54, 22, 41,
                 2, 61, 29, 34, 13, 50, 18, 45, 5, 58, 26, 37, 10, 53, 21, 42],
            128: [0, 127, 63, 64, 31, 96, 32, 95, 15, 112, 48, 79, 16, 111, 47, 80,
                  7, 120, 56, 71, 24, 103, 39, 88, 8, 119, 55, 72, 23, 104, 40, 87,
                  3, 124, 60, 67, 28, 99, 35, 92, 12, 115, 51, 76, 19, 108, 44, 83,
                  4, 123, 59, 68, 27, 100, 36, 91, 11, 116, 52, 75, 20, 107, 43, 84,
                  1, 126, 62, 65, 30, 97, 33, 94, 14, 113, 49, 78, 17, 110, 46, 81,
                  6, 121, 57, 70, 25, 102, 38, 89, 9, 118, 54, 73, 22, 105, 41, 86,
                  2, 125, 61, 66, 29, 98, 34, 93, 13, 114, 50, 77, 18, 109, 45, 82,
                  5, 122, 58, 69, 26, 101, 37, 90, 10, 117, 53, 74, 21, 106, 42, 85]
        }
        
        if bracket_size in seeding_orders:
            return seeding_orders[bracket_size]
        
        # Gera recursivamente para tamanhos não mapeados
        half_size = bracket_size // 2
        half_order = SeedingGenerator.generate_seeding_order(half_size)
        
        full_order = []
        for position in half_order:
            full_order.extend([position, bracket_size - 1 - position])
        
        return full_order


class RoundNamer:
    """Utilitário para nomear rodadas do chaveamento."""
    
    @staticmethod
    def get_round_name(participants_count: int) -> str:
        """
        Retorna nome da rodada baseado no número de participantes.
        
        Args:
            participants_count: Número de participantes na rodada
            
        Returns:
            Nome da rodada em português
        """
        round_names = {
            2: "FINAL",
            4: "SEMIFINAIS", 
            8: "QUARTAS DE FINAL",
            16: "OITAVAS DE FINAL",
            32: "16-AVOS DE FINAL",
            64: "32-AVOS DE FINAL",
            128: "64-AVOS DE FINAL",
            256: "128-AVOS DE FINAL"
        }
        
        return round_names.get(participants_count, f"RODADA DE {participants_count}")


class TournamentBracket:
    """
    Classe principal para geração e gerenciamento de chaveamentos.
    
    Attributes:
        athletes: Lista de atletas no chaveamento
        category: Nome da categoria
        rounds: Lista de rodadas (cada rodada é uma lista de lutas)
        round_names: Nomes das rodadas
        medalists: Dicionário com medalhistas
    """
    
    def __init__(self, athletes: List[Athlete], category: str):
        self.athletes = athletes
        self.category = category
        self.rounds: List[List[Match]] = []
        self.round_names: List[str] = []
        self.medalists: Dict = {}
        
        if len(athletes) > 1:
            self._build_bracket()

    def _calculate_bracket_size(self) -> Tuple[int, int]:
        """
        Calcula tamanho da chave e número de byes necessários.
        
        Returns:
            Tupla com (tamanho_da_chave, numero_de_byes)
        """
        num_athletes = len(self.athletes)
        bracket_size = 2 ** math.ceil(math.log2(num_athletes))
        num_byes = bracket_size - num_athletes
        
        return bracket_size, num_byes

    def _reassign_seeds(self) -> None:
        """Reatribui seeds de 1 a N mantendo ordem original."""
        for new_seed, athlete in enumerate(self.athletes, start=1):
            athlete.seed = new_seed

    def _create_initial_bracket(self) -> List[Optional[Athlete]]:
        """
        Cria chave inicial com atletas posicionados e byes.
        
        Returns:
            Lista representando a chave inicial
        """
        bracket_size, num_byes = self._calculate_bracket_size()
        seeding_order = SeedingGenerator.generate_seeding_order(bracket_size)
        
        # Ordena atletas por seed
        sorted_athletes = sorted(self.athletes, key=lambda x: x.seed)
        
        # Cria chave inicial vazia
        initial_bracket = [None] * bracket_size
        
        # Posiciona atletas seguindo ordem de seeding
        for i, athlete in enumerate(sorted_athletes):
            position = seeding_order[i]
            initial_bracket[position] = athlete
        
        self._optimize_bye_positions(initial_bracket, seeding_order, sorted_athletes)
        
        return initial_bracket

    def _optimize_bye_positions(
        self, 
        bracket: List[Optional[Athlete]], 
        seeding_order: List[int], 
        sorted_athletes: List[Athlete]
    ) -> None:
        """
        Otimiza posições de bye para que melhores seeds recebam bye.
        
        Args:
            bracket: Chave atual
            seeding_order: Ordem de seeding
            sorted_athletes: Atletas ordenados por seed
        """
        # Identifica posições que resultarão em bye
        bye_positions = []
        bracket_size = len(bracket)
        
        for i in range(0, bracket_size, 2):
            pos1, pos2 = i, i + 1
            if (bracket[pos1] and not bracket[pos2]) or (bracket[pos2] and not bracket[pos1]):
                bye_pos = pos1 if bracket[pos1] else pos2
                bye_positions.append(bye_pos)
        
        if not bye_positions:
            return
        
        # Reordena: melhores seeds nas posições de bye
        bracket.clear()
        bracket.extend([None] * bracket_size)
        
        # Ordena posições de bye pela ordem de seeding
        ordered_bye_positions = [pos for pos in seeding_order if pos in bye_positions]
        
        # Coloca melhores seeds nas posições de bye
        for i, position in enumerate(ordered_bye_positions):
            if i < len(sorted_athletes):
                bracket[position] = sorted_athletes[i]
        
        # Coloca demais atletas nas posições restantes
        occupied_positions = set(ordered_bye_positions)
        free_positions = [pos for pos in seeding_order if pos not in occupied_positions]
        
        athlete_index = len(ordered_bye_positions)
        for position in free_positions:
            if athlete_index < len(sorted_athletes):
                bracket[position] = sorted_athletes[athlete_index]
                athlete_index += 1

    def _create_first_round(self, initial_bracket: List[Optional[Athlete]]) -> List[Match]:
        """
        Cria primeira rodada baseada na chave inicial.
        
        Args:
            initial_bracket: Chave inicial com atletas posicionados
            
        Returns:
            Lista de lutas da primeira rodada
        """
        first_round = []
        match_number = 1
        bracket_size = len(initial_bracket)
        
        for i in range(0, bracket_size, 2):
            match = Match(initial_bracket[i], initial_bracket[i + 1])
            
            if match.has_both_athletes():
                match.number = match_number
                match_number += 1
            elif match.athlete1 or match.athlete2:
                match.process_bye()
            
            first_round.append(match)
        
        return first_round

    def _create_subsequent_rounds(self, previous_round: List[Match]) -> None:
        """
        Cria rodadas subsequentes baseadas na rodada anterior.
        
        Args:
            previous_round: Rodada anterior para avançar vencedores
        """
        match_number = sum(
            1 for round_matches in self.rounds 
            for match in round_matches 
            if match.has_both_athletes()
        ) + 1
        
        current_round = previous_round
        
        while len(current_round) > 1:
            next_round = []
            
            for i in range(0, len(current_round), 2):
                winner1 = current_round[i].winner if i < len(current_round) else None
                winner2 = current_round[i + 1].winner if i + 1 < len(current_round) else None
                
                match = Match(winner1, winner2)
                if winner1 and winner2:
                    match.number = match_number
                    match_number += 1
                
                next_round.append(match)
            
            self.rounds.append(next_round)
            self.round_names.append(RoundNamer.get_round_name(len(next_round) * 2))
            current_round = next_round

    def _build_bracket(self) -> None:
        """Constrói o chaveamento completo."""
        self._reassign_seeds()
        
        # Cria chave inicial
        initial_bracket = self._create_initial_bracket()
        
        # Cria primeira rodada
        first_round = self._create_first_round(initial_bracket)
        bracket_size, _ = self._calculate_bracket_size()
        
        self.rounds.append(first_round)
        self.round_names.append(RoundNamer.get_round_name(bracket_size))
        
        # Cria rodadas subsequentes
        self._create_subsequent_rounds(first_round)


# ========================================================================
# INTEGRAÇÃO COM GOOGLE SHEETS
# ========================================================================

class GoogleSheetsLoader:
    """Classe para carregar dados do Google Sheets."""
    
    @staticmethod
    def load_dataframe(sheet_url: str) -> pd.DataFrame:
        """
        Carrega dados do Google Sheets como DataFrame.
        
        Args:
            sheet_url: URL do Google Sheets (pública)
            
        Returns:
            DataFrame com dados carregados
            
        Raises:
            Exception: Se houver erro no carregamento
        """
        try:
            sheet_id = GoogleSheetsLoader._extract_sheet_id(sheet_url)
            csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
            
            response = requests.get(csv_url)
            response.raise_for_status()
            response.encoding = 'utf-8'
            
            csv_data = StringIO(response.text)
            df = pd.read_csv(csv_data)
            
            return df
            
        except Exception as e:
            raise Exception(f"Erro ao carregar planilha: {str(e)}")

    @staticmethod
    def _extract_sheet_id(sheet_url: str) -> str:
        """Extrai ID da planilha da URL."""
        if "/edit" in sheet_url:
            return sheet_url.split("/d/")[1].split("/edit")[0]
        return sheet_url


class AthleteProcessor:
    """Processador de dados de atletas."""
    
    @staticmethod
    def process_dataframe(df: pd.DataFrame) -> List[Athlete]:
        """
        Processa DataFrame e converte em lista de atletas.
        
        Args:
            df: DataFrame com dados dos atletas
            
        Returns:
            Lista de objetos Athlete
        """
        athletes = []
        
        for i, row in df.iterrows():
            if pd.notna(row.iloc[0]):
                athlete = AthleteProcessor._create_athlete_from_row(row, i + 1)
                athletes.append(athlete)
        
        return athletes

    @staticmethod
    def _create_athlete_from_row(row: pd.Series, seed: int) -> Athlete:
        """Cria objeto Athlete a partir de linha do DataFrame."""
        name = sanitize_text(str(row.iloc[0]))
        age_category = sanitize_text(str(row.iloc[1]) if pd.notna(row.iloc[1]) else "")
        weight_category = sanitize_text(str(row.iloc[2]) if pd.notna(row.iloc[2]) else "")
        belt = sanitize_text(str(row.iloc[4]) if pd.notna(row.iloc[4]) else "")
        gender = sanitize_text(str(row.iloc[5]) if pd.notna(row.iloc[5]) else "")
        
        if len(row) > 6 and pd.notna(row.iloc[6]):
            team = sanitize_text(str(row.iloc[6]))
        else:
            team = "EQUIPE NÃO INFORMADA"
        
        return Athlete(
            name=name,
            team=team,
            seed=seed,
            age_category=age_category,
            weight_category=weight_category,
            belt=belt,
            gender=gender
        )


# ========================================================================
# FILTROS E SELEÇÃO
# ========================================================================

class AthleteFilter:
    """Classe para filtrar atletas por categorias."""
    
    @staticmethod
    def get_available_options(athletes: List[Athlete]) -> Dict[str, List[str]]:
        """
        Retorna opções disponíveis para filtros.
        
        Args:
            athletes: Lista de atletas
            
        Returns:
            Dicionário com opções disponíveis para cada filtro
        """
        return {
            'genders': sorted(list(set(a.gender for a in athletes if a.gender))),
            'belts': sorted(list(set(a.belt for a in athletes if a.belt))),
            'age_categories': sorted(list(set(a.age_category for a in athletes if a.age_category))),
            'weight_categories': sorted(list(set(a.weight_category for a in athletes if a.weight_category)))
        }

    @staticmethod
    def filter_by_gender(athletes: List[Athlete], gender: str) -> List[Athlete]:
        """Filtra atletas por gênero."""
        return [a for a in athletes if a.gender == gender]

    @staticmethod
    def filter_by_belt(athletes: List[Athlete], belt: str) -> List[Athlete]:
        """Filtra atletas por faixa."""
        return [a for a in athletes if a.belt == belt]

    @staticmethod
    def filter_by_age_category(athletes: List[Athlete], age_category: str) -> List[Athlete]:
        """Filtra atletas por categoria de idade."""
        return [a for a in athletes if a.age_category == age_category]

    @staticmethod
    def filter_by_weight_category(athletes: List[Athlete], weight_category: str) -> List[Athlete]:
        """Filtra atletas por categoria de peso."""
        return [a for a in athletes if a.weight_category == weight_category]


# ========================================================================
# INTERFACE DE USUÁRIO
# ========================================================================

class StyleManager:
    """Gerenciador de estilos CSS para a interface."""
    
    @staticmethod
    def apply_dark_theme() -> None:
        """Aplica tema escuro customizado."""
        css = """
        <style>
            .stApp {
                background: linear-gradient(135deg, #0f0f0f 0%, #1a1a1a 100%);
            }
            
            .css-1d391kg {
                background: linear-gradient(180deg, #1a1a1a 0%, #0f0f0f 100%);
                border-right: 1px solid #333333;
            }
            
            .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {
                color: #e0e0e0 !important;
                text-shadow: 0 2px 4px rgba(0, 0, 0, 0.8);
            }
            
            .css-1d391kg .stMarkdown h2 {
                color: #f0f0f0 !important;
            }
            
            .stAlert {
                background: rgba(45, 45, 45, 0.8) !important;
                border: 1px solid #444444 !important;
                border-radius: 8px !important;
            }
            
            div[data-testid="metric-container"] {
                background: linear-gradient(145deg, #2a2a2a 0%, #1f1f1f 100%);
                border: 1px solid #444444;
                border-radius: 8px;
                padding: 1rem;
                box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
            }
            
            .stButton > button {
                background: linear-gradient(145deg, #ff6b35 0%, #f7931e 100%) !important;
                color: white !important;
                border: none !important;
                border-radius: 8px !important;
                font-weight: 600 !important;
                box-shadow: 0 4px 16px rgba(255, 107, 53, 0.3) !important;
                transition: all 0.3s ease !important;
            }
            
            .stButton > button:hover {
                transform: translateY(-2px) !important;
                box-shadow: 0 6px 20px rgba(255, 107, 53, 0.4) !important;
            }
            
            hr {
                border-color: #444444 !important;
            }
        </style>
        """
        st.markdown(css, unsafe_allow_html=True)


class BracketRenderer:
    """Renderizador de chaveamentos em formato visual."""
    
    @staticmethod
    def render_bracket(bracket: TournamentBracket) -> None:
        """
        Renderiza chaveamento com design responsivo.
        
        Args:
            bracket: Objeto TournamentBracket para renderizar
        """
        if not bracket.rounds:
            return
        
        css = BracketRenderer._get_bracket_css()
        html = BracketRenderer._generate_bracket_html(bracket)
        
        st.markdown(css, unsafe_allow_html=True)
        st.markdown(html, unsafe_allow_html=True)

    @staticmethod
    def _get_bracket_css() -> str:
        """Retorna CSS para estilização do bracket."""
        return """
        <style>
            .bracket-wrapper {
                background: transparent;
                padding: 16px;
                overflow-x: auto;
                min-height: 400px;
            }
            
            .bracket-container {
                display: flex;
                gap: 32px;
                align-items: stretch;
                min-width: max-content;
                position: relative;
            }
            
            .round-column {
                display: flex;
                flex-direction: column;
                justify-content: space-around;
                min-width: 180px;
                position: relative;
                z-index: 2;
            }
            
            .round-title {
                color: #e0e0e0;
                font-size: 11px;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 1px;
                margin-bottom: 16px;
                text-align: center;
                padding: 8px 6px;
                background: linear-gradient(135deg, #404040 0%, #333333 100%);
                border-radius: 6px;
                border: 1px solid #555555;
                text-shadow: 0 1px 2px rgba(0, 0, 0, 0.8);
            }
            
            .matches-container {
                display: flex;
                flex-direction: column;
                justify-content: space-around;
                flex: 1;
                gap: 12px;
            }
            
            .match-wrapper {
                display: flex;
                align-items: center;
                flex: 1;
                position: relative;
            }
            
            .connector-horizontal {
                position: absolute;
                right: -16px;
                width: 16px;
                height: 2px;
                background: #666666;
                top: 50%;
                transform: translateY(-1px);
                z-index: 1;
            }
            
            .connector-vertical-top {
                position: absolute;
                right: -16px;
                width: 2px;
                background: #666666;
                height: calc(50% + 6px);
                bottom: 50%;
                z-index: 1;
            }
            
            .connector-vertical-bottom {
                position: absolute;
                right: -16px;
                width: 2px;
                background: #666666;
                height: calc(50% + 6px);
                top: 50%;
                z-index: 1;
            }
            
            .connector-entry {
                position: absolute;
                left: -16px;
                width: 16px;
                height: 2px;
                background: #666666;
                top: 50%;
                transform: translateY(-1px);
                z-index: 1;
            }
            
            .fight-card {
                background: linear-gradient(145deg, #2a2a2a 0%, #1f1f1f 100%);
                border: 1px solid #444444;
                border-radius: 6px;
                width: 100%;
                overflow: hidden;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
                transition: all 0.3s ease;
            }
            
            .fight-card:hover {
                transform: translateY(-1px);
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
                border-color: #666666;
            }
            
            .participant {
                padding: 6px 10px;
                font-size: 12px;
                display: flex;
                align-items: center;
                min-height: 24px;
                transition: all 0.2s ease;
            }
            
            .participant-top {
                border-bottom: 1px solid #444444;
            }
            
            .participant-bottom {
                background: transparent;
            }
            
            .participant-info {
                flex: 1;
            }
            
            .participant-name {
                color: #f0f0f0;
                font-weight: 600;
                line-height: 1.2;
            }
            
            .participant-team {
                color: #b0b0b0;
                font-size: 10px;
                margin-top: 1px;
                opacity: 0.9;
            }
            
            .seed {
                color: #ff9500;
                font-weight: 700;
                font-size: 10px;
                text-shadow: 0 1px 2px rgba(0, 0, 0, 0.8);
            }
            
            .bye {
                color: #666666;
                text-align: center;
                padding: 12px;
                font-style: italic;
                font-size: 11px;
                background: linear-gradient(145deg, #1a1a1a 0%, #0f0f0f 100%);
                border: 1px dashed #333333;
            }
            
            .winner {
                background: #2d4a2d !important;
                border-color: #4caf50 !important;
            }
            
            .winner .participant-name {
                color: #81c784 !important;
                font-weight: 700;
            }
            
            .winner .participant-team {
                color: #a5d6a7 !important;
            }
            
            @media (max-width: 768px) {
                .bracket-container {
                    gap: 20px;
                }
                
                .round-column {
                    min-width: 160px;
                }
                
                .participant {
                    padding: 5px 8px;
                    font-size: 11px;
                }
                
                .round-title {
                    font-size: 10px;
                    padding: 6px 4px;
                }
            }
        </style>
        """

    @staticmethod
    def _generate_bracket_html(bracket: TournamentBracket) -> str:
        """Gera HTML do bracket."""
        html_parts = ['<div class="bracket-wrapper"><div class="bracket-container">']
        
        for round_idx, (round_matches, round_name) in enumerate(zip(bracket.rounds, bracket.round_names)):
            html_parts.append('<div class="round-column">')
            html_parts.append(f'<div class="round-title">{round_name}</div>')
            html_parts.append('<div class="matches-container">')
            
            for match_idx, match in enumerate(round_matches):
                html_parts.extend(BracketRenderer._generate_match_html(match, round_idx, match_idx, len(bracket.rounds)))
            
            html_parts.append('</div></div>')
        
        html_parts.append('</div></div>')
        return ''.join(html_parts)

    @staticmethod
    def _generate_match_html(match: Match, round_idx: int, match_idx: int, total_rounds: int) -> List[str]:
        """Gera HTML para uma luta específica."""
        html_parts = ['<div class="match-wrapper">']
        html_parts.append('<div class="fight-card">')
        
        # Renderiza atletas
        if not match.athlete1 and not match.athlete2:
            # Luta vazia
            html_parts.append('<div class="participant participant-top"><div class="participant-info">&nbsp;</div></div>')
            html_parts.append('<div class="participant participant-bottom"><div class="participant-info">&nbsp;</div></div>')
        else:
            # Atleta 1
            html_parts.extend(BracketRenderer._generate_athlete_html(match.athlete1, match, "top", round_idx == 0))
            # Atleta 2  
            html_parts.extend(BracketRenderer._generate_athlete_html(match.athlete2, match, "bottom", round_idx == 0))
        
        html_parts.append('</div>')
        
        # Conectores
        if round_idx > 0:
            html_parts.append('<div class="connector-entry"></div>')
        
        if round_idx < total_rounds - 1:
            html_parts.append('<div class="connector-horizontal"></div>')
            
            if match_idx % 2 == 0:
                html_parts.append('<div class="connector-vertical-bottom"></div>')
            else:
                html_parts.append('<div class="connector-vertical-top"></div>')
        
        html_parts.append('</div>')
        return html_parts

    @staticmethod
    def _generate_athlete_html(athlete: Optional[Athlete], match: Match, position: str, is_first_round: bool) -> List[str]:
        """Gera HTML para um atleta."""
        html_parts = []
        
        if athlete:
            winner_class = "winner" if match.winner == athlete else ""
            seed_text = f' <span class="seed">#{athlete.seed}</span>'
            
            html_parts.append(f'<div class="participant participant-{position} {winner_class}">')
            html_parts.append('<div class="participant-info">')
            html_parts.append(f'<div class="participant-name">{athlete.name}{seed_text}</div>')
            html_parts.append(f'<div class="participant-team">{athlete.team}</div>')
            html_parts.append('</div></div>')
        else:
            if is_first_round:
                html_parts.append('<div class="bye">BYE</div>')
            else:
                html_parts.append(f'<div class="participant participant-{position}"><div class="participant-info">&nbsp;</div></div>')
        
        return html_parts


class SidebarManager:
    """Gerenciador da barra lateral da aplicação."""
    
    @staticmethod
    def render_data_loading_section() -> Optional[str]:
        """
        Renderiza seção de carregamento de dados.
        
        Returns:
            URL da planilha se fornecida, None caso contrário
        """
        st.header("Configurações")
        
        sheet_url = st.text_input(
            "URL do Google Sheets:",
            value="",
            help="Cole a URL pública do Google Sheets"
        )
        
        if st.button("Carregar Dados", type="primary", use_container_width=True):
            return sheet_url
            
        return None

    @staticmethod
    def render_filter_section(athletes: List[Athlete]) -> Tuple[str, str, str, str]:
        """
        Renderiza seção de filtros de categoria.
        
        Args:
            athletes: Lista de atletas para filtrar
            
        Returns:
            Tupla com (gênero, faixa, categoria_idade, categoria_peso) selecionados
        """
        st.divider()
        
        options = AthleteFilter.get_available_options(athletes)
        
        # Seleção de gênero
        selected_gender = st.selectbox(
            "Gênero:", 
            options['genders'] if options['genders'] else ["Nenhum"]
        )
        
        # Filtrar por gênero e buscar faixas
        gender_filtered = AthleteFilter.filter_by_gender(athletes, selected_gender)
        gender_options = AthleteFilter.get_available_options(gender_filtered)
        
        # Seleção de faixa
        selected_belt = st.selectbox(
            "Faixa:", 
            gender_options['belts'] if gender_options['belts'] else ["Nenhuma"]
        )
        
        # Filtrar por faixa e buscar idades
        belt_filtered = AthleteFilter.filter_by_belt(gender_filtered, selected_belt)
        belt_options = AthleteFilter.get_available_options(belt_filtered)
        
        # Seleção de categoria de idade
        selected_age = st.selectbox(
            "Categoria de Idade:", 
            belt_options['age_categories'] if belt_options['age_categories'] else ["Nenhuma"]
        )
        
        # Filtrar por idade e buscar pesos
        age_filtered = AthleteFilter.filter_by_age_category(belt_filtered, selected_age)
        age_options = AthleteFilter.get_available_options(age_filtered)
        
        # Seleção de categoria de peso
        selected_weight = st.selectbox(
            "Categoria de Peso:", 
            age_options['weight_categories'] if age_options['weight_categories'] else ["Nenhuma"]
        )
        
        return selected_gender, selected_belt, selected_age, selected_weight

    @staticmethod
    def render_generate_button(filtered_athletes: List[Athlete]) -> bool:
        """
        Renderiza botão de geração e informações dos atletas.
        
        Args:
            filtered_athletes: Lista de atletas filtrados
            
        Returns:
            True se botão foi clicado, False caso contrário
        """
        st.info(f"Atletas encontrados: {len(filtered_athletes)}")
        
        if len(filtered_athletes) >= 2:
            return st.button("Gerar Chave", use_container_width=True)
        elif len(filtered_athletes) == 1:
            st.warning("Apenas 1 atleta encontrado")
        else:
            st.warning("Nenhum atleta encontrado com estes filtros")
        
        return False


# ========================================================================
# APLICAÇÃO PRINCIPAL
# ========================================================================

class IBJJFApp:
    """Classe principal da aplicação IBJJF."""
    
    def __init__(self):
        configure_streamlit()
        StyleManager.apply_dark_theme()

    def run(self) -> None:
        """Executa a aplicação principal."""
        self._render_header()
        
        with st.sidebar:
            self._handle_sidebar()
        
        self._render_main_content()

    def _render_header(self) -> None:
        """Renderiza cabeçalho da aplicação."""
        st.title("Sistema de Chaves IBJJF")
        st.markdown("**Geração automática por categorias**")

    def _handle_sidebar(self) -> None:
        """Gerencia interações da barra lateral."""
        # Seção de carregamento de dados
        sheet_url = SidebarManager.render_data_loading_section()
        
        if sheet_url:
            self._load_data_from_sheets(sheet_url)
        
        # Seção de filtros (se dados carregados)
        if 'athletes_data' in st.session_state:
            self._handle_filter_section()

    def _load_data_from_sheets(self, sheet_url: str) -> None:
        """Carrega dados do Google Sheets."""
        with st.spinner("Carregando dados..."):
            try:
                df = GoogleSheetsLoader.load_dataframe(sheet_url)
                if not df.empty:
                    st.session_state.athletes_dataframe = df
                    st.session_state.athletes_data = AthleteProcessor.process_dataframe(df)
                    st.success(f"{len(st.session_state.athletes_data)} atletas carregados!")
            except Exception as e:
                st.error(str(e))

    def _handle_filter_section(self) -> None:
        """Gerencia seção de filtros."""
        athletes = st.session_state.athletes_data
        
        # Renderiza filtros
        selected_gender, selected_belt, selected_age, selected_weight = \
            SidebarManager.render_filter_section(athletes)
        
        # Aplica filtros
        filtered_athletes = self._apply_filters(
            athletes, selected_gender, selected_belt, selected_age, selected_weight
        )
        
        # Renderiza botão de geração
        if SidebarManager.render_generate_button(filtered_athletes):
            self._generate_bracket(filtered_athletes, selected_gender, selected_belt, selected_age, selected_weight)

    def _apply_filters(
        self, 
        athletes: List[Athlete], 
        gender: str, 
        belt: str, 
        age: str, 
        weight: str
    ) -> List[Athlete]:
        """Aplica todos os filtros sequencialmente."""
        filtered = AthleteFilter.filter_by_gender(athletes, gender)
        filtered = AthleteFilter.filter_by_belt(filtered, belt)
        filtered = AthleteFilter.filter_by_age_category(filtered, age)
        filtered = AthleteFilter.filter_by_weight_category(filtered, weight)
        
        return filtered

    def _generate_bracket(
        self, 
        athletes: List[Athlete], 
        gender: str, 
        belt: str, 
        age: str, 
        weight: str
    ) -> None:
        """Gera chaveamento para os atletas filtrados."""
        category_name = f"{age} / {gender} / {weight} / {belt}"
        st.session_state.current_bracket = TournamentBracket(athletes, category_name)

    def _render_main_content(self) -> None:
        """Renderiza conteúdo principal."""
        if 'current_bracket' in st.session_state:
            bracket = st.session_state.current_bracket
            
            st.header(bracket.category)
            st.markdown(f"**{len(bracket.athletes)} atletas**")
            
            st.divider()
            st.subheader("Chaveamento")
            BracketRenderer.render_bracket(bracket)
        else:
            st.info("Carregue os dados e selecione os filtros para gerar uma chave")


# ========================================================================
# PONTO DE ENTRADA
# ========================================================================

def main():
    """Função principal da aplicação."""
    app = IBJJFApp()
    app.run()


if __name__ == "__main__":
    main()
