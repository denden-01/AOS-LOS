import streamlit as st
import ephem
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
import requests
import matplotlib.pyplot as plt

# JSTへのタイムゾーン設定
JST = timezone(timedelta(hours=9))

# TLEデータをNASAのサイトから取得
ef get_tle(spacecraft):
    url = "https://celestrak.org/NORAD/elements/stations.txt"
    response = requests.get(url)
    tle_lines = response.text.splitlines()
    
    # スペースクラフト名に部分一致するTLEを取得
    for i in range(0, len(tle_lines), 3):
        if spacecraft.lower() in tle_lines[i].lower():
            return tle_lines[i+1], tle_lines[i+2]
    raise ValueError(f"TLE for {spacecraft} not found.")

# Streamlitアプリケーション
st.title("Satellite Pass Prediction")

# ユーザー入力フォーム
latitude = st.text_input("Latitude (緯度)", "35.9864")
longitude = st.text_input("Longitude (経度)", "139.3739")
elevation = st.number_input("Altitude (高度, m)", value=0)
start_date = st.date_input("Start Date (開始日)", value=datetime(2024, 11, 20))
end_date = st.date_input("End Date (終了日)", value=datetime(2025, 1, 20))
spacecraft = st.text_input("Satellite (衛星名)", "ISS")

# 計算ボタン
if st.button("Calculate Passes") or 'pass_data' not in st.session_state:
    # 地上局を設定
    observer = ephem.Observer()
    observer.lat = latitude
    observer.lon = longitude
    observer.elevation = elevation

    # TLEデータを取得
    try:
        line1, line2 = get_tle(spacecraft)
        satellite = ephem.readtle(spacecraft, line1, line2)
    except ValueError as e:
        st.error(e)
        st.stop()

    # 開始日と終了日を設定
    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(end_date, datetime.min.time())

    # AOS、LOS、最大仰角のリストを初期化
    data = []
    current_time = start_datetime

    # 指定された期間で衛星のパスを計算
    while current_time < end_datetime:
        observer.date = current_time
        satellite.compute(observer)
        
        # 1日あたりのパスを全て記録するためのループ
        while True:
            aos_list = []
            los_list = []
            max_elevation_list = []
            azimuth_elevation_data = []  # 方位角と仰角のデータを保存

            # AOS（信号取得）を探す
            observer.date = current_time
            satellite.compute(observer)
            aos_time = observer.date.datetime()

            # 仰角が1度以上のタイミングを探す
            while satellite.alt < 1 * ephem.degree:
                current_time += timedelta(seconds=10)
                observer.date = current_time
                satellite.compute(observer)
                aos_time = observer.date.datetime()

            aos_list.append(aos_time)
            
            # LOS（信号喪失）を探す
            while satellite.alt > 1 * ephem.degree:
                max_elevation_list.append((observer.date.datetime(), satellite.alt))
                azimuth_elevation_data.append((satellite.az, satellite.alt))  # 方位角と仰角を保存
                current_time += timedelta(seconds=10)
                observer.date = current_time
                satellite.compute(observer)
                los_time = observer.date.datetime()

            los_list.append(los_time)

            # 仰角の最大値を計算
            if max_elevation_list:
                max_elevation_time, max_elevation = max(max_elevation_list, key=lambda x: x[1])
            else:
                max_elevation_time, max_elevation = None, None

            # AOSとLOSのデータが揃ったら記録
            if aos_list and los_list:
                visible_time = (los_list[0] - aos_list[0]).total_seconds()
                data.append({
                    "Day": aos_list[0].strftime('%Y-%m-%d'),
                    "AOS(JST)": aos_list[0].astimezone(JST).strftime('%H:%M:%S'),
                    "LOS(JST)": los_list[0].astimezone(JST).strftime('%H:%M:%S'),
                    "MEL": max_elevation * (180.0 / ephem.pi),  # 最大仰角を度に変換
                    "T-MEL(JST)": max_elevation_time.astimezone(JST).strftime('%H:%M:%S') if max_elevation_time else None,
                    "VTIME(s)": visible_time,
                    "SAT": spacecraft,
                    "Az-El Data": azimuth_elevation_data  # 方位角-仰角データ
                })

            # その日の最後のパスに到達した場合、次の日へ
            if observer.date.datetime().date() != aos_list[0].date():
                break
        
        # 翌日に進む
        current_time = datetime.combine(current_time.date() + timedelta(days=1), datetime.min.time())

    # データをDataFrameに変換して表示
    df = pd.DataFrame(data)
    st.session_state['pass_data'] = df  # セッションステートに保存

# セッションステートからデータを取得して表示
if 'pass_data' in st.session_state:
    df = st.session_state['pass_data']
    st.write(df)

    # パスを選択して方位角-仰角プロットを表示
    selected_pass = st.selectbox("Select a pass to plot", df.index)
    if selected_pass is not None:
        az_el_data = df.iloc[selected_pass]["Az-El Data"]
        azimuths = [x[0] for x in az_el_data]
        elevations = [(x[1] * (180.0 / ephem.pi)) for x in az_el_data]  # 仰角を度に変換

        # 方位角-仰角プロットを作成
        fig, ax = plt.subplots(subplot_kw={'projection': 'polar'})
        ax.plot(azimuths, elevations)

        # 仰角のスケール表示を逆に設定（天頂が90度、地平線が0度になるように表示）
        ax.set_ylim(0, 90)  
        ax.set_yticks([0, 30, 60, 90])  # 仰角のラベルをカスタマイズ
        ax.set_yticklabels(['90°', '60°', '30°', '0°'])  # ラベルを逆に設定

        # 方位角の設定：0度が北（上）、180度が南（下）
        ax.set_theta_zero_location('N')
        ax.set_theta_direction(-1)  # 反時計回りに設定

        # タイトルとプロットを表示
        ax.set_title(f"Azimuth-Elevation Plot for {spacecraft} Pass")
        st.pyplot(fig)
