import requests
import pandas as pd
from datetime import datetime, timedelta
import streamlit as st

# ===========================
# Funzioni
# ===========================

def ultime_date(n_giorni=14):
    """Restituisce una lista di date a ritroso a partire da oggi, formato GG-MM-AAAA"""
    oggi = datetime.now()
    return [(oggi - timedelta(days=i)).strftime("%d-%m-%Y") for i in range(n_giorni)]

@st.cache_data(ttl=3600)
def carica_dati():
    """
    Scarica i dati dallo scraping Sisal per le ultime 14 giornate e restituisce un DataFrame.
    """
    base_url = "https://betting.sisal.it/api/vrol-api/vrol/archivio/getArchivioGareCampionato/1/3/6/"
    giornate = ultime_date()
    
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json"
    }
    
    rows = []

    for giorno in giornate:
        try:
            r = requests.get(base_url + giorno, headers=headers, timeout=10)
            data = r.json()
        except Exception as e:
            st.warning(f"Errore caricando {giorno}: {e}")
            continue

        for giornata_obj in data:
            giornata_num = giornata_obj["giornata"]
            data_evento = giornata_obj.get("dataPrimoEvento", "")[:10]

            risultati_map = giornata_obj.get("risultatoModelloScommessaCampionatoMap", {})
            for modelli in risultati_map.values():
                for modello in modelli:
                    eventi = modello.get("eventiScommessaList", [])
                    for evento in eventi:
                        match = evento["descrizioneAvventimento"]
                        home, away = match.split(" - ")
                        orario = evento["dataOra"]
                        risultati = evento.get("risultatoScommessaUfficialeList", [])
                        for res in risultati:
                            rows.append({
                                "data": data_evento,
                                "giornata": giornata_num,
                                "orario": orario,
                                "match": match,
                                "home": home,
                                "away": away,
                                "descrizioneScommessa": res["descrizioneScommessa"],
                                "esito": res["risultato"],
                                "quota": float(res["quoteComb"]) / 100
                            })

    df = pd.DataFrame(rows)
    if not df.empty:
        df["data"] = pd.to_datetime(df["data"])
        df["h2h_key"] = df.apply(lambda r: "-".join(sorted([r["home"], r["away"]])), axis=1)
    return df

# ===========================
# Streamlit App
# ===========================

st.set_page_config(page_title="Archivio Gare Sisal", layout="wide")
st.title("Archivio Gare - Sisal Virtual Race")

# --- Carico dati con cache ---
df = carica_dati()

if df.empty:
    st.warning("Nessun dato disponibile al momento.")
else:
    # --- Filtri ---
    squadre = sorted(list(set(df["home"].unique()) | set(df["away"].unique())))
    squadra = st.selectbox("Seleziona squadra", squadre)
    
    tipo_scommessa = st.multiselect(
        "Tipo di scommessa",
        sorted(df["descrizioneScommessa"].unique()),
        default=["Esito Finale 1X2"]
    )

    # --- Filtraggio ---
    df_filtrato = df[
        ((df["home"] == squadra) | (df["away"] == squadra)) &
        (df["descrizioneScommessa"].isin(tipo_scommessa))
    ].sort_values(["data", "orario"])

    st.write(f"Mostrando {len(df_filtrato)} eventi per {squadra}")
    
    # --- Visualizzazione ---
    st.dataframe(df_filtrato[[
        "data", "match", "home", "away", "descrizioneScommessa", "esito", "quota"
    ]])

    # --- Opzionale: Statistiche ---
    if st.checkbox("Mostra statistiche base"):
        stats = df_filtrato.groupby(["descrizioneScommessa", "esito"])["quota"].agg(["count", "mean"])
        st.write(stats)
