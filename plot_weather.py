import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from google.oauth2 import service_account
import pandas as pd
import plotly.express as px
import datetime as dt

# --- Подключение ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# Читаем ключ из Secrets
creds_dict = dict(st.secrets["gcp_service_account"])
creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=scope)
client = gspread.authorize(creds)

sheet = client.open_by_key("1gd_j4lDsvdSS-fcsGMjwz3mvBNeKc1S6HYdCdTSKwAA").sheet1
data = sheet.get_all_values()

# --- DataFrame ---
df = pd.DataFrame(data[1:], columns=[
    "Время", "CO2", "Temp_SCD", "Hum_SCD", "Lux",
    "Temp_BME", "Pressure", "Hum_BME", "Gas",
    "PM1.0", "PM2.5", "PM10"
])



# --- Очистка чисел ---
def clean_number(x):
    if isinstance(x, str):
        x = x.strip().replace(',', '.')
        if '.' not in x and x.isdigit() and len(x) > 2:
            x = x[:-2] + '.' + x[-2:]
    try:
        return float(x)
    except:
        return None



for col in df.columns[1:]:
    df[col] = df[col].apply(clean_number)


# --- Удаление невалидных нулей (артефакты отвала датчиков) ---
# CO2: реальный минимум ~400 ppm, 0 = отвал
df.loc[df['CO2'] <= 10, 'CO2'] = pd.NA

# Pressure (BME680): реально ~300–1100 гПа, 0 = отвал
df.loc[df['Pressure'] <= 100, 'Pressure'] = pd.NA

# Gas (BME680): сопротивление не может быть 0, 0 = сенсор не прогрет
df.loc[df['Gas'] <= 0, 'Gas'] = pd.NA

# PM: 0 допустим теоретически, но при отвале датчик даёт 0 или 65535 —
# 65535 точно мусор, 0 оставляем (может быть реально чистый воздух)
for c in ['PM1.0', 'PM2.5', 'PM10']:
    df.loc[df[c] >= 65000, c] = pd.NA

# Lux: 0 оставляем — это нормальная темнота
# Temp/Hum: 0 в °C возможен (зимой), 0 % влажности — нет, но
# SCD/BME в 0 обычно означают отвал — мягко обработаем влажность
df.loc[df['Hum_SCD'] <= 0, 'Hum_SCD'] = pd.NA
df.loc[df['Hum_BME'] <= 0, 'Hum_BME'] = pd.NA

# --- Парсинг времени (американский формат!) ---
df['Время'] = pd.to_datetime(df['Время'], format='%m/%d/%Y %H:%M:%S', errors='coerce')



df = df.dropna(subset=['Время'])



# --- Графики ---
# --- Графики ---

st.title("🌍 Экологический мониторинг")

# --- Выбор периода ---
min_date = df['Время'].min().date()
max_date = df['Время'].max().date()

col1, col2 = st.columns(2)
with col1:
    date_from = st.date_input("С даты", value=min_date,
                              min_value=min_date, max_value=max_date)
with col2:
    date_to = st.date_input("По дату", value=max_date,
                            min_value=min_date, max_value=max_date)

# фильтр по датам (включая весь последний день)
mask = (df['Время'] >= pd.Timestamp(date_from)) & \
       (df['Время'] <  pd.Timestamp(date_to) + pd.Timedelta(days=1))
df_view = df.loc[mask].copy()

if df_view.empty:
    st.warning("В выбранном периоде нет данных.")
    st.stop()

# helper: добавить пороговые линии
def add_thresholds(fig, thresholds, unit=""):
    """
    thresholds: список (y, label, color)
    """
    for y, label, color in thresholds:
        fig.add_hline(
            y=y,
            line_dash="dash",
            line_color=color,
            annotation_text=f"{label} ({y}{unit})",
            annotation_position="top left",
            annotation_font_size=11,
        )
    return fig
# --- вспомогательные функции ---
def with_rangeslider(fig):
    fig.update_xaxes(
        rangeslider_visible=True,
        rangeselector=dict(
            buttons=[
                dict(count=6,  label="6ч",  step="hour",  stepmode="backward"),
                dict(count=1,  label="1д",  step="day",   stepmode="backward"),
                dict(count=7,  label="7д",  step="day",   stepmode="backward"),
                dict(count=1,  label="1м",  step="month", stepmode="backward"),
                dict(step="all", label="всё"),
            ]
        ),
    )
    fig.update_layout(hovermode="x unified",
                      margin=dict(l=10, r=10, t=40, b=10))
    return fig


# ---------- CO2 ----------
fig1 = px.line(df_view, x='Время', y='CO2', title='CO2 (ppm)')
add_thresholds(fig1, [
    (800,  "норма",       "green"),
    (1000, "проветрить",  "orange"),
    (1500, "плохо",       "red"),
], unit=" ppm")
st.plotly_chart(with_rangeslider(fig1), width='stretch')

# ---------- Пыль ----------
fig2 = px.line(df_view, x='Время', y=['PM1.0', 'PM2.5', 'PM10'], title='Пыль (мкг/м³)')
add_thresholds(fig2, [
    (10,  "PM2.5 отлично",   "green"),
    (25,  "PM2.5 хорошо",    "lightgreen"),
    (50,  "PM2.5 умеренно",  "orange"),
    (100, "PM2.5 плохо",     "red"),
], unit=" мкг/м³")
st.plotly_chart(with_rangeslider(fig2), width='stretch')

# ---------- Температура ----------
fig3 = px.line(df_view, x='Время', y=['Temp_SCD', 'Temp_BME'], title='Температура (°C)')
add_thresholds(fig3, [
    (16, "холодно",      "red"),
    (18, "мин. комфорт", "blue"),
    (24, "макс. комфорт","blue"),
    (28, "жарко",        "red"),
], unit=" °C")
st.plotly_chart(with_rangeslider(fig3), width='stretch')

# ---------- Влажность ----------
fig4 = px.line(df_view, x='Время', y=['Hum_SCD', 'Hum_BME'], title='Влажность (%)')
add_thresholds(fig4, [
    (30, "сухо",       "red"),
    (40, "мин. норма", "green"),
    (60, "макс. норма","green"),
    (70, "сыро",       "red"),
], unit=" %")
st.plotly_chart(with_rangeslider(fig4), width='stretch')

# ---------- Освещённость ----------
fig5 = px.line(df_view, x='Время', y='Lux', title='Освещённость (лк)')
add_thresholds(fig5, [
    (100,  "тускло",     "orange"),
    (300,  "комфорт",    "green"),
    (1000, "очень ярко", "orange"),
], unit=" лк")
st.plotly_chart(with_rangeslider(fig5), width='stretch')

# ---------- Газ (BME680) ----------
fig6 = px.line(df_view, x='Время', y='Gas',
               title='Газ BME680 (сопротивление, кОм — выше = чище)')

# медиана по выбранному периоду, а не по всему df
gas_median = df_view['Gas'].median(skipna=True)
if pd.notna(gas_median) and gas_median > 0:
    fig6.add_hline(
        y=gas_median,
        line_dash="dot", line_color="gray",
        annotation_text=f"медиана ≈ {gas_median:.1f} кОм",
        annotation_position="top left",
    )
    for frac, label, color in [
        (0.5,  "VOC ↑ заметно (½ медианы)", "orange"),
        (0.25, "VOC ↑↑ сильно (¼ медианы)", "red"),
    ]:
        y = gas_median * frac
        fig6.add_hline(
            y=y, line_dash="dash", line_color=color,
            annotation_text=f"{label}: {y:.1f}",
            annotation_position="bottom left",
            annotation_font_size=11,
        )
st.plotly_chart(with_rangeslider(fig6), width='stretch')

# ---------- Давление BME680 ----------
fig7 = px.line(df_view, x='Время', y='Pressure',
               title='Атмосферное давление (гПа, BME680)')
add_thresholds(fig7, [
    (1000, "низкое",  "orange"),
    (1025, "высокое", "orange"),
], unit=" гПа")
st.plotly_chart(with_rangeslider(fig7), width='stretch')

# ---------- Расхождение датчиков (диагностика) ----------
df_diag = df_view.dropna(subset=['Temp_SCD', 'Temp_BME', 'Hum_SCD', 'Hum_BME']).copy()
df_diag['ΔTemp'] = df_diag['Temp_SCD'] - df_diag['Temp_BME']
df_diag['ΔHum']  = df_diag['Hum_SCD']  - df_diag['Hum_BME']

fig8 = px.line(df_diag, x='Время', y=['ΔTemp', 'ΔHum'],
               title='Расхождение SCD ↔ BME (ΔTemp °C / ΔHum %)')
add_thresholds(fig8, [
    ( 2, "Temp: подозрительно", "red"),
    (-2, "Temp: подозрительно", "red"),
    ( 10, "Hum: подозрительно", "orange"),
    (-10, "Hum: подозрительно", "orange"),
], unit="")
st.plotly_chart(with_rangeslider(fig8), width='stretch')

st.subheader("Последние 10 записей (выбранный период)")
st.dataframe(df_view.tail(10), width='stretch')
