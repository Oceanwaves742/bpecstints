# -*- coding: utf-8 -*-
"""
Created on Tue Jul  1 09:18:38 2025

@author: z00534vd
"""

import streamlit as st
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import pandas as pd
import time
import tempfile
import matplotlib.pyplot as plt
from streamlit_autorefresh import st_autorefresh
import datetime
from selenium.webdriver.firefox.options import Options

def get_headless_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Firefox(options=options)
    return driver

def parse_lap_time(t):
    if pd.isna(t):
        return None
    try:
        parts = t.split(':')
        if len(parts) == 2:
            minutes = int(parts[0])
            seconds = float(parts[1])
            return 60 * minutes + seconds
        else:
            return float(t)
    except:
        return None

@st.cache_data(show_spinner=True)
def scrape_lap_data(url):
    driver = get_headless_driver()
    try:
        driver.get(url)
        time.sleep(2)
        table = driver.find_element(By.CLASS_NAME, "session-competitor-details-laps")
        rows = table.find_elements(By.TAG_NAME, "tr")
        data = []
        for row in rows:
            cols = row.find_elements(By.TAG_NAME, "td")
            row_data = [col.text.strip() for col in cols]
            if len(row_data) >= 4:
                data.append(row_data)
    finally:
        driver.quit()

    lap_data = pd.DataFrame(data, columns=["Lap Number", "Pos", "Pos Change", "Lap Time", "Gap", "Interval"])
    lap_data["Lap Time (s)"] = lap_data["Lap Time"].apply(parse_lap_time)
    lap_data["Lap Number"] = pd.to_numeric(lap_data["Lap Number"], errors='coerce')
    lap_data["Pos"] = pd.to_numeric(lap_data["Pos"], errors='coerce')
    lap_data["Gap"] = lap_data["Gap"].apply(parse_lap_time)
    lap_data["Interval"] = lap_data["Interval"].apply(parse_lap_time)
    lap_data["Lap Time"] = lap_data["Lap Time (s)"]
    lap_data = lap_data.dropna(subset=["Lap Number", "Lap Time"]).reset_index(drop=True)
    lap_data = lap_data.sort_values(by="Lap Number").reset_index(drop=True)
    return lap_data

@st.cache_data(show_spinner=True)
def analyze_stints(lap_data, pit_threshold, exclude_laps):
    filtered_lap_data = lap_data[~lap_data["Lap Number"].isin(exclude_laps)]
    is_pit = filtered_lap_data["Lap Time"] > pit_threshold
    pit_indices = filtered_lap_data[is_pit].index.tolist()

    stints = []
    stint_start_idx = 0
    stint_number = 1

    for pit_idx in pit_indices:
        stint_laps = filtered_lap_data.iloc[stint_start_idx:pit_idx]

        if not stint_laps.empty:
            start_lap = int(stint_laps["Lap Number"].iloc[0])
            end_lap = int(stint_laps["Lap Number"].iloc[-1])
            stint_len = len(stint_laps)
            stint_time = stint_laps["Lap Time"].sum() / 60.0
            best_lap = stint_laps["Lap Time"].min()
            median_lap = stint_laps["Lap Time"].median()
            pit_lap_time = filtered_lap_data.loc[pit_idx, "Lap Time"]

            stints.append({
                "Stint Number": stint_number,
                "Start Lap": start_lap,
                "End Lap": end_lap,
                "Stint Length (laps)": stint_len,
                "Stint Time (mins)": round(stint_time, 2),
                "Best Lap (s)": round(best_lap, 3),
                "Median Lap (s)": round(median_lap, 3),
                "Pitstop Lap Time (s)": round(pit_lap_time, 3)
            })
            stint_number += 1

        stint_start_idx = pit_idx + 1

    # Final stint
    if stint_start_idx < len(filtered_lap_data):
        stint_laps = filtered_lap_data.iloc[stint_start_idx:]
        if not stint_laps.empty:
            start_lap = int(stint_laps["Lap Number"].iloc[0])
            end_lap = int(stint_laps["Lap Number"].iloc[-1])
            stint_len = len(stint_laps)
            stint_time = stint_laps["Lap Time"].sum() / 60.0
            best_lap = stint_laps["Lap Time"].min()
            median_lap = stint_laps["Lap Time"].median()

            stints.append({
                "Stint Number": stint_number,
                "Start Lap": start_lap,
                "End Lap": end_lap,
                "Stint Length (laps)": stint_len,
                "Stint Time (mins)": round(stint_time, 2),
                "Best Lap (s)": round(best_lap, 3),
                "Median Lap (s)": round(median_lap, 3),
                "Pitstop Lap Time (s)": None
            })

    return pd.DataFrame(stints), filtered_lap_data

st.title("OBABLTMTSA (Ocean Bach's amazing BPEC Live Timing Multi-Team Stint Analyser)")

st.markdown("### Paste up to 5 team URLs below (one per line):")
urls_input = st.text_area("Team URLs", height=140)

team_urls = [u.strip() for u in urls_input.splitlines() if u.strip()][:5]

pit_threshold = st.number_input("Pit stop lap time threshold (seconds):", value=80, min_value=10, max_value=300)

if team_urls:
    lap_data_dict = {}
    for idx, url in enumerate(team_urls):
        with st.spinner(f"Fetching data for Team {idx+1}..."):
            try:
                lap_data_dict[url] = scrape_lap_data(url)
            except Exception as e:
                st.error(f"Error scraping URL {url}: {e}")
                lap_data_dict[url] = None

    lap_data_dict = {k:v for k,v in lap_data_dict.items() if v is not None}

    if not lap_data_dict:
        st.warning("No valid lap data scraped.")
    else:
        team_names = {url: f"Team {i+1}" for i, url in enumerate(lap_data_dict.keys())}

        st.subheader("Team Names")
        for url in list(lap_data_dict.keys()):
            new_name = st.text_input(f"Name for {url}", value=team_names[url], key=f"name_{url}")
            team_names[url] = new_name if new_name.strip() else team_names[url]

        exclude_dict = {}

        st.subheader("Exclude laps above threshold (mistakes/pitstops) per team")
        for url, lap_data in lap_data_dict.items():
            st.markdown(f"**{team_names[url]}**")
            laps_above_threshold = lap_data[lap_data["Lap Time"] > pit_threshold]

            exclude_laps = st.multiselect(
                f"Laps to exclude from analysis for {team_names[url]}:",
                options=laps_above_threshold["Lap Number"].tolist(),
                format_func=lambda x, url=url, lap_data=lap_data: f"Lap {int(x)} (Time: {lap_data.loc[lap_data['Lap Number'] == x, 'Lap Time'].values[0]:.3f}s)",
                key=f"exclude_{url}"
            )
            exclude_dict[url] = exclude_laps

        st.subheader("Select team to view stint summary")
        selected_team_url = st.selectbox("Choose a team:", options=list(lap_data_dict.keys()), format_func=lambda x: team_names[x])

        stint_df, filtered_lap_data = analyze_stints(lap_data_dict[selected_team_url], pit_threshold, exclude_dict[selected_team_url])
        st.dataframe(stint_df)

        st.subheader("Compare teams in graph")

        selected_teams_for_plot = st.multiselect("Select teams to plot:", options=list(lap_data_dict.keys()), format_func=lambda x: team_names[x], default=list(lap_data_dict.keys()))
        if selected_teams_for_plot:
            min_lap = 1
            max_lap = max(int(lap_data_dict[url]["Lap Number"].max()) for url in selected_teams_for_plot)

        start_lap = st.number_input("Start Lap Number (absolute range):", min_value=min_lap, max_value=max_lap, value=min_lap)
        use_current_lap_as_xmax = st.checkbox("Set X-axis maximum to current lap", value=False)

        if use_current_lap_as_xmax:
            end_lap = max(int(lap_data_dict[url]["Lap Number"].max()) for url in selected_teams_for_plot)
            st.write(f"X-axis maximum automatically set to current lap: {end_lap}")
        else:
            end_lap = st.number_input("End Lap Number (common range):", min_value=start_lap, max_value=max_lap, value=max_lap)

        plot_vars = {
            "Position": "Pos",
            "Lap Time (s)": "Lap Time",
            "Gap (s)": "Gap",
            "Interval (s)": "Interval"
        }
        var_choice = st.selectbox("Select variable to plot:", options=list(plot_vars.keys()))

        y_min = st.number_input(f"Y-axis minimum ({var_choice}):", value=None, format="%.3f", key="y_min", step=0.1)

        y_max = st.number_input(f"Y-axis maximum ({var_choice}):", value=None, format="%.3f", key="y_max", step=0.1)
        fig, ax = plt.subplots(figsize=(12, 6))
        y_col = plot_vars[var_choice]

        for url in selected_teams_for_plot:
            stint_df, filtered_lap_data = analyze_stints(lap_data_dict[url], pit_threshold, exclude_dict[url])
            plot_data = filtered_lap_data[(filtered_lap_data["Lap Number"] >= start_lap) & (filtered_lap_data["Lap Number"] <= end_lap)]
        
            ax.plot(
                plot_data["Lap Number"],
                plot_data[y_col],
                marker='o',
                label=team_names[url]
            )

        ax.set_xlabel("Lap Number")
        ax.set_ylabel(var_choice)
        ax.set_title(f"{var_choice} over Laps")
        ax.legend()
        if y_min is not None and y_max is not None and y_min < y_max:
            ax.set_ylim(y_min, y_max)
        ax.grid(True)
        st.pyplot(fig)

    st.markdown("---")

        # Set refresh interval (30 seconds)
    refresh_interval_sec = 30
    st_autorefresh(interval=refresh_interval_sec * 1000, key="datarefresh")

        # Show last refresh time
    last_refresh = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.markdown(f"---\n:hourglass_flowing_sand: Data refreshes every {refresh_interval_sec}s  \n**Last refreshed:** {last_refresh} MS URBN Blue are the best")

else:
    st.info("Please enter at least one team URL to begin.")