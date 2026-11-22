import streamlit as st
from analyzer import BankAnalyzer
from datetime import datetime

# Настройка страницы (строго и без лишних украшательств)
st.set_page_config(page_title="GleanFint", layout="wide")
# st.markdown(
#     """
#     <style>
#     html, body, [class*="css"] {
#         font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif !important;
#     }
#     </style>
#     """,
#     unsafe_allow_html=True
# )
#
st.title("GleanFint1")
st.caption("Автоматический парсер-анализатор банковских выписок")

# 1. Переносим загрузку файла в боковое меню
with st.sidebar:
    st.header("Настройки")
    uploaded_file = st.file_uploader("Загрузите выписку (.csv, .xlsx)", type=["csv", "xlsx"])

# Если файл не загружен, показываем аккуратное приветствие по центру
if not uploaded_file:
    st.info("Пожалуйста, загрузите банковскую выписку в левом меню для начала работы.")
else:
    try:
        with st.spinner("Обработка данных..."):
            analyzer = BankAnalyzer(uploaded_file, uploaded_file.name)
            analyzer.process_data()
            analytics = analyzer.get_analytics()
            markdown_text = analyzer.generate_markdown_report()

        # 2. Метрики (округляем до целых чисел, чтобы копейки не мусорили интерфейс)
        total_exp = abs(analyzer.expenses['Сумма_чистая'].sum()) if not analyzer.expenses.empty else 0
        total_inc = abs(analyzer.income['Сумма_чистая'].sum()) if not analyzer.income.empty else 0
        total_trans = abs(analyzer.transit['Сумма_чистая'].sum()) if not analyzer.transit.empty else 0

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Поступления", f"{total_inc:,.0f} ₽")
        col2.metric("Расходы", f"{total_exp:,.0f} ₽")
        col3.metric("Переводы", f"{total_trans:,.0f} ₽")
        if analytics:
            col4.metric("Средний чек", f"{analytics['avg_expense']:,.0f} ₽")

        st.divider()  # Нативный разделитель Streamlit вместо маркдауна

        # 3. Графики и Топ-5 (аккуратно и строго)
        if analytics:
            col_chart, col_top = st.columns([3, 2], gap="large")

            with col_chart:
                st.subheader("Структура расходов")
                st.bar_chart(analytics["category_sums"])

            with col_top:
                st.subheader("Топ-5 покупок")
                # Делаем из Топ-5 аккуратную мини-таблицу вместо цветастых блоков
                top_df = analytics["top_5"][[analyzer.col_desc, 'Сумма_чистая']].copy()
                top_df['Сумма_чистая'] = top_df['Сумма_чистая'].abs().apply(lambda x: f"{x:,.2f} ₽")
                top_df.columns = ["Описание", "Сумма"]
                # hide_index=True убирает лишние технические номера строк слева
                st.dataframe(top_df, hide_index=True, use_container_width=True)

        st.divider()

        # 4. Компактное отображение отчета и таблиц (всё во вкладках)
        st.subheader("Детализация и отчеты")

        tab1, tab2, tab3, tab4 = st.tabs([
            "📄 Markdown Отчет",
            "Расходы",
            "Поступления",
            "Транзит"
        ])

        with tab1:
            col_btn, _ = st.columns([1, 4])
            with col_btn:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M")
                st.download_button(
                    label="Скачать отчет (.md)",
                    data=markdown_text,
                    file_name=f"report_{timestamp}.md",
                    mime="text/markdown",
                    use_container_width=True,
                )
            # Выводим код под кнопкой, чтобы было удобно копировать текст
            st.code(markdown_text, language="markdown")

        with tab2:
            st.dataframe(analyzer.expenses, use_container_width=True)
        with tab3:
            st.dataframe(analyzer.income, use_container_width=True)
        with tab4:
            st.dataframe(analyzer.transit, use_container_width=True)

    except Exception as e:
        st.error(f"Ошибка при обработке файла: {e}")