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

# --- Configuração da Página do Streamlit ---
st.set_page_config(
    page_title="Dashboard ProCompetidor",
    page_icon="📊",
    layout="wide"
)

# --- Função de Extração e Limpeza de Dados ---
def raspar_dados(url, progress_bar, status_text):
    """
    Função ajustada para rodar em ambiente de deploy (Hugging Face),
    apontando diretamente para o driver do sistema.
    """
    # --- Configuração do Selenium para ambiente de produção (Hugging Face) ---
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")

    # --- LINHA MAIS IMPORTANTE PARA O DEPLOY ---
    # Aponta diretamente para o chromedriver instalado via packages.txt
    service = Service(executable_path="/usr/bin/chromedriver")
    driver = webdriver.Chrome(service=service, options=chrome_options) 
    # ----------------------------------------------
    
    competition_title = "Competição" # Título padrão
    
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
                    inscrito = {"Nome": nome, "Equipe": equipe, "Professor": professor, "Categoria de Idade": categoria_idade, "Faixa": faixa, "Categoria de Peso": categoria_peso, "Gênero": genero}
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

# --- Interface Principal do Streamlit (UI) ---
st.title("🥋 Dashboard de Análise ProCompetidor")
st.markdown("Insira a URL de uma página de checagem para extrair, limpar e visualizar os dados dos inscritos.")

url = st.text_input("URL da página de checagem", "https://procompetidor.com.br/checagem/UNpYfAt1jAPYxUTcuhgD")

if st.button("Analisar Competição", type="primary"):
    progress_bar = st.progress(0)
    status_text = st.empty()

    df, title = raspar_dados(url, progress_bar, status_text)
    
    status_text.empty()
    progress_bar.empty()
    
    if not df.empty:
        # Define o título principal da página com o nome do evento
        st.header(f"Resultados para: {title}", divider='orange')

        # Apresenta as métricas principais (KPIs)
        total_atletas = len(df)
        total_equipes = df['Equipe'].nunique()
        genero_counts = df['Gênero'].value_counts()
        
        kpi1, kpi2, kpi3 = st.columns(3)
        kpi1.metric(label="Total de Atletas 👥", value=total_atletas)
        kpi2.metric(label="Total de Equipes 🛡️", value=total_equipes)
        kpi3.metric(label="Masculino / Feminino ♂️♀️", value=f"{genero_counts.get('MASCULINO', 0)} / {genero_counts.get('FEMININO', 0)}")

        # Organiza o conteúdo principal em abas
        tab1, tab2 = st.tabs(["📊 Análise Gráfica", "📋 Tabela de Dados Completa"])

        with tab2:
            st.subheader(f"Tabela de Competidores Corrigida - {title}")
            st.dataframe(df)
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(label="Baixar dados como CSV", data=csv, file_name=f'inscritos_{title}.csv', mime='text/csv')

        with tab1:
            # Prepara os dados para os gráficos
            conditions = [df['Categoria de Idade'].str.contains('MASTER'), df['Categoria de Idade'].str.contains('ADULTO')]
            choices = ['MASTERS', 'ADULTO']
            df['Grupo Etário'] = np.select(conditions, choices, default='KIDS')
            gender_colors = {'MASCULINO': '#1f77b4', 'FEMININO': '#e377c2'}

            # Função auxiliar para criar gráficos de barras
            def create_bar_chart(data_frame, group_by_col, title):
                grouped_data = data_frame.groupby([group_by_col, 'Gênero']).size().reset_index(name='Contagem')
                fig = px.bar(grouped_data, x=group_by_col, y='Contagem', color='Gênero', title=title, labels={'Contagem': 'Número de Atletas', group_by_col: title.split(' por ')[-1]}, color_discrete_map=gender_colors, text_auto=True)
                fig.update_xaxes(categoryorder='total descending', tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)

            # Gera os gráficos principais
            col1, col2 = st.columns(2)
            with col1: 
                create_bar_chart(df, 'Grupo Etário', 'Atletas por Grupo Etário')
            with col2: 
                create_bar_chart(df, 'Categoria de Idade', 'Atletas por Categoria de Idade')
            
            create_bar_chart(df, 'Faixa', 'Atletas por Faixa')
            create_bar_chart(df, 'Categoria de Peso', 'Atletas por Categoria de Peso')
            
            st.subheader("🏆 Análise de Equipes e Professores", divider='orange')
            
            # Função auxiliar para criar gráficos de Top 10
            def create_top10_chart(data_frame, group_by_col, title):
                top_10_list = data_frame[group_by_col].value_counts().nlargest(10).index
                df_top10 = data_frame[data_frame[group_by_col].isin(top_10_list)]
                create_bar_chart(df_top10, group_by_col, title)
            
            # Gera os gráficos de Top 10
            col3, col4 = st.columns(2)
            with col3: 
                create_top10_chart(df, 'Equipe', 'Top 10 Equipes com Mais Atletas')
            with col4: 
                create_top10_chart(df, 'Professor', 'Top 10 Professores com Mais Atletas')

    else:
        st.warning("Nenhum dado foi encontrado. A URL pode estar inativa ou a estrutura do site mudou.")
