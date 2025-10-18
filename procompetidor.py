"""
Sistema Integrado de Análise e Chaveamento IBJJF
=================================================

Sistema completo que:
1. Extrai dados de competidores do ProCompetidor
2. Gera análises e dashboards
3. Cria chaveamentos automáticos seguindo padrões IBJJF

Versão: 3.0 - Integrada
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import random
import math
from typing import List, Optional, Dict, Tuple
import unicodedata


# ========================================================================
# CONFIGURAÇÃO DA APLICAÇÃO
# ========================================================================

st.set_page_config(
    page_title="Sistema Integrado IBJJF",
    page_icon="🥋",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ========================================================================
# EXTRAÇÃO DE DADOS (ProCompetidor)
# ========================================================================

def raspar_dados(url, progress_bar, status_text):
    """
    Extrai dados de competidores do ProCompetidor usando Selenium.
    """
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")

    service = Service(executable_path="/usr/bin/chromedriver")
    driver = webdriver.Chrome(service=service, options=chrome_options) 
    
    competition_title = "Competição"
    
    try:
        driver.get(url)
        wait = WebDriverWait(driver, 30)
        
        status_text.text("Carregando a página e buscando informações...")
        
        try:
            title_element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "h4.MuiTypography-root")))
            competition_title = title_element.text
        except Exception:
            status_text.text("Título da competição não encontrado, usando título padrão.")
            pass

        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".MuiAccordion-root")))
        
        accordions = driver.find_elements(By.CSS_SELECTOR, ".MuiAccordion-root")
        total_accordions = len(accordions)
        lista_de_inscritos = []

        for i, accordion in enumerate(accordions):
            progress = (i + 1) / total_accordions
            status_text.text(f"Processando categoria {i + 1} de {total_accordions}...")
            progress_bar.progress(progress)
            
            try:
                summary_header = accordion.find_element(By.CSS_SELECTOR, ".MuiAccordionSummary-root")
                titulo_raw = summary_header.find_element(By.CSS_SELECTOR, ".MuiTypography-root").text
            except Exception: 
                continue

            partes_titulo = [p.strip() for p in titulo_raw.split(',')]
            if len(partes_titulo) >= 4:
                categoria_idade, faixa, categoria_peso, genero = partes_titulo[0], partes_titulo[1], partes_titulo[2], partes_titulo[3].split(' - ')[0].strip()
            elif len(partes_titulo) == 3:
                categoria_idade, faixa, genero_raw = partes_titulo[0], partes_titulo[1], partes_titulo[2]
                genero, categoria_peso = genero_raw.split(' - ')[0].strip(), "N/A"
            else: 
                continue

            try: 
                driver.execute_script("arguments[0].click();", summary_header)
                time.sleep(0.5)
            except Exception: 
                continue

            cards_inscritos = accordion.find_elements(By.CSS_SELECTOR, ".MuiBox-root.css-g32t2d")
            for card in cards_inscritos:
                try:
                    nome = card.find_element(By.TAG_NAME, "h6").text
                    infos = card.find_elements(By.TAG_NAME, "p")
                    equipe = infos[0].text.replace("Equipe: ", "").strip()
                    professor = infos[1].text.replace("Professor(a): ", "").strip() if len(infos) > 1 else "N/A"
                    inscrito = {
                        "Nome": nome, 
                        "Equipe": equipe, 
                        "Professor": professor, 
                        "Categoria de Idade": categoria_idade, 
                        "Faixa": faixa, 
                        "Categoria de Peso": categoria_peso, 
                        "Gênero": genero
                    }
                    lista_de_inscritos.append(inscrito)
                except Exception: 
                    continue
        
        if not lista_de_inscritos: 
            return pd.DataFrame(), competition_title

        status_text.text("Finalizando extração. Limpando e organizando os dados...")
        df = pd.DataFrame(lista_de_inscritos)

        df['Faixa'] = df['Faixa'].str.replace('+', 'E', regex=False)
        df['Categoria de Peso'] = df['Categoria de Peso'].str.replace(' - ', '/', regex=False)
        df['Categoria de Idade'] = df['Categoria de Idade'].str.replace(r'\s*\(.*\)', '', regex=True).str.strip()
        df['Categoria de Peso'] = df['Categoria de Peso'].str.replace(r'\s*\(.*\)', '', regex=True).str.strip()
        
        for column in df.select_dtypes(include=['object']).columns:
            df[column] = df[column].str.normalize('NFD').str.encode('ascii', 'ignore').str.decode('utf-8').str.upper()
        
        ordem_final = ["Nome", "Categoria de Idade", "Faixa", "Categoria de Peso", "Gênero", "Equipe", "Professor"]
        df = df[ordem_final]
        
        return df, competition_title
    
    finally:
        driver.quit()


# ========================================================================
# CLASSES DE DADOS (Sistema de Chaves)
# ========================================================================

class Athlete:
    """Representa um atleta no sistema de chaveamento."""
    
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
    """Representa uma luta no chaveamento."""
    
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
        """Processa automaticamente lutas com bye."""
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
    """Gerador de ordens de seeding."""
    
    @staticmethod
    def generate_seeding_order(bracket_size: int) -> List[int]:
        """Gera ordem de seeding padrão para eliminação simples."""
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
        
        half_size = bracket_size // 2
        half_order = SeedingGenerator.generate_seeding_order(half_size)
        
        full_order = []
        for position in half_order:
            full_order.extend([position, bracket_size - 1 - position])
        
        return full_order


class RoundNamer:
    """Utilitário para nomear rodadas."""
    
    @staticmethod
    def get_round_name(participants_count: int) -> str:
        """Retorna nome da rodada baseado no número de participantes."""
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
    """Classe principal para geração de chaveamentos."""
    
    def __init__(self, athletes: List[Athlete], category: str):
        self.athletes = athletes
        self.category = category
        self.bracket_size = self._calculate_bracket_size()
        self.rounds: List[List[Match]] = []
        self._generate_bracket()

    def _calculate_bracket_size(self) -> int:
        """Calcula próxima potência de 2."""
        return 2 ** math.ceil(math.log2(len(self.athletes)))

    def _generate_bracket(self) -> None:
        """Gera estrutura completa do chaveamento."""
        self._assign_seeds()
        self._create_first_round()
        self._create_subsequent_rounds()
        self._number_matches()

    def _assign_seeds(self) -> None:
        """Atribui seeds aos atletas evitando confrontos da mesma equipe."""
        teams = {}
        for athlete in self.athletes:
            if athlete.team not in teams:
                teams[athlete.team] = []
            teams[athlete.team].append(athlete)
        
        sorted_teams = sorted(teams.items(), key=lambda x: len(x[1]), reverse=True)
        
        seeded_athletes = []
        team_indices = {team: 0 for team, _ in sorted_teams}
        
        while len(seeded_athletes) < len(self.athletes):
            for team, athletes_list in sorted_teams:
                if team_indices[team] < len(athletes_list):
                    seeded_athletes.append(athletes_list[team_indices[team]])
                    team_indices[team] += 1
        
        for idx, athlete in enumerate(seeded_athletes):
            athlete.seed = idx + 1

    def _create_first_round(self) -> None:
        """Cria primeira rodada do chaveamento."""
        seeding_order = SeedingGenerator.generate_seeding_order(self.bracket_size)
        
        positioned_athletes = [None] * self.bracket_size
        for i, athlete in enumerate(self.athletes):
            positioned_athletes[seeding_order[i]] = athlete
        
        first_round = []
        for i in range(0, self.bracket_size, 2):
            match = Match(positioned_athletes[i], positioned_athletes[i + 1])
            match.process_bye()
            first_round.append(match)
        
        self.rounds.append(first_round)

    def _create_subsequent_rounds(self) -> None:
        """Cria rodadas subsequentes."""
        current_round = self.rounds[0]
        
        while len(current_round) > 1:
            next_round = []
            for i in range(0, len(current_round), 2):
                match = Match()
                next_round.append(match)
            self.rounds.append(next_round)
            current_round = next_round

    def _number_matches(self) -> None:
        """Numera todas as lutas."""
        match_number = 1
        for round_matches in self.rounds:
            for match in round_matches:
                if match.has_both_athletes() or match.is_bye():
                    match.number = match_number
                    match_number += 1


class AthleteFilter:
    """Utilitários para filtrar atletas."""
    
    @staticmethod
    def get_available_options(athletes: List[Athlete]) -> Dict[str, List[str]]:
        """Retorna opções disponíveis de filtros."""
        if not athletes:
            return {
                'genders': [],
                'belts': [],
                'age_categories': [],
                'weight_categories': []
            }
        
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


class AthleteProcessor:
    """Processa DataFrame e converte para objetos Athlete."""
    
    @staticmethod
    def process_dataframe(df: pd.DataFrame) -> List[Athlete]:
        """Converte DataFrame em lista de objetos Athlete."""
        athletes = []
        
        for _, row in df.iterrows():
            athlete = Athlete(
                name=str(row.get('Nome', '')),
                team=str(row.get('Equipe', '')),
                age_category=str(row.get('Categoria de Idade', '')),
                weight_category=str(row.get('Categoria de Peso', '')),
                belt=str(row.get('Faixa', '')),
                gender=str(row.get('Gênero', ''))
            )
            athletes.append(athlete)
        
        return athletes


# ========================================================================
# RENDERIZAÇÃO DE CHAVES
# ========================================================================

class StyleManager:
    """Gerenciador de estilos CSS."""
    
    @staticmethod
    def apply_dark_theme() -> None:
        """Aplica tema escuro para chaveamento."""
        st.markdown("""
        <style>
        .bracket-container {
            display: flex;
            overflow-x: auto;
            padding: 20px;
            background: #1e1e1e;
            border-radius: 10px;
            margin: 20px 0;
        }
        
        .round {
            display: flex;
            flex-direction: column;
            justify-content: space-around;
            min-width: 250px;
            margin: 0 10px;
        }
        
        .round-title {
            color: #ffa500;
            font-weight: bold;
            text-align: center;
            margin-bottom: 20px;
            font-size: 1.1em;
            padding: 10px;
            background: #2a2a2a;
            border-radius: 5px;
        }
        
        .match-container {
            margin: 10px 0;
            position: relative;
        }
        
        .match {
            background: #2a2a2a;
            border: 2px solid #444;
            border-radius: 8px;
            padding: 5px;
            min-height: 80px;
        }
        
        .participant {
            padding: 8px 12px;
            margin: 2px 0;
            background: #363636;
            border-radius: 5px;
            border-left: 3px solid #ffa500;
        }
        
        .participant-name {
            color: #fff;
            font-weight: 500;
            font-size: 0.95em;
        }
        
        .participant-team {
            color: #999;
            font-size: 0.85em;
            margin-top: 2px;
        }
        
        .match-number {
            color: #ffa500;
            font-size: 0.8em;
            font-weight: bold;
            text-align: center;
            margin-bottom: 5px;
        }
        
        .bye {
            color: #666;
            font-style: italic;
            text-align: center;
            padding: 10px;
        }
        </style>
        """, unsafe_allow_html=True)


class BracketRenderer:
    """Renderizador de chaveamento."""
    
    @staticmethod
    def render_bracket(bracket: TournamentBracket) -> None:
        """Renderiza chaveamento completo em HTML."""
        html_parts = ['<div class="bracket-container">']
        
        for round_idx, round_matches in enumerate(bracket.rounds):
            participants_in_round = len(round_matches) * 2
            round_name = RoundNamer.get_round_name(participants_in_round)
            
            html_parts.append('<div class="round">')
            html_parts.append(f'<div class="round-title">{round_name}</div>')
            
            for match in round_matches:
                html_parts.extend(BracketRenderer._render_match(match, round_idx == 0))
            
            html_parts.append('</div>')
        
        html_parts.append('</div>')
        
        st.markdown(''.join(html_parts), unsafe_allow_html=True)

    @staticmethod
    def _render_match(match: Match, is_first_round: bool) -> List[str]:
        """Renderiza uma única luta."""
        html_parts = ['<div class="match-container"><div class="match">']
        
        if match.number > 0:
            html_parts.append(f'<div class="match-number">Luta #{match.number}</div>')
        
        html_parts.extend(BracketRenderer._render_participant(match.athlete1, 1, is_first_round))
        html_parts.extend(BracketRenderer._render_participant(match.athlete2, 2, is_first_round))
        
        html_parts.append('</div></div>')
        return html_parts

    @staticmethod
    def _render_participant(athlete: Optional[Athlete], position: int, is_first_round: bool) -> List[str]:
        """Renderiza um participante."""
        html_parts = []
        
        if athlete:
            html_parts.append(f'<div class="participant participant-{position}">')
            html_parts.append(f'<div class="participant-name">{athlete.name}</div>')
            html_parts.append(f'<div class="participant-team">{athlete.team}</div>')
            html_parts.append('</div>')
        else:
            if is_first_round:
                html_parts.append('<div class="bye">BYE</div>')
            else:
                html_parts.append(f'<div class="participant participant-{position}">')
                html_parts.append('<div class="participant-name">&nbsp;</div>')
                html_parts.append('</div>')
        
        return html_parts


# ========================================================================
# DASHBOARD DE ANÁLISE
# ========================================================================

def render_dashboard(df: pd.DataFrame, title: str) -> None:
    """Renderiza dashboard completo de análise."""
    st.header(f"📊 Análise: {title}", divider='orange')

    # KPIs
    total_atletas = len(df)
    total_equipes = df['Equipe'].nunique()
    genero_counts = df['Gênero'].value_counts()
    
    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric(label="Total de Atletas 👥", value=total_atletas)
    kpi2.metric(label="Total de Equipes 🛡️", value=total_equipes)
    kpi3.metric(label="Masculino / Feminino ♂️♀️", value=f"{genero_counts.get('MASCULINO', 0)} / {genero_counts.get('FEMININO', 0)}")

    # Abas
    tab1, tab2 = st.tabs(["📋 Tabela de Dados", "📊 Análise Gráfica"])

    with tab1:
        st.subheader(f"Tabela de Competidores - {title}")
        st.dataframe(df, use_container_width=True)
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Baixar dados como CSV", 
            data=csv, 
            file_name=f'inscritos_{title}.csv', 
            mime='text/csv'
        )

    with tab2:
        # Prepara dados para gráficos
        conditions = [
            df['Categoria de Idade'].str.contains('MASTER'),
            df['Categoria de Idade'].str.contains('ADULTO')
        ]
        choices = ['MASTERS', 'ADULTO']
        df['Grupo Etário'] = np.select(conditions, choices, default='KIDS')
        gender_colors = {'MASCULINO': '#1f77b4', 'FEMININO': '#e377c2'}

        def create_bar_chart(data_frame, group_by_col, chart_title):
            grouped_data = data_frame.groupby([group_by_col, 'Gênero']).size().reset_index(name='Contagem')
            fig = px.bar(
                grouped_data, 
                x=group_by_col, 
                y='Contagem', 
                color='Gênero', 
                title=chart_title,
                labels={'Contagem': 'Número de Atletas', group_by_col: chart_title.split(' por ')[-1]},
                color_discrete_map=gender_colors,
                text_auto=True
            )
            fig.update_xaxes(categoryorder='total descending', tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)

        # Gráficos
        col1, col2 = st.columns(2)
        with col1: 
            create_bar_chart(df, 'Grupo Etário', 'Atletas por Grupo Etário')
        with col2: 
            create_bar_chart(df, 'Categoria de Idade', 'Atletas por Categoria de Idade')
        
        create_bar_chart(df, 'Faixa', 'Atletas por Faixa')
        create_bar_chart(df, 'Categoria de Peso', 'Atletas por Categoria de Peso')
        
        st.subheader("🏆 Análise de Equipes e Professores", divider='orange')
        
        def create_top10_chart(data_frame, group_by_col, chart_title):
            top_10_list = data_frame[group_by_col].value_counts().nlargest(10).index
            df_top10 = data_frame[data_frame[group_by_col].isin(top_10_list)]
            create_bar_chart(df_top10, group_by_col, chart_title)
        
        col3, col4 = st.columns(2)
        with col3: 
            create_top10_chart(df, 'Equipe', 'Top 10 Equipes com Mais Atletas')
        with col4: 
            create_top10_chart(df, 'Professor', 'Top 10 Professores com Mais Atletas')


# ========================================================================
# INTERFACE PRINCIPAL
# ========================================================================

def main():
    """Função principal da aplicação."""
    StyleManager.apply_dark_theme()
    
    st.title("🥋 Sistema Integrado IBJJF")
    st.markdown("**Análise de Competidores + Geração de Chaves Automáticas**")
    
    # Sidebar
    with st.sidebar:
        st.header("⚙️ Configurações")
        
        # Seção de carregamento de dados
        st.subheader("1️⃣ Carregar Dados")
        url = st.text_input(
            "URL da Checagem ProCompetidor:",
            value="https://procompetidor.com.br/checagem/UNpYfAt1jAPYxUTcuhgD",
            help="Cole a URL da página de checagem"
        )
        
        if st.button("🔍 Extrair Dados", type="primary", use_container_width=True):
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            df, title = raspar_dados(url, progress_bar, status_text)
            
            status_text.empty()
            progress_bar.empty()
            
            if not df.empty:
                st.session_state.df = df
                st.session_state.title = title
                st.session_state.athletes_data = AthleteProcessor.process_dataframe(df)
                st.success(f"✅ {len(df)} atletas carregados!")
            else:
                st.error("❌ Nenhum dado encontrado. Verifique a URL.")
        
        st.divider()
        
        # Seção de geração de chaves (apenas se dados carregados)
        if 'athletes_data' in st.session_state:
            st.subheader("2️⃣ Gerar Chave")
            
            athletes = st.session_state.athletes_data
            options = AthleteFilter.get_available_options(athletes)
            
            # Filtros em cascata
            selected_gender = st.selectbox(
                "Gênero:", 
                options['genders'] if options['genders'] else ["Nenhum"]
            )
            
            gender_filtered = AthleteFilter.filter_by_gender(athletes, selected_gender)
            gender_options = AthleteFilter.get_available_options(gender_filtered)
            
            selected_belt = st.selectbox(
                "Faixa:", 
                gender_options['belts'] if gender_options['belts'] else ["Nenhuma"]
            )
            
            belt_filtered = AthleteFilter.filter_by_belt(gender_filtered, selected_belt)
            belt_options = AthleteFilter.get_available_options(belt_filtered)
            
            selected_age = st.selectbox(
                "Categoria de Idade:", 
                belt_options['age_categories'] if belt_options['age_categories'] else ["Nenhuma"]
            )
            
            age_filtered = AthleteFilter.filter_by_age_category(belt_filtered, selected_age)
            age_options = AthleteFilter.get_available_options(age_filtered)
            
            selected_weight = st.selectbox(
                "Categoria de Peso:", 
                age_options['weight_categories'] if age_options['weight_categories'] else ["Nenhuma"]
            )
            
            # Aplicar todos os filtros
            filtered_athletes = AthleteFilter.filter_by_weight_category(age_filtered, selected_weight)
            
            st.info(f"Atletas encontrados: {len(filtered_athletes)}")
            
            if len(filtered_athletes) >= 2:
                if st.button("🏆 Gerar Chaveamento", use_container_width=True):
                    category_name = f"{selected_age} / {selected_gender} / {selected_weight} / {selected_belt}"
                    st.session_state.current_bracket = TournamentBracket(filtered_athletes, category_name)
                    st.session_state.show_bracket = True
                    st.rerun()
            elif len(filtered_athletes) == 1:
                st.warning("⚠️ Apenas 1 atleta encontrado")
            else:
                st.warning("⚠️ Nenhum atleta encontrado com estes filtros")
    
    # Área principal
    if 'df' in st.session_state:
        # Seletor de visualização
        view_mode = st.radio(
            "Visualizar:",
            ["📊 Dashboard de Análise", "🏆 Chaveamento"],
            horizontal=True
        )
        
        if view_mode == "📊 Dashboard de Análise":
            st.session_state.show_bracket = False
            render_dashboard(st.session_state.df, st.session_state.title)
        
        elif view_mode == "🏆 Chaveamento":
            if 'current_bracket' in st.session_state and st.session_state.get('show_bracket', False):
                bracket = st.session_state.current_bracket
                
                st.header(f"🥋 {bracket.category}", divider='orange')
                st.markdown(f"**{len(bracket.athletes)} atletas no chaveamento**")
                
                st.divider()
                st.subheader("Chaveamento Completo")
                BracketRenderer.render_bracket(bracket)
            else:
                st.info("👈 Selecione os filtros na barra lateral e clique em 'Gerar Chaveamento'")
    else:
        st.info("👈 Insira a URL na barra lateral e clique em 'Extrair Dados' para começar")


if __name__ == "__main__":
    main()
