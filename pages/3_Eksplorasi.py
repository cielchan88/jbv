import streamlit as st
import warnings
warnings.filterwarnings('ignore', category=DeprecationWarning)
warnings.filterwarnings('ignore', message='.*keyword arguments have been deprecated.*')
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from statsmodels.tsa.seasonal import seasonal_decompose

# Page config
st.set_page_config(page_title="Eksplorasi - JBV Dashboard", layout="wide")

# Import utils
from utils.data_loader import load_etl_output

# Title
st.title("📊 Eksplorasi Data")
st.markdown("Visualisasi dan analisis data JBV hasil ETL Pipeline.")

st.divider()

# Load ETL output data (NOT raw processed data!)
df, metadata_cols, time_cols = load_etl_output()

# Show NET SDV (always visible)

# Get D row
d_row = df[df['Row_ID'] == 'D']
if len(d_row) > 0:
    d_values = d_row[time_cols].values.flatten()
    d_dates = pd.to_datetime(time_cols)

    # Plot Net SDV
    fig_d = go.Figure()
    fig_d.add_trace(go.Scatter(
        x=d_dates,
        y=d_values,
        mode='lines+markers',
        name='Net SDV',
        line=dict(color='#1f77b4', width=3)
    ))

    fig_d.update_layout(
        title="Time Series Net Supply Demand Valas",
        xaxis_title="Tanggal",
        yaxis_title="Nilai (USD Juta)",
        hovermode='x unified',
        height=400
    )

    st.plotly_chart(fig_d, width='stretch')

    # Informasi Data section
    st.subheader("📋 Informasi Data")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Tanggal Awal", d_dates[0].strftime('%Y-%m-%d'))
    with col2:
        st.metric("Tanggal Terakhir", d_dates[-1].strftime('%Y-%m-%d'))
    with col3:
        st.metric("Nilai Terakhir", f"{d_values[-1]:.2f}")

    st.divider()

    # Deskriptif Statistik section
    st.subheader("📊 Deskriptif Statistik")
    min_idx = d_values.argmin()
    max_idx = d_values.argmax()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            "Minimum",
            f"{d_values[min_idx]:.2f}",
            help=f"Tanggal: {d_dates[min_idx].strftime('%Y-%m-%d')}"
        )
    with col2:
        st.metric(
            "Maksimum",
            f"{d_values[max_idx]:.2f}",
            help=f"Tanggal: {d_dates[max_idx].strftime('%Y-%m-%d')}"
        )
    with col3:
        st.metric(
            "Rata-rata",
            f"{d_values.mean():.2f}"
        )
    with col4:
        st.metric(
            "Median",
            f"{pd.Series(d_values).median():.2f}"
        )

st.divider()

# Breakdown by main categories
st.subheader("Breakdown per Kategori")

# Get all categories with their labels
main_categories = ['A', 'B', 'C']
category_options = {}
for cat in main_categories:
    cat_data = df[df['Row_ID'] == cat]
    if len(cat_data) > 0:
        cat_label = cat_data.iloc[0]['Row_Label']
        clean_label = cat_label.split('. ', 1)[-1] if '. ' in cat_label else cat_label
        category_options[clean_label] = cat

# Selectbox to choose category
selected_category_label = st.selectbox(
    "Pilih kategori untuk breakdown:",
    options=list(category_options.keys())
)

# Get selected category data
selected_cat_id = category_options[selected_category_label]
cat_data = df[df['Row_ID'] == selected_cat_id]

if len(cat_data) > 0:
    # Get children (parse JSON string to list)
    from utils.data_loader import parse_children
    children_list = parse_children(cat_data.iloc[0]['Children'])

    # Special handling for KORPORASI (3 levels)
    if selected_cat_id == 'A':
        # Build level 2 options (PTMN / Korporasi Lainnya)
        level2_options = {}
        for child_id in children_list:
            child_data = df[df['Row_ID'] == child_id]
            if len(child_data) > 0:
                child_label = child_data.iloc[0]['Row_Label']
                clean_child_label = child_label.split('. ', 1)[-1] if '. ' in child_label else child_label
                level2_options[clean_child_label] = child_id

        # Selectbox for level 2
        selected_level2_label = st.selectbox(
            "Pilih sub-kategori level 2:",
            options=list(level2_options.keys())
        )

        selected_level2_id = level2_options[selected_level2_label]
        level2_data = df[df['Row_ID'] == selected_level2_id]

        if len(level2_data) > 0:
            # Get level 3 children
            level3_children = parse_children(level2_data.iloc[0]['Children'])

            if len(level3_children) > 0:
                # Build level 3 options
                level3_options = {}
                for child_id in level3_children:
                    child_data = df[df['Row_ID'] == child_id]
                    if len(child_data) > 0:
                        child_label = child_data.iloc[0]['Row_Label']
                        clean_child_label = child_label.split('. ', 1)[-1] if '. ' in child_label else child_label
                        level3_options[clean_child_label] = child_id

                # Selectbox for level 3
                selected_level3_label = st.selectbox(
                    "Pilih sub-kategori detail:",
                    options=list(level3_options.keys())
                )

                # Plot selected level 3
                selected_level3_id = level3_options[selected_level3_label]
                dates = pd.to_datetime(time_cols)

                fig = go.Figure()

                child_data = df[df['Row_ID'] == selected_level3_id]
                if len(child_data) > 0:
                    child_values = child_data[time_cols].values.flatten()

                    fig.add_trace(go.Scatter(
                        x=dates,
                        y=child_values,
                        mode='lines',
                        name=selected_level3_label,
                        line=dict(width=3)
                    ))

                fig.update_layout(
                    title=selected_level3_label,
                    xaxis_title="Tanggal",
                    yaxis_title="Nilai (USD Juta)",
                    hovermode='x unified',
                    height=500
                )

                st.plotly_chart(fig, width='stretch')

    else:
        # For INDIVIDU and NON RESIDEN (2 levels only)
        if len(children_list) > 0:
            # Build sub-category options
            subcategory_options = {}
            for child_id in children_list:
                child_data = df[df['Row_ID'] == child_id]
                if len(child_data) > 0:
                    child_label = child_data.iloc[0]['Row_Label']
                    clean_child_label = child_label.split('. ', 1)[-1] if '. ' in child_label else child_label
                    subcategory_options[clean_child_label] = child_id

            # Selectbox for sub-category
            selected_subcategory_label = st.selectbox(
                "Pilih sub-kategori:",
                options=list(subcategory_options.keys())
            )

            # Plot selected child only
            selected_child_id = subcategory_options[selected_subcategory_label]
            dates = pd.to_datetime(time_cols)

            fig = go.Figure()

            # Add selected child line only
            child_data = df[df['Row_ID'] == selected_child_id]
            if len(child_data) > 0:
                child_values = child_data[time_cols].values.flatten()

                fig.add_trace(go.Scatter(
                    x=dates,
                    y=child_values,
                    mode='lines',
                    name=selected_subcategory_label,
                    line=dict(width=3)
                ))

            fig.update_layout(
                title=selected_subcategory_label,
                xaxis_title="Tanggal",
                yaxis_title="Nilai (USD Juta)",
                hovermode='x unified',
                height=500
            )

            st.plotly_chart(fig, width='stretch')

        else:
            # Just plot the category
            cat_values = cat_data[time_cols].values.flatten()
            dates = pd.to_datetime(time_cols)

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=dates,
                y=cat_values,
                mode='lines+markers',
                name=selected_category_label
            ))

            fig.update_layout(
                title=selected_category_label,
                xaxis_title="Tanggal",
                yaxis_title="Nilai (USD Juta)",
                hovermode='x unified',
                height=500
            )

            st.plotly_chart(fig, width='stretch')

st.divider()

# Advanced Analytics Section
st.subheader("📊 Analisis Lanjutan")

# ---- Pemilih series untuk analisis mendalam ----
# Semua tab analitik di bawah (kecuali korelasi & external features yang memang
# lintas-kategori) mengikuti pilihan ini, supaya bisa membedah komponen mana pun,
# tidak terkunci di NET SDV saja.
series_options = {}
for _, row in df.iterrows():
    label = row['Row_Label']
    clean = label.split('. ', 1)[-1] if '. ' in label else label
    series_options[f"{row['Row_ID']} - {clean}"] = row['Row_ID']

default_key = next((k for k, v in series_options.items() if v == 'D'), list(series_options.keys())[0])
selected_analysis_label = st.selectbox(
    "Pilih series untuk dianalisis:",
    options=list(series_options.keys()),
    index=list(series_options.keys()).index(default_key),
    help="Pilihan ini dipakai oleh tab Dekomposisi, Outlier, Structural Break, Stasioneritas, Distribusi, dan Kualitas Data"
)
selected_analysis_id = series_options[selected_analysis_label]

# Siapkan array nilai & tanggal untuk series terpilih (dipakai bersama semua tab)
_analysis_row = df[df['Row_ID'] == selected_analysis_id]
analysis_values = np.nan_to_num(
    np.array(_analysis_row[time_cols].values.flatten(), dtype=float),
    nan=0.0, posinf=0.0, neginf=0.0
)
analysis_dates = pd.to_datetime(time_cols)

from utils import analytics

tabs = st.tabs([
    "🔍 Dekomposisi",
    "🎯 Outlier",
    "📐 Structural Break",
    "📉 Stasioneritas & ACF",
    "📊 Distribusi",
    "🧹 Kualitas Data",
    "🔗 Korelasi",
    "🌍 External Features",
])

# Tab 1: Trend Decomposition
with tabs[0]:
    st.markdown(f"**Dekomposisi Time Series** - Pisahkan komponen Trend, Seasonal, dan Residual dari `{selected_analysis_label}`")

    decomp_period = st.selectbox(
        "Periode musiman:",
        options=[5, 7, 21, 30],
        index=0,
        format_func=lambda x: {5: "5 (mingguan - hari kerja)", 7: "7 (mingguan - kalender)",
                               21: "21 (bulanan - hari kerja)", 30: "30 (bulanan - kalender)"}[x],
        help="Data SDV hanya berisi hari kerja, jadi siklus mingguan sebenarnya = 5 hari, bukan 7"
    )

    series_data = _analysis_row
    if len(series_data) > 0:
        decomp_values = analysis_values
        decomp_dates = analysis_dates

        # Create time series
        ts = pd.Series(decomp_values, index=decomp_dates)

        # Perform decomposition
        try:
            decomposition = seasonal_decompose(ts, model='additive', period=decomp_period, extrapolate_trend='freq')

            # Create subplots
            fig_decomp = make_subplots(
                rows=4, cols=1,
                subplot_titles=('Original', 'Trend', 'Seasonal', 'Residual'),
                vertical_spacing=0.08
            )

            # Original
            fig_decomp.add_trace(
                go.Scatter(x=decomp_dates, y=decomp_values, name='Original', line=dict(color='blue')),
                row=1, col=1
            )

            # Trend
            fig_decomp.add_trace(
                go.Scatter(x=decomp_dates, y=decomposition.trend, name='Trend', line=dict(color='red')),
                row=2, col=1
            )

            # Seasonal
            fig_decomp.add_trace(
                go.Scatter(x=decomp_dates, y=decomposition.seasonal, name='Seasonal', line=dict(color='green')),
                row=3, col=1
            )

            # Residual
            fig_decomp.add_trace(
                go.Scatter(x=decomp_dates, y=decomposition.resid, name='Residual', line=dict(color='orange')),
                row=4, col=1
            )

            fig_decomp.update_layout(height=800, showlegend=False,
                                     title_text=f"Decomposition: {selected_analysis_label}")
            fig_decomp.update_xaxes(title_text="Tanggal", row=4, col=1)

            st.plotly_chart(fig_decomp, width='stretch')

            # Kekuatan komponen musiman & trend (Hyndman-style strength measures)
            resid = pd.Series(decomposition.resid).dropna()
            seasonal = pd.Series(decomposition.seasonal).dropna()
            trend = pd.Series(decomposition.trend).dropna()
            var_resid = float(resid.var()) if len(resid) > 1 else 0.0

            if var_resid > 0:
                seas_strength = max(0.0, 1 - var_resid / float((resid + seasonal).var()))
                trend_strength = max(0.0, 1 - var_resid / float((resid + trend).var()))
                c1, c2 = st.columns(2)
                with c1:
                    st.metric("Kekuatan Trend", f"{trend_strength:.2f}",
                              help="0 = tidak ada trend, 1 = sangat didominasi trend")
                with c2:
                    st.metric("Kekuatan Musiman", f"{seas_strength:.2f}",
                              help="0 = tidak ada pola musiman, 1 = sangat kuat musiman")

                if seas_strength < 0.1:
                    st.info("ℹ️ Pola musiman sangat lemah pada periode ini - coba periode lain, "
                            "atau memang seasonality-nya tidak dominan di series ini.")

            # Insights
            st.info("""
            **📌 Cara baca:**
            - **Trend**: Arah umum data (naik/turun jangka panjang)
            - **Seasonal**: Pola berulang sesuai periode yang dipilih
            - **Residual**: Sisa variasi yang tidak dijelaskan trend/musiman - residual besar
              dan bergerombol menandakan ada faktor lain (kejutan pasar, structural break)
            """)

        except Exception as e:
            st.error(f"Error saat decomposition: {str(e)}")
            st.info("Data mungkin tidak cukup panjang untuk analisis seasonal.")

# Tab 2: Outlier Analysis
with tabs[1]:
    st.markdown(f"**Analisis Outlier** - Deteksi nilai ekstrem pada `{selected_analysis_label}`")

    col_m1, col_m2 = st.columns([1, 1])
    with col_m1:
        outlier_method = st.selectbox(
            "Metode deteksi:",
            options=['mad', 'iqr', 'zscore'],
            format_func=lambda x: {
                'mad': 'Modified Z-score (MAD) - paling robust',
                'iqr': 'IQR (Tukey fences)',
                'zscore': 'Z-score standar',
            }[x],
            help="MAD direkomendasikan untuk data volatil: median & MAD tidak ikut tertarik oleh outlier itu sendiri"
        )
    with col_m2:
        if outlier_method == 'iqr':
            threshold = st.slider("Pengali IQR (k)", 1.0, 3.0, 1.5, 0.5)
            detector_kwargs = {'k': threshold}
        elif outlier_method == 'zscore':
            threshold = st.slider("Ambang Z-score", 2.0, 5.0, 3.0, 0.5)
            detector_kwargs = {'threshold': threshold}
        else:
            threshold = st.slider("Ambang Modified Z-score", 2.0, 5.0, 3.5, 0.5)
            detector_kwargs = {'threshold': threshold}

    outlier_df, outlier_res = analytics.summarize_outliers(
        analysis_dates, analysis_values, method=outlier_method, **detector_kwargs
    )

    n_out = outlier_res['count']
    pct_out = n_out / len(analysis_values) * 100 if len(analysis_values) else 0

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Jumlah Outlier", f"{n_out:,}")
    with c2:
        st.metric("Persentase", f"{pct_out:.2f}%")
    with c3:
        if outlier_method == 'iqr':
            st.metric("Batas", f"{outlier_res['lower']:,.0f} s/d {outlier_res['upper']:,.0f}")
        else:
            st.metric("Ambang Skor", f"±{threshold}")

    # Plot dengan outlier ditandai
    mask = outlier_res['mask']
    fig_out = go.Figure()
    fig_out.add_trace(go.Scatter(
        x=analysis_dates, y=analysis_values, mode='lines',
        name='Nilai', line=dict(color='#1f77b4', width=1)
    ))
    if mask.any():
        fig_out.add_trace(go.Scatter(
            x=analysis_dates[mask], y=analysis_values[mask], mode='markers',
            name='Outlier', marker=dict(color='red', size=7, symbol='x')
        ))
    if outlier_method == 'iqr':
        fig_out.add_hline(y=outlier_res['upper'], line_dash='dash', line_color='orange',
                          annotation_text='Batas atas')
        fig_out.add_hline(y=outlier_res['lower'], line_dash='dash', line_color='orange',
                          annotation_text='Batas bawah')

    fig_out.update_layout(title=f"Outlier: {selected_analysis_label}",
                          xaxis_title="Tanggal", yaxis_title="Nilai (USD Juta)",
                          height=450, hovermode='x unified')
    st.plotly_chart(fig_out, width='stretch')

    if n_out > 0:
        st.markdown("**📋 Daftar Outlier (diurutkan dari deviasi terbesar)**")
        show_df = outlier_df.copy()
        show_df['Nilai'] = show_df['Nilai'].map(lambda v: f"{v:,.2f}")
        show_df['Skor'] = show_df['Skor'].map(lambda v: f"{v:,.2f}")
        st.dataframe(show_df.head(50), width='stretch', hide_index=True)
        if len(show_df) > 50:
            st.caption(f"Menampilkan 50 dari {len(show_df)} outlier.")

        # Distribusi outlier per tahun - bantu lihat apakah terkonsentrasi di periode tertentu
        years = pd.to_datetime(outlier_df['Tanggal']).dt.year.value_counts().sort_index()
        fig_year = go.Figure(go.Bar(x=years.index.astype(str), y=years.values,
                                    marker_color='indianred'))
        fig_year.update_layout(title="Sebaran Outlier per Tahun", xaxis_title="Tahun",
                               yaxis_title="Jumlah Outlier", height=300)
        st.plotly_chart(fig_year, width='stretch')
        st.caption("Outlier yang menumpuk di satu periode biasanya menandakan kejadian pasar "
                   "tertentu atau perubahan cara pencatatan data - bukan sekadar noise acak.")
    else:
        st.success("✅ Tidak ada outlier terdeteksi dengan pengaturan ini.")

# Tab 3: Structural Break
with tabs[2]:
    st.markdown(f"**Analisis Structural Break** - Deteksi pergeseran level/rezim pada `{selected_analysis_label}`")
    st.caption("Structural break = titik di mana perilaku deret berubah secara permanen (bukan lonjakan sesaat). "
               "Penting untuk forecasting: data sebelum break bisa jadi menyesatkan kalau rezimnya sudah berubah.")

    cb1, cb2, cb3 = st.columns(3)
    with cb1:
        max_breaks = st.slider("Maks. jumlah break", 1, 10, 5)
    with cb2:
        min_size = st.slider("Min. panjang segmen (hari)", 30, 365, 90, 30)
    with cb3:
        sensitivity = st.slider("Sensitivitas (%)", 0.5, 10.0, 1.0, 0.5,
                                help="Ambang minimal perbaikan agar sebuah break diterima. "
                                     "Makin kecil = makin sensitif (lebih banyak break terdeteksi).")

    break_res = analytics.detect_structural_breaks(
        analysis_values, max_breaks=max_breaks, min_size=min_size,
        min_gain_ratio=sensitivity / 100.0
    )

    if break_res.get('note'):
        st.warning(f"⚠️ {break_res['note']}")

    bps = break_res['breakpoints']

    fig_break = go.Figure()
    fig_break.add_trace(go.Scatter(
        x=analysis_dates, y=analysis_values, mode='lines',
        name='Nilai', line=dict(color='#1f77b4', width=1), opacity=0.6
    ))

    # Garis mean per segmen
    for i, seg in enumerate(break_res['segments']):
        seg_dates = analysis_dates[seg['start_idx']:seg['end_idx'] + 1]
        fig_break.add_trace(go.Scatter(
            x=seg_dates, y=np.full(len(seg_dates), seg['mean']),
            mode='lines', name=f"Mean segmen {i+1}",
            line=dict(color='red', width=3)
        ))

    for bp in bps:
        fig_break.add_vline(x=analysis_dates[bp], line_dash='dash', line_color='black')

    fig_break.update_layout(title=f"Structural Break: {selected_analysis_label}",
                            xaxis_title="Tanggal", yaxis_title="Nilai (USD Juta)",
                            height=450, hovermode='x unified')
    st.plotly_chart(fig_break, width='stretch')

    if bps:
        st.markdown(f"**📍 {len(bps)} Break Terdeteksi**")
        seg_rows = []
        for i, seg in enumerate(break_res['segments']):
            seg_rows.append({
                'Segmen': i + 1,
                'Mulai': analysis_dates[seg['start_idx']].strftime('%Y-%m-%d'),
                'Selesai': analysis_dates[seg['end_idx']].strftime('%Y-%m-%d'),
                'Jumlah Hari': seg['n'],
                'Rata-rata': f"{seg['mean']:,.2f}",
                'Std Dev': f"{seg['std']:,.2f}",
            })
        st.dataframe(pd.DataFrame(seg_rows), width='stretch', hide_index=True)

        st.markdown("**Tanggal Break:**")
        for i, bp in enumerate(bps, 1):
            prev_mean = break_res['segments'][i - 1]['mean']
            next_mean = break_res['segments'][i]['mean']
            delta = next_mean - prev_mean
            arah = "naik" if delta > 0 else "turun"
            st.write(f"{i}. **{analysis_dates[bp].strftime('%Y-%m-%d')}** - "
                     f"rata-rata {arah} dari {prev_mean:,.2f} ke {next_mean:,.2f} "
                     f"(selisih {delta:+,.2f})")
    else:
        st.success("✅ Tidak ada structural break signifikan - level deret relatif stabil "
                   "sepanjang periode (dengan sensitivitas saat ini).")

    # CUSUM
    st.divider()
    st.markdown("**📈 CUSUM (Cumulative Sum)**")
    st.caption("Akumulasi simpangan terhadap rata-rata keseluruhan. Kurva naik = periode di atas "
               "rata-rata, turun = di bawah. Titik balik kurva sering menandai pergeseran rezim.")

    cusum_vals = analytics.cusum(analysis_values)
    fig_cusum = go.Figure()
    fig_cusum.add_trace(go.Scatter(x=analysis_dates, y=cusum_vals, mode='lines',
                                   name='CUSUM', line=dict(color='purple', width=2)))
    fig_cusum.add_hline(y=0, line_dash='dash', line_color='gray')
    for bp in bps:
        fig_cusum.add_vline(x=analysis_dates[bp], line_dash='dash', line_color='black')
    fig_cusum.update_layout(xaxis_title="Tanggal", yaxis_title="CUSUM",
                            height=350, hovermode='x unified')
    st.plotly_chart(fig_cusum, width='stretch')

    # Rolling statistics
    st.divider()
    st.markdown("**📊 Rolling Mean & Volatilitas**")
    roll_window = st.slider("Window rolling (hari)", 30, 365, 90, 30, key='roll_win')
    roll = analytics.rolling_statistics(analysis_values, window=roll_window)

    fig_roll = make_subplots(rows=2, cols=1, shared_xaxes=True,
                             subplot_titles=(f'Rolling Mean ({roll_window} hari)',
                                             f'Rolling Std Dev / Volatilitas ({roll_window} hari)'),
                             vertical_spacing=0.12)
    fig_roll.add_trace(go.Scatter(x=analysis_dates, y=roll['mean'], mode='lines',
                                  line=dict(color='blue')), row=1, col=1)
    fig_roll.add_trace(go.Scatter(x=analysis_dates, y=roll['std'], mode='lines',
                                  line=dict(color='orange')), row=2, col=1)
    fig_roll.update_layout(height=500, showlegend=False)
    st.plotly_chart(fig_roll, width='stretch')
    st.caption("Rolling std yang melonjak = periode volatilitas tinggi. Kalau levelnya bergeser "
               "permanen, itu tanda perubahan rezim volatilitas (bukan cuma level).")

# Tab 4: Stasioneritas & Autokorelasi
with tabs[3]:
    st.markdown(f"**Uji Stasioneritas & Autokorelasi** - `{selected_analysis_label}`")
    st.caption("Menentukan apakah deret perlu differencing sebelum dimodelkan dengan ARIMA/VAR, "
               "dan struktur lag mana yang paling informatif.")

    use_diff = st.checkbox("Uji pada data setelah differencing (selisih hari ke hari)", value=False)
    test_values = np.diff(analysis_values) if use_diff else analysis_values

    stat_res = analytics.stationarity_tests(test_values)

    if 'error' in stat_res:
        st.error(f"❌ {stat_res['error']}")
    else:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**ADF Test** (H₀: ada unit root / tidak stasioner)")
            adf = stat_res.get('adf', {})
            if 'error' in adf:
                st.error(adf['error'])
            else:
                st.metric("p-value", f"{adf['pvalue']:.4f}",
                          delta="Stasioner" if adf['stationary'] else "Tidak stasioner",
                          delta_color="normal" if adf['stationary'] else "inverse")
                st.caption(f"Statistik: {adf['statistic']:.4f}")
        with c2:
            st.markdown("**KPSS Test** (H₀: stasioner)")
            kp = stat_res.get('kpss', {})
            if 'error' in kp:
                st.error(kp['error'])
            else:
                st.metric("p-value", f"{kp['pvalue']:.4f}",
                          delta="Stasioner" if kp['stationary'] else "Tidak stasioner",
                          delta_color="normal" if kp['stationary'] else "inverse")
                st.caption(f"Statistik: {kp['statistic']:.4f}")

        conclusion = stat_res['conclusion']
        if 'TIDAK STASIONER' in conclusion:
            st.warning(f"⚠️ **Kesimpulan:** {conclusion}")
        elif conclusion.startswith('STASIONER'):
            st.success(f"✅ **Kesimpulan:** {conclusion}")
        else:
            st.info(f"ℹ️ **Kesimpulan:** {conclusion}")

    # ACF / PACF
    st.divider()
    st.markdown("**📊 ACF & PACF**")
    nlags = st.slider("Jumlah lag", 10, 90, 40, 10)
    ap = analytics.compute_acf_pacf(test_values, nlags=nlags)

    if 'error' in ap:
        st.error(f"❌ {ap['error']}")
    else:
        fig_acf = make_subplots(rows=2, cols=1,
                                subplot_titles=('ACF (Autocorrelation)', 'PACF (Partial Autocorrelation)'),
                                vertical_spacing=0.15)
        fig_acf.add_trace(go.Bar(x=ap['lags'], y=ap['acf'], marker_color='steelblue'), row=1, col=1)
        fig_acf.add_trace(go.Bar(x=ap['lags'], y=ap['pacf'], marker_color='seagreen'), row=2, col=1)
        for r in (1, 2):
            fig_acf.add_hline(y=ap['conf'], line_dash='dash', line_color='red', row=r, col=1)
            fig_acf.add_hline(y=-ap['conf'], line_dash='dash', line_color='red', row=r, col=1)
            fig_acf.add_hline(y=0, line_color='gray', row=r, col=1)
        fig_acf.update_layout(height=600, showlegend=False)
        fig_acf.update_xaxes(title_text="Lag", row=2, col=1)
        st.plotly_chart(fig_acf, width='stretch')

        sig_lags = [int(l) for l, v in zip(ap['lags'][1:], ap['acf'][1:]) if abs(v) > ap['conf']]
        if sig_lags:
            st.info(f"**Lag signifikan (ACF di luar batas 95%):** {sig_lags[:20]}"
                    + (" ..." if len(sig_lags) > 20 else ""))
            weekly = [l for l in sig_lags if l % 5 == 0]
            if weekly:
                st.caption(f"Lag kelipatan 5 yang signifikan: {weekly[:10]} - indikasi pola mingguan "
                           f"(data hari kerja: 1 minggu = 5 observasi).")
        else:
            st.caption("Tidak ada lag signifikan - deret mendekati white noise pada level ini.")

# Tab 5: Distribusi
with tabs[4]:
    st.markdown(f"**Analisis Distribusi** - `{selected_analysis_label}`")

    dist = analytics.distribution_stats(analysis_values)

    if 'error' in dist:
        st.error(f"❌ {dist['error']}")
    else:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Skewness", f"{dist['skewness']:.3f}",
                      help="0 = simetris, >0 = ekor kanan panjang, <0 = ekor kiri panjang")
        with c2:
            st.metric("Excess Kurtosis", f"{dist['kurtosis_excess']:.3f}",
                      help="0 = seperti normal, >0 = ekor tebal (lebih sering nilai ekstrem)")
        with c3:
            st.metric("Jarque-Bera p", f"{dist['jb_pvalue']:.4f}" if dist['jb_pvalue'] is not None else "N/A")
        with c4:
            st.metric("Normal?", "Ya" if dist['normal'] else "Tidak")

        if not dist['normal']:
            st.warning("⚠️ Distribusi menyimpang dari normal. Ini penting karena beberapa model "
                       "(ARIMA/VAR) membangun confidence interval dengan asumsi normal - "
                       "interval bisa terlalu sempit kalau ekornya tebal.")
        if abs(dist['kurtosis_excess']) > 3:
            st.info("ℹ️ Excess kurtosis tinggi = nilai ekstrem jauh lebih sering muncul dibanding "
                    "distribusi normal. Pertimbangkan transformasi (mis. signed-log) untuk model ML.")

        # Histogram + kurva normal pembanding
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Histogram(x=analysis_values, nbinsx=60, name='Data',
                                        histnorm='probability density', marker_color='steelblue'))
        x_range = np.linspace(np.min(analysis_values), np.max(analysis_values), 200)
        normal_pdf = (1 / (dist['std'] * np.sqrt(2 * np.pi))) * np.exp(
            -0.5 * ((x_range - dist['mean']) / dist['std']) ** 2)
        fig_hist.add_trace(go.Scatter(x=x_range, y=normal_pdf, mode='lines',
                                      name='Normal (pembanding)', line=dict(color='red', width=2)))
        fig_hist.update_layout(title="Distribusi Nilai vs Kurva Normal",
                               xaxis_title="Nilai (USD Juta)", yaxis_title="Densitas", height=400)
        st.plotly_chart(fig_hist, width='stretch')

    # ========================================================================
    # GRAFIK NORMALITAS (Q-Q plot & ECDF)
    # ========================================================================
    st.divider()
    st.markdown("**📐 Grafik Normalitas**")

    # Pilihan level vs perubahan harian.
    #
    # Ini bukan sekadar opsi tambahan - untuk data deret waktu, normalitas LEVEL
    # jarang bermakna (level punya tren dan autokorelasi, jadi hampir selalu
    # "tidak normal" tanpa memberi tahu apa pun yang berguna). Yang benar-benar
    # diasumsikan normal oleh ARIMA/VAR saat membangun confidence interval
    # adalah INOVASI-nya, dan perubahan harian adalah pendekatan terdekat yang
    # bisa dilihat langsung dari data mentah.
    norm_basis = st.radio(
        "Data yang diuji:",
        ["Perubahan harian (delta)", "Nilai (level)"],
        index=0,
        horizontal=True,
        help="ARIMA/VAR mengasumsikan INOVASI berdistribusi normal, bukan levelnya. "
             "Perubahan harian adalah pendekatan terdekat untuk itu, jadi dipakai sebagai default."
    )

    if norm_basis.startswith("Perubahan"):
        norm_values = np.diff(analysis_values)
        norm_unit = "Perubahan harian (USD Juta)"
    else:
        norm_values = analysis_values
        norm_unit = "Nilai (USD Juta)"

    nd = analytics.normality_diagnostics(norm_values)

    if 'error' in nd:
        st.error(f"❌ {nd['error']}")
    else:
        gq1, gq2 = st.columns(2)

        with gq1:
            fig_qq = go.Figure()
            fig_qq.add_trace(go.Scatter(
                x=nd['theoretical_q'], y=nd['sample_q'], mode='markers',
                name='Data', marker=dict(color='steelblue', size=4, opacity=0.6)))
            _lx = np.array([nd['theoretical_q'][0], nd['theoretical_q'][-1]])
            fig_qq.add_trace(go.Scatter(
                x=_lx, y=nd['line_slope'] * _lx + nd['line_intercept'], mode='lines',
                name='Garis normal', line=dict(color='red', width=2)))
            fig_qq.update_layout(
                title=f"Q-Q Plot (R² = {nd['r_squared']:.4f})",
                xaxis_title="Kuantil teoretis (normal)", yaxis_title=norm_unit,
                height=430, legend=dict(orientation='h', y=1.02, yanchor='bottom'))
            st.plotly_chart(fig_qq, width='stretch')
            st.caption("Data normal jatuh tepat di garis merah. Titik yang **melengkung "
                       "naik di kanan dan turun di kiri** berarti ekor lebih tebal dari "
                       "normal - nilai ekstrem jauh lebih sering terjadi daripada yang "
                       "diasumsikan model.")

        with gq2:
            fig_ecdf = go.Figure()
            fig_ecdf.add_trace(go.Scatter(
                x=nd['ecdf_x'], y=nd['ecdf_emp'], mode='lines',
                name='ECDF data', line=dict(color='steelblue', width=2)))
            fig_ecdf.add_trace(go.Scatter(
                x=nd['ecdf_x'], y=nd['ecdf_theo'], mode='lines',
                name='CDF normal', line=dict(color='red', width=2, dash='dash')))
            fig_ecdf.update_layout(
                title=f"ECDF vs CDF Normal (jarak maks = {nd['ks_distance']:.4f})",
                xaxis_title=norm_unit, yaxis_title="Probabilitas kumulatif",
                height=430, legend=dict(orientation='h', y=1.02, yanchor='bottom'))
            st.plotly_chart(fig_ecdf, width='stretch')
            st.caption("Jarak vertikal terbesar antara kedua kurva adalah statistik "
                       "Kolmogorov-Smirnov. Makin lebar jaraknya, makin jauh data "
                       "menyimpang dari normal.")

        # Ringkasan uji normalitas
        if nd['tests']:
            _rows = []
            for t in nd['tests']:
                _rows.append({
                    'Uji': t['nama'],
                    'Statistik': f"{t['statistik']:.4f}",
                    'p-value': f"{t['p']:.4g}" if t['p'] is not None else "—",
                    'Kesimpulan': "Normal" if t['normal'] else "Tidak normal",
                    'Catatan': t['catatan'],
                })
            st.dataframe(pd.DataFrame(_rows), width='stretch', hide_index=True)

            _n_tolak = sum(1 for t in nd['tests'] if not t['normal'])
            if _n_tolak == len(nd['tests']):
                st.warning(
                    f"⚠️ **Seluruh {len(nd['tests'])} uji menolak normalitas.** "
                    f"Konsekuensinya nyata: confidence interval ARIMA/VAR dan pita "
                    f"±1,96σ di Lembar Kerja dibangun dengan asumsi normal, sehingga "
                    f"cakupannya lebih sempit dari yang tertulis - kejadian ekstrem "
                    f"akan lebih sering jatuh di luar pita daripada 5% yang dijanjikan."
                )
            elif _n_tolak == 0:
                st.success(f"✅ Seluruh {len(nd['tests'])} uji konsisten dengan distribusi normal.")
            else:
                st.info(
                    f"ℹ️ Hasil uji terbelah: {len(nd['tests']) - _n_tolak} menyatakan normal, "
                    f"{_n_tolak} menolak. Perbedaan ini normal karena tiap uji peka pada "
                    f"aspek yang berbeda (lihat kolom Catatan) - baca Q-Q plot untuk "
                    f"menentukan di bagian mana penyimpangannya."
                )

    # Box plot perbandingan antar kategori (dipertahankan dari versi sebelumnya)
    st.divider()
    st.markdown("**📦 Perbandingan Distribusi Antar Kategori Utama**")

    category_labels = {'A': 'KORPORASI', 'B': 'INDIVIDU', 'C': 'NON RESIDEN', 'D': 'NET SDV'}
    box_data, box_labels = [], []
    for cat in ['A', 'B', 'C', 'D']:
        cat_row = df[df['Row_ID'] == cat]
        if len(cat_row) > 0:
            box_data.append(cat_row.iloc[0][time_cols].values)
            box_labels.append(category_labels[cat])

    fig_box = go.Figure()
    for data, label in zip(box_data, box_labels):
        fig_box.add_trace(go.Box(y=data, name=label, boxmean='sd'))
    fig_box.update_layout(title="Distribusi Nilai per Kategori (dengan Mean & Std Dev)",
                          yaxis_title="Nilai (USD Juta)", height=500, showlegend=True)
    st.plotly_chart(fig_box, width='stretch')

    stats_data = []
    for data, label in zip(box_data, box_labels):
        arr = np.array(data, dtype=float)
        stats_data.append({
            'Kategori': label,
            'Mean': f"{np.mean(arr):.2f}",
            'Median': f"{np.median(arr):.2f}",
            'Std Dev': f"{np.std(arr):.2f}",
            'Min': f"{np.min(arr):.2f}",
            'Max': f"{np.max(arr):.2f}",
            'Range': f"{np.max(arr) - np.min(arr):.2f}",
        })
    st.dataframe(pd.DataFrame(stats_data), width='stretch', hide_index=True)

# Tab 6: Kualitas Data
with tabs[5]:
    st.markdown(f"**Analisis Kualitas Data** - `{selected_analysis_label}`")
    st.caption("Cek masalah data yang bisa merusak model tanpa terlihat jelas di grafik biasa.")

    n_total = len(analysis_values)
    n_zero = int((analysis_values == 0).sum())
    pct_zero = n_zero / n_total * 100 if n_total else 0

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Total Observasi", f"{n_total:,}")
    with c2:
        st.metric("Nilai Nol", f"{n_zero:,}")
    with c3:
        st.metric("Persentase Nol", f"{pct_zero:.1f}%")

    if pct_zero > 30:
        st.warning(f"⚠️ {pct_zero:.1f}% data bernilai nol. Perlu diperhatikan: ETL mengubah sel kosong "
                   "menjadi 0, jadi nilai 0 bisa berarti **tidak ada transaksi** ATAU **data belum "
                   "tersedia** - keduanya tidak bisa dibedakan setelah tahap ETL.")

    st.divider()
    st.markdown("**🔢 Deret Nilai Nol Berturut-turut**")
    min_run = st.slider("Minimal panjang deret (hari)", 2, 30, 3)
    zero_runs = analytics.analyze_zero_runs(analysis_dates, analysis_values, min_run=min_run)

    if len(zero_runs) > 0:
        st.dataframe(zero_runs.head(30), width='stretch', hide_index=True)
        st.caption(f"Total {len(zero_runs)} deret nol dengan panjang ≥ {min_run} hari. "
                   "Deret panjang lebih mungkin masalah ketersediaan data daripada kondisi pasar riil.")
    else:
        st.success(f"✅ Tidak ada deret nol berturut-turut ≥ {min_run} hari.")

    st.divider()
    st.markdown("**📅 Gap Tanggal**")
    gaps = analytics.analyze_date_gaps(analysis_dates)
    if len(gaps) > 0:
        st.dataframe(gaps.head(30), width='stretch', hide_index=True)
        st.caption("Gap > 4 hari kalender (di luar pola akhir pekan normal) - "
                   "bisa jadi libur panjang atau data yang benar-benar hilang.")
    else:
        st.success("✅ Tidak ada gap tanggal yang tidak wajar (akhir pekan normal diabaikan).")

# Tab 7: Correlation Heatmap
with tabs[6]:
    st.markdown("**Correlation Heatmap** - Korelasi antar kategori utama SDV")

    # Get main categories data
    categories = ['A', 'B', 'C', 'D']
    category_labels = {
        'A': 'KORPORASI',
        'B': 'INDIVIDU',
        'C': 'NON RESIDEN',
        'D': 'NET SDV'
    }

    # Build correlation matrix
    corr_data = {}
    for cat in categories:
        cat_row = df[df['Row_ID'] == cat]
        if len(cat_row) > 0:
            corr_data[category_labels[cat]] = cat_row.iloc[0][time_cols].values

    corr_df = pd.DataFrame(corr_data)
    corr_matrix = corr_df.corr()

    # Create heatmap
    fig_corr = go.Figure(data=go.Heatmap(
        z=corr_matrix.values,
        x=corr_matrix.columns,
        y=corr_matrix.columns,
        colorscale='RdBu',
        zmid=0,
        text=corr_matrix.values.round(2),
        texttemplate='%{text}',
        textfont={"size": 12},
        colorbar=dict(title="Korelasi")
    ))

    fig_corr.update_layout(
        title="Correlation Heatmap: Kategori Utama SDV",
        xaxis_title="",
        yaxis_title="",
        height=500
    )

    st.plotly_chart(fig_corr, width='stretch')

# Tab 8: External Features
with tabs[7]:
    st.markdown("**External Features** - Fitur eksternal (Oil Price, USD/IDR, Sentiment, dll)")

    from utils.external_loader import ENABLE_EXTERNAL_FEATURES
    if not ENABLE_EXTERNAL_FEATURES:
        st.warning("⚠️ External features sedang **dimatikan** untuk forecasting "
                   "(`ENABLE_EXTERNAL_FEATURES = False` di `utils/external_loader.py`). "
                   "Data di bawah hanya untuk melihat isi file - tidak dipakai model saat ini.")

    try:
        # Load external features (use default sheet)
        df_ext = pd.read_excel('data/external_features.xlsx')
        df_ext['Tanggal'] = pd.to_datetime(df_ext['Tanggal'])

        # Info section
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Features", len(df_ext.columns) - 1)  # Exclude Tanggal
        with col2:
            st.metric("Total Records", f"{len(df_ext):,}")
        with col3:
            st.metric("Latest Date", df_ext['Tanggal'].max().strftime('%Y-%m-%d'))

        st.write("")

        # Feature selector
        feature_cols = [col for col in df_ext.columns if col != 'Tanggal']

        st.markdown("**📊 Visualisasi Time Series External Features**")

        # Multi-select for features
        selected_features = st.multiselect(
            "Pilih fitur untuk ditampilkan:",
            options=feature_cols,
            default=feature_cols[:3] if len(feature_cols) >= 3 else feature_cols
        )

        if selected_features:
            # Create subplot for each feature
            from plotly.subplots import make_subplots

            fig_ext = make_subplots(
                rows=len(selected_features),
                cols=1,
                subplot_titles=selected_features,
                vertical_spacing=0.05
            )

            for i, feature in enumerate(selected_features, 1):
                fig_ext.add_trace(
                    go.Scatter(
                        x=df_ext['Tanggal'],
                        y=df_ext[feature],
                        mode='lines',
                        name=feature,
                        line=dict(width=2)
                    ),
                    row=i, col=1
                )

                fig_ext.update_yaxes(title_text=feature, row=i, col=1)

            fig_ext.update_layout(
                height=300 * len(selected_features),
                showlegend=False,
                title_text="External Features Time Series"
            )
            fig_ext.update_xaxes(title_text="Tanggal", row=len(selected_features), col=1)

            st.plotly_chart(fig_ext, width='stretch')

            # Correlation with SDV Categories
            st.markdown("**🔗 Korelasi dengan Kategori SDV**")

            # Get all SDV categories data
            categories = ['A', 'B', 'C', 'D']
            category_labels = {
                'A': 'KORPORASI',
                'B': 'INDIVIDU',
                'C': 'NON RESIDEN',
                'D': 'NET SDV'
            }

            # Build SDV dataframe with all categories
            sdv_data = {'Tanggal': pd.to_datetime(time_cols)}
            for cat_id, cat_label in category_labels.items():
                cat_row = df[df['Row_ID'] == cat_id]
                if len(cat_row) > 0:
                    sdv_data[cat_label] = cat_row[time_cols].values.flatten()

            df_sdv = pd.DataFrame(sdv_data)

            # Merge with external features
            df_merged = pd.merge(df_ext, df_sdv, on='Tanggal', how='inner')

            if len(df_merged) > 0:
                # Calculate correlations for each feature with each SDV category
                corr_matrix_data = []

                for feature in selected_features:
                    corr_row = {'Feature': feature}
                    for cat_label in category_labels.values():
                        if cat_label in df_merged.columns:
                            corr = df_merged[cat_label].corr(df_merged[feature])
                            corr_row[cat_label] = corr
                    corr_matrix_data.append(corr_row)

                corr_matrix_df = pd.DataFrame(corr_matrix_data)

                # Create heatmap
                fig_corr_heatmap = go.Figure(data=go.Heatmap(
                    z=corr_matrix_df[list(category_labels.values())].values,
                    x=list(category_labels.values()),
                    y=corr_matrix_df['Feature'],
                    colorscale='RdBu',
                    zmid=0,
                    text=corr_matrix_df[list(category_labels.values())].values.round(3),
                    texttemplate='%{text}',
                    textfont={"size": 11},
                    colorbar=dict(title="Korelasi")
                ))

                fig_corr_heatmap.update_layout(
                    title="Heatmap: Korelasi External Features dengan Kategori SDV",
                    xaxis_title="Kategori SDV",
                    yaxis_title="External Feature",
                    height=max(400, len(selected_features) * 80),
                    xaxis={'side': 'bottom'}
                )

                st.plotly_chart(fig_corr_heatmap, width='stretch')

        # Statistics table
        st.markdown("**📊 Statistik Ringkasan External Features**")

        stats_ext = []
        for col in feature_cols:
            stats_ext.append({
                'Feature': col,
                'Mean': f"{df_ext[col].mean():.2f}",
                'Median': f"{df_ext[col].median():.2f}",
                'Std': f"{df_ext[col].std():.2f}",
                'Min': f"{df_ext[col].min():.2f}",
                'Max': f"{df_ext[col].max():.2f}",
                'Missing': df_ext[col].isna().sum()
            })

        stats_ext_df = pd.DataFrame(stats_ext)
        st.dataframe(stats_ext_df, width='stretch', hide_index=True)

    except FileNotFoundError:
        st.warning("⚠️ File external_features.xlsx tidak ditemukan")
        st.info("Jalankan **Scrape & Update Sentiment** di halaman **Fitur Eksternal** untuk membuat file ini")
    except Exception as e:
        st.error(f"Error loading external features: {e}")
