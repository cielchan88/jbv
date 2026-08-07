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

    st.plotly_chart(fig_d, use_container_width=True)

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

                st.plotly_chart(fig, use_container_width=True)

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

            st.plotly_chart(fig, use_container_width=True)

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

            st.plotly_chart(fig, use_container_width=True)

st.divider()

# Advanced Analytics Section
st.subheader("📊 Analisis Lanjutan")

tabs = st.tabs(["🔍 Trend Decomposition", "🔗 Correlation Heatmap", "📦 Distribution Box Plot", "🌍 External Features"])

# Tab 1: Trend Decomposition
with tabs[0]:
    st.markdown("**Dekomposisi Time Series** - Pisahkan komponen Trend, Seasonal, dan Residual dari Net Supply Demand Valas")

    # Use D (NET SDV) directly - no selectbox
    series_data = df[df['Row_ID'] == 'D']
    if len(series_data) > 0:
        decomp_values = series_data[time_cols].values.flatten()
        decomp_dates = pd.to_datetime(time_cols)

        # Create time series
        ts = pd.Series(decomp_values, index=decomp_dates)

        # Perform decomposition (weekly seasonality: period=7)
        try:
            decomposition = seasonal_decompose(ts, model='additive', period=7, extrapolate_trend='freq')

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

            fig_decomp.update_layout(height=800, showlegend=False, title_text="Decomposition: Net Supply Demand Valas")
            fig_decomp.update_xaxes(title_text="Tanggal", row=4, col=1)

            st.plotly_chart(fig_decomp, use_container_width=True)

            # Insights
            st.info("""
            **📌 Insights:**
            - **Trend**: Arah umum data (naik/turun jangka panjang)
            - **Seasonal**: Pola berulang (mingguan dalam kasus ini)
            - **Residual**: Noise atau variasi yang tidak terjelaskan
            """)

        except Exception as e:
            st.error(f"Error saat decomposition: {str(e)}")
            st.info("Data mungkin tidak cukup panjang untuk analisis seasonal.")

# Tab 2: Correlation Heatmap
with tabs[1]:
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

    st.plotly_chart(fig_corr, use_container_width=True)

# Tab 3: Distribution Box Plot
with tabs[2]:
    st.markdown("**Distribution Analysis** - Distribusi dan volatilitas masing-masing kategori")

    # Get main categories data
    box_data = []
    box_labels = []

    for cat in ['A', 'B', 'C', 'D']:
        cat_row = df[df['Row_ID'] == cat]
        if len(cat_row) > 0:
            values = cat_row.iloc[0][time_cols].values
            box_data.append(values)
            box_labels.append(category_labels[cat])

    # Create box plot
    fig_box = go.Figure()

    for i, (data, label) in enumerate(zip(box_data, box_labels)):
        fig_box.add_trace(go.Box(
            y=data,
            name=label,
            boxmean='sd'  # Show mean and standard deviation
        ))

    fig_box.update_layout(
        title="Distribusi Nilai per Kategori (dengan Mean & Std Dev)",
        yaxis_title="Nilai (USD Juta)",
        height=500,
        showlegend=True
    )

    st.plotly_chart(fig_box, use_container_width=True)

    # Statistics table
    st.markdown("**📊 Statistik Ringkasan**")

    stats_data = []
    for data, label in zip(box_data, box_labels):
        stats_data.append({
            'Kategori': label,
            'Mean': f"{np.mean(data):.2f}",
            'Median': f"{np.median(data):.2f}",
            'Std Dev': f"{np.std(data):.2f}",
            'Min': f"{np.min(data):.2f}",
            'Max': f"{np.max(data):.2f}",
            'Range': f"{np.max(data) - np.min(data):.2f}"
        })

    stats_df = pd.DataFrame(stats_data)
    st.dataframe(stats_df, use_container_width=True, hide_index=True)

    st.info("""
    **📌 Insights:**
    - **Box**: Range dari Q1 (25%) hingga Q3 (75%) - ini adalah 50% data tengah
    - **Line dalam box**: Median (nilai tengah)
    - **Diamond**: Mean (rata-rata)
    - **Whiskers**: Min dan Max (atau 1.5×IQR)
    - **Dots**: Outliers (nilai ekstrem)
    - **Std Dev lebih besar** = Lebih volatile/bervariasi
    """)

# Tab 4: External Features
with tabs[3]:
    st.markdown("**External Features** - Fitur eksternal yang digunakan untuk forecasting")

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

            st.plotly_chart(fig_ext, use_container_width=True)

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

                st.plotly_chart(fig_corr_heatmap, use_container_width=True)

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
        st.dataframe(stats_ext_df, use_container_width=True, hide_index=True)

    except FileNotFoundError:
        st.warning("⚠️ File external_features.xlsx tidak ditemukan")
        st.info("Upload data Trading Economics di halaman **Scraper** untuk menampilkan external features")
    except Exception as e:
        st.error(f"Error loading external features: {e}")
