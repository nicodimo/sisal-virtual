import requests
import pandas as pd
import streamlit as st
import plotly.express as px
from datetime import datetime

# =========================
# CONFIG
# =========================

BASE_URL = "https://betting.sisal.it/api/vrol-api/vrol/archivio/getArchivioGareCampionato/"
CAMPIONATO_ID = 1
PROVIDER_ID = 3
TIPO_GARA = 6
MODELLO_TARGET = "Goal/No Goal"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
}

st.set_page_config(
    page_title="GG / NG Analytics",
    layout="wide"
)

# =========================
# DATA DOWNLOAD
# =========================

@st.cache_data
def scarica_dati_oggi(_refresh):
    oggi = datetime.now().strftime("%d-%m-%Y")
    url = f"{BASE_URL}{CAMPIONATO_ID}/{PROVIDER_ID}/{TIPO_GARA}/{oggi}"
    r = requests.get(url, headers=HEADERS)
    r.raise_for_status()
    return r.json()

# =========================
# DATASET CREATION
# =========================

def crea_dataset(tutti_dati):
    rows = []

    for g in tutti_dati:
        giornata = g.get("giornata")
        timestamp = pd.to_datetime(g.get("dataPrimoEvento"))

        modelli = g.get("risultatoModelloScommessaCampionatoMap", {}).get(str(PROVIDER_ID), [])

        for m in modelli:
            if m.get("modelloScommessa") != MODELLO_TARGET:
                continue

            for e in m.get("eventiScommessaList", []):
                casa, trasferta = e.get("descrizioneAvventimento").split(" - ")

                for r in e.get("risultatoScommessaUfficialeList", []):
                    rows.append({
                        "giornata": giornata,
                        "timestamp": timestamp,
                        "casa": casa.strip(),
                        "trasferta": trasferta.strip(),
                        "esito": r.get("risultato")
                    })

    return pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)

# =========================
# CAMPIONATI
# =========================

def ricostruisci_campionati(df):
    df = df.copy()
    df["campionato_id"] = None

    df_rev = df[::-1].reset_index()

    # attuale
    viste = set()
    for i, r in df_rev.iterrows():
        viste.add(r["giornata"])
        df.at[r["index"], "campionato_id"] = 0
        if 1 in viste:
            break

    # passato
    viste = set()
    for j in range(i + 1, len(df_rev)):
        viste.add(df_rev.at[j, "giornata"])
        df.at[df_rev.at[j, "index"], "campionato_id"] = 1
        if len(viste) == 22:
            break

    return df

# =========================
# UI HEADER
# =========================

st.title("⚽ GG / NG Analytics")

# if st.sidebar.button("🔄 Ricarica dati"):
#     st.cache_data.clear()

with st.spinner("⏳ Caricamento dati..."):
    df = ricostruisci_campionati(crea_dataset(scarica_dati_oggi("x")))

# =========================
# DATA SPLIT
# =========================

df_att = df[df.campionato_id == 0]
df_pas = df[df.campionato_id == 1]

# =========================
# RIASSUNTO RAPIDO
# =========================

def summary(df):
    tot = len(df)
    gg = (df.esito == "Goal").sum()
    return tot, gg, round(gg / tot * 100, 2)

c1, c2 = st.columns(2)
for col, titolo, d in [
    (c1, "🟢 Campionato attuale", df_att),
    (c2, "🔵 Campionato passato", df_pas)
]:
    tot, gg, rate = summary(d)
    col.metric(titolo, f"{rate} % GG", f"{gg}/{tot}")

# =========================
# ANDAMENTO GIORNATE
# =========================

def andamento(df):
    g = (
        df.groupby("giornata")["esito"]
        .value_counts()
        .unstack(fill_value=0)
        .reset_index()
    )

    # FORZO LE COLONNE
    if "Goal" not in g.columns:
        g["Goal"] = 0
    if "No Goal" not in g.columns:
        g["No Goal"] = 0

    g["GG_rate"] = g["Goal"] / (g["Goal"] + g["No Goal"])

    return g.sort_values("giornata")

st.subheader("📈 Andamento giornate")

fig1 = px.line(
    andamento(df_att),
    x="giornata",
    y="GG_rate",
    markers=True,
    title="Campionato attuale – GG rate"
)
fig1.update_yaxes(range=[0, 1])
st.plotly_chart(fig1, use_container_width=True)

fig2 = px.line(
    andamento(df_pas),
    x="giornata",
    y="GG_rate",
    markers=True,
    title="Campionato passato – GG rate (22 giornate)"
)
fig2.update_yaxes(range=[0, 1])
st.plotly_chart(fig2, use_container_width=True)

# =========================
# GIORNATE ANOMALE
# =========================

st.subheader("🚨 Giornate anomale")

soglia = st.slider("Soglia anomalia (%)", 10, 40, 20)

att = andamento(df_att)
media = att.GG_rate.mean()

att["anomalia"] = att.GG_rate.apply(
    lambda x: "⬆️ Alta" if x > media * (1 + soglia/100)
    else "⬇️ Bassa" if x < media * (1 - soglia/100)
    else ""
)

st.dataframe(
    att[["giornata", "GG_rate", "anomalia"]],
    use_container_width=True
)

# =========================
# STATISTICHE SQUADRE
# =========================

st.subheader("👕 Statistiche per squadra")

df_team = pd.concat([
    df.assign(squadra=df.casa),
    df.assign(squadra=df.trasferta)
])

camp_sel = st.selectbox(
    "Campionato",
    {"Attuale": 0, "Passato": 1}
)

teams = sorted(df_team[df_team.campionato_id == camp_sel].squadra.unique())
team_sel = st.selectbox("Squadra", teams)

team_df = df_team[
    (df_team.squadra == team_sel) &
    (df_team.campionato_id == camp_sel)
]

tot = len(team_df)
gg = (team_df.esito == "Goal").sum()

st.metric(
    f"{team_sel}",
    f"{round(gg/tot*100,2)} % GG",
    f"{gg}/{tot} partite"
)

team_and = andamento(team_df)

fig_team = px.bar(
    team_and,
    x="giornata",
    y="GG_rate",
    title=f"{team_sel} – GG rate per giornata"
)
fig_team.update_yaxes(range=[0, 1])
st.plotly_chart(fig_team, use_container_width=True)

# =========================
# RAW DATA
# =========================

with st.expander("📄 Dataset completo"):
    st.dataframe(df, use_container_width=True)
