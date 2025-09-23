import streamlit as st
import random
import math
import pandas as pd
import requests
from io import StringIO
from typing import List, Optional, Dict
import unicodedata

st.set_page_config(page_title="Sistema de Chaves IBJJF", layout="wide", initial_sidebar_state="expanded")


def sanitizar_string(texto: str) -> str:
    """
    Remove acentos, converte para maiúsculas e remove espaços extras.
    """
    if not isinstance(texto, str):
        return ""
    texto_normalizado = unicodedata.normalize('NFD', texto)
    texto_sem_acentos = "".join(c for c in texto_normalizado if unicodedata.category(c) != 'Mn')
    return texto_sem_acentos.upper().strip()


# --- Classes de Dados ---
class Atleta:
    def __init__(self, nome: str, equipe: str, seed: int = 0, categoria_idade: str = "", categoria_peso: str = "", faixa: str = "", genero: str = ""):
        self.nome = nome
        self.equipe = equipe
        self.seed = seed
        self.categoria_idade = categoria_idade
        self.categoria_peso = categoria_peso
        self.faixa = faixa
        self.genero = genero

class Luta:
    def __init__(self, atleta1: Optional[Atleta] = None, atleta2: Optional[Atleta] = None):
        self.atleta1 = atleta1
        self.atleta2 = atleta2
        self.vencedor: Optional[Atleta] = None
        self.numero: int = 0

    def processar(self) -> Optional[Atleta]:
        if self.atleta1 and not self.atleta2: 
            self.vencedor = self.atleta1
        elif self.atleta2 and not self.atleta1: 
            self.vencedor = self.atleta2
        return self.vencedor

# --- Lógica de Chaveamento ---
class ChaveamentoProfissional:
    def __init__(self, atletas: List[Atleta], categoria: str):
        self.atletas = atletas
        self.categoria = categoria
        self.rodadas: List[List[Luta]] = []
        self.medalhistas: Dict = {}
        self.nomes_rodadas: List[str] = []

        if len(atletas) > 1:
            self._construir_chave_parcial()

    def _distribuir_por_equipe(self, atletas: List[Atleta], posicoes: List[int], tamanho_chave: int) -> List[tuple]:
        """
        Distribui atletas evitando que mesma equipe se enfrente antes da final/semifinal
        """
        # Agrupa atletas por equipe
        equipes = {}
        for atleta in atletas:
            if atleta.equipe not in equipes:
                equipes[atleta.equipe] = []
            equipes[atleta.equipe].append(atleta)
        
        # Define quadrantes baseado no tamanho da chave
        num_quadrantes = min(4, tamanho_chave // 4) if tamanho_chave >= 8 else 2
        tamanho_quadrante = len(posicoes) // num_quadrantes
        
        quadrantes = []
        for i in range(num_quadrantes):
            inicio = i * tamanho_quadrante
            fim = inicio + tamanho_quadrante if i < num_quadrantes - 1 else len(posicoes)
            quadrantes.append(posicoes[inicio:fim])
        
        print(f"DEBUG: Distribuindo {len(atletas)} atletas em {num_quadrantes} quadrantes")
        
        # Distribui atletas da mesma equipe em quadrantes diferentes
        resultado = []
        quadrante_atual = 0
        
        for equipe, atletas_equipe in equipes.items():
            if len(atletas_equipe) > 1:
                print(f"DEBUG: Equipe '{equipe}' tem {len(atletas_equipe)} atletas - separando")
            
            for atleta in atletas_equipe:
                # Encontra posição disponível no quadrante atual
                if quadrantes[quadrante_atual]:
                    pos = quadrantes[quadrante_atual].pop(0)
                    resultado.append((atleta, pos))
                    print(f"DEBUG: {atleta.nome} ({equipe}) -> quadrante {quadrante_atual + 1}, posição {pos}")
                
                # Muda para próximo quadrante se há múltiplos atletas da mesma equipe
                if len(atletas_equipe) > 1:
                    quadrante_atual = (quadrante_atual + 1) % num_quadrantes
        
        return resultado

    def _construir_chave_parcial(self):
        n = len(self.atletas)
        if n == 0: 
            return

        # USA ORDEM DA LISTA COMO SEED (mais simples e direto)
        # Já estão ordenados por seed que vem da ordem da planilha
        atletas_ordenados = sorted(self.atletas, key=lambda x: x.seed)
        
        tamanho_chave = 2 ** math.ceil(math.log2(n))
        num_byes = tamanho_chave - n
        
        print(f"DEBUG: {n} atletas, chave {tamanho_chave}, {num_byes} byes")
        
        # Identifica quais posições resultarão em bye
        chave_inicial = [None] * tamanho_chave
        ordem_seeding = self._gerar_ordem_seeding(tamanho_chave)
        
        # Coloca atletas nas primeiras N posições da ordem seeding
        for i, atleta in enumerate(atletas_ordenados):
            pos = ordem_seeding[i]
            chave_inicial[pos] = atleta
        
        # Identifica posições que terão bye
        posicoes_bye = []
        for i in range(0, tamanho_chave, 2):
            pos1, pos2 = i, i + 1
            if chave_inicial[pos1] and not chave_inicial[pos2]:
                posicoes_bye.append(pos1)
            elif chave_inicial[pos2] and not chave_inicial[pos1]:
                posicoes_bye.append(pos2)
        
        print(f"DEBUG: Posições com bye: {posicoes_bye}")
        
        # Reorganiza: melhores seeds nas posições de bye
        if posicoes_bye:
            # Ordena posições de bye pela ordem seeding
            posicoes_bye_ordenadas = [pos for pos in ordem_seeding if pos in posicoes_bye]
            
            # Limpa chave e redistribui
            chave_inicial = [None] * tamanho_chave
            
            # Coloca melhores seeds nas posições de bye
            for i, pos in enumerate(posicoes_bye_ordenadas):
                if i < len(atletas_ordenados):
                    chave_inicial[pos] = atletas_ordenados[i]
                    print(f"DEBUG: BYE - {atletas_ordenados[i].nome} (seed #{atletas_ordenados[i].seed}) -> posição {pos}")
            
            # Coloca demais atletas nas posições restantes
            pos_ocupadas = set(posicoes_bye_ordenadas)
            pos_livres = [pos for pos in ordem_seeding if pos not in pos_ocupadas]
            
            idx_atleta = len(posicoes_bye_ordenadas)
            for pos in pos_livres:
                if idx_atleta < len(atletas_ordenados):
                    chave_inicial[pos] = atletas_ordenados[idx_atleta]
                    print(f"DEBUG: LUTA - {atletas_ordenados[idx_atleta].nome} (seed #{atletas_ordenados[idx_atleta].seed}) -> posição {pos}")
                    idx_atleta += 1
        
        # Cria primeira rodada
        rodada1 = []
        numero_luta = 1
        
        for i in range(0, tamanho_chave, 2):
            luta = Luta(chave_inicial[i], chave_inicial[i+1])
            
            if luta.atleta1 and luta.atleta2:
                luta.numero = numero_luta
                numero_luta += 1
                print(f"DEBUG: Luta {numero_luta-1}: {luta.atleta1.nome} vs {luta.atleta2.nome}")
            elif luta.atleta1 or luta.atleta2:
                luta.processar()
                vencedor = luta.atleta1 or luta.atleta2
                print(f"DEBUG: Bye para: {vencedor.nome}")
                
            rodada1.append(luta)
        
        self.rodadas.append(rodada1)
        self.nomes_rodadas.append(self._get_nome_rodada(tamanho_chave))
        
        # Rodadas subsequentes
        rodada_anterior = rodada1
        while len(rodada_anterior) > 1:
            nova_rodada = []
            for i in range(0, len(rodada_anterior), 2):
                vencedor1 = rodada_anterior[i].vencedor if i < len(rodada_anterior) else None
                vencedor2 = rodada_anterior[i+1].vencedor if i+1 < len(rodada_anterior) else None
                
                luta = Luta(vencedor1, vencedor2)
                if vencedor1 and vencedor2:
                    luta.numero = numero_luta
                    numero_luta += 1
                
                nova_rodada.append(luta)
            
            self.rodadas.append(nova_rodada)
            self.nomes_rodadas.append(self._get_nome_rodada(len(nova_rodada) * 2))
            rodada_anterior = nova_rodada

    def _gerar_ordem_seeding(self, n: int) -> List[int]:
        if n <= 1: return [0]
        if n == 2: return [0, 1]
        if n == 4: return [0, 3, 1, 2]
        if n == 8: return [0, 7, 3, 4, 1, 6, 2, 5]
        if n == 16: return [0, 15, 7, 8, 3, 12, 4, 11, 1, 14, 6, 9, 2, 13, 5, 10]
        if n == 32: return [0, 31, 15, 16, 7, 24, 8, 23, 3, 28, 12, 19, 4, 27, 11, 20,
                             1, 30, 14, 17, 6, 25, 9, 22, 2, 29, 13, 18, 5, 26, 10, 21]
        if n == 64: return [0, 63, 31, 32, 15, 48, 16, 47, 7, 56, 24, 39, 8, 55, 23, 40,
                             3, 60, 28, 35, 12, 51, 19, 44, 4, 59, 27, 36, 11, 52, 20, 43,
                             1, 62, 30, 33, 14, 49, 17, 46, 6, 57, 25, 38, 9, 54, 22, 41,
                             2, 61, 29, 34, 13, 50, 18, 45, 5, 58, 26, 37, 10, 53, 21, 42]
        if n == 128: return [0, 127, 63, 64, 31, 96, 32, 95, 15, 112, 48, 79, 16, 111, 47, 80,
                             7, 120, 56, 71, 24, 103, 39, 88, 8, 119, 55, 72, 23, 104, 40, 87,
                             3, 124, 60, 67, 28, 99, 35, 92, 12, 115, 51, 76, 19, 108, 44, 83,
                             4, 123, 59, 68, 27, 100, 36, 91, 11, 116, 52, 75, 20, 107, 43, 84,
                             1, 126, 62, 65, 30, 97, 33, 94, 14, 113, 49, 78, 17, 110, 46, 81,
                             6, 121, 57, 70, 25, 102, 38, 89, 9, 118, 54, 73, 22, 105, 41, 86,
                             2, 125, 61, 66, 29, 98, 34, 93, 13, 114, 50, 77, 18, 109, 45, 82,
                             5, 122, 58, 69, 26, 101, 37, 90, 10, 117, 53, 74, 21, 106, 42, 85]
        
        metade = self._gerar_ordem_seeding(n // 2)
        ordem = []
        for i in metade:
            ordem.append(i)
            ordem.append(n - 1 - i)
        return ordem
        
    def _get_nome_rodada(self, n: int) -> str:
        if n == 2: return "FINAL"
        if n == 4: return "SEMIFINAIS"
        if n == 8: return "QUARTAS DE FINAL"
        if n == 16: return "OITAVAS DE FINAL"
        if n == 32: return "16-AVOS DE FINAL"
        if n == 64: return "32-AVOS DE FINAL"
        if n == 128: return "64-AVOS DE FINAL"
        if n == 256: return "128-AVOS DE FINAL"
        return f"RODADA DE {n}"

# --- Funções Google Sheets ---
def carregar_dados_google_sheets(sheet_url: str) -> pd.DataFrame:
    try:
        if "/edit" in sheet_url:
            sheet_id = sheet_url.split("/d/")[1].split("/edit")[0]
        else:
            sheet_id = sheet_url
            
        csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
        
        response = requests.get(csv_url)
        response.raise_for_status()
        response.encoding = 'utf-8'
        
        csv_data = StringIO(response.text)
        df = pd.read_csv(csv_data)
        
        return df
    except Exception as e:
        st.error(f"Erro ao carregar planilha: {str(e)}")
        return pd.DataFrame()

def processar_atletas_planilha(df: pd.DataFrame) -> List[Atleta]:
    atletas = []
    
    for i, row in df.iterrows():
        if pd.notna(row.iloc[0]):
            nome = sanitizar_string(str(row.iloc[0]))
            categoria_idade = sanitizar_string(str(row.iloc[1]) if pd.notna(row.iloc[1]) else "")
            categoria_peso = sanitizar_string(str(row.iloc[2]) if pd.notna(row.iloc[2]) else "")
            faixa = sanitizar_string(str(row.iloc[4]) if pd.notna(row.iloc[4]) else "")
            genero = sanitizar_string(str(row.iloc[5]) if pd.notna(row.iloc[5]) else "")
            
            if len(row) > 6 and pd.notna(row.iloc[6]):
                equipe = sanitizar_string(str(row.iloc[6]))
            else:
                equipe = sanitizar_string("Equipe não informada")
            
            atletas.append(Atleta(
                nome=nome,
                equipe=equipe,
                seed=i+1,
                categoria_idade=categoria_idade,
                categoria_peso=categoria_peso,
                faixa=faixa,
                genero=genero
            ))
    
    return atletas

# --- FUNÇÃO DE VISUALIZAÇÃO RESTAURADA PARA A VERSÃO ORIGINAL E CORRETA ---
# --- FUNÇÃO DE VISUALIZAÇÃO COM LÓGICA DE BYE CORRIGIDA ---
def renderizar_bracket_flexbox(chave: ChaveamentoProfissional):
    """Renderiza bracket com design dark theme integrado e linhas conectoras corretas"""
    
    if not chave.rodadas:
        return
    
    css = """
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
        
        .rodada-column {
            display: flex;
            flex-direction: column;
            justify-content: space-around;
            min-width: 180px;
            position: relative;
            z-index: 2;
        }
        
        .rodada-titulo {
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
        
        .lutas-container {
            display: flex;
            flex-direction: column;
            justify-content: space-around;
            flex: 1;
            gap: 12px;
        }
        
        .luta-wrapper {
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
        
        .trophy {
            margin-left: 6px;
            font-size: 12px;
            filter: drop-shadow(0 1px 2px rgba(255, 215, 0, 0.8));
        }
        
        @media (max-width: 768px) {
            .bracket-container {
                gap: 20px;
            }
            
            .rodada-column {
                min-width: 160px;
            }
            
            .participant {
                padding: 5px 8px;
                font-size: 11px;
            }
            
            .rodada-titulo {
                font-size: 10px;
                padding: 6px 4px;
            }
        }
    </style>
    """
    
    html_parts = ['<div class="bracket-wrapper"><div class="bracket-container">']
    
    for rodada_idx, (rodada, nome) in enumerate(zip(chave.rodadas, chave.nomes_rodadas)):
        html_parts.append('<div class="rodada-column">')
        html_parts.append(f'<div class="rodada-titulo">{nome}</div>')
        html_parts.append('<div class="lutas-container">')
        
        for luta_idx, luta in enumerate(rodada):
            html_parts.append('<div class="luta-wrapper">')
            html_parts.append('<div class="fight-card">')
            
            # Caso de uma luta futura completamente vazia
            if not luta.atleta1 and not luta.atleta2:
                html_parts.append('<div class="participant participant-top"><div class="participant-info">&nbsp;</div></div>')
                html_parts.append('<div class="participant participant-bottom"><div class="participant-info">&nbsp;</div></div>')
            else:
                # --- Lógica de renderização do Atleta 1 ---
                if luta.atleta1:
                    winner_class = "winner" if luta.vencedor == luta.atleta1 else ""
                    seed_text = f' <span class="seed">#{luta.atleta1.seed}</span>'
                    
                    html_parts.append(f'<div class="participant participant-top {winner_class}">')
                    html_parts.append('<div class="participant-info">')
                    html_parts.append(f'<div class="participant-name">{luta.atleta1.nome}{seed_text}</div>')
                    html_parts.append(f'<div class="participant-team">{luta.atleta1.equipe}</div>')
                    html_parts.append('</div></div>')
                else:
                    # ******** CORREÇÃO APLICADA AQUI ********
                    # Só mostra BYE na primeira rodada. Nas outras, mostra um slot vazio.
                    if rodada_idx == 0:
                        html_parts.append('<div class="bye">BYE</div>')
                    else:
                        html_parts.append('<div class="participant participant-top"><div class="participant-info">&nbsp;</div></div>')

                # --- Lógica de renderização do Atleta 2 ---
                if luta.atleta2:
                    winner_class = "winner" if luta.vencedor == luta.atleta2 else ""
                    seed_text = f' <span class="seed">#{luta.atleta2.seed}</span>'
                    
                    html_parts.append(f'<div class="participant participant-bottom {winner_class}">')
                    html_parts.append('<div class="participant-info">')
                    html_parts.append(f'<div class="participant-name">{luta.atleta2.nome}{seed_text}</div>')
                    html_parts.append(f'<div class="participant-team">{luta.atleta2.equipe}</div>')
                    html_parts.append('</div></div>')
                elif luta.atleta1:
                    # ******** CORREÇÃO APLICADA AQUI ********
                    # Só mostra BYE na primeira rodada. Nas outras, mostra um slot vazio.
                    if rodada_idx == 0:
                        html_parts.append('<div class="bye">BYE</div>')
                    else:
                        html_parts.append('<div class="participant participant-bottom"><div class="participant-info">&nbsp;</div></div>')
            
            html_parts.append('</div>')
            
            if rodada_idx > 0:
                html_parts.append('<div class="connector-entry"></div>')
            
            if rodada_idx < len(chave.rodadas) - 1:
                html_parts.append('<div class="connector-horizontal"></div>')
                
                if luta_idx % 2 == 0:
                    html_parts.append('<div class="connector-vertical-bottom"></div>')
                else:
                    html_parts.append('<div class="connector-vertical-top"></div>')
            
            html_parts.append('</div>')
        
        html_parts.append('</div></div>')
    
    html_parts.append('</div></div>')
    
    st.markdown(css, unsafe_allow_html=True)
    st.markdown(''.join(html_parts), unsafe_allow_html=True)

# --- Custom Dark Theme CSS for Streamlit ---
def apply_dark_theme():
    st.markdown("""
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
    """, unsafe_allow_html=True)

# --- Interface Principal ---
def app():
    apply_dark_theme()
    
    st.title("Sistema de Chaves IBJJF")
    st.markdown("**Geração automática por categorias**")

    with st.sidebar:
        st.header("Configurações")
        
        sheet_url = st.text_input(
            "URL do Google Sheets:",
            value=" ",
            help="Cole a URL pública do Google Sheets"
        )
        
        if st.button("Carregar Dados", type="primary", use_container_width=True):
            with st.spinner("Carregando dados..."):
                df = carregar_dados_google_sheets(sheet_url)
                if not df.empty:
                    st.session_state.df_atletas = df
                    st.session_state.atletas_processados = processar_atletas_planilha(df)
                    st.success(f"{len(st.session_state.atletas_processados)} atletas carregados!")

        if 'atletas_processados' in st.session_state:
            st.divider()
            
            atletas = st.session_state.atletas_processados
            
            generos_disponiveis = sorted(list(set(a.genero for a in atletas if a.genero)))
            genero_sel = st.selectbox("Gênero:", generos_disponiveis if generos_disponiveis else ["Nenhum"])
            
            atletas_filtrados_genero = [a for a in atletas if a.genero == genero_sel]

            faixas_disponiveis = sorted(list(set(a.faixa for a in atletas_filtrados_genero if a.faixa)))
            faixa_sel = st.selectbox("Faixa:", faixas_disponiveis if faixas_disponiveis else ["Nenhuma"])
            
            atletas_filtrados_faixa = [a for a in atletas_filtrados_genero if a.faixa == faixa_sel]

            idades_disponiveis = sorted(list(set(a.categoria_idade for a in atletas_filtrados_faixa if a.categoria_idade)))
            categoria_idade_sel = st.selectbox("Categoria de Idade:", idades_disponiveis if idades_disponiveis else ["Nenhuma"])

            atletas_filtrados_idade = [a for a in atletas_filtrados_faixa if a.categoria_idade == categoria_idade_sel]

            pesos_disponiveis = sorted(list(set(a.categoria_peso for a in atletas_filtrados_idade if a.categoria_peso)))
            categoria_peso_sel = st.selectbox("Categoria de Peso:", pesos_disponiveis if pesos_disponiveis else ["Nenhuma"])

            atletas_filtrados = [a for a in atletas_filtrados_idade if a.categoria_peso == categoria_peso_sel]
            
            # ******** NOVA LÓGICA DE REATRIBUIÇÃO DE SEED ********
            # Reatribui os seeds de 1 a N para os atletas da categoria filtrada,
            # mantendo a ordem original da planilha como critério de desempate.
            for novo_seed, atleta in enumerate(atletas_filtrados, start=1):
                atleta.seed = novo_seed
            # ******************************************************
            
            st.info(f"Atletas encontrados: {len(atletas_filtrados)}")
            
            if len(atletas_filtrados) >= 2:
                if st.button("Gerar Chave", use_container_width=True):
                    categoria_completa = f"{categoria_idade_sel} / {genero_sel} / {categoria_peso_sel} / {faixa_sel}"
                    st.session_state.chaveamento = ChaveamentoProfissional(atletas_filtrados, categoria_completa)
            elif len(atletas_filtrados) == 1:
                st.warning("Apenas 1 atleta encontrado")
            else:
                st.warning("Nenhum atleta encontrado com estes filtros")

    if 'chaveamento' in st.session_state:
        chave = st.session_state.chaveamento
        
        st.header(chave.categoria)
        st.markdown(f"**{len(chave.atletas)} atletas**")
        
        st.divider()
        st.subheader("Chaveamento")
        renderizar_bracket_flexbox(chave)
    
    else:
        st.info("Carregue os dados e selecione os filtros para gerar uma chave")

if __name__ == "__main__":
    app()
