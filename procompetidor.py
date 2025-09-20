import streamlit as st
import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options  # Importando Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import re
import unicodedata
import numpy as np

# --- Função para remover acentos (sem alterações) ---
def remove_accents(input_str):
    if not isinstance(input_str, str):
        return input_str
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

# --- Função de Sanitização (sem alterações) ---
def sanitize_data(df):
    text_columns = ['faixa', 'genero', 'equipe', 'professor', 'categoria_de_idade', 'categoria_de_peso']

    for col in text_columns:
        if col in df.columns and not df[col].empty:
            series = df[col].astype(str)
            if col == 'categoria_de_peso':
                series = series.str.replace(r'\s*\([^)]*\)', '', regex=True)
                series = series.str.replace(' - ', '/', regex=False)
            if col == 'categoria_de_idade':
                series = series.str.replace(r'\s*\([^)]*\)', '', regex=True)
            if col == 'faixa':
                series = series.str.replace('+', ' E ', regex=False)
                series = series.str.replace('/', ' E ', regex=False)
                series = series.replace({"MARON": "MARROM"})

            series = series.apply(remove_accents)
            series = series.str.upper()
            series = series.str.replace(r'\s+', ' ', regex=True)
            series = series.str.strip()
            df[col] = series
            
    return df

# --- Função de Scraping (COM AJUSTES) ---
@st.cache_data(show_spinner=True, ttl=3600)
def perform_scraping(url):
    """
    Realiza o scraping do título do evento e dos dados de atletas,
    usando a inicialização moderna do Selenium 4.
    """
    # --- CONFIGURAÇÃO DO SELENIUM 4 (MODO MODERNO) ---
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    try:
        # O Selenium Manager (parte do Selenium 4+) gerencia o driver automaticamente.
        # Não é mais necessário usar o webdriver-manager.
        service = Service()
        driver = webdriver.Chrome(service=service, options=options)
        
    except Exception as e:
        st.error(f"Erro ao inicializar o WebDriver: {e}")
        st.error("Isso pode ocorrer se as dependências do sistema (packages.txt) ou do Python (requirements.txt) estiverem incorretas.")
        return None, "Erro de Inicialização"
    # --------------------------------------------------------

    st.write(f"Iniciando raspagem de dados de: {url}")
    
    championship_title = "Análise de Inscritos"
    
    try:
        driver.get(url)
        
        try:
            title_xpath = "//*[@id='root']/div/div/div/div[1]/div/div/div[1]/h1"
            wait = WebDriverWait(driver, 10)
            title_element = wait.until(EC.visibility_of_element_located((By.XPATH, title_xpath)))
            full_title = title_element.text
            championship_title = full_title.replace("CHECAGEM", "").strip()
            st.success(f"Título do evento encontrado: {championship_title}")
        except Exception as e:
            st.warning(f"Não foi possível capturar o título do evento. Usando título padrão. Erro: {e}")

        button_xpath = """//*[@id="ratings-widget-25"]/div/div[4]/div"""
        wait = WebDriverWait(driver, 30)
        load_list_button = wait.until(EC.element_to_be_clickable((By.XPATH, button_xpath)))
        load_list_button.click()
        st.write("Botão 'Ver Lista de Inscritos' clicado. Aguardando carregamento...")

        card_class_name = "ticket-style-1"
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, card_class_name)))
        time.sleep(3)

        html_content = driver.page_source
        soup = BeautifulSoup(html_content, 'lxml')
        athlete_cards = soup.find_all('div', class_=card_class_name)
        st.success(f"Dados raspados com sucesso! Encontrados {len(athlete_cards)} atletas.")

        lista_de_atletas = []

        for card in athlete_cards:
            dados_atleta = {}
            try:
                h3_tag = card.find('h3')
                if not h3_tag: continue
                nome_bruto = h3_tag.get_text(separator=' ').strip()
                nome_limpo = re.sub(r'Somente Peso|Categoria Peso e Absoluto', '', nome_bruto, flags=re.IGNORECASE)
                dados_atleta['nome'] = " ".join(nome_limpo.split())
                info_divs = card.find_all('div', class_='ticket-info')
                if info_divs and any(div.find('strong') for div in info_divs):
                    for info in info_divs:
                        strong_tag = info.find('strong')
                        if strong_tag:
                            chave = strong_tag.text.strip().replace(':', ''); valor = strong_tag.next_sibling.strip() if strong_tag.next_sibling else ""
                            if 'Idade' in chave: dados_atleta['categoria_de_idade'] = valor
                            elif 'Faixa' in chave: dados_atleta['faixa'] = valor
                            elif 'Peso' in chave: dados_atleta['categoria_de_peso'] = valor
                            elif 'Gênero' in chave: dados_atleta['genero'] = valor
                            elif 'Equipe' in chave: dados_atleta['equipe'] = valor
                            elif 'Professor' in chave: dados_atleta['professor'] = valor
                else:
                    p_tag = card.find('p')
                    if p_tag:
                        linhas_brutas = str(p_tag).split('<br/>'); linhas = [BeautifulSoup(linha, "lxml").get_text().strip() for linha in linhas_brutas]
                        if len(linhas) >= 3:
                            dados_atleta['categoria_de_idade'] = linhas[0]
                            partes = [p.strip() for p in linhas[1].split('/')]
                            if len(partes) >= 2:
                                dados_atleta['faixa'] = partes[0]; dados_atleta['genero'] = partes[-1]; dados_atleta['categoria_de_peso'] = "/".join(partes[1:-1]).strip()
                            partes_linha_2 = [p.strip() for p in linhas[2].split('/')]
                            if len(partes_linha_2) >= 2:
                                dados_atleta['equipe'] = partes_linha_2[0]; dados_atleta['professor'] = partes_linha_2[1]
                lista_de_atletas.append(dados_atleta)
            except Exception as e:
                st.warning(f"Erro ao processar um card: {e}")

        df = pd.DataFrame(lista_de_atletas)
        colunas_ordenadas = ['nome', 'categoria_de_idade', 'faixa', 'categoria_de_peso', 'genero', 'equipe', 'professor']
        
        for col in colunas_ordenadas:
            if col not in df.columns: df[col] = pd.NA
        df = df[colunas_ordenadas]
        
        df = sanitize_data(df)
        
        return df, championship_title

    except Exception as e:
        st.error(f"Ocorreu um erro crítico durante a raspagem de dados: {e}")
        return None, championship_title
    finally:
        # Garante que o driver seja fechado mesmo se ocorrerem erros
        if 'driver' in locals() and driver:
            driver.quit()

# --- Interface Streamlit (sem alterações) ---
st.set_page_config(layout="wide", page_title="Extractor de Atletas ProCompetidor")
st.title("💪 Extrator de Atletas ProCompetidor")
st.markdown("Esta ferramenta extrai a lista de atletas de uma página de checagem do site ProCompetidor. Insira a URL abaixo e clique em 'Extrair Dados'.")

default_url = "https://procompetidor.com.br/checagem/UNpYfAt1jAPYxUTcuhgD"
url_input = st.text_input("URL da página de checagem:", default_url)

if st.button("Extrair Dados"):
    if url_input:
        df_atletas, title = perform_scraping(url_input)
        
        if title:
            st.title(f"📊 Análise de Inscritos: {title}")
        
        if df_atletas is not None and not df_atletas.empty:
            st.subheader("Dados dos Atletas Extraídos e Padronizados")
            st.dataframe(df_atletas, use_container_width=True)
            
            csv = df_atletas.to_csv(index=False).encode('utf-8-sig')
            st.download_button("Baixar dados como CSV", csv, "atletas_procompetidor.csv", "text/csv")
            
            st.divider()
            st.header("📊 Análise Visual dos Dados")
            
            try:
                if 'genero' in df_atletas.columns and not df_atletas['genero'].dropna().empty:
                    color_map = {"FEMININO": "#FF69B4", "MASCULINO": "#1E90FF"}
                    
                    # --- NOVA LÓGICA: Cria a coluna 'grupo_etario' para o novo gráfico ---
                    conditions = [
                        df_atletas['categoria_de_idade'].str.contains('MASTER'),
                        df_atletas['categoria_de_idade'].str.contains('ADULTO')
                    ]
                    choices = ['MASTERS', 'ADULTOS']
                    df_atletas['grupo_etario'] = np.select(conditions, choices, default='KIDS')
                    # ----------------------------------------------------------------------

                    # --- NOVO GRÁFICO: Divisão Geral por Grupo Etário ---
                    st.subheader("Visão Geral: Divisão por Grupo Etário")
                    grupo_etario_counts = df_atletas.groupby(['grupo_etario', 'genero']).size().unstack(fill_value=0)
                    colors = [color_map.get(col, "#808080") for col in grupo_etario_counts.columns]
                    st.bar_chart(grupo_etario_counts, use_container_width=True, color=colors)
                    # -----------------------------------------------------

                    st.divider() # Adiciona uma linha divisória para separar a visão geral dos detalhes

                    col1, col2 = st.columns(2)
                    with col1:
                        st.subheader("Atletas por Categoria de Idade (Detalhado)")
                        idade_gender_counts = df_atletas.groupby(['categoria_de_idade', 'genero']).size().unstack(fill_value=0)
                        idade_gender_counts['total'] = idade_gender_counts.sum(axis=1)
                        idade_gender_counts = idade_gender_counts.sort_values('total', ascending=False).drop(columns='total')
                        colors = [color_map.get(col, "#808080") for col in idade_gender_counts.columns]
                        st.bar_chart(idade_gender_counts, use_container_width=True, color=colors)
                        
                    with col2:
                        st.subheader("Atletas por Faixa")
                        faixa_gender_counts = df_atletas.groupby(['faixa', 'genero']).size().unstack(fill_value=0)
                        faixa_gender_counts['total'] = faixa_gender_counts.sum(axis=1)
                        faixa_gender_counts = faixa_gender_counts.sort_values('total', ascending=False).drop(columns='total')
                        colors = [color_map.get(col, "#808080") for col in faixa_gender_counts.columns]
                        st.bar_chart(faixa_gender_counts, use_container_width=True, color=colors)

                    st.subheader("Atletas por Categoria de Peso")
                    peso_gender_counts = df_atletas.groupby(['categoria_de_peso', 'genero']).size().unstack(fill_value=0)
                    peso_gender_counts['total'] = peso_gender_counts.sum(axis=1)
                    peso_gender_counts = peso_gender_counts.sort_values('total', ascending=False).drop(columns='total')
                    colors = [color_map.get(col, "#808080") for col in peso_gender_counts.columns]
                    st.bar_chart(peso_gender_counts, use_container_width=True, color=colors)
                    
                    st.subheader("Top 15 Equipes com Mais Atletas")
                    equipe_gender_counts = df_atletas.groupby(['equipe', 'genero']).size().unstack(fill_value=0)
                    equipe_gender_counts['total'] = equipe_gender_counts.sum(axis=1)
                    top_equipes = equipe_gender_counts.sort_values('total', ascending=False).head(15).drop(columns='total')
                    colors = [color_map.get(col, "#808080") for col in top_equipes.columns]
                    st.bar_chart(top_equipes, use_container_width=True, color=colors)

                    st.subheader("Top 15 Professores com Mais Atletas")
                    prof_gender_counts = df_atletas.groupby(['professor', 'genero']).size().unstack(fill_value=0)
                    prof_gender_counts['total'] = prof_gender_counts.sum(axis=1)
                    top_prof = prof_gender_counts.sort_values('total', ascending=False).head(15).drop(columns='total')
                    colors = [color_map.get(col, "#808080") for col in top_prof.columns]
                    st.bar_chart(top_prof, use_container_width=True, color=colors)

                else:
                    st.warning("Não foi possível gerar gráficos por gênero pois a coluna 'genero' está vazia ou ausente.")
            except Exception as e:
                st.error(f"Ocorreu um erro ao gerar os gráficos: {e}")

        elif df_atletas is not None and df_atletas.empty:
            st.warning("Nenhum atleta foi encontrado na página.")
        else:
            st.error("Não foi possível extrair os dados.")
    else:
        st.warning("Por favor, insira uma URL para continuar.")

st.markdown("---")
st.markdown("Desenvolvido com ❤️ e Python.")
