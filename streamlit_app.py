import streamlit as st
import ephem
import pandas as pd
from datetime import datetime, timedelta, timezone
import requests
import matplotlib.pyplot as plt

# JSTへのタイムゾーン設定
JST = timezone(timedelta(hours=9))

# カスタムCSSで幅を1.5倍に調整
st.markdown(
    """
    <style>
    .main .block-container {
        max-width: 1500px;
        padding-left: 5rem;
        padding-right: 5rem;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# TLEデータをCelesTrakから取得する関数
def get_tle_from_celestrak(spacecraft):
    url = "https://celestrak.org/NORAD/elements/stations.txt"
    response = requests.get(url)
    tle_lines = response.text.splitlines()
    
    # スペースクラフト名に部分一致するTLEを取得
    for i in range(0, len(tle_lines), 3):
        if spacecraft.lower() in tle_lines[i].lower():
            return tle_lines[i+1], tle_lines[i+2]
    raise ValueError(f"TLE for {spacecraft} not found.")

# TLEファイルをアップロードする関数
def get_tle_from_file(uploaded_file):
    tle_data = uploaded_file.read().decode("utf-8")
    tle_lines = tle_data.splitlines()

    # ファイルが3行以上であることを確認（1行目: 名前、2行目: Line1、3行目: Line2）
    if len(tle_lines) >= 3:
        satellite_name = tle_lines[0]
        line1 = tle_lines[1]
        line2 = tle_lines[2]
        return satellite_name, line1, line2
    else:
        raise ValueError("Invalid TLE file format. The file must contain at least 3 lines (satellite name, line 1, and line 2).")

# 現在の日付を取得
today = datetime.today()
# Start Date = 今日, End Date = Start Dateから1ヶ月後
default_start_date = today
default_end_date = today + timedelta(days=30)

# 初期状態の設定
if 'tle_source' not in st.session_state:
    st.session_state.tle_source = "CelesTrakから取得"  # 初期値の設定

# Streamlitアプリケーション
st.title("Satellite Pass Prediction")

# 上段（TLE取得、地上局設定、日付設定）
upper_col1, upper_col2, upper_col3 = st.columns([1, 1, 1])

# 下段（Pass結果とAz-Elプロット）
lower_col1, lower_col2 = st.columns([2, 1])

# 左上段：TLE取得セクション
with upper_col1:
    st.subheader("TLEデータ取得")
    st.session_state.tle_source = st.radio("TLE取得方法を選択してください", 
                                           ("CelesTrakから取得", "TLEファイルをアップロード"),
                                           index=0 if st.session_state.tle_source == "CelesTrakから取得" else 1)

    # TLEデータの初期化
    tle_name, tle_line1, tle_line2 = None, None, None

    # CelesTrakから取得を選んだ場合
    if st.session_state.tle_source == "CelesTrakから取得":
        spacecraft = st.text_input("衛星名（例: ISS）", "ISS")
        if st.button("TLEを取得"):
            try:
                tle_line1, tle_line2 = get_tle_from_celestrak(spacecraft)
                tle_name = spacecraft  # TLEの名前をセット
                st.session_state.tle_name = tle_name
                st.session_state.tle_line1 = tle_line1
                st.session_state.tle_line2 = tle_line2
                st.success(f"TLE取得成功:\n{tle_line1}\n{tle_line2}")
            except Exception as e:
                st.error(f"エラーが発生しました: {e}")

    # TLEファイルをアップロードを選んだ場合
    elif st.session_state.tle_source == "TLEファイルをアップロード":
        uploaded_file = st.file_uploader("TLEファイルをアップロードしてください", type="txt")
        if uploaded_file is not None:
            try:
                tle_name, tle_line1, tle_line2 = get_tle_from_file(uploaded_file)
                st.session_state.tle_name = tle_name
                st.session_state.tle_line1 = tle_line1
                st.session_state.tle_line2 = tle_line2
                st.success(f"TLEファイル読み込み成功:\n{tle_name}\n{tle_line1}\n{tle_line2}")
            except Exception as e:
                st.error(f"エラーが発生しました: {e}")

# 中央上段：地上局の設定セクション
with upper_col2:
    st.subheader("地上局の設定")
    latitude = st.text_input("Latitude (緯度)", "35.9864")
    longitude = st.text_input("Longitude (経度)", "139.3739")
    elevation = st.number_input("Altitude (高度, m)", value=0)

# 右上段：日付の設定セクション
with upper_col3:
    st.subheader("日付の設定")
    start_date = st.date_input("Start Date (開始日)", value=st.session_state.get('start_date', default_start_date))
    end_date = st.date_input("End Date (終了日)", value=st.session_state.get('end_date', default_end_date))

    # ユーザーの入力を保存
    st.session_state['start_date'] = start_date
    st.session_state['end_date'] = end_date

    # Pass計算ボタン
    if st.button("Calculate Passes"):
        # 衛星TLEデータが存在しない場合のエラーチェック
        if "tle_name" not in st.session_state or "tle_line1" not in st.session_state or "tle_line2" not in st.session_state:
            st.error("TLEデータが設定されていません。TLEデータを取得またはアップロードしてください。")
        else:
            observer = ephem.Observer()
            observer.lat = latitude
            observer.lon = longitude
            observer.elevation = elevation
            observer.date = ephem.Date(start_date)  # Start Dateを設定

            try:
                # 衛星データを設定
                satellite = ephem.readtle(st.session_state.tle_name, st.session_state.tle_line1, st.session_state.tle_line2)

                # 開始日と終了日を設定
                start_datetime = datetime.combine(start_date, datetime.min.time())  # 開始日を含む
                end_datetime = datetime.combine(end_date, datetime.max.time())  # 終了日を含む

                # AOS、LOS、最大仰角、方位角-仰角データのリストを初期化
                data = []
                current_time = start_datetime

                # 指定された期間で衛星のパスを計算
                while current_time <= end_datetime:
                    # 次のパスを探す
                    next_pass = observer.next_pass(satellite)

                    # AOS, LOS, 最大仰角などの情報を取得
                    aos_time = ephem.localtime(next_pass[0])
                    los_time = ephem.localtime(next_pass[4])
                    max_elevation = next_pass[3] * (180.0 / ephem.pi)  # 最大仰角を度に変換

                    # 方位角-仰角データを収集
                    az_el_data = []
                    observer.date = next_pass[0]  # AOS時刻を設定
                    while observer.date < next_pass[4]:  # LOSまで方位角と仰角を取得
                        satellite.compute(observer)
                        az_el_data.append((satellite.az, satellite.alt))
                        observer.date += ephem.minute  # 1分ごとに計算

                    # パスが期間内にあるか確認
                    if aos_time > end_datetime:
                        break  # 計算を終了

                    # パス情報をリストに追加
                    data.append({
                        "Day": aos_time.strftime('%Y-%m-%d'),
                        "AOS(JST)": aos_time.astimezone(JST).strftime('%H:%M:%S'),
                        "LOS(JST)": los_time.astimezone(JST).strftime('%H:%M:%S'),
                        "MEL": max_elevation,
                        "T-MEL(JST)": ephem.localtime(next_pass[3]).astimezone(JST).strftime('%H:%M:%S'),
                        "VTIME(s)": (los_time - aos_time).total_seconds(),
                        "SAT": st.session_state.tle_name,
                        "Az-El Data": az_el_data  # 方位角-仰角データ
                    })

                    # current_timeを次のLOSの後に設定して次のパスを探す
                    current_time = los_time + timedelta(seconds=10)
                    observer.date = current_time

                # データをDataFrameに変換して表示
                df = pd.DataFrame(data)
                st.session_state['pass_data'] = df  # セッションステートに保存

            except Exception as e:
                st.error(f"エラーが発生しました: {e}")

# 左下段と中央：pass計算結果の表示セクション
with lower_col1:
    if 'pass_data' in st.session_state:
        st.subheader("Pass計算結果")
        st.write(st.session_state['pass_data'])

# 右下段：Az-Elプロットの表示セクション
with lower_col2:
    if 'pass_data' in st.session_state:
        st.subheader("Az-Elプロット")
        selected_pass = st.selectbox("Select a pass to plot", st.session_state['pass_data'].index)
        if selected_pass is not None:
            az_el_data = st.session_state['pass_data'].iloc[selected_pass]["Az-El Data"]
            azimuths = [x[0] for x in az_el_data]
            elevations = [(x[1] * (180.0 / ephem.pi)) for x in az_el_data]  # 仰角を0-90度に変換

            # 方位角-仰角プロットを作成
            fig, ax = plt.subplots(subplot_kw={'projection': 'polar'}, figsize=(6,6))  # グラフの大きさを調整
            ax.plot(azimuths, elevations)

            # 仰角のスケールを適切に設定
            ax.set_ylim(90, 0)  # 天頂が90度、地平線が0度
            
            # 方位角の設定：0度が北（上）、180度が南（下）
            ax.set_theta_zero_location('N')
            ax.set_theta_direction(-1)  # 反時計回りに設定

            # タイトルとプロットを表示
            ax.set_title(f"Azimuth-Elevation Plot for Satellite Pass")
            st.pyplot(fig)
