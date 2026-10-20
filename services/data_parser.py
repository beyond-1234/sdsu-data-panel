import os
import pandas as pd
import numpy as np

def generate_sample_clm_timeseries(filepath: str, year: int = 2021, site: str = 'Global-Terrestrial'):
    """
    Generates synthetic daily time-series CSV for demonstration when raw files are not uploaded:
    DOY, Soil_Temp_10cm, Soil_Moisture_10cm, FBC, BBC, HR, CH4_Flux, GPP
    """
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    days = 365
    doy = np.arange(1, days + 1)
    
    temp_seasonal = 10.0 * np.sin(2 * np.pi * (doy - 105) / 365) + 2.0 + np.random.normal(0, 1.2, days)
    moisture = 0.35 + 0.15 * np.sin(2 * np.pi * (doy - 80) / 365) + np.random.normal(0, 0.03, days)
    moisture = np.clip(moisture, 0.1, 0.8)
    
    fbc = 18.0 + 8.0 * np.sin(2 * np.pi * (doy - 120) / 365) + np.random.normal(0, 0.8, days)
    bbc = 32.0 + 14.0 * np.sin(2 * np.pi * (doy - 110) / 365) + np.random.normal(0, 1.1, days)
    fbc = np.clip(fbc, 5.0, 45.0)
    bbc = np.clip(bbc, 10.0, 70.0)
    
    hr = 0.5 + 2.8 * np.exp(0.08 * temp_seasonal) * (bbc / 40.0) * moisture + np.random.normal(0, 0.15, days)
    hr = np.clip(hr, 0.05, 12.0)
    
    ch4 = 5.0 + 25.0 * np.exp(0.07 * temp_seasonal) * (moisture ** 2) + np.random.normal(0, 1.8, days)
    ch4 = np.clip(ch4, 0.0, 85.0)

    gpp = np.maximum(0, 8.5 * np.sin(np.pi * (doy - 120) / 120)) + np.random.normal(0, 0.3, days)
    gpp = np.where((doy < 120) | (doy > 240), 0.0, gpp)

    df = pd.DataFrame({
        'DOY': doy,
        'Soil_Temp_10cm': np.round(temp_seasonal, 2),
        'Soil_Moisture_10cm': np.round(moisture, 3),
        'FBC': np.round(fbc, 2),
        'BBC': np.round(bbc, 2),
        'HR': np.round(hr, 3),
        'CH4_Flux': np.round(ch4, 2),
        'GPP': np.round(gpp, 2)
    })
    df.to_csv(filepath, index=False)
    return filepath

def parse_dataset_timeseries(filepath: str):
    """
    Reads CSV and returns dictionary for ECharts and data table snapshot.
    Supports utf-8 and latin1 encodings.
    """
    if not os.path.exists(filepath):
        return None
    try:
        try:
            df = pd.read_csv(filepath, encoding='utf-8')
        except UnicodeDecodeError:
            df = pd.read_csv(filepath, encoding='latin1')
    except Exception:
        return None

    # Filter out metadata type description row if present
    if 'Country' in df.columns and len(df) > 1 and df.iloc[0]['Country'] == 'Character':
        df = df.iloc[1:].copy()

    columns = list(df.columns)
    records = df.head(50).to_dict(orient='records')

    # Extract time series columns if present
    doy = df['DOY'].tolist() if 'DOY' in df.columns else list(range(1, min(len(df) + 1, 366)))
    hr = df['HR'].tolist() if 'HR' in df.columns else []
    ch4 = df['CH4_Flux'].tolist() if 'CH4_Flux' in df.columns else []
    soil_temp = df['Soil_Temp_10cm'].tolist() if 'Soil_Temp_10cm' in df.columns else []
    soil_moisture = df['Soil_Moisture_10cm'].tolist() if 'Soil_Moisture_10cm' in df.columns else []
    fbc = df['FBC'].tolist() if 'FBC' in df.columns else []
    bbc = df['BBC'].tolist() if 'BBC' in df.columns else []

    # Map microbial biomass columns if spatial table
    if not hr and 'Soil_microbial_biomass_carbon' in df.columns:
        mbc_clean = pd.to_numeric(df['Soil_microbial_biomass_carbon'], errors='coerce').dropna().head(100).tolist()
        mbn_clean = pd.to_numeric(df['Soil_microbial_biomass_nitrogen'], errors='coerce').dropna().head(100).tolist() if 'Soil_microbial_biomass_nitrogen' in df.columns else []
        hr = mbc_clean
        ch4 = mbn_clean
        doy = list(range(1, len(mbc_clean) + 1))

    return {
        'columns': columns,
        'records': records,
        'doy': doy,
        'hr': hr,
        'ch4': ch4,
        'soil_temp': soil_temp,
        'soil_moisture': soil_moisture,
        'fbc': fbc,
        'bbc': bbc
    }

def get_depth_profile_data():
    """
    Soil vertical depth profile gradient data (0 ~ 1.5m, 10 layers).
    """
    depths = [0.02, 0.05, 0.10, 0.20, 0.35, 0.55, 0.80, 1.10, 1.35, 1.50]
    depth_labels = [f"{d*100:.0f}cm" for d in depths]
    
    fbc_profile = [35.2, 28.4, 19.8, 12.3, 7.1, 3.8, 1.9, 0.8, 0.4, 0.2]
    bbc_profile = [54.8, 48.6, 38.2, 29.5, 21.0, 14.2, 8.5, 4.3, 2.1, 1.0]
    soc_profile = [85.0, 72.0, 58.0, 42.0, 31.0, 22.0, 15.0, 9.5, 6.0, 4.2] # kg C/m3
    q10_profile = [2.4, 2.3, 2.2, 2.1, 2.0, 1.9, 1.8, 1.7, 1.6, 1.5]

    return {
        'depths': depths,
        'depth_labels': depth_labels,
        'fbc': fbc_profile,
        'bbc': bbc_profile,
        'soc': soc_profile,
        'q10': q10_profile
    }

def calculate_kinetics_curve(vmax=12.5, km=25.0, temp=15.0, q10=2.2):
    """
    Substrate kinetics and thermal response calculation:
    V = (Vmax(T) * [S]) / (Km + [S])
    """
    substrate = np.linspace(0.5, 150.0, 60)
    t_factor = q10 ** ((temp - 20.0) / 10.0)
    vmax_adj = vmax * t_factor
    rates = (vmax_adj * substrate) / (km + substrate)
    
    return {
        'substrate': [round(float(x), 2) for x in substrate],
        'rate': [round(float(y), 3) for y in rates],
        'vmax_adj': round(float(vmax_adj), 3),
        'km': km,
        'temp': temp
    }
