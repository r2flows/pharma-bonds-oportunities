import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import matplotlib

# Configuración de la página
st.set_page_config(page_title="Análisis de Compras y Productos POS", layout="wide")
st.title("Análisis de Compras Reales vs Potenciales por Punto de Venta")

# Funciones de utilidad
def get_status_description(status):
    """
    Convierte un código de status numérico en su descripción correspondiente
    """
    if pd.isna(status): 
        return "Sin Status"
    
    status_map = {
        0: "Rechazado", 
        1: "Activo", 
        2: "Pendiente",
        -1: "Sin conectar"
    }
    
    return status_map.get(status, f"Status {status}")

def safe_get_status_description(status):
    """
    Función segura para obtener descripción del status,
    manejando valores None, NaN o no válidos
    """
    if pd.isna(status) or status is None:
        return "Sin conectar"
    
    try:
        status = int(status)
        return get_status_description(status)
    except (ValueError, TypeError):
        return "Sin definir"

def obtener_status_vendor(vendor_id, pos_id, df_vendors_pos):
    """
    Obtiene el status de un vendor para un punto de venta específico
    """
    if df_vendors_pos.empty:
        return np.nan
        
    vendor_id = pd.to_numeric(vendor_id, errors='coerce')
    pos_id = pd.to_numeric(pos_id, errors='coerce')
    
    if 'vendor_id' in df_vendors_pos.columns and 'point_of_sale_id' in df_vendors_pos.columns and 'status' in df_vendors_pos.columns:
        df_vendors_pos_copy = df_vendors_pos.copy()
        df_vendors_pos_copy['vendor_id'] = pd.to_numeric(df_vendors_pos_copy['vendor_id'], errors='coerce')
        df_vendors_pos_copy['point_of_sale_id'] = pd.to_numeric(df_vendors_pos_copy['point_of_sale_id'], errors='coerce')
        
        relacion = df_vendors_pos_copy[
            (df_vendors_pos_copy['vendor_id'] == vendor_id) & 
            (df_vendors_pos_copy['point_of_sale_id'] == pos_id)
        ]
        
        if not relacion.empty:
            return relacion['status'].iloc[0]
    
    return np.nan

def obtener_geo_zone(address):
    """
    Extrae la zona geográfica de una dirección
    """
    partes = address.split(', ')
    return ', '.join(partes[-2:-1])

def load_vendors_dm():
    """
    Carga y procesa el archivo vendors_dm.csv
    """
    try:
        df_vendor_dm = pd.read_csv('vendors_dm.csv')
        if 'client_id' in df_vendor_dm.columns and 'vendor_id' not in df_vendor_dm.columns:
            df_vendor_dm.rename(columns={'client_id': 'vendor_id'}, inplace=True)
        return df_vendor_dm
    except Exception as e:
        print(f"Error al procesar vendors_dm.csv: {e}")
        return pd.DataFrame(columns=['vendor_id', 'name', 'drug_manufacturer_id'])

def agregar_columna_clasificacion(df):
    """
    Agrega una columna de clasificación según las reglas de precio
    """
    if df.empty:
        return df
        
    result_df = df.copy()
    result_df['clasificacion'] = ""
    
    # Verificar que las columnas necesarias existan
    required_cols = ['order_id', 'super_catalog_id', 'precio_minimo', 'precio_vendedor']
    missing_cols = [col for col in required_cols if col not in result_df.columns]
    
    if missing_cols:
        st.warning(f"Columnas faltantes para clasificación: {missing_cols}")
        return result_df
    
    grupos = result_df.groupby(['order_id', 'super_catalog_id'])
    
    for (order_id, product_id), group in grupos:
        precio_minimo = group['precio_minimo'].iloc[0]
        min_precio_vendedor = group['precio_vendedor'].min()
        
        indices = group.index
        
        for idx in indices:
            precio_vendedor = result_df.loc[idx, 'precio_vendedor']
            
            if precio_minimo < precio_vendedor:
                result_df.loc[idx, 'clasificacion'] = "Precio droguería minimo"
            else:
                if precio_vendedor == min_precio_vendedor:
                    result_df.loc[idx, 'clasificacion'] = "Precio vendor minimo"
                else:
                    result_df.loc[idx, 'clasificacion'] = "Precio vendor no minimo"
    
    return result_df

def crear_dashboard_ejecutivo_ahorro(df_clasificado, selected_pos):
    """
    Crea un dashboard ejecutivo con KPIs principales de ahorro
    """
    if df_clasificado.empty:
        st.warning("No hay datos para crear el dashboard ejecutivo")
        return
        
    df_pos = df_clasificado[df_clasificado['point_of_sale_id'] == selected_pos].copy()
    
    if df_pos.empty:
        st.warning("No hay datos para el POS seleccionado")
        return
    
    st.subheader("🎯 Dashboard Ejecutivo de Oportunidades de Ahorro")
    
    # Calcular KPIs principales
    total_comprado = df_pos['valor_vendedor'].sum() if 'valor_vendedor' in df_pos.columns else 0
    total_optimo = df_pos.groupby(['order_id', 'super_catalog_id'])['precio_total_vendedor'].min().sum() if 'precio_total_vendedor' in df_pos.columns else 0
    ahorro_maximo = total_comprado - total_optimo
    ahorro_pct = (ahorro_maximo / total_comprado * 100) if total_comprado > 0 else 0
    
    # Vendors con oportunidad
    vendors_con_ahorro = 0
    if 'vendor_id' in df_pos.columns and 'clasificacion' in df_pos.columns:
        vendors_con_ahorro = df_pos[
            df_pos['clasificacion'].isin(['Precio vendor minimo', 'Precio droguería minimo'])
        ]['vendor_id'].nunique()
    
    # Productos optimizables
    productos_optimizables = 0
    if 'valor_vendedor' in df_pos.columns and 'precio_total_vendedor' in df_pos.columns:
        productos_optimizables = df_pos[
            df_pos['valor_vendedor'] > df_pos['precio_total_vendedor']
        ]['super_catalog_id'].nunique()
    
    # Primera fila de métricas
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "💰 Ahorro Potencial Máximo",
            f"${ahorro_maximo:,.0f}",
            f"{ahorro_pct:.1f}% del total"
        )
    
    with col2:
        st.metric(
            "📊 Gasto Actual Total",
            f"${total_comprado:,.0f}",
            "Baseline actual"
        )
    
    with col3:
        st.metric(
            "🎯 Gasto Óptimo Posible",
            f"${total_optimo:,.0f}",
            f"-${ahorro_maximo:,.0f}"
        )
    
    with col4:
        roi = (ahorro_maximo / total_comprado * 100) if total_comprado > 0 else 0
        st.metric(
            "📈 ROI Potencial",
            f"{roi:.1f}%",
            "Retorno por optimización"
        )
    
    # Segunda fila de métricas
    st.write("")
    col5, col6, col7, col8 = st.columns(4)
    
    with col5:
        st.metric(
            "🏭 Vendors con Oportunidad",
            f"{vendors_con_ahorro}",
            "Con mejores precios"
        )
    
    with col6:
        st.metric(
            "📦 Productos Optimizables",
            f"{productos_optimizables}",
            "Con alternativas más baratas"
        )
    
    with col7:
        ordenes_afectadas = df_pos['order_id'].nunique() if 'order_id' in df_pos.columns else 0
        st.metric(
            "🛒 Órdenes Analizadas",
            f"{ordenes_afectadas}",
            "En el período"
        )
    
    with col8:
        vendors_activos = 0
        vendors_no_activos = 0
        if 'status' in df_pos.columns and 'vendor_id' in df_pos.columns:
            vendors_activos = df_pos[df_pos['status'] == 1]['vendor_id'].nunique()
            vendors_no_activos = df_pos[df_pos['status'].isin([0, 2])]['vendor_id'].nunique()
        
        st.metric(
            "✅ Vendors Activos",
            f"{vendors_activos}",
            f"{vendors_no_activos} por activar"
        )

def generar_recomendaciones_cambio_vendor(df_clasificado, selected_pos, umbral_ahorro=0.1):
    """
    Genera recomendaciones de cambio de vendor basadas en ahorro potencial
    """
    df_pos = df_clasificado[df_clasificado['point_of_sale_id'] == selected_pos].copy()
    
    if df_pos.empty:
        return pd.DataFrame()
    
    recomendaciones = []
    
    required_cols = ['super_catalog_id', 'order_id', 'valor_vendedor', 'vendor_id_x', 
                    'unidades_pedidas', 'precio_total_vendedor', 'vendor_id', 'status', 
                    'precio_minimo', 'precio_vendedor']
    
    missing_cols = [col for col in required_cols if col not in df_pos.columns]
    if missing_cols:
        st.warning(f"Columnas faltantes para recomendaciones: {missing_cols}")
        return pd.DataFrame()
    
    # Agrupar por producto y orden
    for (producto, orden), grupo in df_pos.groupby(['super_catalog_id', 'order_id']):
        if grupo.empty:
            continue
            
        # Encontrar precio actual
        precio_actual = grupo['valor_vendedor'].iloc[0]
        vendor_actual = grupo['vendor_id_x'].iloc[0]
        unidades = grupo['unidades_pedidas'].iloc[0]
        
        # Encontrar mejor alternativa
        mejor_idx = grupo['precio_total_vendedor'].idxmin()
        mejor_alternativa = grupo.loc[mejor_idx]
        
        ahorro = precio_actual - mejor_alternativa['precio_total_vendedor']
        ahorro_pct = (ahorro / precio_actual) if precio_actual > 0 else 0
        
        if ahorro_pct >= umbral_ahorro:
            recomendaciones.append({
                'producto_id': producto,
                'orden_id': orden,
                'unidades': unidades,
                'drogueria_actual': vendor_actual,
                'vendor_recomendado': mejor_alternativa['vendor_id'],
                'status_vendor': get_status_description(mejor_alternativa['status']),
                'precio_actual_unitario': mejor_alternativa['precio_minimo'],
                'precio_recomendado_unitario': mejor_alternativa['precio_vendedor'],
                'ahorro_total': ahorro,
                'ahorro_porcentaje': ahorro_pct * 100,
                'prioridad': 'Alta' if ahorro > 1000 else ('Media' if ahorro > 500 else 'Baja')
            })
    
    df_recomendaciones = pd.DataFrame(recomendaciones)
    
    if not df_recomendaciones.empty:
        df_recomendaciones = df_recomendaciones.sort_values('ahorro_total', ascending=False)
    
    return df_recomendaciones

def calcular_impacto_activacion_vendors(df_clasificado, df_vendors_pos, selected_pos):
    """
    Calcula el impacto potencial de activar vendors pendientes o rechazados
    """
    df_pos = df_clasificado[df_clasificado['point_of_sale_id'] == selected_pos].copy()
    
    if df_pos.empty:
        return pd.DataFrame()
    
    # Identificar la columna correcta de vendor
    vendor_col = None
    if 'vendor_id_y' in df_pos.columns:
        vendor_col = 'vendor_id_y'
    elif 'vendor_id' in df_pos.columns:
        vendor_col = 'vendor_id'
    
    if vendor_col is None or 'status' not in df_pos.columns:
        return pd.DataFrame()
    
    # Identificar vendors no activos con potencial
    vendors_no_activos = df_pos[df_pos['status'].isin([0, 2])][vendor_col].unique()
    
    impacto = []
    
    for vendor in vendors_no_activos:
        df_vendor = df_pos[df_pos[vendor_col] == vendor]
        
        if df_vendor.empty:
            continue
        
        # Calcular productos donde este vendor tiene mejor precio
        productos_ganadores = 0
        if 'clasificacion' in df_vendor.columns:
            productos_ganadores = df_vendor[
                df_vendor['clasificacion'] == 'Precio vendor minimo'
            ]['super_catalog_id'].nunique()
        
        # Calcular ahorro potencial
        ahorro_potencial = 0
        for _, row in df_vendor.iterrows():
            # Comparar con precio actual de la droguería
            productos_mismo = df_pos[
                (df_pos['super_catalog_id'] == row['super_catalog_id']) &
                (df_pos['order_id'] == row['order_id'])
            ]
            if not productos_mismo.empty and 'valor_vendedor' in productos_mismo.columns and 'precio_total_vendedor' in row:
                precio_actual = productos_mismo['valor_vendedor'].iloc[0]
                ahorro = precio_actual - row['precio_total_vendedor']
                if ahorro > 0:
                    ahorro_potencial += ahorro
        
        status = df_vendor['status'].iloc[0] if not df_vendor.empty else None
        
        impacto.append({
            'vendor_id': vendor,
            'status_actual': get_status_description(status),
            'productos_con_mejor_precio': productos_ganadores,
            'ahorro_potencial_total': ahorro_potencial,
            'productos_totales': df_vendor['super_catalog_id'].nunique(),
            'ordenes_afectadas': df_vendor['order_id'].nunique()
        })
    
    df_impacto = pd.DataFrame(impacto)
    
    if not df_impacto.empty:
        df_impacto = df_impacto.sort_values('ahorro_potencial_total', ascending=False)
    
    return df_impacto

@st.cache_data
def load_and_process_data():
    """Función principal que procesa todos los datos necesarios"""
    try:
        # Cargar archivos básicos
        df_pos_address = pd.read_csv('pos_address.csv')
        df_pedidos = pd.read_csv('orders_delivered_pos_vendor_geozone.csv')
        df_proveedores = pd.read_csv('vendors_catalog.csv')
        df_vendors_pos = pd.read_csv('vendor_pos_relations.csv')
        #df_products = pd.read_csv('top_5_productos_geozona.csv')
        df_vendor_dm = load_vendors_dm()
        
        try:
            df_min_purchase = pd.read_csv('minimum_purchase.csv')
        except FileNotFoundError:
            df_min_purchase = pd.DataFrame(columns=['vendor_id', 'name', 'min_purchase'])
        
        # Procesar dirección y geo_zone
        df_pos_address['geo_zone'] = df_pos_address['address'].apply(obtener_geo_zone)
        
        # Limpiar columnas duplicadas
        if 'geo_zone' in df_pedidos.columns:
            df_pedidos = df_pedidos.drop(columns=['geo_zone'])
            
        # Normalizar datos
        df_proveedores['percentage'].fillna(0, inplace=True)
        pos_geo_zones = df_pos_address[['point_of_sale_id', 'geo_zone']].copy()
        
        # Reemplazar abreviaturas
        abreviaturas = {
            'B.C.S.': 'Baja California Sur', 'Qro.': 'Querétaro', 'Jal.': 'Jalisco',
            'Pue.': 'Puebla', 'Méx.': 'CDMX', 'Oax.': 'Oaxaca', 'Chih.': 'Chihuahua',
            'Coah.': 'Coahuila de Zaragoza', 'Mich.': 'Michoacán de Ocampo',
            'Ver.': 'Veracruz de Ignacio de la Llave', 'Chis.': 'Chiapas',
            'N.L.': 'Nuevo León', 'Hgo.': 'Hidalgo', 'Tlax.': 'Tlaxcala',
            'Tamps.': 'Tamaulipas', 'Yuc.': 'Yucatan', 'Mor.': 'Morelos',
            'Sin.': 'Sinaloa', 'S.L.P.': 'San Luis Potosí', 'Q.R.': 'Quintana Roo',
            'Dgo.': 'Durango', 'B.C.': 'Baja California', 'Gto.': 'Guanajuato',
            'Camp.': 'Campeche', 'Tab.': 'Tabasco', 'Son.': 'Sonora',
            'Gro.': 'Guerrero', 'Zac.': 'Zacatecas', 'Ags.': 'Aguascalientes',
            'Nay.': 'Nayarit'
        }
        pos_geo_zones['geo_zone'] = pos_geo_zones['geo_zone'].replace(abreviaturas)
        
        # Separar proveedores nacionales y regionales
        df_proveedores_nacional = df_proveedores[df_proveedores['name'] == 'México'].copy()
        df_proveedores_regional = df_proveedores[df_proveedores['name'] != 'México'].copy()
        
        # Unir pedidos con zonas geográficas
        df_pedidos_zonas = pd.merge(df_pedidos, pos_geo_zones, on='point_of_sale_id', how='left')
        df_pedidos_zonas = df_pedidos_zonas[df_pedidos_zonas['unidades_pedidas'] > 0]
        
        # Procesar con proveedores nacionales y regionales
        df_pedidos_proveedores_nacional = pd.merge(
            df_pedidos_zonas, df_proveedores_nacional, on='super_catalog_id', how='inner'
        )
        df_pedidos_proveedores_nacional = df_pedidos_proveedores_nacional[
            df_pedidos_proveedores_nacional['unidades_pedidas'] > 0
        ]
        
        df_pedidos_proveedores_regional = pd.merge(
            df_pedidos_zonas, df_proveedores_regional, 
            left_on=['super_catalog_id', 'geo_zone'], right_on=['super_catalog_id', 'name'], 
            how='inner'
        )
        df_pedidos_proveedores_regional = df_pedidos_proveedores_regional[
            df_pedidos_proveedores_regional['unidades_pedidas'] > 0
        ]
        
        # Convertir tipos de datos para cálculos correctos
        for df in [df_pedidos_proveedores_nacional, df_pedidos_proveedores_regional]:
            df['base_price'] = df['base_price'].astype(float)
            df['percentage'] = df['percentage'].astype(float)
            df['precio_vendedor'] = df['base_price'] + (df['base_price'] * df['percentage'] / 100)
        
        # Unir dataframes
        df_pedidos_proveedores = pd.concat([
            df_pedidos_proveedores_regional, df_pedidos_proveedores_nacional
        ], axis=0, ignore_index=True)
        
        # Calcular precio_total_vendedor
        if 'precio_vendedor' in df_pedidos_proveedores.columns and 'unidades_pedidas' in df_pedidos_proveedores.columns:
            df_pedidos_proveedores['precio_total_vendedor'] = (
                df_pedidos_proveedores['unidades_pedidas'].astype(float) * 
                df_pedidos_proveedores['precio_vendedor'].astype(float)
            )
        
        # CORECCIÓN CRÍTICA: Manejo correcto del merge con vendor_pos_relations
        if 'vendor_id' in df_pedidos_proveedores.columns and 'point_of_sale_id' in df_pedidos_proveedores.columns:
            # Primero, renombrar la columna vendor_id original para evitar conflictos
            df_pedidos_proveedores = df_pedidos_proveedores.rename(columns={'vendor_id': 'drug_manufacturer_id'})
            
            # Hacer el merge manteniendo los nombres correctos
            df_pedidos_proveedores = pd.merge(
                df_pedidos_proveedores, 
                df_vendors_pos[['point_of_sale_id', 'vendor_id', 'status']],
                on='point_of_sale_id', 
                how='left'
            )
        
        # Calcular precios mínimos locales
        cols_needed = ['point_of_sale_id', 'super_catalog_id', 'precio_minimo', 'order_id']
        if all(col in df_pedidos_proveedores.columns for col in cols_needed):
            min_prices = (df_pedidos_proveedores
                         .groupby(['point_of_sale_id', 'order_id', 'super_catalog_id'])['precio_minimo']
                         .min()
                         .reset_index())
            min_prices.columns = ['point_of_sale_id', 'order_id', 'super_catalog_id', 'precio_minimo_orders']
            
            # Unir para comparar precios
            df_con_precios_minimos_local = pd.merge(
                df_pedidos_proveedores, min_prices,
                on=['point_of_sale_id', 'super_catalog_id', 'order_id'], how='left'
            )
            
            # Clasificar productos
            df_clasificado = agregar_columna_clasificacion(df_con_precios_minimos_local)
        else:
            df_clasificado = pd.DataFrame()
        
        # Calcular métricas para visualización
        df_orders = df_pedidos.copy()
        
        # Agregar total_compra si no existe
        if 'total_compra' not in df_orders.columns and 'unidades_pedidas' in df_orders.columns and 'precio_minimo' in df_orders.columns:
            df_orders['total_compra'] = df_orders['unidades_pedidas'] * df_orders['precio_minimo']
        
        # Calcular estadísticas por POS
        if all(col in df_orders.columns for col in ['point_of_sale_id', 'order_id', 'total_compra']):
            order_totals = df_orders.groupby(['point_of_sale_id', 'order_id'])['total_compra'].sum().reset_index()
            pos_order_stats = order_totals.groupby('point_of_sale_id').agg({
                'total_compra': ['mean', 'count']
            }).reset_index()
            pos_order_stats.columns = ['point_of_sale_id', 'promedio_por_orden', 'numero_ordenes']
        else:
            pos_order_stats = pd.DataFrame(columns=['point_of_sale_id', 'promedio_por_orden', 'numero_ordenes'])
        
        # Calcular totales por vendor
        if all(col in df_orders.columns for col in ['point_of_sale_id', 'vendor_id', 'total_compra']):
            pos_vendor_totals = df_orders.groupby(['point_of_sale_id', 'vendor_id'])['total_compra'].sum().reset_index()
        else:
            pos_vendor_totals = pd.DataFrame(columns=['point_of_sale_id', 'vendor_id', 'total_compra'])
        
        return pos_vendor_totals, df_pedidos, pos_order_stats, df_min_purchase, df_vendor_dm, pos_geo_zones, df_clasificado, df_vendors_pos
    
    except Exception as e:
        import traceback
        print("Error en load_and_process_data:", traceback.format_exc())
        empty_df = pd.DataFrame()
        return empty_df, empty_df, empty_df, empty_df, empty_df, empty_df, empty_df, empty_df

# Código principal
try:    
    pos_vendor_totals, df_original, pos_order_stats, df_min_purchase, df_vendor_dm, pos_geo_zones, df_clasificado, df_vendors_pos = load_and_process_data()
    
    # Filtro de punto de venta
    st.header("Análisis Individual de POS")
    pos_list = sorted(list(set(pos_vendor_totals['point_of_sale_id']))) if not pos_vendor_totals.empty else []
    
    if not pos_list:
        st.warning("No hay puntos de venta disponibles para analizar")
    else:
        selected_pos = st.selectbox("Seleccionar Punto de Venta", options=pos_list)

        # Mostrar información del POS seleccionado
        if selected_pos:
            # Filtrar datos para el POS seleccionado
            pos_data = pos_vendor_totals[pos_vendor_totals['point_of_sale_id'] == selected_pos]
            pos_data = pos_data.sort_values('total_compra', ascending=False) if not pos_data.empty else pd.DataFrame()

            # Obtener estadísticas
            pos_stats = pos_order_stats[pos_order_stats['point_of_sale_id'] == selected_pos]
            promedio_por_orden = pos_stats.iloc[0]['promedio_por_orden'] if not pos_stats.empty else 0
            numero_ordenes = int(pos_stats.iloc[0]['numero_ordenes']) if not pos_stats.empty else 0
                
            st.subheader("Información del Punto de Venta")

            # Métricas principales
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(f"Total de Compras - POS {selected_pos}", 
                          f"${pos_data['total_compra'].sum():,.2f}" if not pos_data.empty else "$0.00")
            with col2:
                st.metric("Promedio por Orden", f"${promedio_por_orden:,.2f}")
            with col3:
                st.metric("Número de Órdenes", f"{numero_ordenes:,}")

            # Información adicional
            pos_info = pos_geo_zones[pos_geo_zones['point_of_sale_id'] == selected_pos]
            pos_country = df_original[df_original['point_of_sale_id'] == selected_pos]

            country = pos_country['country'].iloc[0] if not pos_country.empty and 'country' in pos_country.columns else 'No disponible'
            geo_zone = pos_info['geo_zone'].iloc[0] if not pos_info.empty and 'geo_zone' in pos_info.columns else 'No disponible'

            info_col1, info_col2, info_col3 = st.columns(3)
            
            with info_col1:
                st.metric("País", country)
            with info_col2:
                st.metric("Zona Geográfica", geo_zone)
            with info_col3:
                st.metric("Total Vendors", len(pos_data) if not pos_data.empty else 0)

            # Detalle de compras
            st.subheader("Detalle de Compras por Droguería/Vendor")
            if not pos_data.empty:
                pos_data['porcentaje'] = (pos_data['total_compra'] / pos_data['total_compra'].sum()) * 100    
                detail_table = pos_data.copy()
                detail_table.columns = ['POS ID', 'Droguería/Vendor ID', 'Total Comprado', 'Porcentaje']
                detail_table = detail_table.round({'Porcentaje': 2})
                
                st.dataframe(
                    detail_table.style.format({
                        'Total Comprado': '${:,.2f}',
                        'Porcentaje': '{:.2f}%'
                    })
                )

                # NUEVA SECCIÓN: Análisis de Oportunidades de Ahorro por Producto
                st.header("📊 Análisis Detallado de Oportunidades de Ahorro por Producto")

                # Verificar si tenemos los datos necesarios
                if not df_clasificado.empty and selected_pos:
                    # Filtrar datos para el POS seleccionado
                    df_pos_clasificado = df_clasificado[df_clasificado['point_of_sale_id'] == selected_pos].copy()
                    
                    if not df_pos_clasificado.empty:
                        
                        # Dashboard ejecutivo
                        #crear_dashboard_ejecutivo_ahorro(df_clasificado, selected_pos)

                        # Tabs para diferentes vistas
                        tab1, tab2 = st.tabs(["🏭 Análisis por Vendor", "📊 Análisis Detallado por Producto"])
                        
                        with tab1:
                            #st.subheader("🏭 Análisis Detallado de Potencial de Ahorro por Vendor")
                            
                            # Primero mostrar las columnas disponibles para debug
                            #st.write("**Columnas disponibles en los datos:**")

                            #st.write(list(df_pos_clasificado.columns))
                            
                            # Identificar las columnas correctas de vendor
                            vendor_col = None
                            if 'vendor_id_y' in df_pos_clasificado.columns:
                                vendor_col = 'vendor_id_y'  # Esta debería ser la columna del vendor del catálogo
                            elif 'vendor_id' in df_pos_clasificado.columns:
                                vendor_col = 'vendor_id'
                            
                            if vendor_col is None:
                                st.error("No se encontró la columna de vendor_id. Columnas disponibles:")
                                st.write(list(df_pos_clasificado.columns))
                                #return
                            
                            # Filtrar productos donde hay vendors disponibles (excluyendo solo productos de droguería)
                            productos_con_vendors = df_pos_clasificado[
                                df_pos_clasificado['clasificacion'].isin(['Precio vendor minimo', 'Precio vendor no minimo'])
                            ].copy()
                            
                            if not productos_con_vendors.empty:
                                #st.write(f"**Analizando {len(productos_con_vendors)} registros de productos con opciones de vendors disponibles**")
                                #st.write(f"**Usando columna de vendor: {vendor_col}**")
                                
                                # Agrupar por vendor y calcular potencial de ahorro
                                vendor_analysis = []
                                
                                for vendor_id in productos_con_vendors[vendor_col].unique():
                                    if pd.isna(vendor_id):
                                        continue
                                        
                                    vendor_products = productos_con_vendors[productos_con_vendors[vendor_col] == vendor_id]
                                    
                                    # Calcular métricas por vendor
                                    total_valor_drogueria = 0
                                    total_valor_vendor = 0
                                    productos_unicos = set()
                                    ordenes_uniques = set()
                                    productos_mejor_precio = 0
                                    
                                    for _, row in vendor_products.iterrows():
                                        # Buscar el precio actual de droguería para este producto y orden
                                        precio_drogueria_row = df_pos_clasificado[
                                            (df_pos_clasificado['super_catalog_id'] == row['super_catalog_id']) &
                                            (df_pos_clasificado['order_id'] == row['order_id']) &
                                            (df_pos_clasificado['clasificacion'] == 'Precio droguería minimo')
                                        ]
                                        
                                        if not precio_drogueria_row.empty:
                                            precio_drogueria = precio_drogueria_row['valor_vendedor'].iloc[0]
                                            precio_vendor = row['precio_total_vendedor']
                                            
                                            total_valor_drogueria += precio_drogueria
                                            total_valor_vendor += precio_vendor
                                            productos_unicos.add(row['super_catalog_id'])
                                            ordenes_uniques.add(row['order_id'])
                                            
                                            # Contar si este vendor tiene mejor precio
                                            if precio_vendor < precio_drogueria:
                                                productos_mejor_precio += 1
                                    
                                    if total_valor_drogueria > 0:  # Solo incluir vendors con comparaciones válidas
                                        ahorro_total = total_valor_drogueria - total_valor_vendor
                                        porcentaje_ahorro = (ahorro_total / total_valor_drogueria) * 100
                                        
                                        # Obtener status del vendor
                                        status_vendor = obtener_status_vendor(vendor_id, selected_pos, df_vendors_pos)
                                        
                                        vendor_analysis.append({
                                            'Vendor ID': int(vendor_id),
                                            'Status': get_status_description(status_vendor),
                                            'Productos Únicos': len(productos_unicos),
                                            'Órdenes Afectadas': len(ordenes_uniques),
                                            'Registros con Mejor Precio': productos_mejor_precio,
                                            'Valor Actual (Droguería)': total_valor_drogueria,
                                            'Valor con Vendor': total_valor_vendor,
                                            'Ahorro Potencial': ahorro_total,
                                            'Porcentaje Ahorro': porcentaje_ahorro,
                                            'Clasificación': 'Oportunidad Alta' if porcentaje_ahorro > 15 else ('Oportunidad Media' if porcentaje_ahorro > 5 else 'Oportunidad Baja')
                                        })
                                
                                if vendor_analysis:
                                    df_vendor_analysis = pd.DataFrame(vendor_analysis)
                                    df_vendor_analysis = df_vendor_analysis.sort_values('Ahorro Potencial', ascending=False)
                                    
                                    # Métricas resumen
                                    col1, col2, col3, col4 = st.columns(4)
                                    with col1:
                                        st.metric("Vendors Analizados", len(df_vendor_analysis))
                                    with col2:
                                        total_ahorro = df_vendor_analysis['Ahorro Potencial'].sum()
                                        st.metric("Ahorro Total Potencial", f"${total_ahorro:,.2f}")
                                    with col3:
                                        vendors_positivos = len(df_vendor_analysis[df_vendor_analysis['Ahorro Potencial'] > 0])
                                        st.metric("Vendors con Ahorro Positivo", vendors_positivos)
                                    with col4:
                                        vendors_activos = len(df_vendor_analysis[df_vendor_analysis['Status'] == 'Activo'])
                                        st.metric("Vendors Activos", vendors_activos)
                                    
                                    # Filtros
                                    col1, col2, col3 = st.columns(3)
                                    with col1:
                                        status_filter = st.multiselect(
                                            "Filtrar por Status:",
                                            options=df_vendor_analysis['Status'].unique(),
                                            default=df_vendor_analysis['Status'].unique()
                                        )
                                    with col2:
                                        ahorro_minimo = st.number_input(
                                            "Ahorro mínimo ($):",
                                            min_value=0.0,
                                            value=0.0,
                                            step=500.0
                                        )
                                    with col3:
                                        clasificacion_filter = st.multiselect(
                                            "Filtrar por Clasificación:",
                                            options=df_vendor_analysis['Clasificación'].unique(),
                                            default=df_vendor_analysis['Clasificación'].unique()
                                        )
                                    
                                    # Aplicar filtros
                                    df_filtrado = df_vendor_analysis[
                                        (df_vendor_analysis['Status'].isin(status_filter)) &
                                        (df_vendor_analysis['Ahorro Potencial'] >= ahorro_minimo) &
                                        (df_vendor_analysis['Clasificación'].isin(clasificacion_filter))
                                    ]
                                    
                                    # Función para colorear status
                                    def color_status(val):
                                        if val == "Activo":
                                            return 'background-color: #90EE90'
                                        elif val == "Pendiente":
                                            return 'background-color: #FFD700'
                                        elif val == "Rechazado":
                                            return 'background-color: #ffcccb'
                                        else:
                                            return 'background-color: #e6f3ff'
                                    
                                    # Mostrar tabla
                                    styled_df = df_filtrado.style.format({
                                        'Valor Actual (Droguería)': '${:,.2f}',
                                        'Valor con Vendor': '${:,.2f}',
                                        'Ahorro Potencial': '${:,.2f}',
                                        'Porcentaje Ahorro': '{:.1f}%'
                                    }).applymap(color_status, subset=['Status']).background_gradient(subset=['Ahorro Potencial'], cmap='RdYlGn')
                                    
                                    st.dataframe(styled_df)
                                    
                                    # Gráfico de vendors con mayor potencial
                                    #if len(df_filtrado) > 0:
                                     #   fig_vendors = px.bar(
                                      #      df_filtrado.head(15),
                                       #     x='Vendor ID',
                                        #    y='Ahorro Potencial',
                                         #   color='Status',
                                          #  title='Top 15 Vendors por Ahorro Potencial',
                                           # labels={'Ahorro Potencial': 'Ahorro Potencial ($)'},
                                            #color_discrete_map={
                                        #        'Activo': '#51cf66',
                                         #       'Pendiente': '#ffd43b',
                                          #      'Rechazado': '#ff6b6b',
                                           #     'Sin Status': '#87ceeb'
                                            #}
                                        #)
                                        #fig_vendors.update_layout(xaxis_tickangle=-45)
                                        #st.plotly_chart(fig_vendors, use_container_width=True)
                                        
                                        # Análisis por status
                                        #st.subheader("Análisis por Status de Vendor")
                                        #status_summary = df_filtrado.groupby('Status').agg({
                                        #    'Ahorro Potencial': ['sum', 'mean', 'count'],
                                        #    'Vendor ID': 'count'
                                        #}).round(2)
                                        
                                        #status_summary.columns = ['Ahorro Total', 'Ahorro Promedio', 'Count1', 'Número de Vendors']
                                        #status_summary = status_summary.drop('Count1', axis=1)
                                        
                                        #st.dataframe(
                                        #    status_summary.style.format({
                                        #        'Ahorro Total': '${:,.2f}',
                                        #        'Ahorro Promedio': '${:,.2f}'
                                        #    })
                                        #)
                                #else:
                            #        st.warning("No se encontraron vendors con datos válidos para el análisis.")
                            #else:
                             #   st.warning("No se encontraron productos con opciones de vendors disponibles.")

                        #with tab2:
                         #   st.subheader("🚀 Impacto Potencial de Activación de Vendors")
                          #  df_impacto = calcular_impacto_activacion_vendors(df_clasificado, df_vendors_pos, selected_pos)

                           # if not df_impacto.empty:
                            #    st.dataframe(
                             #       df_impacto.style.format({
                              #          'ahorro_potencial_total': '${:,.2f}'
                               #     }).background_gradient(subset=['ahorro_potencial_total'], cmap='Blues')
                                #)
                                
                        #        total_impacto = df_impacto['ahorro_potencial_total'].sum()
                         #       st.success(
                          #          f"**Ahorro potencial activando vendors pendientes/rechazados:** ${total_impacto:,.2f}"
                           #     )
                            #else:
                             #   st.info("Todos los vendors con potencial de ahorro están activos.")

                        with tab2:
                            st.subheader("📊 Análisis Detallado Producto por Producto")
                            
                            # Identificar las columnas correctas de vendor
                            vendor_col = None
                            if 'vendor_id_y' in df_pos_clasificado.columns:
                                vendor_col = 'vendor_id_y'  # Esta debería ser la columna del vendor del catálogo
                            elif 'vendor_id' in df_pos_clasificado.columns:
                                vendor_col = 'vendor_id'
                            
                            drogueria_col = None
                            if 'vendor_id_x' in df_pos_clasificado.columns:
                                drogueria_col = 'vendor_id_x'  # Esta debería ser la columna de la droguería
                            elif 'drug_manufacturer_id' in df_pos_clasificado.columns:
                                drogueria_col = 'drug_manufacturer_id'
                            
                            if vendor_col is None or drogueria_col is None:
                                st.error(f"No se encontraron las columnas necesarias. Vendor: {vendor_col}, Droguería: {drogueria_col}")
                                st.write("Columnas disponibles:")
                                
                                st.write(list(df_pos_clasificado.columns))
                                #return
                            
                            # Crear análisis detallado producto por producto
                            productos_con_vendors = df_pos_clasificado[
                                df_pos_clasificado['clasificacion'].isin(['Precio vendor minimo', 'Precio vendor no minimo'])
                            ].copy()
                            
                            if not productos_con_vendors.empty:
                                # Crear análisis por producto
                                producto_analysis = []
                                
                                for producto_id in productos_con_vendors['super_catalog_id'].unique():
                                    for order_id in productos_con_vendors[productos_con_vendors['super_catalog_id'] == producto_id]['order_id'].unique():
                                        
                                        # Obtener precio de droguería para este producto y orden
                                        precio_drogueria_row = df_pos_clasificado[
                                            (df_pos_clasificado['super_catalog_id'] == producto_id) &
                                            (df_pos_clasificado['order_id'] == order_id) &
                                            (df_pos_clasificado['clasificacion'] == 'Precio droguería minimo')
                                        ]
                                        
                                        if not precio_drogueria_row.empty:
                                            precio_drogueria = precio_drogueria_row['valor_vendedor'].iloc[0]
                                            drogueria_id = precio_drogueria_row[drogueria_col].iloc[0]
                                            unidades = precio_drogueria_row['unidades_pedidas'].iloc[0]
                                            precio_unitario_drogueria = precio_drogueria_row['precio_minimo'].iloc[0]
                                            
                                            # Obtener todas las opciones de vendors para este producto y orden
                                            vendor_options = productos_con_vendors[
                                                (productos_con_vendors['super_catalog_id'] == producto_id) &
                                                (productos_con_vendors['order_id'] == order_id)
                                            ]
                                            
                                            # Encontrar la mejor opción de vendor
                                            if not vendor_options.empty:
                                                mejor_vendor = vendor_options.loc[vendor_options['precio_total_vendedor'].idxmin()]
                                                
                                                ahorro_mejor = precio_drogueria - mejor_vendor['precio_total_vendedor']
                                                porcentaje_ahorro_mejor = (ahorro_mejor / precio_drogueria * 100) if precio_drogueria > 0 else 0
                                                
                                                # Obtener status si está disponible
                                                status_mejor_vendor = "Sin Status"
                                                if 'status' in mejor_vendor:
                                                    status_mejor_vendor = get_status_description(mejor_vendor['status'])
                                                
                                                producto_analysis.append({
                                                    'Producto ID': producto_id,
                                                    'Orden ID': order_id,
                                                    'Unidades': unidades,
                                                    'Droguería ID': drogueria_id,
                                                    'Precio Unit. Droguería': precio_unitario_drogueria,
                                                    'Precio Total Droguería': precio_drogueria,
                                                    'Opciones Vendors': len(vendor_options),
                                                    'Mejor Vendor ID': mejor_vendor[vendor_col],
                                                    'Status Mejor Vendor': status_mejor_vendor,
                                                    'Precio Unit. Mejor Vendor': mejor_vendor['precio_vendedor'],
                                                    'Precio Total Mejor Vendor': mejor_vendor['precio_total_vendedor'],
                                                    'Ahorro con Mejor Vendor': ahorro_mejor,
                                                    'Porcentaje Ahorro': porcentaje_ahorro_mejor,
                                                    'Tipo Ahorro': 'Alto' if porcentaje_ahorro_mejor > 20 else ('Medio' if porcentaje_ahorro_mejor > 10 else 'Bajo')
                                                })
                                
                                if producto_analysis:
                                    df_producto_analysis = pd.DataFrame(producto_analysis)
                                    df_producto_analysis = df_producto_analysis.sort_values('Ahorro con Mejor Vendor', ascending=False)
                                    
                                    # Métricas resumen
                                    col1, col2, col3, col4 = st.columns(4)
                                    with col1:
                                        st.metric("Productos Analizados", len(df_producto_analysis))
                                    with col2:
                                        total_ahorro_productos = df_producto_analysis['Ahorro con Mejor Vendor'].sum()
                                        st.metric("Ahorro Total Productos", f"${total_ahorro_productos:,.2f}")
                                    with col3:
                                        productos_con_ahorro = len(df_producto_analysis[df_producto_analysis['Ahorro con Mejor Vendor'] > 0])
                                        st.metric("Productos con Ahorro", productos_con_ahorro)
                                    with col4:
                                        promedio_opciones = df_producto_analysis['Opciones Vendors'].mean()
                                        st.metric("Promedio Opciones/Producto", f"{promedio_opciones:.1f}")
                                    
                                    # Filtros para productos
                                    col1, col2, col3 = st.columns(3)
                                    with col1:
                                        ahorro_min_producto = st.number_input(
                                            "Ahorro mínimo por producto ($):",
                                            min_value=0.0,
                                            value=0.0,
                                            step=100.0,
                                            key="ahorro_min_producto"
                                        )
                                    with col2:
                                        tipo_ahorro_filter = st.multiselect(
                                            "Filtrar por Tipo de Ahorro:",
                                            options=['Alto', 'Medio', 'Bajo'],
                                            default=['Alto', 'Medio'],
                                            key="tipo_ahorro_filter"
                                        )
                                    with col3:
                                        status_vendor_filter = st.multiselect(
                                            "Status del Mejor Vendor:",
                                            options=df_producto_analysis['Status Mejor Vendor'].unique(),
                                            default=df_producto_analysis['Status Mejor Vendor'].unique(),
                                            key="status_vendor_filter"
                                        )
                                    
                                    # Aplicar filtros
                                    df_productos_filtrado = df_producto_analysis[
                                        (df_producto_analysis['Ahorro con Mejor Vendor'] >= ahorro_min_producto) &
                                        (df_producto_analysis['Tipo Ahorro'].isin(tipo_ahorro_filter)) &
                                        (df_producto_analysis['Status Mejor Vendor'].isin(status_vendor_filter))
                                    ]
                                    
                                    # Mostrar tabla de productos
                                    st.write(f"**Mostrando {len(df_productos_filtrado)} productos de {len(df_producto_analysis)} totales**")
                                    
                                    styled_productos = df_productos_filtrado.style.format({
                                        'Precio Unit. Droguería': '${:,.2f}',
                                        'Precio Total Droguería': '${:,.2f}',
                                        'Precio Unit. Mejor Vendor': '${:,.2f}',
                                        'Precio Total Mejor Vendor': '${:,.2f}',
                                        'Ahorro con Mejor Vendor': '${:,.2f}',
                                        'Porcentaje Ahorro': '{:.1f}%',
                                        'Unidades': '{:,.0f}'
                                    }).background_gradient(subset=['Ahorro con Mejor Vendor'], cmap='RdYlGn')
                                    
                                    st.dataframe(styled_productos, height=400)
                                    
                                    # Gráficos adicionales
                                    if len(df_productos_filtrado) > 0:
                                        #col1, col2 = st.columns(2)
                                        
                                        #with col1:
                                            # Distribución de ahorro por tipo
                                        tipo_ahorro_dist = df_productos_filtrado.groupby('Tipo Ahorro')['Ahorro con Mejor Vendor'].sum().reset_index()
                                        fig_tipo = px.pie(
                                            tipo_ahorro_dist,
                                            values='Ahorro con Mejor Vendor',
                                            names='Tipo Ahorro',
                                            title='Distribución de Ahorro por Tipo'
                                        )
                                        st.plotly_chart(fig_tipo, use_container_width=True)
                                    
                                    #with col2:
                                        # Top productos con mayor ahorro
                                        #   top_productos = df_productos_filtrado.head(10)
                                        #  fig_productos = px.bar(
                                        #     top_productos,
                                        #    x='Producto ID',
                                            #   y='Ahorro con Mejor Vendor',
                                            #  color='Tipo Ahorro',
                                            # title='Top 10 Productos con Mayor Ahorro'
                                        #)
                                        #fig_productos.update_layout(xaxis_tickangle=-45)
                                        #st.plotly_chart(fig_productos, use_container_width=True)
                                    
                                    # Resumen por vendor más frecuente como mejor opción
                                    st.subheader("Vendors que Aparecen Más Frecuentemente como Mejor Opción")
                                    vendor_frecuencia = df_productos_filtrado.groupby(['Mejor Vendor ID', 'Status Mejor Vendor']).agg({
                                        'Producto ID': 'count',
                                        'Ahorro con Mejor Vendor': ['sum', 'mean']
                                    }).round(2)
                                    
                                    vendor_frecuencia.columns = ['Productos Como Mejor Opción', 'Ahorro Total', 'Ahorro Promedio']
                                    vendor_frecuencia = vendor_frecuencia.reset_index().sort_values('Ahorro Total', ascending=False)
                                    
                                    st.dataframe(
                                        vendor_frecuencia.style.format({
                                            'Ahorro Total': '${:,.2f}',
                                            'Ahorro Promedio': '${:,.2f}'
                                        })
                                    )
                                else:
                                    st.warning("No se pudieron generar análisis de productos.")
                            else:
                                st.warning("No se encontraron productos con opciones de vendors disponibles.")
                    else:
                        st.warning("No hay datos clasificados disponibles para el punto de venta seleccionado.")
                else:
                    st.warning("No hay datos de clasificación disponibles.")

                # Información sobre status y metodología
                st.info("""
                **Leyenda de Status de Vendors:**
                - 🟢 **Activo**: Vendor conectado y funcionando
                - 🟡 **Pendiente**: Vendor en proceso de activación  
                - 🔴 **Rechazado**: Vendor rechazado
                - 🔵 **Sin conectar**: Vendor disponible pero no conectado (oportunidad de activación)
                
                **Metodología de Análisis:**
                - Se comparan los precios actuales de droguería vs. precios disponibles de vendors
                - Solo se analizan productos donde hay opciones de vendors disponibles
                - El ahorro potencial se calcula como: Precio Droguería - Precio Vendor
                - Los productos se clasifican según si el vendor tiene el precio mínimo o no mínimo
                """)
                
            else:
                st.info("No hay datos de compras para este punto de venta.")

except Exception as e:
    st.error(f"Error al procesar los datos: {str(e)}")
    st.error("Información de debug:")
    
    # Mostrar información de debug
    if 'df_clasificado' in locals():
        st.write("**Columnas disponibles en df_clasificado:**")
        st.write(list(df_clasificado.columns))
        st.write("**Primeras 5 filas:**")
        st.dataframe(df_clasificado.head())
    
    import traceback
    st.expander("Ver detalles del error", expanded=False).code(traceback.format_exc())
    st.info("Asegúrate de que todos los archivos CSV estén en el directorio correcto y tengan el formato esperado.")